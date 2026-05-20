"""Case management — save / get / list / search / calculate / revise."""
from __future__ import annotations
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from flask import Blueprint, request

from .. import config
from ..database import (audit, execute, fetch_all, fetch_one, get_connection)
from ..services import calculator, compounding, matcher
from ..utils import (envelope_error, envelope_ok, from_json_str,
                     get_json_body, normalize_account, parse_date,
                     safe_float, safe_int, to_json_str)

log = logging.getLogger(__name__)
bp = Blueprint("case", __name__, url_prefix="/api")


# ===================================================================
# helpers
# ===================================================================
def _new_case_id() -> str:
    return "RC-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()


def _hydrate(case: dict) -> dict:
    case["devices"] = from_json_str(case.get("devices_json")) or []
    case["assessment"] = from_json_str(case.get("assessment_json"))
    case.pop("devices_json", None)
    case.pop("assessment_json", None)
    return case


def _resolve_consumer(account: str | None, name: str | None,
                      father: str | None, village: str | None) -> dict | None:
    if account:
        row = fetch_one("SELECT * FROM consumers WHERE account_number=?",
                        (normalize_account(account),))
        if row:
            return row
    hits = matcher.find_consumer(account=account, name=name,
                                 father=father, village=village,
                                 fuzzy_limit=1)
    if hits:
        return hits[0].record
    return None


def _ensure_consumer(payload: dict) -> int | None:
    """If consumer doesn't exist, insert a minimal record and return id."""
    acct = normalize_account(payload.get("account_number"))
    if not acct:
        return None
    existing = fetch_one("SELECT id FROM consumers WHERE account_number=?",
                        (acct,))
    if existing:
        return existing["id"]
    cur = execute(
        """INSERT INTO consumers
              (account_number, name, father_name, address, village,
               mobile, supply_type, category, sub_substation, div_code,
               connection_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            acct,
            payload.get("name"),
            payload.get("father_name"),
            payload.get("address"),
            payload.get("village"),
            payload.get("mobile"),
            payload.get("supply_type"),
            payload.get("category"),
            payload.get("sub_substation"),
            payload.get("div_code"),
            payload.get("connection_status") or "Active",
        ),
    )
    return cur.lastrowid


# ===================================================================
# 1. CREATE / UPDATE
# ===================================================================
@bp.post("/cases")
def save_case():
    """Create or update a raid case (idempotent on case_id)."""
    body = get_json_body(request)
    case_id = body.get("case_id") or _new_case_id()

    # Resolve / ensure consumer
    consumer_id = _ensure_consumer(body)
    account = normalize_account(body.get("account_number"))

    # Calculate assessment if not provided
    assessment = body.get("assessment")
    if not assessment and body.get("devices"):
        assessment = calculator.calculate_assessment(body)

    total = safe_float(body.get("total_assessment")) \
        or safe_float((assessment or {}).get("grand_total"))

    # Compounding (Section 152) — optional, only if requested
    compounding_amount = safe_float(body.get("compounding_amount"))
    if not compounding_amount and body.get("calculate_compounding"):
        cload_kw = safe_float(body.get("connected_load_kw"))
        if cload_kw <= 0:
            cload_kw = sum(safe_float(d.get("L") or d.get("load"))
                           for d in (body.get("devices") or [])) / 1000.0
        comp = compounding.calculate_compounding({
            "load_kw": cload_kw,
            "category": body.get("category"),
            "section":  body.get("section"),
            "rate_per_kw": body.get("rate_per_kw"),
        })
        if comp.get("ok"):
            compounding_amount = comp["compounding_amount"]

    devices_json   = to_json_str(body.get("devices") or [])
    assessment_json = to_json_str(assessment)

    existing = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if existing:
        execute(
            """UPDATE raid_cases SET
                  online_no=?, consumer_id=?, account_number=?,
                  inspection_date=?, section=?, section_other=?,
                  checking_type=?, je_name=?, sub_substation=?,
                  td_date=?, connected_load_kw=?,
                  user_name=?, user_father=?, user_address=?,
                  devices_json=?, less_unit=?, multiplier=?,
                  offense_count=?, assessment_json=?, total_assessment=?,
                  compounding_amount=?, fir_number=?, case_status=?,
                  updated_at=datetime('now')
               WHERE case_id=?""",
            (
                body.get("online_no"),
                consumer_id,
                account,
                parse_date(body.get("inspection_date")) or date.today().isoformat(),
                body.get("section"),
                body.get("section_other"),
                body.get("checking_type"),
                body.get("je_name"),
                body.get("sub_substation"),
                parse_date(body.get("td_date")),
                safe_float(body.get("connected_load_kw")) or None,
                body.get("user_name"),
                body.get("user_father"),
                body.get("user_address"),
                devices_json,
                safe_float(body.get("less_unit")) or None,
                safe_float(body.get("multiplier"), 2.0),
                safe_int(body.get("offense_count"), 1),
                assessment_json,
                total or None,
                compounding_amount or None,
                body.get("fir_number"),
                body.get("case_status") or existing["case_status"],
                case_id,
            ),
        )
        audit(body.get("created_by") or "system", "UPDATE", "raid_cases",
              case_id, old=existing, new=body)
        action = "updated"
    else:
        execute(
            """INSERT INTO raid_cases
                  (case_id, online_no, consumer_id, account_number,
                   inspection_date, section, section_other,
                   checking_type, je_name, sub_substation, td_date,
                   connected_load_kw, user_name, user_father, user_address,
                   devices_json, less_unit, multiplier, offense_count,
                   assessment_json, total_assessment, compounding_amount,
                   fir_number, case_status, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case_id,
                body.get("online_no"),
                consumer_id,
                account,
                parse_date(body.get("inspection_date")) or date.today().isoformat(),
                body.get("section"),
                body.get("section_other"),
                body.get("checking_type"),
                body.get("je_name"),
                body.get("sub_substation"),
                parse_date(body.get("td_date")),
                safe_float(body.get("connected_load_kw")) or None,
                body.get("user_name"),
                body.get("user_father"),
                body.get("user_address"),
                devices_json,
                safe_float(body.get("less_unit")) or None,
                safe_float(body.get("multiplier"), 2.0),
                safe_int(body.get("offense_count"), 1),
                assessment_json,
                total or None,
                compounding_amount or None,
                body.get("fir_number"),
                body.get("case_status") or "open",
                body.get("created_by") or "system",
            ),
        )
        audit(body.get("created_by") or "system", "CREATE", "raid_cases",
              case_id, new=body)
        action = "created"

    case_row = _hydrate(fetch_one(
        "SELECT * FROM raid_cases WHERE case_id=?", (case_id,)
    ))
    return envelope_ok({"action": action, "case": case_row})


# ===================================================================
# 2. READ — single case
# ===================================================================
@bp.get("/cases/<case_id>")
def get_case(case_id: str):
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    case = _hydrate(case)

    consumer = (fetch_one("SELECT * FROM consumers WHERE id=?",
                          (case["consumer_id"],))
                if case.get("consumer_id") else None)

    payments  = fetch_all(
        "SELECT * FROM payments WHERE case_id=? ORDER BY payment_date DESC",
        (case_id,),
    )
    notices   = fetch_all(
        "SELECT * FROM notices WHERE case_id=? ORDER BY created_at DESC",
        (case_id,),
    )
    inquiries = fetch_all(
        "SELECT * FROM inquiries WHERE case_id=? ORDER BY inquiry_date DESC",
        (case_id,),
    )
    revisions = fetch_all(
        "SELECT * FROM case_revisions WHERE case_id=? ORDER BY revision_number DESC",
        (case_id,),
    )
    documents = fetch_all(
        "SELECT * FROM documents WHERE case_id=? ORDER BY created_at DESC",
        (case_id,),
    )

    timeline = _compute_timeline(case)

    return envelope_ok({
        "case": case,
        "consumer": consumer,
        "payments": payments,
        "notices": notices,
        "inquiries": inquiries,
        "revisions": revisions,
        "documents": documents,
        "timeline": timeline,
    })


def _compute_timeline(case: dict) -> dict:
    """Return per-event due/elapsed information for dashboard alerts."""
    insp = parse_date(case.get("inspection_date"))
    if not insp:
        return {}
    insp_d = datetime.strptime(insp, "%Y-%m-%d").date()
    today = date.today()
    elapsed = (today - insp_d).days
    return {
        "inspection_date": insp,
        "elapsed_days": elapsed,
        "provisional_payment_due": (insp_d + timedelta(
            days=config.TIMELINE_PROVISIONAL_PAYMENT)).isoformat(),
        "appeal_window_close":     (insp_d + timedelta(
            days=config.TIMELINE_APPEAL_WINDOW)).isoformat(),
        "section3_dispatch_due":   (insp_d + timedelta(
            days=config.TIMELINE_SECTION_3_DISPATCH)).isoformat(),
        "section5_dispatch_due":   (insp_d + timedelta(
            days=config.TIMELINE_SECTION_5_DISPATCH)).isoformat(),
        "overdue_section3": elapsed > config.TIMELINE_SECTION_3_DISPATCH,
        "overdue_section5": elapsed > config.TIMELINE_SECTION_5_DISPATCH,
    }


# ===================================================================
# 3. LIST / SEARCH
# ===================================================================
@bp.get("/cases")
def list_cases():
    return search_cases()


@bp.get("/cases/search")
def search_cases():
    """
    Multi-parameter search.

    Query params:
        q                — name, online_no, account substring
        account          — exact account
        section          — 135 / 138 / 126 / Other
        status           — open|noticed|paid|closed|appealed
        div_no           — division
        je_name          — junior engineer
        from_date / to_date — inspection date range (max 90 days)
        fir_number
        min_amount / max_amount
        page             — default 1
        page_size        — default 50, max 200
    """
    args = request.args
    where: list[str] = []
    params: list[Any] = []

    q = args.get("q")
    if q:
        where.append("(account_number LIKE ? OR online_no LIKE ? "
                     "OR user_name LIKE ? OR fir_number LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like, like]

    if args.get("account"):
        where.append("account_number=?")
        params.append(normalize_account(args["account"]))
    if args.get("section"):
        where.append("section=?")
        params.append(args["section"])
    if args.get("status"):
        where.append("case_status=?")
        params.append(args["status"])
    if args.get("je_name"):
        where.append("je_name=?")
        params.append(args["je_name"])
    if args.get("fir_number"):
        where.append("fir_number=?")
        params.append(args["fir_number"])

    fr = parse_date(args.get("from_date"))
    to = parse_date(args.get("to_date"))
    if fr:
        where.append("inspection_date >= ?")
        params.append(fr)
    if to:
        where.append("inspection_date <= ?")
        params.append(to)
    if args.get("min_amount"):
        where.append("total_assessment >= ?")
        params.append(safe_float(args["min_amount"]))
    if args.get("max_amount"):
        where.append("total_assessment <= ?")
        params.append(safe_float(args["max_amount"]))

    div_join = ""
    if args.get("div_no"):
        div_join = "JOIN consumers c ON c.id = r.consumer_id "
        where.append("c.div_code=?")
        params.append(args["div_no"])

    where_clause = "WHERE " + " AND ".join(where) if where else ""
    page = max(1, safe_int(args.get("page"), 1))
    page_size = min(200, max(1, safe_int(args.get("page_size"), 50)))
    offset = (page - 1) * page_size

    total = fetch_one(
        f"SELECT COUNT(*) AS c FROM raid_cases r {div_join} {where_clause}",
        params,
    )["c"]
    rows = fetch_all(
        f"""SELECT r.* FROM raid_cases r {div_join}
            {where_clause}
            ORDER BY r.inspection_date DESC, r.id DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    return envelope_ok([_hydrate(r) for r in rows], meta={
        "total": total, "page": page, "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    })


# ===================================================================
# 4. LIVE CALCULATE (without saving)
# ===================================================================
@bp.post("/calculate")
@bp.post("/cases/calculate")
def calculate_endpoint():
    body = get_json_body(request)
    result = calculator.calculate_assessment(body)
    return envelope_ok(result)


@bp.post("/compounding")
@bp.post("/cases/compounding")
def compounding_endpoint():
    body = get_json_body(request)
    result = compounding.calculate_compounding(body)
    if not result.get("ok"):
        return envelope_error(result.get("error", "Bad input"), status=400)
    return envelope_ok(result)


@bp.post("/cases/<case_id>/calculate")
def case_calculate(case_id: str):
    """Re-run calculation for a stored case using its devices/section."""
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    case = _hydrate(case)
    consumer = (fetch_one("SELECT * FROM consumers WHERE id=?",
                          (case["consumer_id"],))
                if case.get("consumer_id") else {}) or {}

    body = get_json_body(request) or {}
    payload = {
        "section": case.get("section"),
        "td_date": case.get("td_date"),
        "inspection_date": case.get("inspection_date"),
        "category": consumer.get("category") or body.get("category"),
        "connected_load_kw": case.get("connected_load_kw"),
        "devices": case.get("devices") or [],
        "less_unit": case.get("less_unit"),
        "multiplier": body.get("multiplier") or case.get("multiplier"),
        **{k: v for k, v in body.items() if v is not None},
    }
    result = calculator.calculate_assessment(payload)

    # Persist new assessment back to the case
    execute(
        """UPDATE raid_cases SET
              assessment_json=?, total_assessment=?, multiplier=?,
              updated_at=datetime('now')
           WHERE case_id=?""",
        (to_json_str(result), result["grand_total"],
         result["multiplier"], case_id),
    )
    audit(body.get("user") or "system", "RECALC", "raid_cases", case_id,
          new={"assessment": result})
    return envelope_ok(result)


@bp.post("/cases/<case_id>/compounding")
def case_compounding(case_id: str):
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    consumer = (fetch_one("SELECT * FROM consumers WHERE id=?",
                          (case["consumer_id"],))
                if case["consumer_id"] else {}) or {}
    body = get_json_body(request) or {}
    load_w = safe_float(body.get("load_w"))
    if load_w <= 0:
        load_kw = safe_float(body.get("load_kw")) \
            or safe_float(case.get("connected_load_kw"))
        load_w = load_kw * 1000.0

    result = compounding.calculate_compounding({
        "load_w":   load_w,
        "category": body.get("category") or consumer.get("category"),
        "section":  body.get("section")  or case.get("section"),
        "rate_per_kw": body.get("rate_per_kw"),
    })
    if not result.get("ok"):
        return envelope_error(result["error"], status=400)
    execute(
        "UPDATE raid_cases SET compounding_amount=?, updated_at=datetime('now') "
        "WHERE case_id=?",
        (result["compounding_amount"], case_id),
    )
    return envelope_ok(result)


# ===================================================================
# 5. OFFENSE CHECK (specific to a case)
# ===================================================================
@bp.get("/cases/<case_id>/offense-check")
def case_offense_check(case_id: str):
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    consumer = (fetch_one("SELECT * FROM consumers WHERE id=?",
                          (case["consumer_id"],))
                if case["consumer_id"] else None) or {}
    history = matcher.offense_history(
        account=case.get("account_number"),
        name=consumer.get("name"),
        father=consumer.get("father_name"),
        village=consumer.get("village"),
    )
    cfg = {r["config_key"]: r["config_value"]
           for r in fetch_all("SELECT config_key, config_value FROM system_config")}
    threshold = int(cfg.get("repeat_offense_threshold", "2"))
    multiplier = (float(cfg.get("multiplier_repeat_offense", "6"))
                  if history["total_offenses"] >= threshold
                  else float(cfg.get("multiplier_first_offense", "2")))
    return envelope_ok({
        "case_id": case_id,
        "history": history,
        "is_repeat_offender": history["total_offenses"] >= threshold,
        "suggested_multiplier": multiplier,
    })


# ===================================================================
# 6. REVISE (post-appeal modification)
# ===================================================================
@bp.post("/cases/<case_id>/revise")
def revise_case(case_id: str):
    """Create a new revision row + apply changes to the live case."""
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")

    body = get_json_body(request)
    reason = body.get("reason") or "appeal"
    overrides = body.get("overrides") or {}
    revised_by = body.get("revised_by") or "system"

    last = fetch_one(
        "SELECT MAX(revision_number) AS m FROM case_revisions WHERE case_id=?",
        (case_id,),
    )
    next_rev = (last["m"] or 0) + 1

    # Apply overrides on top of current case + recompute
    case_h = _hydrate(case)
    new_payload = {**case_h, **overrides}
    if "devices" not in new_payload:
        new_payload["devices"] = case_h.get("devices") or []
    new_assessment = calculator.calculate_assessment({
        "section":  new_payload.get("section"),
        "td_date":  new_payload.get("td_date"),
        "inspection_date": new_payload.get("inspection_date"),
        "category": overrides.get("category"),
        "connected_load_kw": new_payload.get("connected_load_kw"),
        "devices":  new_payload.get("devices"),
        "less_unit": new_payload.get("less_unit"),
        "multiplier": new_payload.get("multiplier"),
        "ed_percent": overrides.get("ed_percent"),
    })

    execute(
        """INSERT INTO case_revisions
              (case_id, revision_number, revision_reason,
               original_assessment, revised_assessment, revised_by,
               revision_details)
           VALUES (?,?,?,?,?,?,?)""",
        (case_id, next_rev, reason,
         case.get("total_assessment"),
         new_assessment["grand_total"],
         revised_by,
         to_json_str({"overrides": overrides,
                      "new_assessment": new_assessment})),
    )

    execute(
        """UPDATE raid_cases SET
              section=COALESCE(?, section),
              td_date=COALESCE(?, td_date),
              connected_load_kw=COALESCE(?, connected_load_kw),
              less_unit=COALESCE(?, less_unit),
              multiplier=COALESCE(?, multiplier),
              devices_json=COALESCE(?, devices_json),
              assessment_json=?,
              total_assessment=?,
              case_status='revised',
              updated_at=datetime('now')
           WHERE case_id=?""",
        (
            overrides.get("section"),
            parse_date(overrides.get("td_date")),
            safe_float(overrides.get("connected_load_kw")) or None,
            safe_float(overrides.get("less_unit")) or None,
            safe_float(overrides.get("multiplier")) or None,
            to_json_str(overrides.get("devices")) if overrides.get("devices") else None,
            to_json_str(new_assessment),
            new_assessment["grand_total"],
            case_id,
        ),
    )
    audit(revised_by, "REVISE", "raid_cases", case_id,
          old=case, new={"overrides": overrides, "new_total": new_assessment["grand_total"]})

    return envelope_ok({
        "revision_number": next_rev,
        "original_assessment": case.get("total_assessment"),
        "revised_assessment": new_assessment["grand_total"],
        "delta": round((new_assessment["grand_total"]
                        - (case.get("total_assessment") or 0)), 2),
        "new_assessment": new_assessment,
    })
