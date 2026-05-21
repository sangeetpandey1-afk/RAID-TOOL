"""Device master + rate slab read/write APIs (incl. Excel upload)."""
from __future__ import annotations
import logging
import os
import tempfile
from datetime import date
from pathlib import Path

from flask import Blueprint, request

from .. import config
from ..database import execute, execute_many, fetch_all, fetch_one, audit
from ..utils import envelope_ok, envelope_error, safe_float, safe_int, parse_date

log = logging.getLogger(__name__)
bp = Blueprint("device_rate", __name__, url_prefix="/api")


# ===================================================================
# DEVICES
# ===================================================================
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


# ===================================================================
# RATES — READ
# ===================================================================
@bp.get("/rates")
def list_rates():
    cat = request.args.get("category")
    eff = request.args.get("effective_date")
    if not cat:
        rows = fetch_all(
            "SELECT DISTINCT category FROM rate_master WHERE status='active' ORDER BY category"
        )
        return envelope_ok([r["category"] for r in rows],
                           meta={"hint": "pass ?category=LMV-1 for slab details"})
    params = [cat]
    date_clause = ""
    if eff:
        date_clause = "AND effective_date = ?"
        params.append(eff)
    rows = fetch_all(
        f"""SELECT * FROM rate_master WHERE category=? AND status='active'
            {date_clause}
            ORDER BY effective_date DESC, slab_start ASC""",
        params,
    )
    if not rows:
        return envelope_error(f"No rates found for category '{cat}'",
                              status=404, code="NO_RATES")
    return envelope_ok(rows, meta={"count": len(rows)})


@bp.get("/rates/categories")
def rate_categories():
    """All distinct categories with slab count + effective dates."""
    rows = fetch_all(
        """SELECT category,
                  COUNT(*) AS slab_count,
                  MIN(slab_start) AS lo,
                  MAX(COALESCE(slab_end, 999999)) AS hi,
                  MAX(effective_date) AS latest_effective_date,
                  MIN(COALESCE(fixed_charge, 0)) AS fixed_charge_min,
                  MAX(COALESCE(fixed_charge, 0)) AS fixed_charge_max,
                  AVG(COALESCE(duty_percent, 0)) AS avg_ed_percent
           FROM rate_master
           WHERE status = 'active'
           GROUP BY category
           ORDER BY category"""
    )
    return envelope_ok(rows)


@bp.get("/rates/effective-dates")
def rate_effective_dates():
    """List all distinct effective dates (for version dropdown)."""
    rows = fetch_all(
        """SELECT DISTINCT effective_date, COUNT(*) AS slab_count
           FROM rate_master WHERE status='active'
           GROUP BY effective_date
           ORDER BY effective_date DESC"""
    )
    return envelope_ok(rows)


@bp.get("/rates/full")
def rates_full():
    """Return ALL active rate slabs grouped by category (for UI dropdowns)."""
    rows = fetch_all(
        """SELECT * FROM rate_master WHERE status='active'
           ORDER BY category, effective_date DESC, slab_start ASC"""
    )
    # Group by category
    grouped = {}
    for r in rows:
        cat = r["category"]
        if cat not in grouped:
            grouped[cat] = {
                "category": cat,
                "effective_date": r.get("effective_date"),
                "fixed_charge": r.get("fixed_charge"),
                "duty_percent": r.get("duty_percent"),
                "condition": r.get("condition"),
                "slabs": [],
            }
        grouped[cat]["slabs"].append(r)
    return envelope_ok(list(grouped.values()), meta={"categories": len(grouped)})


# ===================================================================
# RATES — UPLOAD (Excel file)
# ===================================================================
@bp.post("/rates/upload")
def upload_rates():
    """
    Upload a rate schedule Excel file.

    Accepts multipart/form-data with:
      - file: The .xlsx/.xls file
      - effective_date: (optional) override date, else reads from file or uses today
      - replace: (optional) "true" to deactivate old rates for same categories

    Expected columns (flexible naming via importer synonyms):
      Category, SlabStart, SlabEnd, RatePerUnit, FixedCharge, DutyPercent,
      Condition, EffectiveDate
    """
    if "file" not in request.files:
        return envelope_error("No file uploaded. Send as multipart with field 'file'.",
                              status=400, code="NO_FILE")

    uploaded = request.files["file"]
    if not uploaded.filename:
        return envelope_error("Empty filename.", status=400, code="NO_FILE")

    ext = Path(uploaded.filename).suffix.lower()
    if ext not in (".xlsx", ".xls", ".xlsm"):
        return envelope_error(
            f"Unsupported file type '{ext}'. Upload .xlsx or .xls.",
            status=400, code="BAD_FILE_TYPE")

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(config.MASTER_DATA_DIR))
    try:
        uploaded.save(tmp.name)
        tmp.close()

        # Parse
        import pandas as pd
        df = pd.read_excel(tmp.name, dtype=object, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        if df.empty:
            return envelope_error("File is empty (0 rows).", status=400,
                                  code="EMPTY_FILE")

        # Column mapping (flexible)
        col_map = _map_rate_columns(df.columns)
        if "category" not in col_map:
            return envelope_error(
                f"Could not find 'Category' column. Available: {list(df.columns)}",
                status=400, code="MISSING_COLUMN")

        # Effective date override
        override_date = request.form.get("effective_date") or request.args.get("effective_date")
        replace_old = (request.form.get("replace") or "").lower() == "true"

        inserted = 0
        skipped = 0
        errors = []
        categories_seen = set()

        for idx, row in df.iterrows():
            try:
                cat = _get(row, col_map, "category")
                if not cat:
                    skipped += 1
                    continue
                cat = str(cat).strip()
                categories_seen.add(cat)

                slab_start = safe_int(_get(row, col_map, "slab_start"), 0)
                slab_end_raw = _get(row, col_map, "slab_end")
                slab_end = None
                if slab_end_raw is not None:
                    sv = safe_int(slab_end_raw, -1)
                    if sv >= 0 and sv < 999999:
                        slab_end = sv

                rate = safe_float(_get(row, col_map, "rate_per_unit"))
                fixed = safe_float(_get(row, col_map, "fixed_charge"))
                duty = safe_float(_get(row, col_map, "duty_percent"))
                condition = _get(row, col_map, "condition")
                if condition:
                    condition = str(condition).strip()

                eff_date = override_date or parse_date(_get(row, col_map, "effective_date")) or date.today().isoformat()

                execute(
                    """INSERT INTO rate_master
                          (category, slab_start, slab_end, rate_per_unit,
                           fixed_charge, duty_percent, condition,
                           effective_date, status)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (cat, slab_start, slab_end, rate, fixed, duty,
                     condition, eff_date, "active"),
                )
                inserted += 1
            except Exception as e:
                errors.append({"row": int(idx) + 2, "error": str(e)})
                skipped += 1

        # Optionally deactivate old rates for same categories
        deactivated = 0
        if replace_old and categories_seen and override_date:
            for cat in categories_seen:
                cur = execute(
                    """UPDATE rate_master SET status='inactive'
                       WHERE category=? AND effective_date != ? AND status='active'""",
                    (cat, override_date),
                )
                deactivated += cur.rowcount

        audit("web-ui", "RATE_UPLOAD", "rate_master", uploaded.filename,
              new={"inserted": inserted, "categories": list(categories_seen),
                   "effective_date": override_date or "from_file"})

        # Also save a permanent copy
        permanent = config.MASTER_DATA_DIR / f"slab_rates_{override_date or date.today().isoformat()}{ext}"
        import shutil
        shutil.copy(tmp.name, str(permanent))

        return envelope_ok({
            "inserted": inserted,
            "skipped": skipped,
            "deactivated": deactivated,
            "error_count": len(errors),
            "errors_sample": errors[:10],
            "categories": sorted(categories_seen),
            "effective_date": override_date or "from_file",
            "saved_as": str(permanent),
            "columns_found": col_map,
        })

    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@bp.delete("/rates/by-date/<eff_date>")
def delete_rates_by_date(eff_date: str):
    """Deactivate (soft-delete) all rates for a given effective_date."""
    cnt = fetch_one(
        "SELECT COUNT(*) AS c FROM rate_master WHERE effective_date=? AND status='active'",
        (eff_date,),
    )
    if not cnt or cnt["c"] == 0:
        return envelope_error(f"No active rates for date {eff_date}",
                              status=404, code="NOT_FOUND")
    execute(
        "UPDATE rate_master SET status='inactive' WHERE effective_date=? AND status='active'",
        (eff_date,),
    )
    audit("web-ui", "RATE_DELETE", "rate_master", eff_date,
          old={"count": cnt["c"]})
    return envelope_ok({"deactivated": cnt["c"], "effective_date": eff_date})


@bp.post("/rates/activate/<eff_date>")
def activate_rates_by_date(eff_date: str):
    """Re-activate rates for a date (undo delete)."""
    execute(
        "UPDATE rate_master SET status='active' WHERE effective_date=?",
        (eff_date,),
    )
    return envelope_ok({"activated_date": eff_date})


# ===================================================================
# Helpers for column mapping
# ===================================================================
import re

_RATE_COL_SYNONYMS = {
    "category":       ["category", "tariff_category", "lmv", "rate_category", "cat"],
    "slab_start":     ["slabstart", "slab_start", "from", "from_unit", "lower", "min_units", "start"],
    "slab_end":       ["slabend", "slab_end", "to", "to_unit", "upper", "max_units", "end"],
    "rate_per_unit":  ["rateperunit", "rate_per_unit", "rate", "tariff", "energy_rate", "unitrate"],
    "fixed_charge":   ["fixedcharge", "fixed_charge", "fixed", "fixedrate", "monthly_fixed", "ixedcharge"],
    "duty_percent":   ["dutypercent", "duty_percent", "duty", "ed", "ed_percent", "utypercent",
                       "electricity_duty", "edpercent"],
    "condition":      ["condition", "remark", "remarks", "note", "cond"],
    "effective_date": ["effectivedate", "effective_date", "from_date", "valid_from",
                       "date", "fectivedate", "eff_date"],
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _map_rate_columns(columns):
    norm_to_orig = {_norm(c): str(c) for c in columns}
    mapping = {}
    for target, candidates in _RATE_COL_SYNONYMS.items():
        for cand in candidates:
            key = _norm(cand)
            if key in norm_to_orig:
                mapping[target] = norm_to_orig[key]
                break
    return mapping


def _get(row, col_map, target):
    import pandas as pd
    actual = col_map.get(target)
    if not actual:
        return None
    val = row.get(actual)
    if pd.isna(val):
        return None
    return val
