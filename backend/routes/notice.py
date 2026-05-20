"""Notice tracking + automated timeline alerts."""
from __future__ import annotations
from datetime import date, datetime, timedelta

from flask import Blueprint, request

from .. import config
from ..database import audit, execute, fetch_all, fetch_one
from ..utils import (envelope_error, envelope_ok, get_json_body, parse_date,
                     safe_float)

bp = Blueprint("notice", __name__, url_prefix="/api")


VALID_NOTICE_TYPES = (
    "provisional", "section3", "section5", "thanedari",
    "envelope", "deposit_slip", "noc",
)


# ===================================================================
# Per-case routes
# ===================================================================
@bp.get("/cases/<case_id>/notices")
def list_notices(case_id: str):
    if not fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?", (case_id,)):
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    rows = fetch_all(
        "SELECT * FROM notices WHERE case_id=? ORDER BY created_at DESC",
        (case_id,),
    )
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.post("/cases/<case_id>/notices")
def add_notice(case_id: str):
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")

    body = get_json_body(request)
    ntype = body.get("notice_type")
    if ntype not in VALID_NOTICE_TYPES:
        return envelope_error(
            f"notice_type must be one of {VALID_NOTICE_TYPES}",
            status=400, code="BAD_TYPE",
        )

    dispatch_date = (parse_date(body.get("dispatch_date"))
                     or date.today().isoformat())
    insp = parse_date(case.get("inspection_date")) or date.today().isoformat()
    insp_d = datetime.strptime(insp, "%Y-%m-%d").date()

    # Auto-derive due_date from notice_type if not provided
    auto_due = {
        "provisional": insp_d + timedelta(days=config.TIMELINE_PROVISIONAL_PAYMENT),
        "section3":    insp_d + timedelta(days=config.TIMELINE_SECTION_3_DISPATCH),
        "section5":    insp_d + timedelta(days=config.TIMELINE_SECTION_5_DISPATCH),
    }
    due = parse_date(body.get("due_date")) \
        or (auto_due[ntype].isoformat() if ntype in auto_due else None)

    amount = safe_float(body.get("amount"))
    if amount == 0 and ntype == "section3":
        amount = round(safe_float(case.get("total_assessment"))
                       + config.ADMIN_FEE_SECTION_3, 2)
    elif amount == 0:
        amount = safe_float(case.get("total_assessment")) or None

    cur = execute(
        """INSERT INTO notices
              (case_id, notice_type, notice_number, dispatch_date,
               due_date, amount, status, document_path)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, ntype, body.get("notice_number"),
         dispatch_date, due, amount,
         body.get("status", "dispatched"),
         body.get("document_path")),
    )

    # Bump case status
    if ntype == "section3":
        execute("UPDATE raid_cases SET case_status=? WHERE case_id=?",
                ("section3_sent", case_id))
    elif ntype == "section5":
        execute("UPDATE raid_cases SET case_status=? WHERE case_id=?",
                ("section5_sent", case_id))
    elif ntype == "provisional":
        execute("UPDATE raid_cases SET case_status=? WHERE case_id=?",
                ("noticed", case_id))

    audit(body.get("user", "system"), "NOTICE", "notices",
          str(cur.lastrowid), new={"type": ntype, "case_id": case_id})

    return envelope_ok({"id": cur.lastrowid, "due_date": due})


@bp.patch("/notices/<int:notice_id>")
def update_notice(notice_id: int):
    """Update notice status (e.g., responded / overdue)."""
    row = fetch_one("SELECT * FROM notices WHERE id=?", (notice_id,))
    if not row:
        return envelope_error("Notice not found", status=404, code="NOT_FOUND")
    body = get_json_body(request)
    fields = []
    params = []
    for key in ("status", "notice_number", "dispatch_date", "due_date",
                "amount", "document_path"):
        if key in body:
            v = body[key]
            if key in ("dispatch_date", "due_date"):
                v = parse_date(v)
            elif key == "amount":
                v = safe_float(v)
            fields.append(f"{key}=?")
            params.append(v)
    if not fields:
        return envelope_error("Nothing to update", status=400)
    params.append(notice_id)
    execute(f"UPDATE notices SET {', '.join(fields)} WHERE id=?", params)
    audit("system", "NOTICE_UPDATE", "notices", str(notice_id),
          old=row, new=body)
    return envelope_ok({"id": notice_id})


# ===================================================================
# Dashboard / alert routes
# ===================================================================
@bp.get("/notices/overdue")
def overdue_notices():
    """All notices past their due date that aren't 'responded'."""
    today = date.today().isoformat()
    rows = fetch_all(
        """SELECT n.*, c.account_number, c.user_name, c.section,
                  c.total_assessment, c.case_status
           FROM notices n
           JOIN raid_cases c ON c.case_id = n.case_id
           WHERE n.due_date < ?
             AND n.status NOT IN ('responded', 'closed')
           ORDER BY n.due_date ASC""",
        (today,),
    )
    return envelope_ok(rows, meta={"count": len(rows), "as_of": today})


@bp.get("/dashboard/timeline-alerts")
def timeline_alerts():
    """
    Cases breaching the legal timeline:
      * `provisional_overdue`  – inspection >7 days, no payment
      * `section3_due`         – inspection >45 days, no Section 3 dispatched
      * `section5_due`         – inspection >90 days, no Section 5 dispatched
      * `appeal_window_open`   – inspection within 15 days
    """
    today = date.today()

    insp_cutoff = lambda d: (today - timedelta(days=d)).isoformat()
    sec3_cut = insp_cutoff(config.TIMELINE_SECTION_3_DISPATCH)
    sec5_cut = insp_cutoff(config.TIMELINE_SECTION_5_DISPATCH)
    prov_cut = insp_cutoff(config.TIMELINE_PROVISIONAL_PAYMENT)
    appeal_open_cut = insp_cutoff(config.TIMELINE_APPEAL_WINDOW)

    section3_due = fetch_all(
        """SELECT case_id, account_number, user_name, inspection_date,
                  total_assessment, case_status
           FROM raid_cases
           WHERE inspection_date <= ?
             AND case_status NOT IN ('paid', 'closed', 'section3_sent',
                                     'section5_sent')
             AND case_id NOT IN (SELECT case_id FROM notices
                                 WHERE notice_type='section3'
                                   AND status IN ('dispatched','responded'))
           ORDER BY inspection_date ASC""",
        (sec3_cut,),
    )

    section5_due = fetch_all(
        """SELECT case_id, account_number, user_name, inspection_date,
                  total_assessment, case_status
           FROM raid_cases
           WHERE inspection_date <= ?
             AND case_status NOT IN ('paid', 'closed', 'section5_sent')
             AND case_id NOT IN (SELECT case_id FROM notices
                                 WHERE notice_type='section5'
                                   AND status IN ('dispatched','responded'))
           ORDER BY inspection_date ASC""",
        (sec5_cut,),
    )

    provisional_overdue = fetch_all(
        """SELECT case_id, account_number, user_name, inspection_date,
                  total_assessment
           FROM raid_cases
           WHERE inspection_date <= ?
             AND case_status IN ('open','noticed')
             AND case_id NOT IN
                 (SELECT DISTINCT case_id FROM payments)""",
        (prov_cut,),
    )

    appeal_window_open = fetch_all(
        """SELECT case_id, account_number, user_name, inspection_date,
                  total_assessment, case_status
           FROM raid_cases
           WHERE inspection_date >= ?""",
        (appeal_open_cut,),
    )

    return envelope_ok({
        "as_of": today.isoformat(),
        "section3_due_count": len(section3_due),
        "section5_due_count": len(section5_due),
        "provisional_overdue_count": len(provisional_overdue),
        "appeal_window_open_count": len(appeal_window_open),
        "section3_due": section3_due,
        "section5_due": section5_due,
        "provisional_overdue": provisional_overdue,
        "appeal_window_open": appeal_window_open,
    })


@bp.get("/dashboard/summary")
def dashboard_summary():
    """At-a-glance counts for the home dashboard."""
    rows = fetch_all(
        """SELECT case_status, COUNT(*) AS c, COALESCE(SUM(total_assessment),0) AS amt
           FROM raid_cases GROUP BY case_status"""
    )
    by_status = {r["case_status"]: {"count": r["c"], "amount": r["amt"]}
                 for r in rows}
    today = date.today().isoformat()
    today_paid = fetch_one(
        "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS amt "
        "FROM payments WHERE payment_date=?",
        (today,),
    )
    return envelope_ok({
        "by_status": by_status,
        "total_cases":   sum(v["count"] for v in by_status.values()),
        "total_assessment": round(sum(v["amount"] for v in by_status.values()), 2),
        "today_payment_count":  today_paid["c"],
        "today_payment_amount": round(today_paid["amt"] or 0, 2),
    })
