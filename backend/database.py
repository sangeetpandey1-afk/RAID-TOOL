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
    _run_tariff_rate_migrations()
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

    # PR2 — historical_cases extensions for richer offense-history preview.
    # All nullable / additive. Older rows just get NULL.
    ("historical_cases", "notice_no",         "TEXT"),
    ("historical_cases", "address",           "TEXT"),
    ("historical_cases", "use_name",          "TEXT"),
    ("historical_cases", "user_father_name",  "TEXT"),
    ("historical_cases", "sub_substation",    "TEXT"),
    ("historical_cases", "old_account_id",    "TEXT"),
    ("historical_cases", "new_account_id",    "TEXT"),
    ("historical_cases", "category",          "TEXT"),
    ("historical_cases", "irregularity",      "TEXT"),
    ("historical_cases", "paid_status",       "TEXT"),
]

_LIGHTWEIGHT_INDEX_ADDS: list[tuple[str, str]] = [
    # (index_name, create_sql)
    ("idx_case_check_report",
     "CREATE INDEX IF NOT EXISTS idx_case_check_report "
     "ON raid_cases(checking_report_number)"),

    # PR2 — fast indexed lookup for offense verification (PR4 consumer).
    # historical_cases.account_id already has idx_hist_account from
    # schema.sql; these add the new account-id columns introduced above.
    ("idx_hist_old_account",
     "CREATE INDEX IF NOT EXISTS idx_hist_old_account "
     "ON historical_cases(old_account_id)"),
    ("idx_hist_new_account",
     "CREATE INDEX IF NOT EXISTS idx_hist_new_account "
     "ON historical_cases(new_account_id)"),
    ("idx_hist_notice_no",
     "CREATE INDEX IF NOT EXISTS idx_hist_notice_no "
     "ON historical_cases(notice_no)"),
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


# ----------------------------------------------------- tariff_rates migrations
# tariff_rates table — timeline-aware rate schedule.
# Idempotent + additive: safe to run repeatedly.
#
# HOTFIX (post-PR4): an earlier deployment created a partial tariff_rates
# table (e.g. via the old mixed branch) that was missing slab_start /
# rate_per_unit / etc. CREATE TABLE IF NOT EXISTS is a no-op on those
# DBs, so the original "ALTER ADD COLUMN for the 6 PR1 extensions only"
# migration silently left base columns missing — which then caused
# Excel uploads to fail with "table tariff_rates has no column named
# slab_start".
#
# This migration now verifies EVERY expected column individually via
# PRAGMA table_info and ADDs any that's missing. Safe on:
#   * fresh DBs                 — CREATE TABLE creates everything
#   * partial pre-existing DBs  — ALTER ADD COLUMN fills the gaps
#   * already-fully-migrated DBs — every check is a no-op
# NEVER drops, NEVER recreates, NEVER destroys uploaded data.
_TARIFF_RATES_BASE_DDL = """
CREATE TABLE IF NOT EXISTS tariff_rates (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    category                 TEXT,
    slab_start               INTEGER,
    slab_end                 INTEGER,
    rate_per_unit            REAL,
    rate                     REAL,
    fixed_charge             REAL,
    duty_percent             REAL,
    condition                TEXT,
    condition_load           TEXT,
    subcategory              TEXT,
    slab_name                TEXT,
    meter_rent               REAL,
    rebate                   REAL,
    schedule_name            TEXT,
    schedule_effective_from  TEXT,
    schedule_effective_to    TEXT,
    effective_from           TEXT,
    effective_to             TEXT,
    status                   TEXT DEFAULT 'active',
    source                   TEXT,
    source_file              TEXT,
    notes                    TEXT,
    created_at               TEXT DEFAULT (datetime('now')),
    updated_at               TEXT DEFAULT (datetime('now'))
)
"""

# Full superset of every column tariff_rates is expected to have, across
# every code path that ever touches it:
#
#   * the original PR1 schema (rate_per_unit, condition, slab_name,
#     schedule_effective_from/to, source, ...) — kept because
#     services/tariff_engine.py reads/writes these names
#
#   * the user's hotfix-list aliases (subcategory, rate, source_file) —
#     reserved for forward compatibility / explicit operator request
#
# Each tuple is (column_name, alter_table_spec). The spec is what gets
# appended after "ALTER TABLE tariff_rates ADD COLUMN <name>". SQLite
# disallows NOT NULL on ALTER ADD COLUMN unless a DEFAULT is provided,
# so `category` here is plain TEXT — fresh CREATE-TABLE keeps it nullable
# too, since the import path drops blank rows via _is_blank_rate_row().
_TARIFF_RATES_REQUIRED_COLUMNS: tuple[tuple[str, str], ...] = (
    # --- columns that MUST exist for every code path ---
    ("category",                "TEXT"),
    ("schedule_name",           "TEXT"),
    ("subcategory",             "TEXT"),
    ("condition_load",          "TEXT"),
    ("condition",               "TEXT"),
    ("slab_name",               "TEXT"),
    ("slab_start",              "INTEGER"),
    ("slab_end",                "INTEGER"),
    ("rate",                    "REAL"),
    ("rate_per_unit",           "REAL"),
    ("fixed_charge",            "REAL"),
    ("duty_percent",            "REAL"),
    ("meter_rent",              "REAL"),
    ("rebate",                  "REAL"),
    ("effective_from",          "TEXT"),
    ("effective_to",            "TEXT"),
    ("schedule_effective_from", "TEXT"),
    ("schedule_effective_to",   "TEXT"),
    ("status",                  "TEXT DEFAULT 'active'"),
    ("source",                  "TEXT"),
    ("source_file",             "TEXT"),
    ("notes",                   "TEXT"),
    # NOTE: SQLite's ALTER TABLE ADD COLUMN forbids non-constant defaults
    # like (datetime('now')). The fresh CREATE TABLE above still uses
    # DEFAULT (datetime('now')) for these two; on migrated partial DBs
    # the columns are added as plain nullable TEXT — bookkeeping-only
    # fields, never read by business logic. Existing rows keep whatever
    # value they had; new rows get NULL unless the INSERT supplies one.
    ("created_at",              "TEXT"),
    ("updated_at",              "TEXT"),
)


def _run_tariff_rate_migrations() -> None:
    """Bring tariff_rates up to the FULL required column set.

    Step 1: CREATE TABLE IF NOT EXISTS — handles the fresh-DB path.
    Step 2: For EVERY column in _TARIFF_RATES_REQUIRED_COLUMNS, check
            PRAGMA table_info and ALTER ADD COLUMN if missing. This is
            the critical fix — pre-existing partial tariff_rates tables
            (where CREATE TABLE was a no-op) get all their missing
            columns filled in.
    Step 3: Ensure idx_tariff_rate_effective exists.
    Idempotent + additive. NEVER drops / recreates / destroys data.
    """
    with standalone_connection() as conn:
        # Step 1
        conn.execute(_TARIFF_RATES_BASE_DDL)
        # Step 2 — verify EVERY expected column individually
        existing = {r["name"] for r in
                    conn.execute("PRAGMA table_info(tariff_rates)").fetchall()}
        for col, alter_spec in _TARIFF_RATES_REQUIRED_COLUMNS:
            if col not in existing:
                conn.execute(
                    f"ALTER TABLE tariff_rates ADD COLUMN {col} {alter_spec}"
                )
                log.info("Migration: added tariff_rates.%s (%s)",
                         col, alter_spec)
        # Step 3
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tariff_rate_effective "
            "ON tariff_rates(effective_from, effective_to)"
        )


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
