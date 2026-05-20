"""Consumer search & profile routes."""
from __future__ import annotations
from flask import Blueprint, request

from ..database import fetch_one, fetch_all
from ..services import matcher
from ..utils import envelope_ok, envelope_error, normalize_account

bp = Blueprint("consumer", __name__, url_prefix="/api")


@bp.get("/consumers/search")
def search_consumers():
    """
    Multi-parameter consumer search.

    Query params (any combination):
        account     — exact / mapping / SC lookup
        sc          — SC number
        q           — free-text name (uses fuzzy)
        name, father, village  — explicit fuzzy fields
        limit       — fuzzy result cap (default 10)
        threshold   — fuzzy threshold (default 0.70)
    """
    account = request.args.get("account") or request.args.get("acct") or None
    sc_no   = request.args.get("sc") or None
    q       = request.args.get("q") or None
    name    = request.args.get("name") or q
    father  = request.args.get("father") or None
    village = request.args.get("village") or None
    limit   = int(request.args.get("limit", "10"))
    thresh  = float(request.args.get("threshold", "0.70"))

    if not any([account, sc_no, name]):
        return envelope_error("Provide at least one of: account, sc, q/name",
                              status=400, code="MISSING_PARAM")

    hits = matcher.find_consumer(
        account=account, sc_number=sc_no,
        name=name, father=father, village=village,
        fuzzy_threshold=thresh, fuzzy_limit=limit,
    )
    return envelope_ok([h.to_dict() for h in hits],
                       meta={"count": len(hits)})


@bp.get("/consumers/<account>")
def get_consumer(account: str):
    """Full profile for a consumer + offense summary + recent inquiries."""
    acct = normalize_account(account)
    cons = fetch_one("SELECT * FROM consumers WHERE account_number=?", (acct,))
    if not cons:
        # Try via mapping fallback
        hit = matcher.by_account_mapping(account)
        if hit:
            cons = fetch_one(
                "SELECT * FROM consumers WHERE id=?", (hit.consumer_id,)
            )
    if not cons:
        return envelope_error("Consumer not found", status=404,
                              code="NOT_FOUND")

    history = matcher.offense_history(
        account=cons["account_number"],
        name=cons.get("name"),
        father=cons.get("father_name"),
        village=cons.get("village"),
    )

    # Recent inquiries linked to any case of this consumer
    inquiries = fetch_all(
        """SELECT i.* FROM inquiries i
           JOIN raid_cases c ON c.case_id = i.case_id
           WHERE c.account_number = ?
           ORDER BY i.inquiry_date DESC
           LIMIT 50""",
        (cons["account_number"],),
    )

    return envelope_ok({
        "consumer": cons,
        "offense_history": history,
        "inquiries": inquiries,
    })


@bp.get("/consumers/<account>/offense-check")
def offense_check(account: str):
    """Just the offense aggregate (for live multiplier preview in Excel)."""
    cons = fetch_one(
        "SELECT * FROM consumers WHERE account_number=?",
        (normalize_account(account),),
    )
    name    = request.args.get("name")    or (cons["name"]    if cons else None)
    father  = request.args.get("father")  or (cons["father_name"] if cons else None)
    village = request.args.get("village") or (cons["village"] if cons else None)

    history = matcher.offense_history(
        account=account, name=name, father=father, village=village,
    )

    # Multiplier decision
    from ..database import fetch_one as fo
    cfg = {
        r["config_key"]: r["config_value"]
        for r in fetch_all(
            "SELECT config_key, config_value FROM system_config "
            "WHERE config_key IN ('multiplier_first_offense', "
            "'multiplier_repeat_offense', 'repeat_offense_threshold')"
        )
    }
    threshold = int(cfg.get("repeat_offense_threshold", "2"))
    mult_first = float(cfg.get("multiplier_first_offense", "2"))
    mult_rpt   = float(cfg.get("multiplier_repeat_offense", "6"))
    is_repeat = history["total_offenses"] >= threshold
    multiplier = mult_rpt if is_repeat else mult_first

    return envelope_ok({
        "consumer": cons,
        "history": history,
        "is_repeat_offender": is_repeat,
        "suggested_multiplier": multiplier,
        "multiplier_basis": "repeat" if is_repeat else "first",
    })
