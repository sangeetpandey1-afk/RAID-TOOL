"""Device master + rate slab read APIs."""
from __future__ import annotations
from flask import Blueprint, request

from ..database import fetch_all, fetch_one
from ..utils import envelope_ok, envelope_error

bp = Blueprint("device_rate", __name__, url_prefix="/api")


@bp.get("/devices")
def list_devices():
    cat = request.args.get("category")
    if cat:
        rows = fetch_all(
            "SELECT * FROM device_master WHERE category=? ORDER BY device_name",
            (cat,),
        )
    else:
        rows = fetch_all("SELECT * FROM device_master ORDER BY category, device_name")
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.get("/devices/categories")
def device_categories():
    rows = fetch_all(
        "SELECT category, COUNT(*) AS device_count "
        "FROM device_master GROUP BY category ORDER BY category"
    )
    return envelope_ok(rows)


@bp.get("/rates")
def list_rates():
    cat = request.args.get("category")
    if not cat:
        rows = fetch_all(
            "SELECT DISTINCT category FROM rate_master ORDER BY category"
        )
        return envelope_ok([r["category"] for r in rows],
                           meta={"hint": "pass ?category=LMV-1 for slab details"})
    rows = fetch_all(
        "SELECT * FROM rate_master WHERE category=? "
        "ORDER BY effective_date DESC, slab_start ASC",
        (cat,),
    )
    if not rows:
        return envelope_error(f"No rates found for category '{cat}'",
                              status=404, code="NO_RATES")
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.get("/rates/categories")
def rate_categories():
    rows = fetch_all(
        "SELECT category, COUNT(*) AS slab_count, MIN(slab_start) AS lo, "
        "       MAX(COALESCE(slab_end, 999999)) AS hi "
        "FROM rate_master GROUP BY category ORDER BY category"
    )
    return envelope_ok(rows)
