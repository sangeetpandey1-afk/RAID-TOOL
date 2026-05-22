"""
SQLite connection management + schema bootstrap + seed data.

Every request gets its own connection (Flask `g`) so we don't share
connections across threads, which would otherwise raise
`sqlite3.ProgrammingError` under Werkzeug's threaded server.
"""
from __future__ import annotations
import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

from flask import g

from .config import DB_PATH, SCHEMA_FILE

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ helpers
def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection() -> sqlite3.Connection:
    """Return a per-request SQLite connection. Reuses one stored in flask.g."""
    if "db" not in g:
        conn = sqlite3.connect(
            str(DB_PATH),
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
            timeout=30.0,
        )
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        g.db = conn
    return g.db


def close_connection(_exc: Optional[BaseException] = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            log.exception("Error closing DB connection")


@contextmanager
def standalone_connection() -> Iterator[sqlite3.Connection]:
    """Direct connection for scripts/CLI usage outside Flask request context."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30.0)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ schema
def init_schema() -> None:
    """Create all tables/indexes from schema.sql (idempotent)."""
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema file missing: {SCHEMA_FILE}")
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with standalone_connection() as conn:
        conn.executescript(sql)
    log.info("Schema initialized at %s", DB_PATH)
    _apply_lightweight_migrations()
    _seed_devices_if_empty()
    _seed_config_if_empty()


# ------------------------------------------------------------------ migrations
# Lightweight, idempotent column/index additions for older databases.
# Each migration must be:
#   * additive only (ADD COLUMN / CREATE INDEX, never DROP / RENAME / ALTER)
#   * guarded by an existence check (PRAGMA table_info / sqlite_master)
#   * safe to run on every boot (no-op if already applied)
#
# DO NOT add destructive operations here. For schema redesigns, write a
# proper migration script under scripts/ instead.
_LIGHTWEIGHT_COLUMN_ADDS: list[tuple[str, str, str]] = [
    # (table, column, type)
    ("raid_cases", "checking_report_number", "TEXT"),
    # Sum of LFHD device wattages (auto-computed in the UI, but operator
    # can override). Stored separately from connected_load_kw which is the
    # Contracted/Sanctioned load on the meter — both fields exist on
    # purpose. Nullable; older rows simply get NULL.
    ("raid_cases", "total_connected_load_kw", "REAL"),
]

_LIGHTWEIGHT_INDEX_ADDS: list[tuple[str, str]] = [
    # (index_name, create_sql)
    ("idx_case_check_report",
     "CREATE INDEX IF NOT EXISTS idx_case_check_report "
     "ON raid_cases(checking_report_number)"),
]


def _apply_lightweight_migrations() -> None:
    """Add nullable columns / indexes that newer code expects, idempotently."""
    with standalone_connection() as conn:
        for table, column, coltype in _LIGHTWEIGHT_COLUMN_ADDS:
            existing = {r["name"] for r in
                        conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
                )
                log.info("Migration: added %s.%s (%s)", table, column, coltype)
        for _name, sql in _LIGHTWEIGHT_INDEX_ADDS:
            conn.execute(sql)


# ------------------------------------------------------------------ seed
DEFAULT_DEVICES: list[dict[str, Any]] = [
    # name, category, default_load(W), default_factor, default_hours, default_days
    ("Bulb / LED",            "Lighting & Fan",       9,    1.0, 6,  365),
    ("Tube Light / CFL",      "Lighting & Fan",       40,   1.0, 6,  365),
    ("Ceiling Fan",           "Lighting & Fan",       75,   1.0, 12, 365),
    ("Table Fan",             "Lighting & Fan",       60,   1.0, 8,  365),
    ("Exhaust Fan",           "Lighting & Fan",       50,   1.0, 4,  365),
    ("Air Cooler",            "Cooling",              200,  1.0, 10, 180),
    ("Cooler with Pump",      "Cooling",              250,  1.0, 10, 180),
    ("Refrigerator",          "Cooling",              200,  0.7, 24, 365),
    ("Deep Freezer",          "Cooling",              350,  0.7, 24, 365),
    ("AC 1 Ton",              "Cooling",              1500, 1.0, 8,  120),
    ("AC 1.5 Ton",            "Cooling",              1800, 1.0, 8,  120),
    ("AC 2 Ton",              "Cooling",              2200, 1.0, 8,  120),
    ("Water Heater (Geyser)", "Heating",              2000, 1.0, 1,  120),
    ("Room Heater",           "Heating",              1500, 1.0, 4,  60),
    ("Electric Iron",         "Heating",              750,  1.0, 1,  365),
    ("Induction Cooktop",     "Heating",              1500, 1.0, 1,  365),
    ("Microwave Oven",        "Heating",              1200, 1.0, 1,  365),
    ("Electric Kettle",       "Heating",              1500, 1.0, 1,  365),
    ("Washing Machine",       "Washing & Cleaning",   500,  1.0, 1,  365),
    ("Cloth Dryer",           "Washing & Cleaning",   2000, 1.0, 1,  120),
    ("Dish Washer",           "Washing & Cleaning",   1800, 1.0, 1,  365),
    ("Vacuum Cleaner",        "Washing & Cleaning",   1000, 1.0, 1,  365),
    ("Mixer / Grinder",       "Kitchen",              500,  1.0, 1,  365),
    ("Juicer / Blender",      "Kitchen",              400,  1.0, 1,  365),
    ("Toaster",               "Kitchen",              800,  1.0, 1,  365),
    ("Sandwich Maker",        "Kitchen",              700,  1.0, 1,  365),
    ("Rice Cooker",           "Kitchen",              700,  1.0, 1,  365),
    ("Coffee Maker",          "Kitchen",              800,  1.0, 1,  365),
    ("Water Pump 0.5 HP",     "Pumping",              370,  1.0, 4,  365),
    ("Water Pump 1 HP",       "Pumping",              745,  1.0, 4,  365),
    ("Water Pump 2 HP",       "Pumping",              1490, 1.0, 4,  365),
    ("Television",            "Electronics",          120,  1.0, 6,  365),
    ("Computer / Laptop",     "Electronics",          150,  1.0, 8,  365),
    ("Mobile Charger",        "Electronics",          10,   1.0, 4,  365),
    ("Set-Top Box",           "Electronics",          15,   1.0, 6,  365),
    ("Home Theatre",          "Electronics",          200,  1.0, 4,  365),
    ("Sewing Machine",        "Misc",                 80,   1.0, 2,  300),
    ("Hair Dryer",            "Misc",                 1500, 1.0, 1,  365),
    ("Air Purifier",          "Misc",                 50,   1.0, 12, 365),
    ("Inverter + Battery",    "Misc",                 500,  1.0, 4,  365),
]


def _seed_devices_if_empty() -> None:
    with standalone_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM device_master").fetchone()["c"]
        if count > 0:
            return
        rows = [
            (n, c, w, f, h, d, "Nos") for (n, c, w, f, h, d) in DEFAULT_DEVICES
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO device_master
               (device_name, category, default_load, default_factor,
                default_hours, default_days, unit)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        log.info("Seeded %d default devices", len(rows))


DEFAULT_CONFIG: dict[str, str] = {
    "multiplier_first_offense":  "2",
    "multiplier_repeat_offense": "6",
    "repeat_offense_threshold":  "2",
    "default_days_section_135":  "365",
    "admin_fee_section_3":       "25",
    "timeline_provisional_payment": "7",
    "timeline_appeal_window":       "15",
    "timeline_section_3_dispatch":  "45",
    "timeline_section_5_dispatch":  "90",
    "ed_default_percent":           "5",
}


def _seed_config_if_empty() -> None:
    with standalone_connection() as conn:
        for k, v in DEFAULT_CONFIG.items():
            conn.execute(
                """INSERT OR IGNORE INTO system_config(config_key, config_value)
                   VALUES (?, ?)""",
                (k, v),
            )


# ------------------------------------------------------------------ helpers
def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    return get_connection().execute(sql, tuple(params)).fetchone()


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return list(get_connection().execute(sql, tuple(params)).fetchall())


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    cur = get_connection().execute(sql, tuple(params))
    get_connection().commit()
    return cur


def execute_many(sql: str, seq_of_params: Iterable[Iterable[Any]]) -> None:
    conn = get_connection()
    conn.executemany(sql, [tuple(p) for p in seq_of_params])
    conn.commit()


def audit(user: str, action: str, table: str, record_id: str,
          old: Any = None, new: Any = None, ip: str | None = None) -> None:
    execute(
        """INSERT INTO audit_log(user_name, action, table_name, record_id,
                                  old_values, new_values, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user, action, table, str(record_id),
         json.dumps(old, ensure_ascii=False) if old is not None else None,
         json.dumps(new, ensure_ascii=False) if new is not None else None,
         ip),
    )
