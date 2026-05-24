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
from datetime import datetime
from pathlib import Path

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
