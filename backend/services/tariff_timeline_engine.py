"""
Tariff timeline engine — splits an LFHD consumption period across
schedule boundaries.

The LFHD `days` value represents a *historical* consumption window
ending on the inspection date.  When tariff schedules change inside
that window (e.g. a new FY starts on 1 April), the assessed amount
must use the rate that was in force during each segment, not whatever
rate is current today.

This module supplies two layers:

1. ``split_period(start, end, schedules)`` — pure list-of-segments
   splitter.  No database, no rate lookup.  Works on plain dicts so
   it is straightforward to unit-test.

2. ``build_timeline(conn, *, category, ...)`` — convenience wrapper
   that uses :mod:`backend.services.tariff_engine` to look up the
   applicable rate for each segment and, optionally, computes a
   proportional-units split for an LFHD total.

Safety contract
---------------
* No mutation of any DB row — purely read-only against
  ``tariff_schedules`` + ``tariff_rates``.
* Pure stdlib + ``backend.services.tariff_engine``.
* Returns plain dicts and primitives so the route layer can pass
  them straight into ``envelope_ok``.

The actual LFHD calculator (``backend/services/calculator.py``) is
NOT modified by this PR.  Wiring the timeline engine into the
calculator is a deliberate next step that the project owner can opt
into per-template.

Examples
--------
>>> from datetime import date
>>> schedules = [
...     {"id": 1, "schedule_name": "FY2024-25",
...      "effective_from": "2024-04-01", "effective_to": "2025-03-31"},
...     {"id": 2, "schedule_name": "FY2025-26",
...      "effective_from": "2025-04-01", "effective_to": "2026-03-31"},
... ]
>>> segs = split_period(date(2024, 8, 15), date(2025, 8, 15), schedules)
>>> [(s["from_date"], s["to_date"], s["days"], s["schedule_name"]) for s in segs]
[('2024-08-15', '2025-03-31', 229, 'FY2024-25'), ('2025-04-01', '2025-08-15', 137, 'FY2025-26')]
>>> sum(s["days"] for s in segs)
366
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any

from . import tariff_engine
from ..utils import parse_date

log = logging.getLogger(__name__)


__all__ = [
    "Segment",
    "split_period",
    "compute_period_from_lfhd",
    "build_timeline",
]


# ---------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------

def _to_date(v: Any) -> date | None:
    """Accept date | datetime | ISO yyyy-mm-dd | other parseable strings."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    iso = parse_date(v)
    if not iso:
        return None
    return datetime.strptime(iso, "%Y-%m-%d").date()


def _max(a: date | None, b: date | None) -> date | None:
    if a is None: return b
    if b is None: return a
    return max(a, b)


def _min(a: date | None, b: date | None) -> date | None:
    if a is None: return b
    if b is None: return a
    return min(a, b)


def _isofmt(d: date | None) -> str | None:
    return d.strftime("%Y-%m-%d") if d else None


# ---------------------------------------------------------------------
# Segment dataclass
# ---------------------------------------------------------------------

@dataclass
class Segment:
    from_date:    str
    to_date:      str
    days:         int                 # inclusive day count
    schedule_id:  int | None = None
    schedule_name: str | None = None
    rate:         dict[str, Any] | None = None
    units:        float | None = None
    proportion:   float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Pure splitter
# ---------------------------------------------------------------------

def _days_inclusive(a: date, b: date) -> int:
    """Inclusive day count: a..b counts as (b - a) + 1 days."""
    return (b - a).days + 1


def split_period(start: date | str,
                 end:   date | str,
                 schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split [start, end] into contiguous segments along schedule edges.

    Parameters
    ----------
    start, end
        Inclusive boundaries of the LFHD consumption window
        (start <= end).
    schedules
        List of schedule dicts with at minimum ``id``, ``schedule_name``,
        ``effective_from``, ``effective_to`` (the latter two may be
        None for open-ended schedules).  Order is irrelevant.

    Returns
    -------
    list[dict]
        Ordered, contiguous, non-overlapping segments covering
        ``[start, end]``.  Each segment is::

            {
              "from_date":     "yyyy-mm-dd",
              "to_date":       "yyyy-mm-dd",
              "days":          int,           # inclusive
              "schedule_id":   int | None,    # None if no schedule
                                              # covers this gap
              "schedule_name": str | None,
            }

        Coverage gaps (no active schedule for that date range) are
        emitted as segments with ``schedule_id`` = None so the route
        layer can warn the operator.
    """
    s = _to_date(start)
    e = _to_date(end)
    if s is None or e is None:
        return []
    if s > e:
        s, e = e, s

    # Build a list of edge dates: window endpoints + every schedule's
    # start day + (end day + 1).  We then walk these in order.
    edges: set[date] = {s, e + timedelta(days=1)}
    for sch in schedules:
        f = _to_date(sch.get("effective_from"))
        t = _to_date(sch.get("effective_to"))
        if f is not None and s <= f <= e + timedelta(days=1):
            edges.add(f)
        if t is not None and s <= (t + timedelta(days=1)) <= e + timedelta(days=1):
            edges.add(t + timedelta(days=1))
    edge_list = sorted(edges)

    segments: list[dict[str, Any]] = []
    for i in range(len(edge_list) - 1):
        seg_start = edge_list[i]
        seg_end   = edge_list[i + 1] - timedelta(days=1)
        if seg_start > seg_end or seg_end < s or seg_start > e:
            continue

        # Pick the schedule whose window covers (seg_start..seg_end).
        # If multiple cover, prefer the most recently uploaded one.
        chosen: dict[str, Any] | None = None
        for sch in schedules:
            f = _to_date(sch.get("effective_from"))
            t = _to_date(sch.get("effective_to"))
            if (f is None or f <= seg_start) and (t is None or t >= seg_end):
                if chosen is None:
                    chosen = sch
                else:
                    # Prefer the schedule with the later effective_from
                    # (or higher id) — same heuristic as
                    # tariff_engine.find_applicable_rate.
                    cf = _to_date(chosen.get("effective_from"))
                    if (f is not None and (cf is None or f > cf)) or \
                       (f == cf and (sch.get("id") or 0) > (chosen.get("id") or 0)):
                        chosen = sch

        segments.append({
            "from_date":     _isofmt(seg_start),
            "to_date":       _isofmt(seg_end),
            "days":          _days_inclusive(seg_start, seg_end),
            "schedule_id":   chosen.get("id") if chosen else None,
            "schedule_name": chosen.get("schedule_name") if chosen else None,
        })

    return segments


# ---------------------------------------------------------------------
# LFHD start-date helper
# ---------------------------------------------------------------------

def compute_period_from_lfhd(inspection_date: date | str,
                             lfhd_days: int) -> tuple[str, str]:
    """Return ``(start_iso, end_iso)`` for an LFHD window.

    ``inspection_date`` is the END of the window (inclusive) and
    ``lfhd_days`` is the inclusive day count, so for an inspection on
    2025-08-15 with 365 days, the window starts 2024-08-16
    (NOT 2024-08-15) -- that gives exactly 365 days.

    Examples
    --------
    >>> compute_period_from_lfhd("2025-08-15", 365)
    ('2024-08-16', '2025-08-15')
    >>> compute_period_from_lfhd("2025-08-15", 1)
    ('2025-08-15', '2025-08-15')
    """
    end = _to_date(inspection_date)
    if end is None:
        raise ValueError(f"inspection_date must be parseable, got {inspection_date!r}")
    days = max(1, int(lfhd_days))
    start = end - timedelta(days=days - 1)
    return _isofmt(start), _isofmt(end)


# ---------------------------------------------------------------------
# Higher-level: build segments + pick rate per segment + split units
# ---------------------------------------------------------------------

def build_timeline(conn: sqlite3.Connection,
                   *,
                   category: str,
                   subcategory: str | None = None,
                   supply_type: str | None = None,
                   load_kw: float | None = None,
                   start_date: str | None = None,
                   end_date: str | None = None,
                   inspection_date: str | None = None,
                   lfhd_days: int | None = None,
                   total_units: float | None = None) -> dict[str, Any]:
    """Compute a tariff timeline for an LFHD assessment.

    Either ``(start_date, end_date)`` *or* ``(inspection_date, lfhd_days)``
    must be supplied; the latter is the typical operator entry path
    and gets converted via :func:`compute_period_from_lfhd`.

    Returns a dict::

        {
          "category":        "LMV-2",
          "subcategory":     "Urban ≤4KW",
          "supply_type":     "Commercial",
          "start_date":      "2024-08-16",
          "end_date":        "2025-08-15",
          "total_days":      365,
          "total_units":     2365.0,
          "segments": [
            {
              "from_date": "2024-08-16",
              "to_date":   "2025-03-31",
              "days":      228,
              "schedule_id":   1,
              "schedule_name": "FY2024-25",
              "rate":          { ...applicable tariff_rates row... },
              "units":         1478.16,
              "proportion":    0.625,
            },
            {
              "from_date": "2025-04-01",
              ...
            }
          ],
          "warnings": [
            "no_schedule_for_segment 2024-08-16 .. 2024-12-31",
            ...
          ]
        }
    """
    if start_date and end_date:
        sd, ed = parse_date(start_date), parse_date(end_date)
    elif inspection_date and lfhd_days:
        sd, ed = compute_period_from_lfhd(inspection_date, lfhd_days)
    else:
        raise ValueError(
            "Either (start_date, end_date) or (inspection_date, lfhd_days) "
            "must be supplied"
        )

    if not sd or not ed:
        raise ValueError("Could not parse the supplied dates")

    # Pull all active schedules — small list, fine to read once.
    schedules = [
        (dict(r) if not isinstance(r, dict) else r)
        for r in conn.execute(
            "SELECT id, schedule_name, effective_from, effective_to "
            "FROM tariff_schedules WHERE is_active = 1 "
            "ORDER BY effective_from"
        ).fetchall()
    ]

    raw_segments = split_period(sd, ed, schedules)
    total_days = sum(s["days"] for s in raw_segments)

    warnings: list[str] = []
    enriched: list[dict[str, Any]] = []
    for seg in raw_segments:
        sched_id = seg.get("schedule_id")
        rate = None
        if sched_id is None:
            warnings.append(
                f"no_schedule_for_segment {seg['from_date']}..{seg['to_date']}"
            )
        else:
            # Use the segment's own midpoint as the on_date so we always
            # land inside the chosen schedule.  This matters when more
            # than one schedule overlaps a segment (find_applicable_rate
            # would otherwise pick by effective_from order).
            mid = _midpoint(seg["from_date"], seg["to_date"])
            rate = tariff_engine.find_applicable_rate(
                conn,
                category=category,
                subcategory=subcategory,
                supply_type=supply_type,
                load_kw=load_kw,
                on_date=mid,
            )
            if rate is None or rate.get("schedule_id") != sched_id:
                # Either no matching tariff_rates row, or the lookup
                # picked a different schedule than the splitter chose.
                # Fall back to a strict per-schedule lookup.
                rate = _find_in_schedule(
                    conn, sched_id, category, subcategory,
                    supply_type=supply_type, load_kw=load_kw,
                )
                if rate is None:
                    warnings.append(
                        f"no_matching_rate {seg['from_date']}..{seg['to_date']} "
                        f"category={category!r} sub={subcategory!r}"
                    )

        proportion = (seg["days"] / total_days) if total_days else 0.0
        units = (round(total_units * proportion, 3)
                 if total_units is not None else None)

        enriched.append({
            **seg,
            "rate":       rate,
            "proportion": round(proportion, 6),
            "units":      units,
        })

    return {
        "category":     category,
        "subcategory":  subcategory,
        "supply_type":  supply_type,
        "load_kw":      load_kw,
        "start_date":   sd,
        "end_date":     ed,
        "total_days":   total_days,
        "total_units":  total_units,
        "segments":     enriched,
        "warnings":     warnings,
    }


def _midpoint(a: str, b: str) -> str:
    """ISO midpoint of two ISO dates (rounded down)."""
    da = _to_date(a); db = _to_date(b)
    if da is None or db is None:
        return a
    mid = da + timedelta(days=(db - da).days // 2)
    return _isofmt(mid)


def _find_in_schedule(conn: sqlite3.Connection,
                      schedule_id: int,
                      category: str,
                      subcategory: str | None = None,
                      *,
                      supply_type: str | None = None,
                      load_kw: float | None = None) -> dict | None:
    """Strict per-schedule lookup (used when find_applicable_rate's
    schedule choice diverges from the splitter's segment assignment)."""
    rows = [
        (dict(r) if not isinstance(r, dict) else r)
        for r in conn.execute(
            "SELECT * FROM tariff_rates WHERE schedule_id=? AND category=?",
            (schedule_id, category),
        ).fetchall()
    ]
    if not rows:
        return None

    from ..utils import normalize_text

    def match(r):
        if subcategory and r.get("subcategory") and \
           normalize_text(r["subcategory"]) != normalize_text(subcategory):
            return False
        if supply_type and r.get("supply_type") and \
           normalize_text(r["supply_type"]) != normalize_text(supply_type):
            return False
        if load_kw is not None:
            lf, lt = r.get("load_from"), r.get("load_to")
            if lf is not None and load_kw < lf - 1e-9: return False
            if lt is not None and load_kw > lt + 1e-9: return False
        return True

    matched = [r for r in rows if match(r)]
    if not matched:
        return None

    matched.sort(
        key=lambda r: (
            8 if r.get("subcategory") else 0,
            4 if r.get("supply_type") else 0,
            2 if r.get("load_from") is not None or r.get("load_to") is not None else 0,
        ),
        reverse=True,
    )
    return matched[0]
