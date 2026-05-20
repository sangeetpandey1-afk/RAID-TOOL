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
