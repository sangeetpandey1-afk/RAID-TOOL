"""
Backup service.

Two flavours, both available through the same API:

* **local** — always available; produces a timestamped ``.zip`` inside
  ``backup/`` containing the SQLite database, the ``master_data/`` folder
  and the ``docs/`` folder.

* **gdrive** — optional; when the Google Drive python client libraries are
  installed AND a service-account JSON path is provided via
  ``RAID_GDRIVE_CREDS`` and a folder id via ``RAID_GDRIVE_FOLDER_ID``,
  every backup is also uploaded to Google Drive.

The local backend is used unconditionally; the cloud upload is best-effort
and never breaks the primary backup operation.
"""
from __future__ import annotations
import logging
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import config

log = logging.getLogger(__name__)


# ===================================================================
# Google Drive (optional) — import lazily so the rest of the service
# is fully usable without the google libs installed.
# ===================================================================
def _gdrive_enabled() -> tuple[bool, str | None]:
    """Return (enabled, reason_if_disabled)."""
    creds_path = os.environ.get("RAID_GDRIVE_CREDS")
    folder_id  = os.environ.get("RAID_GDRIVE_FOLDER_ID")
    if not creds_path or not folder_id:
        return False, "RAID_GDRIVE_CREDS / RAID_GDRIVE_FOLDER_ID not set"
    if not Path(creds_path).exists():
        return False, f"creds file not found: {creds_path}"
    try:
        import google.oauth2.service_account  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.http import MediaFileUpload  # noqa: F401
    except ImportError as e:
        return False, f"google libs not installed: {e}"
    return True, None


def _upload_to_gdrive(local_zip: Path) -> dict:
    """Upload a file to Google Drive. Returns {ok, drive_id, link}."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_path = os.environ["RAID_GDRIVE_CREDS"]
    folder_id  = os.environ["RAID_GDRIVE_FOLDER_ID"]

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(str(local_zip), mimetype="application/zip",
                            resumable=False)
    body = {"name": local_zip.name, "parents": [folder_id]}
    f = service.files().create(
        body=body, media_body=media,
        fields="id, name, webViewLink, size",
    ).execute()
    return {
        "ok": True,
        "drive_id":   f["id"],
        "drive_name": f["name"],
        "drive_link": f.get("webViewLink"),
        "drive_size": f.get("size"),
    }


# ===================================================================
# Local zip backup
# ===================================================================
def _safe_db_copy(src: Path, dst: Path) -> None:
    """
    Copy a (possibly live) SQLite DB safely using the backup API so that
    any in-flight write transactions are captured cleanly.
    """
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()


def _zip_dir(zf: zipfile.ZipFile, src: Path, arc_root: str) -> int:
    if not src.exists():
        return 0
    n = 0
    for p in src.rglob("*"):
        if p.is_file():
            zf.write(p, arcname=f"{arc_root}/{p.relative_to(src)}")
            n += 1
    return n


def create_backup(*, include_docs: bool = True,
                  include_master_data: bool = True,
                  upload_gdrive: bool = True) -> dict:
    """Create a local zip backup; optionally upload to Drive."""
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"raid_backup_{ts}.zip"
    zip_path = config.BACKUP_DIR / zip_name

    summary: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "zip_path":   str(zip_path),
        "zip_name":   zip_name,
        "files": {"db": 0, "master_data": 0, "docs": 0},
    }

    # 1) Snapshot the DB to a temp file so the zip is clean
    tmp_db = config.BACKUP_DIR / f"_tmp_{ts}.db"
    if config.DB_PATH.exists():
        try:
            _safe_db_copy(config.DB_PATH, tmp_db)
        except Exception:  # noqa: BLE001
            log.exception("DB online backup failed; falling back to file copy")
            shutil.copy(config.DB_PATH, tmp_db)
    else:
        log.warning("DB file does not exist at %s", config.DB_PATH)

    # 2) Build the zip
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if tmp_db.exists():
            zf.write(tmp_db, arcname=f"raid_database.db")
            summary["files"]["db"] = 1
        if include_master_data:
            summary["files"]["master_data"] = _zip_dir(
                zf, config.MASTER_DATA_DIR, "master_data")
        if include_docs:
            summary["files"]["docs"] = _zip_dir(
                zf, config.DOCS_DIR, "docs")

    # Cleanup temp db copy
    if tmp_db.exists():
        try:
            tmp_db.unlink()
        except OSError:
            pass

    summary["zip_size"]    = zip_path.stat().st_size
    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")

    # 3) Optional Google Drive upload
    gd_ok, gd_reason = _gdrive_enabled()
    if upload_gdrive and gd_ok:
        try:
            res = _upload_to_gdrive(zip_path)
            summary["gdrive"] = res
        except Exception as e:  # noqa: BLE001
            log.exception("Google Drive upload failed")
            summary["gdrive"] = {"ok": False, "error": str(e)}
    else:
        summary["gdrive"] = {"ok": False, "skipped": True,
                             "reason": gd_reason or "disabled"}

    log.info("Backup created: %s (%.1f KB)",
             zip_path.name, summary["zip_size"] / 1024)
    return summary


def list_backups() -> list[dict]:
    if not config.BACKUP_DIR.exists():
        return []
    items = []
    for p in sorted(config.BACKUP_DIR.glob("raid_backup_*.zip"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        items.append({
            "name":       p.name,
            "path":       str(p),
            "size":       st.st_size,
            "size_kb":    round(st.st_size / 1024, 1),
            "modified":   datetime.fromtimestamp(st.st_mtime)
                                  .isoformat(timespec="seconds"),
        })
    return items


def restore_from_zip(zip_name: str) -> dict:
    """
    Restore DB, master_data and docs from a previously created backup.
    The current DB is renamed to ``raid_database.db.before_restore_<ts>``.
    """
    zip_path = config.BACKUP_DIR / zip_name
    if not zip_path.exists():
        raise FileNotFoundError(f"Backup not found: {zip_name}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if config.DB_PATH.exists():
        backup_db = config.DB_PATH.with_suffix(f".db.before_restore_{ts}")
        shutil.move(str(config.DB_PATH), str(backup_db))
    else:
        backup_db = None

    extracted = {"db": 0, "master_data": 0, "docs": 0}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if member == "raid_database.db":
                with zf.open(member) as src, open(config.DB_PATH, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted["db"] = 1
            elif member.startswith("master_data/"):
                zf.extract(member, path=config.ROOT_DIR)
                extracted["master_data"] += 1
            elif member.startswith("docs/"):
                zf.extract(member, path=config.ROOT_DIR)
                extracted["docs"] += 1

    return {
        "restored_from":      str(zip_path),
        "previous_db_backup": str(backup_db) if backup_db else None,
        "files":              extracted,
        "completed_at":       datetime.now().isoformat(timespec="seconds"),
    }


def status() -> dict:
    gd_ok, gd_reason = _gdrive_enabled()
    backups = list_backups()
    return {
        "backup_dir":  str(config.BACKUP_DIR),
        "db_path":     str(config.DB_PATH),
        "db_size":     config.DB_PATH.stat().st_size if config.DB_PATH.exists() else 0,
        "gdrive_enabled": gd_ok,
        "gdrive_reason":  gd_reason,
        "gdrive_folder":  os.environ.get("RAID_GDRIVE_FOLDER_ID"),
        "backup_count":   len(backups),
        "latest":         backups[0] if backups else None,
    }
