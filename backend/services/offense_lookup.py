"""
Account-number-only offense lookup (PR4).

Purpose
-------
PR4 introduces an Offense Verification card on the New Case form that
shows the operator every prior raid recorded for the typed account
number. The look-up is intentionally:

  * ACCOUNT-NUMBER-ONLY      — never matches on name / father / village
  * INDEXED                  — uses the legacy `idx_hist_account` plus
                                PR2's new `idx_hist_new_account` and
                                `idx_hist_old_account`
  * FAST                     — no joins, no Python-side scanning, no
                                rapidfuzz, no pandas

Why a NEW module instead of extending matcher.py?
-------------------------------------------------
`services/matcher.py` is the legacy multi-level offense-history engine
(account → SC → mapping → fuzzy name+father+village). It does much more
than account-number lookup, depends on `rapidfuzz`, and is consumed by
existing routes. PR4 must NEVER fall back to fuzzy name matching, so we
keep matcher.py completely untouched and add a dedicated module here.

Consumers of this module:
  * backend/routes/offense.py   (PR4 HTTP layer)
  * frontend/static/offense_verify.js   (PR4 UI)

Returns the 15 historical-row fields PR4 must display:
    notice_no, div_no, case_date, name, father_name,
    use_name, user_father_name, address, sub_substation,
    assessment_amount, old_account_id, new_account_id, account_id,
    category, irregularity, paid_status

(Plus a summary block: matched_count, first/last offense date,
total_assessment, is_repeat, suggested_multiplier.)
"""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional

log = logging.getLogger(__name__)

# Default multipliers — overridden by system_config rows when present.
_DEFAULT_FIRST  = 2.0
_DEFAULT_REPEAT = 6.0
# Threshold: TOTAL offense count (prior + current) at which we switch
# from first → repeat multiplier. Spec says "≥ 2 cases triggers repeat",
# so a single prior offense + the new case = 2 total → repeat.
_DEFAULT_THRESHOLD = 2


# =====================================================================
# Account normalization (kept private to this module — does NOT reuse
# utils.normalize_account so we stay free of the flask request-cycle
# import in case offense_lookup is called from a CLI script).
# =====================================================================
def _normalize_account(v: Any) -> str:
    """Strip non-alphanumeric, uppercase. Empty string for None / blank."""
    if v is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(v)).upper()


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def _conn_ctx(conn: Optional[sqlite3.Connection] = None
              ) -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection. Standalone fallback when conn=None."""
    if conn is not None:
        yield conn
        return
    from ..config import DB_PATH
    own = sqlite3.connect(str(DB_PATH), timeout=30.0)
    own.row_factory = _dict_factory
    try:
        yield own
    finally:
        own.close()


# =====================================================================
# Multiplier resolution from system_config (with sensible fallbacks)
# =====================================================================
def _read_multiplier_config(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT config_key, config_value FROM system_config "
        "WHERE config_key IN ('multiplier_first_offense', "
        "                      'multiplier_repeat_offense', "
        "                      'repeat_offense_threshold')"
    ).fetchall()
    cfg: dict[str, Any] = {}
    for r in rows:
        cfg[r["config_key"]] = r["config_value"]

    def _f(k: str, default: float) -> float:
        try:
            return float(cfg.get(k, default))
        except (TypeError, ValueError):
            return default

    def _i(k: str, default: int) -> int:
        try:
            return int(float(cfg.get(k, default)))
        except (TypeError, ValueError):
            return default

    return {
        "multiplier_first_offense":  _f("multiplier_first_offense",  _DEFAULT_FIRST),
        "multiplier_repeat_offense": _f("multiplier_repeat_offense", _DEFAULT_REPEAT),
        "repeat_offense_threshold":  _i("repeat_offense_threshold",  _DEFAULT_THRESHOLD),
    }


def suggested_multiplier(matched_count: int,
                         cfg: Optional[dict] = None) -> float:
    """
    Suggested multiplier for the NEW case given prior-offense count.

    matched_count = number of prior offenses found in historical_cases
                    (i.e. lookup_by_account().matched_count).
    Total offense count = matched_count + 1 (the current case).
    If total >= threshold ⇒ repeat multiplier; else first.
    """
    cfg = cfg or {}
    threshold = int(cfg.get("repeat_offense_threshold", _DEFAULT_THRESHOLD))
    first  = float(cfg.get("multiplier_first_offense",  _DEFAULT_FIRST))
    repeat = float(cfg.get("multiplier_repeat_offense", _DEFAULT_REPEAT))
    total = int(matched_count) + 1
    return repeat if total >= threshold else first


# =====================================================================
# The lookup
# =====================================================================
# All 15 PR4 display fields + the legacy account_id are returned per row.
_LOOKUP_SQL = """
SELECT
    id,
    notice_no,
    div_no,
    case_date,
    name,
    father_name,
    use_name,
    user_father_name,
    address,
    village,
    sub_substation,
    assessment_amount,
    old_account_id,
    new_account_id,
    account_id,
    category,
    irregularity,
    paid_status,
    fir_number,
    section,
    source,
    imported_at
FROM historical_cases
WHERE account_id     = ?
   OR new_account_id = ?
   OR old_account_id = ?
ORDER BY
    -- nulls last on the date so newest dated rows surface first
    CASE WHEN case_date IS NULL OR case_date = '' THEN 1 ELSE 0 END,
    case_date DESC,
    id DESC
""".strip()


def lookup_by_account(account: Any,
                      conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Indexed historical-offense lookup by account number.

    Strict invariants
    -----------------
    * Single SQL statement, parameterized.
    * Three OR-equality clauses against three indexed columns
      (idx_hist_account, idx_hist_new_account, idx_hist_old_account).
    * NEVER reads or compares name / father / village.
    * Returns an empty `rows` list when account is blank — never errors.

    Returns
    -------
        {
            "account":               normalized account string,
            "matched_count":         len(rows),
            "rows":                  list of dicts (15 PR4 fields + extras),
            "first_offense_date":    earliest non-null case_date (str | None),
            "last_offense_date":     latest non-null case_date  (str | None),
            "total_assessment":      sum of assessment_amount (float),
            "is_repeat":             matched_count >= 1 (any prior = repeat),
            "suggested_multiplier":  config-driven (2× / 6×),
            "config": {              echoed for transparency
                "multiplier_first_offense":  2.0,
                "multiplier_repeat_offense": 6.0,
                "repeat_offense_threshold":  2,
            },
        }
    """
    acct = _normalize_account(account)
    if not acct:
        return {
            "account": "",
            "matched_count": 0,
            "rows": [],
            "first_offense_date": None,
            "last_offense_date":  None,
            "total_assessment":   0.0,
            "is_repeat":          False,
            "suggested_multiplier": _DEFAULT_FIRST,
            "config": {
                "multiplier_first_offense":  _DEFAULT_FIRST,
                "multiplier_repeat_offense": _DEFAULT_REPEAT,
                "repeat_offense_threshold":  _DEFAULT_THRESHOLD,
            },
        }

    with _conn_ctx(conn) as c:
        prev_factory = c.row_factory
        c.row_factory = _dict_factory
        try:
            rows = c.execute(_LOOKUP_SQL, (acct, acct, acct)).fetchall()
            cfg  = _read_multiplier_config(c)
        finally:
            c.row_factory = prev_factory

    rows = [dict(r) for r in rows]

    # Aggregates
    dates = sorted([r["case_date"] for r in rows
                    if r.get("case_date")])
    total_amt = 0.0
    for r in rows:
        v = r.get("assessment_amount")
        try:
            if v is not None:
                total_amt += float(v)
        except (TypeError, ValueError):
            continue

    matched_count = len(rows)
    return {
        "account":              acct,
        "matched_count":        matched_count,
        "rows":                 rows,
        "first_offense_date":   dates[0]  if dates else None,
        "last_offense_date":    dates[-1] if dates else None,
        "total_assessment":     round(total_amt, 2),
        "is_repeat":            matched_count >= 1,
        "suggested_multiplier": suggested_multiplier(matched_count, cfg),
        "config":               cfg,
    }


# =====================================================================
# EXPLAIN QUERY PLAN — used by tests + diagnostics to prove indexes are hit
# =====================================================================
def explain_lookup_plan(account: Any = "DUMMY",
                        conn: Optional[sqlite3.Connection] = None
                        ) -> list[dict]:
    """Return the SQLite query plan rows for the lookup query.

    Each row has at minimum {id, parent, notused, detail}. The 'detail'
    field will mention the index name when SQLite uses the index.
    """
    acct = _normalize_account(account) or "_"
    with _conn_ctx(conn) as c:
        prev = c.row_factory
        c.row_factory = _dict_factory
        try:
            rows = c.execute(
                "EXPLAIN QUERY PLAN " + _LOOKUP_SQL, (acct, acct, acct)
            ).fetchall()
        finally:
            c.row_factory = prev
    return [dict(r) for r in rows]
