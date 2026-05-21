"""HTTP routes for master-data import (the formerly-buggy area)."""
from __future__ import annotations
import logging

from flask import Blueprint, request

from ..services import importer
from ..utils import envelope_ok, envelope_error

log = logging.getLogger(__name__)
bp = Blueprint("master_data", __name__, url_prefix="/api")


@bp.get("/master_files")
def master_files():
    """Diagnostic — show which Excel file the importer will pick for each kind."""
    return envelope_ok({
        "master_data_dir": str(importer.config.MASTER_DATA_DIR),
        "files": importer.list_master_files(),
    })


@bp.post("/import_all_master_data")
def import_all_master_data():
    """Run every importer that has a file present (the buggy endpoint, now safe)."""
    reports = importer.import_all()

    # Aggregate stats for at-a-glance summary
    summary = {
        "total_inserted": sum(r.get("inserted", 0) for r in reports.values()),
        "total_updated":  sum(r.get("updated", 0) for r in reports.values()),
        "total_skipped":  sum(r.get("skipped", 0) for r in reports.values()),
        "total_errors":   sum(r.get("error_count", 0) for r in reports.values()),
        "files_imported": sum(1 for r in reports.values() if r.get("file_path")),
    }
    return envelope_ok({"summary": summary, "reports": reports})


_KIND_MAP = {
    "consumers":  importer.import_consumers,
    "historical": importer.import_historical,
    "current":    importer.import_current,
    "devices":    importer.import_devices,
    "rates":      importer.import_rates,
    "mapping":    importer.import_account_mapping,
}


@bp.post("/import_master/<kind>")
def import_one(kind: str):
    """Import a single master kind. Optional JSON body: {\"path\": \"...\"}."""
    if kind not in _KIND_MAP:
        return envelope_error(
            f"Unknown master kind '{kind}'. Valid: {list(_KIND_MAP)}",
            status=400, code="BAD_KIND",
        )
    body = request.get_json(silent=True) or {}
    custom_path = body.get("path")
    from pathlib import Path
    path = Path(custom_path) if custom_path else None
    if path and not path.exists():
        return envelope_error(f"File does not exist: {path}", status=404,
                              code="FILE_MISSING")
    rep = _KIND_MAP[kind](path)
    return envelope_ok(rep.to_dict())


@bp.post("/import_excel_upload")
def import_excel_upload():
    """
    Upload an Excel file and import it as historical/current/consumer data.

    Multipart form:
      - file: Excel file (.xlsx)
      - kind: consumers|historical|current|devices|rates|mapping (default: historical)

    Use case: purane case ka excel upload karo, offense count build hoga.
    """
    if "file" not in request.files:
        return envelope_error("No file. Send multipart form with 'file' field.",
                              status=400, code="NO_FILE")
    file = request.files["file"]
    if not file or file.filename == "":
        return envelope_error("Empty file", status=400, code="EMPTY_FILE")

    from pathlib import Path
    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls", ".xlsm"):
        return envelope_error("Only Excel files (.xlsx/.xls) accepted",
                              status=400, code="INVALID_TYPE")

    kind = request.form.get("kind", "historical")
    if kind not in _KIND_MAP:
        return envelope_error(f"Unknown kind '{kind}'. Valid: {list(_KIND_MAP)}",
                              status=400, code="BAD_KIND")

    # Save uploaded file temporarily
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False,
                                      dir=str(importer.config.MASTER_DATA_DIR))
    file.save(tmp.name)
    tmp.close()

    try:
        rep = _KIND_MAP[kind](Path(tmp.name))
        result = rep.to_dict()
    finally:
        # Keep the file in master_data for reference (rename with original name)
        dest = importer.config.MASTER_DATA_DIR / file.filename
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_uploaded{ext}")
        os.rename(tmp.name, str(dest))
        result["saved_as"] = str(dest)

    return envelope_ok(result)


@bp.get("/offense_count/<account>")
def offense_count(account: str):
    """
    Quick offense count for an account — used to decide multiplier.
    Also searches by name+father+village in historical_cases.
    """
    from ..database import fetch_one, fetch_all
    from ..utils import normalize_account

    acct = normalize_account(account)

    # Direct account match in historical_cases
    hist_by_acct = fetch_all(
        "SELECT * FROM historical_cases WHERE account_id=? ORDER BY case_date",
        (acct,),
    )

    # Also check offense_summary table
    offense = fetch_one(
        "SELECT * FROM offense_summary WHERE consumer_key=?",
        (acct.lower() if acct else "",),
    )

    # Check raid_cases too (live/new cases)
    raid_cases = fetch_all(
        "SELECT case_id, inspection_date, section, total_assessment, case_status "
        "FROM raid_cases WHERE account_number=? ORDER BY inspection_date",
        (acct,),
    )

    total_offenses = len(hist_by_acct) + len(raid_cases)
    if offense:
        total_offenses = max(total_offenses, offense["total_offenses"])

    # Multiplier suggestion
    threshold = 2
    is_repeat = total_offenses >= threshold
    multiplier = 6.0 if is_repeat else 2.0

    return envelope_ok({
        "account": acct,
        "total_offenses": total_offenses,
        "historical_cases": len(hist_by_acct),
        "active_cases": len(raid_cases),
        "is_repeat_offender": is_repeat,
        "suggested_multiplier": multiplier,
        "offense_summary": dict(offense) if offense else None,
        "historical_details": [dict(h) for h in hist_by_acct[:20]],
        "active_details": [dict(r) for r in raid_cases[:20]],
    })
