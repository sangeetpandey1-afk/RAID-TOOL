"""
Offense verification routes (PR4).

Endpoints (all under /api/offense):

  GET /api/offense/lookup?account=X
        Account-number-only indexed lookup against historical_cases.
        NEVER does fuzzy name / village / father matching. Returns the
        15 display fields PR4 needs plus a summary block with the
        suggested multiplier.

  GET /api/offense/multiplier-suggest?account=X
        Convenience endpoint for the frontend's "Apply" button —
        returns just {suggested_multiplier, matched_count, is_repeat}.

  GET /api/offense/explain-plan
        Diagnostic only. Returns the SQLite EXPLAIN QUERY PLAN rows for
        the lookup query so operators / tests can confirm the indexes
        are being hit.

This is a NEW blueprint — no existing route is shadowed or modified.
The legacy /api/cases/<id>/offense-check route in routes/case.py
continues to use services/matcher.py (which keeps its fuzzy-fallback
behaviour). PR4's flow lives strictly under /api/offense/*.
"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from ..services import offense_lookup
from ..utils import envelope_error, envelope_ok

log = logging.getLogger(__name__)
bp = Blueprint("offense", __name__, url_prefix="/api/offense")


# =====================================================================
# 1. Lookup
# =====================================================================
@bp.get("/lookup")
def lookup():
    account = (request.args.get("account") or "").strip()
    if not account:
        return envelope_error(
            "account is required",
            status=400, code="MISSING_ACCOUNT",
        )
    result = offense_lookup.lookup_by_account(account)
    return envelope_ok(result)


# =====================================================================
# 2. Multiplier suggest (lightweight subset of /lookup)
# =====================================================================
@bp.get("/multiplier-suggest")
def multiplier_suggest():
    account = (request.args.get("account") or "").strip()
    if not account:
        return envelope_error(
            "account is required",
            status=400, code="MISSING_ACCOUNT",
        )
    full = offense_lookup.lookup_by_account(account)
    return envelope_ok({
        "account":              full["account"],
        "matched_count":        full["matched_count"],
        "is_repeat":            full["is_repeat"],
        "suggested_multiplier": full["suggested_multiplier"],
        "config":               full["config"],
    })


# =====================================================================
# 3. Diagnostic — query plan
# =====================================================================
@bp.get("/explain-plan")
def explain_plan():
    """Return the EXPLAIN QUERY PLAN rows so operators can confirm
    that the historical_cases lookup uses the indexes."""
    rows = offense_lookup.explain_lookup_plan(
        account=request.args.get("account") or "PROBE"
    )
    return envelope_ok({
        "plan_rows": rows,
        "indexes_seen": sorted({
            "idx_hist_account",
            "idx_hist_new_account",
            "idx_hist_old_account",
        } & {
            tok for r in rows for tok in str(r.get("detail") or "").split()
        }),
    })
