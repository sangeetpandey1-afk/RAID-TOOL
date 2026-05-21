"""Backup & restore HTTP endpoints."""
from __future__ import annotations
import logging
from flask import Blueprint, request, send_from_directory

from .. import config
from ..services import backup as backup_svc
from ..utils import envelope_error, envelope_ok, get_json_body

log = logging.getLogger(__name__)

bp = Blueprint("backup", __name__, url_prefix="/api/backup")


@bp.get("/status")
def get_status():
    return envelope_ok(backup_svc.status())


@bp.post("/now")
def create_now():
    body = get_json_body(request) if request.data else {}
    res = backup_svc.create_backup(
        include_docs=body.get("include_docs", True),
        include_master_data=body.get("include_master_data", True),
        upload_gdrive=body.get("upload_gdrive", True),
    )
    return envelope_ok(res)


@bp.get("/list")
def list_all():
    items = backup_svc.list_backups()
    return envelope_ok(items, meta={"count": len(items)})


@bp.get("/download/<name>")
def download(name: str):
    # Minimal hardening — only allow files we created
    if not name.startswith("raid_backup_") or not name.endswith(".zip"):
        return envelope_error("Invalid backup name", status=400,
                              code="BAD_NAME")
    target = config.BACKUP_DIR / name
    if not target.exists():
        return envelope_error("Backup not found", status=404,
                              code="NOT_FOUND")
    return send_from_directory(config.BACKUP_DIR, name, as_attachment=True)


@bp.post("/restore")
def restore():
    body = get_json_body(request)
    name = body.get("name")
    if not name:
        return envelope_error("`name` is required (zip file name)",
                              status=400, code="MISSING_NAME")
    try:
        res = backup_svc.restore_from_zip(name)
        return envelope_ok(res)
    except FileNotFoundError as e:
        return envelope_error(str(e), status=404, code="NOT_FOUND")
