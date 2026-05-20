"""Health-check + system info endpoints."""
from __future__ import annotations
import sqlite3
import sys

from flask import Blueprint

from .. import __version__, config
from ..database import fetch_one, fetch_all
from ..utils import envelope_ok

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
    """Return business defaults (multipliers, timelines, etc.)."""
    return envelope_ok({
        r["config_key"]: r["config_value"]
        for r in fetch_all("SELECT config_key, config_value FROM system_config")
    })
