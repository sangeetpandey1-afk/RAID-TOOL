"""
Tariff schedule + rate-master HTTP routes.

Endpoints
---------
POST /api/rates/import
        multipart/form-data file=<workbook>, plus form fields:
            schedule_name      (required)
            effective_from     (optional, ISO yyyy-mm-dd)
            effective_to       (optional, ISO yyyy-mm-dd)
            notes              (optional)
            conflict_strategy  (optional: warn|replace|keep_both|cancel,
                                default 'warn')
        Returns ImportResult dict + envelope.

GET  /api/rates/schedules
        List of schedules + per-schedule rate-row counts and the
        distinct categories present in each schedule.

GET  /api/rates/schedules/<id>
        Full schedule with all its tariff_rates rows.

POST /api/rates/schedules/<id>/activate
        JSON body {"is_active": true|false}.

GET  /api/rates/preview
        ?category=LMV-2&subcategory=Urban+%E2%89%A44KW
        &supply_type=Commercial&load_kw=2.5&on_date=2025-08-15
        Returns the single applicable rate row (or 404 envelope).

GET  /api/rates/timeline
        Same filters as /preview, plus either
            inspection_date=2025-08-15&lfhd_days=365
        or  start_date=2024-08-16&end_date=2025-08-15
        and optional total_units=2365.0
        Returns segments + warnings.

GET  /api/rates/sample.xlsx
        Downloads a template workbook (correct headers + a few sample
        rows).  Operators can edit and re-upload.

Safety notes
------------
* The blueprint never modifies any other table — only
  ``tariff_schedules`` + ``tariff_rates``.
* Calculator / notice templates / save-load are untouched.
* The legacy ``rate_master`` table (slab-based, used by
  services/calculator.py) is NOT read or written here.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from flask import Blueprint, request, send_file

from .. import config
from ..database import get_connection
from ..services import tariff_engine, tariff_timeline_engine
from ..utils import envelope_ok, envelope_error, get_json_body

log = logging.getLogger(__name__)
bp = Blueprint("rates", __name__, url_prefix="/api/rates")


_ALLOWED_EXT = {".xlsx", ".xls", ".xlsm", ".csv", ".txt"}
_MAX_BYTES = 25 * 1024 * 1024


# ---------------------------------------------------------------------
# POST /import
# ---------------------------------------------------------------------

@bp.post("/import")
def import_rates_upload():
    if "file" not in request.files:
        return envelope_error(
            "No file uploaded — send the workbook in form field 'file'.",
            status=400, code="NO_FILE",
        )
    fs = request.files["file"]
    if not fs.filename:
        return envelope_error(
            "Empty filename in upload.", status=400, code="NO_FILENAME",
        )

    suffix = Path(fs.filename).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        return envelope_error(
            f"Unsupported file type {suffix!r}. "
            f"Allowed: {sorted(_ALLOWED_EXT)}",
            status=400, code="BAD_EXT",
        )

    schedule_name = (request.form.get("schedule_name") or "").strip()
    if not schedule_name:
        return envelope_error(
            "Missing schedule_name. Provide it as a form field or in the JSON body.",
            status=400, code="NO_SCHEDULE_NAME",
        )

    effective_from = (request.form.get("effective_from") or "").strip() or None
    effective_to   = (request.form.get("effective_to")   or "").strip() or None
    notes          = (request.form.get("notes")          or "").strip() or None
    strategy       = (request.form.get("conflict_strategy") or "warn").strip().lower()
    if strategy not in ("warn", "replace", "keep_both", "cancel"):
        return envelope_error(
            f"Invalid conflict_strategy {strategy!r}. "
            "Use one of: warn | replace | keep_both | cancel.",
            status=400, code="BAD_STRATEGY",
        )

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = config.LOGS_DIR / "rate_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_stub = "".join(c for c in fs.filename if c.isalnum() or c in "._-") or "upload"
    tmp_path = tmp_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe_stub}"

    try:
        fs.save(str(tmp_path))
        size = tmp_path.stat().st_size
        if size > _MAX_BYTES:
            return envelope_error(
                f"File is {size:,} bytes which exceeds the {_MAX_BYTES:,}-byte"
                f" upload limit. Split the workbook and try again.",
                status=413, code="TOO_LARGE",
            )

        parsed = tariff_engine.parse_rates_file(tmp_path)
        meta = tariff_engine.ScheduleMeta(
            schedule_name=schedule_name,
            effective_from=effective_from,
            effective_to=effective_to,
            notes=notes,
            source_file=fs.filename,
        )
        conn = get_connection()
        result = tariff_engine.import_schedule(
            conn, meta, parsed, conflict_strategy=strategy,
        )
        return envelope_ok({
            "summary": result.to_dict(),
            "applied_strategy": strategy,
        })

    except FileNotFoundError as e:
        return envelope_error(str(e), status=404, code="FILE_MISSING")
    except ValueError as e:
        return envelope_error(str(e), status=400, code="BAD_FILE")
    except Exception as e:  # noqa: BLE001
        log.exception("Tariff import crashed for %s", fs.filename)
        return envelope_error(
            f"{type(e).__name__}: {e}",
            status=500, code="IMPORT_FAILED",
        )
    finally:
        try:
            if tmp_path.exists():
                os.remove(tmp_path)
        except OSError:
            log.warning("Could not delete temp upload %s", tmp_path)


# ---------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------

@bp.get("/schedules")
def list_schedules_route():
    conn = get_connection()
    schedules = tariff_engine.list_schedules(conn)
    return envelope_ok({"schedules": schedules, "count": len(schedules)})


@bp.get("/schedules/<int:schedule_id>")
def get_schedule_route(schedule_id: int):
    conn = get_connection()
    sch = tariff_engine.get_schedule(conn, schedule_id, include_rates=True)
    if not sch:
        return envelope_error(
            f"No schedule with id={schedule_id}", status=404, code="NOT_FOUND",
        )
    return envelope_ok(sch)


@bp.post("/schedules/<int:schedule_id>/activate")
def activate_schedule_route(schedule_id: int):
    body = get_json_body(request)
    is_active = bool(body.get("is_active", True))
    conn = get_connection()
    ok = tariff_engine.set_active(conn, schedule_id, is_active)
    if not ok:
        return envelope_error(
            f"No schedule with id={schedule_id}", status=404, code="NOT_FOUND",
        )
    return envelope_ok({
        "schedule_id": schedule_id,
        "is_active":   is_active,
    })


# ---------------------------------------------------------------------
# Live tariff preview (single applicable rate)
# ---------------------------------------------------------------------

def _arg_float(name: str) -> float | None:
    v = request.args.get(name)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


@bp.get("/preview")
def preview_route():
    category = (request.args.get("category") or "").strip()
    if not category:
        return envelope_error(
            "Missing required query parameter: category.",
            status=400, code="NO_CATEGORY",
        )

    conn = get_connection()
    rate = tariff_engine.find_applicable_rate(
        conn,
        category=category,
        subcategory=(request.args.get("subcategory") or "").strip() or None,
        supply_type=(request.args.get("supply_type") or "").strip() or None,
        load_kw=_arg_float("load_kw"),
        units=_arg_float("units"),
        on_date=(request.args.get("on_date") or "").strip() or None,
    )
    if not rate:
        return envelope_ok({
            "applicable":  None,
            "category":    category,
            "subcategory": (request.args.get("subcategory") or "").strip() or None,
            "supply_type": (request.args.get("supply_type") or "").strip() or None,
            "message": "No active tariff matches these filters.",
        })
    return envelope_ok({"applicable": rate})


# ---------------------------------------------------------------------
# Timeline (split LFHD period across schedules)
# ---------------------------------------------------------------------

@bp.get("/timeline")
def timeline_route():
    category = (request.args.get("category") or "").strip()
    if not category:
        return envelope_error(
            "Missing required query parameter: category.",
            status=400, code="NO_CATEGORY",
        )

    inspection_date = (request.args.get("inspection_date") or "").strip() or None
    lfhd_days = request.args.get("lfhd_days")
    start_date = (request.args.get("start_date") or "").strip() or None
    end_date   = (request.args.get("end_date")   or "").strip() or None

    if not ((start_date and end_date) or (inspection_date and lfhd_days)):
        return envelope_error(
            "Provide either (start_date AND end_date) OR "
            "(inspection_date AND lfhd_days).",
            status=400, code="NO_PERIOD",
        )

    try:
        timeline = tariff_timeline_engine.build_timeline(
            get_connection(),
            category=category,
            subcategory=(request.args.get("subcategory") or "").strip() or None,
            supply_type=(request.args.get("supply_type") or "").strip() or None,
            load_kw=_arg_float("load_kw"),
            start_date=start_date,
            end_date=end_date,
            inspection_date=inspection_date,
            lfhd_days=int(lfhd_days) if lfhd_days else None,
            total_units=_arg_float("total_units"),
        )
    except ValueError as e:
        return envelope_error(str(e), status=400, code="BAD_PERIOD")
    return envelope_ok(timeline)


# ---------------------------------------------------------------------
# Sample workbook
# ---------------------------------------------------------------------

@bp.get("/sample.xlsx")
def sample_route():
    """Generate (if missing) and stream a sample tariff workbook."""
    sample_dir = config.LOGS_DIR / "rate_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / "tariff_sample.xlsx"
    # Always rebuild so format stays in sync with the Excel parser's
    # expected column synonyms.
    tariff_engine.build_sample_workbook(sample_path)
    return send_file(
        str(sample_path),
        as_attachment=True,
        download_name="tariff_sample.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
