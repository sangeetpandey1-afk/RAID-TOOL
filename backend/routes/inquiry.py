"""Inquiry log routes — caller history per case."""
from __future__ import annotations
from flask import Blueprint, request

from ..database import audit, execute, fetch_all, fetch_one
from ..utils import (envelope_error, envelope_ok, get_json_body, parse_date,
                     safe_float)

bp = Blueprint("inquiry", __name__, url_prefix="/api")


@bp.get("/cases/<case_id>/inquiries")
def list_inquiries(case_id: str):
    case = fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    rows = fetch_all(
        "SELECT * FROM inquiries WHERE case_id=? ORDER BY inquiry_date DESC",
        (case_id,),
    )
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.post("/cases/<case_id>/inquiries")
def add_inquiry(case_id: str):
    if not fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?", (case_id,)):
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    body = get_json_body(request)
    if not body.get("caller_name"):
        return envelope_error("caller_name is required",
                              status=400, code="MISSING_PARAM")
    rel = (body.get("relationship") or "other").lower()
    if rel not in ("self", "relative", "advocate", "other"):
        rel = "other"
    cur = execute(
        """INSERT INTO inquiries
              (case_id, caller_name, mobile_number, relationship,
               amount_quoted, inquiry_date, remarks, follow_up_required)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id,
         body["caller_name"],
         body.get("mobile_number"),
         rel,
         safe_float(body.get("amount_quoted")) or None,
         parse_date(body.get("inquiry_date")),  # NULL → DEFAULT now
         body.get("remarks"),
         1 if body.get("follow_up_required") else 0),
    )
    audit(body.get("user", "system"), "INQUIRY", "inquiries",
          str(cur.lastrowid),
          new={"case_id": case_id, "caller": body["caller_name"]})
    return envelope_ok({"id": cur.lastrowid})


@bp.get("/inquiries/recent")
def recent_inquiries():
    limit = int(request.args.get("limit", "50"))
    rows = fetch_all(
        """SELECT i.*, c.account_number, c.user_name
           FROM inquiries i
           JOIN raid_cases c ON c.case_id = i.case_id
           ORDER BY i.inquiry_date DESC, i.id DESC
           LIMIT ?""",
        (limit,),
    )
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.get("/inquiries/by-mobile/<mobile>")
def inquiries_by_mobile(mobile: str):
    """All inquiries from one phone number — useful for spotting repeat callers."""
    rows = fetch_all(
        """SELECT i.*, c.account_number, c.user_name, c.section
           FROM inquiries i
           JOIN raid_cases c ON c.case_id = i.case_id
           WHERE i.mobile_number = ?
           ORDER BY i.inquiry_date DESC""",
        (mobile,),
    )
    return envelope_ok(rows, meta={"count": len(rows)})
