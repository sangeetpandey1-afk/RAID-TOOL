"""
Tariff rate-schedule routes (PR2).

Endpoints (all under /api/rates):

  POST /api/rates/upload-schedule   multipart/form-data
        fields:  file, schedule_name, effective_from, effective_to, source
        action:  saves uploaded xlsx to master_data/, calls
                 tariff_engine.import_schedule(), returns inserted count
                 + per-row mapping diagnostics.

  GET  /api/rates/schedules
        returns: { "schedules": [
            {"schedule_name": ..., "rows": N, "earliest": ..., "latest": ...,
             "categories": [...]}
          ] }

  GET  /api/rates/schedule/<name>
        returns: { "schedule_name": ..., "rows": [ ... full rows ... ] }

  POST /api/rates/check-overlaps    application/json
        body: { category, slab_start?, slab_end?, effective_from,
                effective_to, condition_load?, exclude_id? }
        returns: { "overlaps": [...rows...] }

  POST /api/rates/timeline-calc     application/json
        body: payload accepted by tariff_timeline_engine.calculate_timeline
        returns: full segment-by-segment breakdown

All routes are ADDITIVE — no existing rate / calculator endpoint is
modified or removed.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, request

from .. import config
from ..database import fetch_all, fetch_one, get_connection
from ..services import tariff_engine, tariff_timeline_engine
from ..services.tariff_engine import detect_overlaps
from ..utils import (envelope_error, envelope_ok, get_json_body, parse_date,
                     safe_float, safe_int)

log = logging.getLogger(__name__)
bp = Blueprint("rates", __name__, url_prefix="/api/rates")


# =====================================================================
# 1. Upload tariff schedule  (multipart/form-data)
# =====================================================================
def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return name or "tariff_schedule.xlsx"


@bp.post("/upload-schedule")
def upload_schedule():
    if "file" not in request.files:
        return envelope_error("Missing 'file' in multipart upload",
                              status=400, code="MISSING_FILE")
    f = request.files["file"]
    if not f.filename:
        return envelope_error("Empty filename", status=400, code="EMPTY_NAME")
    if not f.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return envelope_error("File must be .xlsx / .xlsm / .xls",
                              status=400, code="BAD_TYPE")

    schedule_name = (request.form.get("schedule_name") or "").strip()
    if not schedule_name:
        # Default to filename stem
        schedule_name = Path(f.filename).stem
    eff_from = parse_date(request.form.get("effective_from"))
    eff_to = parse_date(request.form.get("effective_to"))
    source_label = (request.form.get("source") or "upload").strip()

    # Persist file under master_data/uploaded_tariff/<timestamp>_<safe>.xlsx
    target_dir = config.MASTER_DATA_DIR / "uploaded_tariff"
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_path = target_dir / f"{ts}_{_safe_filename(f.filename)}"
    f.save(str(target_path))

    started = time.time()
    try:
        result = tariff_engine.import_schedule(
            str(target_path),
            schedule_name=schedule_name,
            schedule_effective_from=eff_from,
            schedule_effective_to=eff_to,
            source=source_label,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Tariff schedule import failed for %s", target_path)
        return envelope_error(
            f"Import failed: {type(e).__name__}: {e}",
            status=500, code="IMPORT_FAILED",
        )

    duration_ms = int((time.time() - started) * 1000)
    return envelope_ok({
        "schedule_name":    result.get("schedule_name") or schedule_name,
        "inserted":         result.get("inserted", 0),
        "skipped_blank":    result.get("skipped_blank", 0),
        "saved_to":         str(target_path),
        "duration_ms":      duration_ms,
        "effective_from":   eff_from,
        "effective_to":     eff_to,
        "source":           source_label,
    })


# =====================================================================
# 2. List schedules
# =====================================================================
@bp.get("/schedules")
def list_schedules():
    rows = fetch_all(
        """SELECT schedule_name,
                  COUNT(*) AS rows,
                  MIN(COALESCE(effective_from, schedule_effective_from)) AS earliest,
                  MAX(COALESCE(effective_to,   schedule_effective_to))   AS latest,
                  GROUP_CONCAT(DISTINCT category)                        AS categories
             FROM tariff_rates
            WHERE schedule_name IS NOT NULL
              AND (status IS NULL OR status = 'active')
            GROUP BY schedule_name
            ORDER BY earliest DESC NULLS LAST, schedule_name""",
    )
    schedules = []
    for r in rows:
        cats_raw = r.get("categories") or ""
        cats = sorted({c.strip() for c in cats_raw.split(",") if c.strip()})
        schedules.append({
            "schedule_name": r.get("schedule_name"),
            "rows":          int(r.get("rows") or 0),
            "earliest":      r.get("earliest"),
            "latest":        r.get("latest"),
            "categories":    cats,
        })
    return envelope_ok({"schedules": schedules})


# =====================================================================
# 3. Schedule details
# =====================================================================
@bp.get("/schedule/<name>")
def schedule_detail(name: str):
    rows = fetch_all(
        "SELECT * FROM tariff_rates WHERE schedule_name = ? ORDER BY id",
        (name,),
    )
    if not rows:
        return envelope_error(f"Schedule not found: {name}",
                              status=404, code="NOT_FOUND")
    return envelope_ok({
        "schedule_name": name,
        "rows":          rows,
        "row_count":     len(rows),
    })


# =====================================================================
# 4. Overlap check
# =====================================================================
@bp.post("/check-overlaps")
def check_overlaps():
    body = get_json_body(request)
    category = (body.get("category") or "").strip()
    if not category:
        return envelope_error("category is required",
                              status=400, code="MISSING_CATEGORY")
    overlaps = detect_overlaps(
        category=category,
        slab_start=body.get("slab_start"),
        slab_end=body.get("slab_end"),
        effective_from=body.get("effective_from"),
        effective_to=body.get("effective_to"),
        condition_load=body.get("condition_load"),
        exclude_id=safe_int(body.get("exclude_id"), 0) or None,
    )
    return envelope_ok({
        "category":       category,
        "overlap_count":  len(overlaps),
        "overlaps":       overlaps,
    })


# =====================================================================
# 5. Timeline calculation
# =====================================================================
@bp.post("/timeline-calc")
def timeline_calc():
    body = get_json_body(request)
    if not body.get("category"):
        return envelope_error("category is required",
                              status=400, code="MISSING_CATEGORY")

    # Allow callers to supply devices instead of yearly_units
    devices = body.get("devices")
    if devices and "yearly_units" not in body:
        body["yearly_units"] = (
            tariff_timeline_engine.yearly_units_from_devices(
                devices, days=safe_int(body.get("days"), 365)
            )
        )

    result = tariff_timeline_engine.calculate_timeline(body)
    if not result.get("ok"):
        return envelope_error(result.get("error", "calculation failed"),
                              status=400, code="CALC_FAILED")
    return envelope_ok(result)


# =====================================================================
# 6. PR3 — Frontend dropdown sources (Category / Subcategory / Cond-Load)
# =====================================================================
# These endpoints power the New Case form's cascading dropdowns. They
# read EXCLUSIVELY from the uploaded tariff_rates table — no hardcoded
# category list, no static mappings. If no tariff schedule has been
# uploaded yet, each endpoint returns an empty list and the frontend
# falls back to its static <option> baseline.
def _date_filter_clause(as_of: Optional[str]) -> tuple[str, list]:
    """Return (sql_fragment, params) that restricts to rows active on as_of.

    Per-row effective dates take priority over schedule-level dates;
    NULL on either side means "open" on that side.
    """
    if not as_of:
        return "", []
    return (
        " AND (\n"
        "       (COALESCE(effective_from, schedule_effective_from) IS NULL\n"
        "         OR COALESCE(effective_from, schedule_effective_from) <= ?)\n"
        "   AND (COALESCE(effective_to,   schedule_effective_to)   IS NULL\n"
        "         OR COALESCE(effective_to,   schedule_effective_to)   >= ?)\n"
        " )",
        [as_of, as_of],
    )


@bp.get("/categories")
def list_categories():
    """
    Distinct, active tariff categories.

    Query:
        as_of_date  (optional, YYYY-MM-DD) — restrict to rows active on
                    this date. Defaults to today.
    """
    as_of = parse_date(request.args.get("as_of_date")) \
            or date.today().isoformat()
    date_sql, date_params = _date_filter_clause(as_of)
    rows = fetch_all(
        f"""SELECT category,
                   COUNT(*) AS row_count,
                   COUNT(DISTINCT schedule_name) AS schedule_count,
                   COUNT(DISTINCT condition_load) AS subcategory_count
              FROM tariff_rates
             WHERE (status IS NULL OR status='active')
               AND category IS NOT NULL
               {date_sql}
             GROUP BY category
             ORDER BY category""",
        date_params,
    )
    return envelope_ok({
        "as_of_date": as_of,
        "categories": [{
            "category":          r["category"],
            "row_count":         int(r.get("row_count") or 0),
            "schedule_count":    int(r.get("schedule_count") or 0),
            "subcategory_count": int(r.get("subcategory_count") or 0),
        } for r in rows],
    })


@bp.get("/subcategories")
def list_subcategories():
    """
    Distinct condition_load values for a category. The frontend treats
    this as the 'Subcategory' dropdown — it sub-divides a category into
    its load bands (domestic/industrial/commercial/...).
    """
    category = (request.args.get("category") or "").strip()
    if not category:
        return envelope_error("category is required",
                              status=400, code="MISSING_CATEGORY")
    as_of = parse_date(request.args.get("as_of_date")) \
            or date.today().isoformat()
    date_sql, date_params = _date_filter_clause(as_of)

    rows = fetch_all(
        f"""SELECT COALESCE(NULLIF(TRIM(condition_load), ''), '__null__')
                       AS subcategory,
                   COUNT(*) AS row_count
              FROM tariff_rates
             WHERE (status IS NULL OR status='active')
               AND category = ?
               {date_sql}
             GROUP BY subcategory
             ORDER BY subcategory""",
        [category] + date_params,
    )
    return envelope_ok({
        "category":      category,
        "as_of_date":    as_of,
        "subcategories": [{
            # Map back our '__null__' sentinel so the UI can render
            # "(not specified)" while we still allow saving null.
            "value":      None if r["subcategory"] == "__null__" else r["subcategory"],
            "label":      "(any load band)" if r["subcategory"] == "__null__"
                          else r["subcategory"],
            "row_count":  int(r.get("row_count") or 0),
        } for r in rows],
    })


@bp.get("/condition-loads")
def list_condition_loads():
    """
    Alias of /subcategories kept under the natural REST path. Returns the
    same payload so the frontend can call either name.
    """
    return list_subcategories()


@bp.get("/preview")
def preview_tariff():
    """
    Preview the active rate set the system would apply for given inputs.

    Query:
        category         (required)
        condition_load   (optional)  — subcategory
        as_of_date       (optional, default today)
        units            (optional, monthly_units for slab-wise illustration)

    Returns:
        {
            "category", "condition_load", "as_of_date",
            "schedule_name", "condition_text",
            "slabs":   [ {slab_start, slab_end, rate_per_unit,
                          slab_name, fixed_charge, duty_percent,
                          meter_rent, rebate}, ... ],
            "matched": {primary row dict},
            "preview": {                        # only if units supplied
                "monthly_units":   N,
                "slab_breakdown": [ {slab, rate, units, amount}, ... ],
                "monthly_subtotal": A,
            }
        }
    """
    category = (request.args.get("category") or "").strip()
    if not category:
        return envelope_error("category is required",
                              status=400, code="MISSING_CATEGORY")
    as_of = parse_date(request.args.get("as_of_date")) \
            or date.today().isoformat()
    condition_load_raw = request.args.get("condition_load")
    condition_load = (condition_load_raw.strip()
                      if isinstance(condition_load_raw, str)
                         and condition_load_raw.strip()
                      else None)

    # Pull active rows for (category) and the date.
    date_sql, date_params = _date_filter_clause(as_of)
    rows = fetch_all(
        f"""SELECT * FROM tariff_rates
             WHERE (status IS NULL OR status='active')
               AND category = ?
               {date_sql}
             ORDER BY COALESCE(slab_start, 0)""",
        [category] + date_params,
    )
    if not rows:
        return envelope_error(
            f"No active tariff rows for category '{category}' on {as_of}",
            status=404, code="NO_RATES",
        )

    # Filter by condition_load (NULL acts as wildcard on row side)
    a_cl = condition_load.lower() if condition_load else None
    eligible = []
    for r in rows:
        b_cl_raw = r.get("condition_load")
        b_cl = (str(b_cl_raw).strip().lower()
                if b_cl_raw is not None and str(b_cl_raw).strip() else None)
        if a_cl is not None and b_cl is not None and a_cl != b_cl:
            continue
        eligible.append(dict(r))
    if not eligible:
        return envelope_error(
            f"No active rows match category '{category}' "
            f"with condition_load='{condition_load}' on {as_of}",
            status=404, code="NO_RATES_FOR_LOAD",
        )

    # Sort: slab_start ASC. Use first row as "primary" for metadata.
    eligible.sort(key=lambda r: int(r.get("slab_start") or 0))
    primary = eligible[0]

    slabs_out = [{
        "slab_start":    int(r.get("slab_start") or 0),
        "slab_end":      r.get("slab_end"),
        "rate_per_unit": _coerce_rate(r.get("rate_per_unit")),
        "slab_name":     r.get("slab_name"),
        "condition":     r.get("condition"),
    } for r in eligible]

    payload = {
        "category":       category,
        "condition_load": condition_load,
        "as_of_date":     as_of,
        "schedule_name":  primary.get("schedule_name"),
        "schedule_effective_from": primary.get("schedule_effective_from"),
        "schedule_effective_to":   primary.get("schedule_effective_to"),
        "condition_text": primary.get("condition") or "",
        "fixed_charge":   _coerce_rate(primary.get("fixed_charge")),
        "duty_percent":   _coerce_rate(primary.get("duty_percent")),
        "meter_rent":     _coerce_rate(primary.get("meter_rent")),
        "rebate":         _coerce_rate(primary.get("rebate")),
        "slabs":          slabs_out,
        "matched_rate_row_id": primary.get("id"),
    }

    # Optional slab-wise breakdown when 'units' supplied
    units = safe_float(request.args.get("units"))
    if units > 0:
        breakdown = []
        remaining = float(units)
        for r in eligible:
            start = int(r.get("slab_start") or 0)
            end_raw = r.get("slab_end")
            end = int(end_raw) if end_raw not in (None, "") else None
            rate = float(r.get("rate_per_unit") or 0)
            cap = (end - start + 1) if end is not None else float("inf")
            consumed = min(remaining, cap)
            if consumed <= 0:
                if remaining <= 0 and breakdown:
                    break
                continue
            breakdown.append({
                "slab_start":   start,
                "slab_end":     end,
                "slab_name":    r.get("slab_name"),
                "rate":         rate,
                "units":        round(consumed, 4),
                "amount":       round(consumed * rate, 4),
            })
            remaining -= consumed
            if remaining <= 0:
                break
        subtotal = round(sum(b["amount"] for b in breakdown), 2)
        payload["preview"] = {
            "monthly_units":     round(units, 4),
            "slab_breakdown":    breakdown,
            "monthly_subtotal":  subtotal,
        }
    return envelope_ok(payload)


def _coerce_rate(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
