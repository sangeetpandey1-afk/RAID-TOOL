"""
Tariff timeline split engine (PR2).

Purpose
-------
A raid case is assessed over a multi-month window (typically 365 days for
Section 135). Inside that window the published tariff may have changed
one or more times — different slab rates, different fixed charges, a new
duty %, a meter rent revision, etc. The legacy calculator (calculator.py)
applies a single rate set to the whole period; that's still used by the
existing UI and notice templates and is preserved untouched.

This module is a NEW, ADDITIVE surface that:

  1. Takes a usage period [start, end] and the LFHD usage for the case.
  2. Reads tariff_rates rows (the PR1-introduced timeline schedule).
  3. Splits the period at every effective-date boundary that falls inside
     [start, end] for the matching (category, condition_load) rows.
  4. For each resulting segment, picks the rate-row set active at the
     segment's midpoint and computes per-segment:
       * pro-rated units  (yearly_units * segment_days / total_days)
       * monthly units    (segment_units / segment_months)
       * slab-wise energy charges
       * fixed charges    (fixed_charge * segment_months)
       * meter rent       (meter_rent * segment_months)
       * rebate           (-rebate per slab applied to subtotal)
       * electricity duty (duty_percent on energy subtotal)
       * multiplier       (applied to energy + fixed, NOT to ED)
  5. Aggregates segments into a final detailed breakup.

Public API
----------
* split_period_by_tariff(category, period_start, period_end,
                          condition_load=None, conn=None) -> list[Segment]
* segment_units(yearly_units, period_start, period_end, segment) -> dict
* compute_segment(segment, monthly_units, multiplier, ...) -> dict
* calculate_timeline(payload) -> dict  (top-level entry point)

Compatibility
-------------
* Does NOT touch calculator.py / compounding.py / matcher.py / doc_generator.
* Does NOT modify any HTTP route — those are added by routes/rates.py.
* Does NOT depend on flask. Standalone-callable for tests.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Optional

from . import tariff_engine as te
from .tariff_engine import _conn_ctx, _coerce_date, _coerce_float, _to_iso

log = logging.getLogger(__name__)


# =====================================================================
# Date helpers (work with ISO yyyy-mm-dd strings end-to-end)
# =====================================================================
def _parse_iso(d: Any) -> Optional[date]:
    iso = _to_iso(d)
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return None


def _max_date(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the later of two ISO dates; None means -infinity (so other wins)."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _min_date(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the earlier of two ISO dates; None means +infinity (so other wins)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _days_inclusive(start: str, end: str) -> int:
    """Inclusive day count between two ISO yyyy-mm-dd dates."""
    s = _parse_iso(start)
    e = _parse_iso(end)
    if not s or not e:
        return 0
    return max(0, (e - s).days + 1)


def _midpoint_iso(start: str, end: str) -> str:
    s = _parse_iso(start)
    e = _parse_iso(end)
    if not s or not e:
        return start
    mid = s + timedelta(days=(e - s).days // 2)
    return mid.isoformat()


# =====================================================================
# 1. Period splitter
# =====================================================================
def split_period_by_tariff(category: str,
                           period_start: Any,
                           period_end: Any,
                           condition_load: Optional[str] = None,
                           conn: Optional[sqlite3.Connection] = None
                           ) -> list[dict]:
    """
    Split [period_start, period_end] at every relevant tariff boundary.

    A "boundary" is an effective_from / effective_to date of any active
    tariff_rates row that:
      * has matching category
      * has compatible condition_load (NULL acts as wildcard, like overlap rule)
      * its own date window intersects [period_start, period_end]

    Returns a list of segments, each:
        {"from": "yyyy-mm-dd", "to": "yyyy-mm-dd", "days": N}
    The segments are contiguous, non-overlapping, and cover the whole
    period (gaps where no tariff applies are still included so the
    operator sees "no rate found" and not silent under-charging).
    """
    p_start = _to_iso(period_start)
    p_end = _to_iso(period_end)
    if not p_start or not p_end or p_start > p_end:
        return []

    a_cl = (str(condition_load).strip().lower()
            if condition_load and str(condition_load).strip() else None)

    with _conn_ctx(conn) as c:
        prev = c.row_factory
        c.row_factory = te._dict_factory
        try:
            rows = c.execute(
                "SELECT * FROM tariff_rates WHERE category = ?",
                (category,),
            ).fetchall()
        finally:
            c.row_factory = prev

    # Filter: active + condition_load compatible + date window intersects period
    boundaries: set[str] = {p_start, p_end}
    for r in rows:
        status = (r.get("status") or "active").strip().lower()
        if status != "active":
            continue
        b_cl_raw = r.get("condition_load")
        b_cl = (str(b_cl_raw).strip().lower()
                if b_cl_raw is not None and str(b_cl_raw).strip() else None)
        if a_cl is not None and b_cl is not None and a_cl != b_cl:
            continue
        eff_from = r.get("effective_from") or r.get("schedule_effective_from")
        eff_to = r.get("effective_to") or r.get("schedule_effective_to")
        # Skip rows whose own window is entirely outside the period
        if eff_to is not None and eff_to < p_start:
            continue
        if eff_from is not None and eff_from > p_end:
            continue
        # Add interior boundaries (clamped to period)
        if eff_from and p_start < eff_from <= p_end:
            boundaries.add(eff_from)
        # effective_to is the LAST day this rate applies — the next segment
        # starts on (effective_to + 1).
        if eff_to and p_start <= eff_to < p_end:
            d = _parse_iso(eff_to)
            if d:
                next_day = (d + timedelta(days=1)).isoformat()
                if p_start < next_day <= p_end:
                    boundaries.add(next_day)

    sorted_b = sorted(boundaries)
    segments: list[dict] = []
    for i in range(len(sorted_b) - 1):
        seg_from = sorted_b[i]
        # The segment ENDS on the day before the next boundary.
        next_d = _parse_iso(sorted_b[i + 1])
        if not next_d:
            continue
        seg_to = (next_d - timedelta(days=1)).isoformat()
        if seg_from > seg_to:
            continue
        segments.append({
            "from": seg_from,
            "to": seg_to,
            "days": _days_inclusive(seg_from, seg_to),
        })
    # If the last boundary is the period_end itself, include the boundary day
    # in the final segment (otherwise we'd lose 1 day at the tail).
    if segments and segments[-1]["to"] < p_end:
        segments[-1]["to"] = p_end
        segments[-1]["days"] = _days_inclusive(
            segments[-1]["from"], segments[-1]["to"])
    return segments


# =====================================================================
# 2. Slab-wise energy calc per segment
# =====================================================================
def _slabs_for_segment(category: str,
                       segment: dict,
                       condition_load: Optional[str],
                       conn: Optional[sqlite3.Connection]) -> list[dict]:
    """
    Return the active slab rows for the segment's midpoint, sorted by
    slab_start. NULL slab_end is treated as +infinity in callers.
    """
    midpoint = _midpoint_iso(segment["from"], segment["to"])
    a_cl = (str(condition_load).strip().lower()
            if condition_load and str(condition_load).strip() else None)
    with _conn_ctx(conn) as c:
        prev = c.row_factory
        c.row_factory = te._dict_factory
        try:
            rows = c.execute(
                "SELECT * FROM tariff_rates WHERE category = ?",
                (category,),
            ).fetchall()
        finally:
            c.row_factory = prev
    eligible: list[dict] = []
    for r in rows:
        status = (r.get("status") or "active").strip().lower()
        if status != "active":
            continue
        b_cl_raw = r.get("condition_load")
        b_cl = (str(b_cl_raw).strip().lower()
                if b_cl_raw is not None and str(b_cl_raw).strip() else None)
        if a_cl is not None and b_cl is not None and a_cl != b_cl:
            continue
        eff_from = r.get("effective_from") or r.get("schedule_effective_from")
        eff_to = r.get("effective_to") or r.get("schedule_effective_to")
        if eff_from and midpoint < eff_from:
            continue
        if eff_to and midpoint > eff_to:
            continue
        eligible.append(dict(r))
    # Prefer rows that were per-row-dated (specificity beats schedule-only)
    eligible.sort(key=lambda r: (
        -te._specificity(r),
        int(r.get("slab_start") or 0),
    ))
    if not eligible:
        return []
    # Pick the per-row-dated set if present, else the schedule-level set
    has_per_row_dates = any(r.get("effective_from") or r.get("effective_to")
                            for r in eligible)
    if has_per_row_dates:
        eligible = [r for r in eligible
                    if r.get("effective_from") or r.get("effective_to")]
    eligible.sort(key=lambda r: int(r.get("slab_start") or 0))
    return eligible


def _apply_slabs(monthly_units: float, slabs: list[dict]) -> dict:
    """Distribute monthly_units across slabs, return per-slab amounts."""
    breakdown: list[dict] = []
    remaining = max(0.0, float(monthly_units))
    for s in slabs:
        start = int(s.get("slab_start") or 0)
        end_raw = s.get("slab_end")
        end = int(end_raw) if end_raw not in (None, "") else None
        rate = float(s.get("rate_per_unit") or 0)
        slab_capacity = (end - start + 1) if end is not None else float("inf")
        consumed = min(remaining, slab_capacity)
        if consumed <= 0:
            if remaining <= 0 and breakdown:
                break
            continue
        breakdown.append({
            "slab_start": start,
            "slab_end":   end,
            "slab_name":  s.get("slab_name") or None,
            "rate_per_unit": rate,
            "monthly_units": round(consumed, 4),
            "monthly_amount": round(consumed * rate, 4),
        })
        remaining -= consumed
        if remaining <= 0:
            break
    monthly_subtotal = round(sum(b["monthly_amount"] for b in breakdown), 4)
    return {"slabs": breakdown, "monthly_subtotal": monthly_subtotal}


def compute_segment(segment: dict,
                    yearly_units: float,
                    total_period_days: int,
                    category: str,
                    multiplier: float,
                    condition_load: Optional[str] = None,
                    fixed_rate_override: Optional[float] = None,
                    duty_percent_override: Optional[float] = None,
                    conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Compute the full assessment breakup for a single segment.

    yearly_units      — total LFHD-derived units for the WHOLE period
    total_period_days — total days of the WHOLE period (for pro-rating)
    multiplier        — first-offense (2x) / repeat (6x), applied to
                        energy + fixed; NEVER to ED, meter rent, or rebate.
    """
    seg_days = int(segment.get("days") or 0)
    seg_months = round(seg_days / 30.0, 4) if seg_days else 0.0

    # Pro-rate units to this segment
    if total_period_days > 0:
        seg_units = round(yearly_units * seg_days / total_period_days, 4)
    else:
        seg_units = 0.0
    monthly_units = round(seg_units / seg_months, 4) if seg_months else 0.0

    slabs = _slabs_for_segment(category, segment, condition_load, conn)
    if not slabs:
        # No rate row covers this segment — surface as a warning in the
        # output but emit a zero-priced segment so totals remain coherent.
        return {
            "from": segment["from"],
            "to": segment["to"],
            "days": seg_days,
            "months": seg_months,
            "units_segment": seg_units,
            "monthly_units": monthly_units,
            "rate_row_id": None,
            "schedule_name": None,
            "condition_load": condition_load,
            "slabs": [],
            "fixed_charge": {"rate": 0, "months": seg_months,
                             "base": 0, "multiplier": multiplier, "final": 0},
            "energy_charge": {"monthly_subtotal": 0, "subtotal": 0,
                              "multiplier": multiplier, "final": 0},
            "electricity_duty": {"base": 0, "percent": 0, "amount": 0},
            "meter_rent": {"rate": 0, "months": seg_months, "amount": 0},
            "rebate":     {"rate": 0, "months": seg_months, "amount": 0},
            "segment_total": 0.0,
            "warning": f"No active tariff_rates row matched ({category}, "
                       f"{condition_load or 'any'}, {segment['from']})",
        }

    # First slab provides per-row metadata (fixed_charge etc. repeat across slabs)
    primary = slabs[0]
    fixed_rate = (float(fixed_rate_override)
                  if fixed_rate_override is not None
                  else float(primary.get("fixed_charge") or 0))
    duty_percent = (float(duty_percent_override)
                    if duty_percent_override is not None
                    else float(primary.get("duty_percent") or 0))
    meter_rent_rate = float(primary.get("meter_rent") or 0)
    rebate_rate = float(primary.get("rebate") or 0)

    # ----- Energy
    monthly_block = _apply_slabs(monthly_units, slabs)
    energy_subtotal = round(monthly_block["monthly_subtotal"] * seg_months, 4)
    energy_final = round(energy_subtotal * multiplier, 2)
    # Scale slab amounts to segment-level
    slab_breakdown = []
    for s in monthly_block["slabs"]:
        seg_amount = round(s["monthly_amount"] * seg_months, 4)
        slab_breakdown.append({
            **s,
            "segment_units":  round(s["monthly_units"] * seg_months, 4),
            "segment_amount": seg_amount,
            "final_amount":   round(seg_amount * multiplier, 2),
        })

    # ----- Fixed
    fixed_base = round(seg_months * fixed_rate, 4)  # caller multiplies by load
    # NOTE: We return per-month "rate" + "months" separately so the route
    # layer can multiply by connected_load_kw. Storing connected load in
    # the segment itself would couple this engine to load, which we want
    # to keep optional. The aggregator at calculate_timeline() does the
    # multiplication once.

    # ----- Duty
    duty_amount = round(energy_subtotal * duty_percent / 100.0, 2)

    # ----- Meter rent + rebate (scale by months, not by multiplier)
    meter_rent_amount = round(meter_rent_rate * seg_months, 2)
    rebate_amount = round(rebate_rate * seg_months, 2)

    return {
        "from": segment["from"],
        "to": segment["to"],
        "days": seg_days,
        "months": seg_months,
        "units_segment": seg_units,
        "monthly_units": monthly_units,
        "rate_row_id":   primary.get("id"),
        "schedule_name": primary.get("schedule_name"),
        "condition_load": primary.get("condition_load") or condition_load,
        "slabs": slab_breakdown,
        "fixed_charge": {
            "rate":      fixed_rate,
            "months":    seg_months,
            "base":      fixed_base,
            "multiplier": multiplier,
            "final":     None,   # filled in at aggregate step (needs load_kw)
        },
        "energy_charge": {
            "monthly_subtotal": monthly_block["monthly_subtotal"],
            "subtotal":         energy_subtotal,
            "multiplier":       multiplier,
            "final":            energy_final,
        },
        "electricity_duty": {
            "base":    energy_subtotal,
            "percent": duty_percent,
            "amount":  duty_amount,
        },
        "meter_rent": {
            "rate":   meter_rent_rate,
            "months": seg_months,
            "amount": meter_rent_amount,
        },
        "rebate": {
            "rate":   rebate_rate,
            "months": seg_months,
            "amount": rebate_amount,
        },
        "warning": None,
    }


# =====================================================================
# 3. Top-level: calculate_timeline
# =====================================================================
def calculate_timeline(payload: dict,
                       conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Inputs (dict — same shape as calculator.calculate_assessment, with
    the additional `condition_load` field):

        {
            "category":           "LMV-1",
            "condition_load":     "domestic" (optional),
            "inspection_date":    "2026-05-01",   (period END, default today)
            "period_start":       "2025-05-02",   (optional, default = end - days)
            "days":               365,            (used if period_start absent)
            "connected_load_kw":  2.122,
            "yearly_units":       1408.9,         (total LFHD units for period)
            "multiplier":         2,
            "less_unit":          0,              (subtracted from yearly_units)
            "fixed_rate_override":   None,
            "duty_percent_override": None,
        }

    Returns:
        {
            "ok": True,
            "category": ..., "condition_load": ...,
            "period": {"from","to","days","months"},
            "segments": [ ... per-segment breakdowns ... ],
            "totals": {
                "units":          ...,
                "fixed_charges":  {"base","multiplier","final"},
                "energy_charges": {"subtotal","multiplier","final"},
                "electricity_duty": {"amount"},
                "meter_rent":     {"amount"},
                "rebate":         {"amount"},
                "grand_total":    ...,
            },
            "warnings": [...],
        }
    """
    warnings: list[str] = []
    category = payload.get("category") or ""
    if not category:
        return {"ok": False, "error": "category is required", "segments": []}

    # Resolve period
    end_iso = _to_iso(payload.get("inspection_date")) or date.today().isoformat()
    start_iso = _to_iso(payload.get("period_start"))
    days = int(payload.get("days") or 365)
    if not start_iso:
        end_d = _parse_iso(end_iso) or date.today()
        start_d = end_d - timedelta(days=max(1, days) - 1)
        start_iso = start_d.isoformat()
    total_days = _days_inclusive(start_iso, end_iso)
    total_months = round(total_days / 30.0, 4)

    yearly_units = float(payload.get("yearly_units") or 0.0)
    less_unit = float(payload.get("less_unit") or 0.0)
    if less_unit < 0:
        warnings.append("Negative less_unit ignored.")
        less_unit = 0.0
    yearly_units = max(0.0, yearly_units - less_unit)

    multiplier = float(payload.get("multiplier") or 2.0)
    connected_load_kw = float(payload.get("connected_load_kw") or 0.0)
    condition_load = payload.get("condition_load")
    fixed_override = payload.get("fixed_rate_override")
    duty_override = payload.get("duty_percent_override")

    # Build segments
    segments_raw = split_period_by_tariff(
        category, start_iso, end_iso,
        condition_load=condition_load, conn=conn,
    )
    if not segments_raw:
        warnings.append("Period contained no tariff boundaries.")
        segments_raw = [{"from": start_iso, "to": end_iso,
                         "days": total_days}]

    segs: list[dict] = []
    total_fixed_base = 0.0
    total_energy_subtotal = 0.0
    total_duty = 0.0
    total_meter = 0.0
    total_rebate = 0.0

    for raw in segments_raw:
        s = compute_segment(
            raw, yearly_units=yearly_units,
            total_period_days=total_days,
            category=category, multiplier=multiplier,
            condition_load=condition_load,
            fixed_rate_override=fixed_override,
            duty_percent_override=duty_override,
            conn=conn,
        )
        # Apply connected_load_kw to fixed_charge.final  (rate * months * load)
        fc = s["fixed_charge"]
        fc_base_with_load = round(fc["base"] * connected_load_kw, 4)
        fc_final = round(fc_base_with_load * multiplier, 2)
        s["fixed_charge"]["base"] = fc_base_with_load
        s["fixed_charge"]["final"] = fc_final
        s["fixed_charge"]["connected_load_kw"] = connected_load_kw

        seg_total = round(
            (s["fixed_charge"]["final"] or 0)
            + (s["energy_charge"]["final"] or 0)
            + (s["electricity_duty"]["amount"] or 0)
            + (s["meter_rent"]["amount"] or 0)
            - (s["rebate"]["amount"] or 0),
            2,
        )
        s["segment_total"] = seg_total
        if s.get("warning"):
            warnings.append(s["warning"])

        total_fixed_base += fc_base_with_load
        total_energy_subtotal += s["energy_charge"]["subtotal"] or 0
        total_duty += s["electricity_duty"]["amount"] or 0
        total_meter += s["meter_rent"]["amount"] or 0
        total_rebate += s["rebate"]["amount"] or 0
        segs.append(s)

    fixed_final = round(total_fixed_base * multiplier, 2)
    energy_final = round(total_energy_subtotal * multiplier, 2)
    grand_total = round(
        fixed_final + energy_final + total_duty
        + total_meter - total_rebate,
        2,
    )

    return {
        "ok": True,
        "category": category,
        "condition_load": condition_load,
        "period": {
            "from":   start_iso,
            "to":     end_iso,
            "days":   total_days,
            "months": total_months,
        },
        "input": {
            "yearly_units_after_less_unit": yearly_units,
            "less_unit": less_unit,
            "multiplier": multiplier,
            "connected_load_kw": connected_load_kw,
        },
        "segments": segs,
        "totals": {
            "units":           round(yearly_units, 4),
            "fixed_charges":   {"base": round(total_fixed_base, 4),
                                "multiplier": multiplier,
                                "final": fixed_final},
            "energy_charges":  {"subtotal": round(total_energy_subtotal, 4),
                                "multiplier": multiplier,
                                "final": energy_final},
            "electricity_duty": {"amount": round(total_duty, 2)},
            "meter_rent":       {"amount": round(total_meter, 2)},
            "rebate":           {"amount": round(total_rebate, 2)},
            "grand_total":      grand_total,
        },
        "warnings": warnings,
    }


# =====================================================================
# 4. LFHD bridge — units-from-devices helper (additive, optional)
# =====================================================================
def yearly_units_from_devices(devices: list[dict], days: int = 365) -> float:
    """
    Sum LFHD units across a list of device dicts for the given total days.

    Each device's effective day count defaults to `days` if the device
    doesn't specify its own.
    """
    total = 0.0
    for d in devices or []:
        L = float(d.get("load") or d.get("L") or 0)
        F = float(d.get("factor") or d.get("F") or 1.0)
        H = float(d.get("hours") or d.get("H") or 0)
        D = float(d.get("days") or d.get("D") or days)
        total += (L * F * H * D) / 1000.0
    return round(total, 4)
