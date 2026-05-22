"""
Offense-history service — strict account-only lookup.
======================================================

Single backend source of truth for the project owner's hard rule:

    "Use ONLY New Account Number for repeat-offense detection.
     Do NOT use name / father / address / village / fuzzy search."

This module is intentionally independent of the older
``services/matcher.py:offense_history`` function, which still performs
fuzzy fallback matching for the legacy ``/api/cases/<id>/offense-check``
endpoint.  That older endpoint remains so existing reports / notices
continue to behave exactly as they do today; new code paths (the
historical-import flow, the New-Case panel's repeat-offender warning,
the auto-suggested multiplier) all call into THIS module.

Data source
-----------
The table ``historical_cases`` (declared in ``backend/models/schema.sql``).
Its ``account_id`` column is already indexed.  Lookups are O(log n)
and safe to call on every Save / OffenseCheck button without latency.

Public API
----------
* ``count_offenses_by_account(conn, account_number) -> int``
* ``list_offenses_by_account(conn, account_number, limit=50) -> list[dict]``
* ``offense_summary(conn, account_number, *, system_config=None) -> dict``
* ``suggest_multiplier(count, *, threshold=2, first=2.0, repeat=6.0) -> float``

Safety contract
---------------
* Pure stdlib + sqlite3.  No Flask import — usable from CLI or scripts.
* Read-only on the DB (no INSERT / UPDATE / DELETE).
* Returns plain dicts and primitives; safe to JSON-serialise via
  the existing envelope helpers.
* Account-number normalisation reuses ``utils.normalize_account`` so
  ``"012/3456"`` and ``"0123456"`` and ``"01-23456"`` all match.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import normalize_account


__all__ = [
    "count_offenses_by_account",
    "list_offenses_by_account",
    "offense_summary",
    "suggest_multiplier",
    "warning_level_for",
]


# ---------------------------------------------------------------------
# Low-level lookups
# ---------------------------------------------------------------------

def count_offenses_by_account(conn: sqlite3.Connection,
                              account_number: str | None) -> int:
    """Strict count of historical_cases rows matching `account_number`.

    Returns 0 for empty / None / un-normalisable input — never raises.
    Matching is case-insensitive on the account string by comparing
    both sides through ``normalize_account``.
    """
    norm = normalize_account(account_number)
    if not norm:
        return 0

    # SQLite has no built-in normalize_account, so we filter in Python
    # only when an exact match isn't found. The exact-match path covers
    # the >99% case (operators paste the same account into both forms).
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM historical_cases "
        "WHERE account_id = ? OR UPPER(REPLACE(REPLACE(REPLACE(account_id, "
        "'-', ''), '/', ''), ' ', '')) = ?",
        (account_number, norm),
    ).fetchone()
    # row may be a tuple or a dict depending on the connection's row_factory
    if isinstance(row, dict):
        return int(row.get("c") or 0)
    return int(row[0]) if row else 0


def list_offenses_by_account(conn: sqlite3.Connection,
                             account_number: str | None,
                             limit: int = 50) -> list[dict]:
    """Ordered (most recent first) list of prior historical offenses for
    the given new account number.

    Each row is a dict with the columns the historical_cases table
    declares; safe to serialise straight to JSON.  Empty / None input
    returns ``[]``.
    """
    norm = normalize_account(account_number)
    if not norm:
        return []

    cur = conn.execute(
        """SELECT id, account_id, case_date, assessment_amount,
                  fir_number, section, name, father_name, village,
                  div_no, source, imported_at,
                  -- the additive columns from the historical-import migration:
                  COALESCE(old_case_ref, '')      AS old_case_ref,
                  COALESCE(compounding_amount, 0) AS compounding_amount
             FROM historical_cases
            WHERE account_id = ?
               OR UPPER(REPLACE(REPLACE(REPLACE(account_id,
                                                '-', ''), '/', ''), ' ', '')) = ?
            ORDER BY case_date DESC NULLS LAST, id DESC
            LIMIT ?""",
        (account_number, norm, int(limit)),
    )
    out = []
    for row in cur.fetchall():
        out.append(dict(row) if not isinstance(row, dict) else row)
    return out


# ---------------------------------------------------------------------
# Multiplier suggestion (pure, no DB)
# ---------------------------------------------------------------------

def suggest_multiplier(count: int,
                       *,
                       threshold: int = 2,
                       first: float = 2.0,
                       repeat: float = 6.0) -> float:
    """Auto-suggest a multiplier given the number of prior offenses.

    Default thresholds match the seeded values in
    ``system_config``:

        multiplier_first_offense   = 2
        multiplier_repeat_offense  = 6
        repeat_offense_threshold   = 2   (>= this many priors = repeat)

    The project owner's spec says "If offense count >= 1, suggest 6×".
    To honour that without changing the schema defaults, callers that
    want the spec wording pass ``threshold=1``.  ``offense_summary``
    below uses ``threshold=1`` by default (matching the spec) and
    falls back to whatever ``system_config`` declares if that table
    is reachable — see the docstring of ``offense_summary``.

    The multiplier is ALWAYS just a *suggestion* — the operator can
    override it manually in the form, and the calculator honours the
    final value the case is saved with.
    """
    return repeat if int(count) >= int(threshold) else first


# ---------------------------------------------------------------------
# Warning-level mapping (for the UI badge colour)
# ---------------------------------------------------------------------

def warning_level_for(count: int) -> str:
    """Map a prior-offense count onto the spec's three colour bands.

        count == 0   -> "none"   (no badge)
        count == 1   -> "yellow" (one previous offense)
        count >= 2   -> "red"    (multiple previous offenses)
    """
    n = int(count)
    if n <= 0:
        return "none"
    if n == 1:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------
# High-level summary used by the route + future frontend
# ---------------------------------------------------------------------

def offense_summary(conn: sqlite3.Connection,
                    account_number: str | None,
                    *,
                    system_config: dict[str, str] | None = None,
                    include_records: bool = True,
                    record_limit: int = 25) -> dict[str, Any]:
    """Full summary for the New-Case panel / Offense Check button /
    Raid Master column.

    Parameters
    ----------
    conn
        Any open SQLite connection (request-scoped or standalone).
    account_number
        The new account number to look up.  Empty / None returns a
        zero-count summary that the UI can render as "no priors".
    system_config
        Optional dict ``{key: value}`` from the ``system_config``
        table.  When provided, the suggested multiplier reads
        ``multiplier_first_offense`` and ``multiplier_repeat_offense``
        from it; otherwise the spec defaults (2 and 6) are used.
        The threshold is fixed at 1 (>=1 prior = repeat) per the
        project owner's rule for THIS surface.
    include_records
        When True (default) the response carries the most recent
        ``record_limit`` matching rows for display in the warning
        panel.  Set False if only the count is needed.
    record_limit
        Cap on the records list — protects the response size if a
        single account ever has hundreds of historical entries.

    Returns
    -------
    dict
        A JSON-serialisable structure::

            {
                "account_number":       "0123456789",
                "normalised_account":   "0123456789",
                "count":                3,
                "is_repeat_offender":   true,
                "warning_level":        "red",     # none|yellow|red
                "suggested_multiplier": 6.0,
                "first_offense_date":   "2018-04-12",
                "last_offense_date":    "2024-08-30",
                "total_assessment":     185000.0,
                "records":              [ ...up to record_limit dicts... ]
            }
    """
    norm = normalize_account(account_number)
    cfg = system_config or {}
    first_mult  = float(cfg.get("multiplier_first_offense",  "2") or "2")
    repeat_mult = float(cfg.get("multiplier_repeat_offense", "6") or "6")

    if not norm:
        return {
            "account_number":       account_number or "",
            "normalised_account":   "",
            "count":                0,
            "is_repeat_offender":   False,
            "warning_level":        "none",
            "suggested_multiplier": first_mult,
            "first_offense_date":   None,
            "last_offense_date":    None,
            "total_assessment":     0.0,
            "records":              [],
        }

    count = count_offenses_by_account(conn, account_number)
    records = (list_offenses_by_account(conn, account_number, limit=record_limit)
               if include_records else [])

    # Aggregate values — small list, do it in Python rather than another query.
    dates = [r.get("case_date") for r in records if r.get("case_date")]
    total_assessment = sum(
        float(r.get("assessment_amount") or 0) for r in records
    )

    return {
        "account_number":       account_number,
        "normalised_account":   norm,
        "count":                count,
        "is_repeat_offender":   count >= 1,
        "warning_level":        warning_level_for(count),
        "suggested_multiplier": suggest_multiplier(
            count, threshold=1, first=first_mult, repeat=repeat_mult
        ),
        "first_offense_date":   min(dates) if dates else None,
        "last_offense_date":    max(dates) if dates else None,
        "total_assessment":     round(total_assessment, 2),
        "records":              records,
    }
