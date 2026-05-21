"""Health-check + system info endpoints."""
from __future__ import annotations
import sqlite3
import sys

from flask import Blueprint, request

from .. import __version__, config
from ..database import fetch_one, fetch_all, execute, audit
from ..utils import envelope_ok, envelope_error, get_json_body

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    """Liveness probe + light DB check."""
    db_ok = False
    table_counts: dict[str, int] = {}
    try:
        for tbl in ("consumers", "historical_cases", "device_master",
                    "rate_master", "raid_cases"):
            row = fetch_one(f"SELECT COUNT(*) AS c FROM {tbl}")
            table_counts[tbl] = row["c"] if row else 0
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        table_counts = {"error": str(exc)}

    return envelope_ok({
        "status": "ok",
        "version": __version__,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "db_path": str(config.DB_PATH),
        "db_ok": db_ok,
        "table_counts": table_counts,
    })


@bp.get("/system/config")
def system_config():
    """Return business defaults (multipliers, timelines, office identity, etc.)."""
    return envelope_ok({
        r["config_key"]: r["config_value"]
        for r in fetch_all("SELECT config_key, config_value FROM system_config")
    })


@bp.post("/system/config")
def update_system_config():
    """Update one or many config keys.

    Body: {"key": "value"} or {"office_phone": "...", "office_email": "..."}
    Or: {"updates": {"key": "value", ...}}
    """
    body = get_json_body(request) or {}
    updates = body.get("updates") if isinstance(body.get("updates"), dict) else body
    if not isinstance(updates, dict) or not updates:
        return envelope_error("Provide config updates as JSON object",
                              status=400, code="EMPTY")

    written = 0
    for key, val in updates.items():
        if not isinstance(key, str) or not key.strip():
            continue
        # UPSERT
        execute(
            """INSERT INTO system_config(config_key, config_value)
               VALUES (?, ?)
               ON CONFLICT(config_key) DO UPDATE SET
                   config_value=excluded.config_value,
                   updated_at=datetime('now')""",
            (key, "" if val is None else str(val)),
        )
        written += 1
    audit("web-ui", "CONFIG_UPDATE", "system_config", "bulk",
          new=updates)
    return envelope_ok({"updated": written, "keys": list(updates.keys())})
