"""HTTP routes for master-data import (the formerly-buggy area)."""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path

from flask import Blueprint, request
from werkzeug.utils import secure_filename

from ..services import importer
from ..utils import envelope_ok, envelope_error

log = logging.getLogger(__name__)
bp = Blueprint("master_data", __name__, url_prefix="/api")

ALLOWED_EXTS = {".xlsx", ".xls", ".xlsm"}


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
    """Import a single master kind.

    Three input modes (in priority order):

    1. **Multipart upload** — ``multipart/form-data`` with a ``file`` field.
       The uploaded workbook is saved to a tmp file, imported, then deleted.
       Used by the web Imports page.
    2. **JSON body** — ``{"path": "/some/file.xlsx"}`` (server-side path).
    3. **No body** — falls back to auto-detecting the file in
       ``master_data/`` (legacy / disk-based behaviour, unchanged).
    """
    if kind not in _KIND_MAP:
        return envelope_error(
            f"Unknown master kind '{kind}'. Valid: {list(_KIND_MAP)}",
            status=400, code="BAD_KIND",
        )

    importer_fn = _KIND_MAP[kind]

    # --- Mode 1: multipart upload from the browser ---
    upload = request.files.get("file") if request.files else None
    if upload and upload.filename:
        safe_name = secure_filename(upload.filename) or "upload.xlsx"
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTS:
            return envelope_error(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {sorted(ALLOWED_EXTS)}",
                status=400, code="BAD_FILETYPE",
            )
        # Persist to a tmp file; importer needs a real path to call
        # pandas.read_excel(). Cleaned up in `finally`.
        tmp = tempfile.NamedTemporaryFile(
            prefix=f"upload_{kind}_", suffix=ext, delete=False,
        )
        try:
            upload.save(tmp.name)
            tmp.close()
            log.info("Uploaded %s (%s) for kind=%s -> %s",
                     safe_name, upload.content_length, kind, tmp.name)
            rep = importer_fn(Path(tmp.name))
            data = rep.to_dict()
            # Don't leak the tmp path to clients - replace with original name
            data["file_path"] = safe_name
            return envelope_ok(data)
        finally:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove tmp upload %s", tmp.name)

    # --- Mode 2/3: JSON path or auto-detect on server ---
    body = request.get_json(silent=True) or {}
    custom_path = body.get("path")
    path = Path(custom_path) if custom_path else None
    if path and not path.exists():
        return envelope_error(f"File does not exist: {path}", status=404,
                              code="FILE_MISSING")
    rep = importer_fn(path)
    return envelope_ok(rep.to_dict())
