"""
LFHD assessment calculator.

Inputs (Python dict, also matches the JSON body of /api/cases/<id>/calculate):
    {
        "section":           "135" | "138" | "126" | "Other",
        "td_date":           "yyyy-mm-dd"  (required if section == 138),
        "inspection_date":   "yyyy-mm-dd"  (defaults to today),
        "category":          "LMV-1" | "LMV-2 RURAL" | ...   (rate_master key),
        "connected_load_kw": 2.122,
        "devices": [
            {"name":"Bulb / LED","load":9,"factor":1,"hours":6,"days":365},
            ...
        ],
        "less_unit":  120,                  (optional yearly consumed units)
        "multiplier": 2,                    (default = system_config setting)
        "ed_percent": 5                     (overrides rate_master if given)
    }

Output:
    {
        "section": "135",
        "days": 365,
        "months": 12.0,
        "multiplier": 2.0,
        "less_unit": 0,
        "devices": [
            {"name":..., "L":9, "F":1, "H":6, "D":365, "units": 19.71}, ...
        ],
        "total_units_calculated": 1408.9,
        "total_units_after_less_unit": 1408.9,
        "monthly_units":  117.4,
        "fixed_charges": {
            "connected_load_kw": 2.122, "fixed_rate": 110, "months": 12,
            "base": 2800.08, "multiplier": 2, "final": 5600.16
        },
        "energy_charges": {
            "slabs":   [ {start,end,rate,units,amount}, ... ],
            "subtotal": 4500.42,
            "multiplier": 2,
            "final":  9000.83
        },
        "electricity_duty": {
            "ed_base": 4500.42, "ed_percent": 5, "amount": 225.02
        },
        "grand_total": 14826.01,
        "rate_meta": { "category": "LMV-1", "effective_date": "...", ... },
        "warnings": []
    }
"""
from __future__ import annotations
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from ..database import fetch_all, fetch_one
from ..utils import safe_float, safe_int, parse_date

log = logging.getLogger(__name__)


# -------------------------------------------------------------- defaults
DEFAULT_FIXED_RATE = 110.0   # ₹/KW/month, used if rate_master has none
DEFAULT_ENERGY_RATE = 6.5    # ₹/unit, fallback
DEFAULT_ED_PERCENT = 5.0


# ===================================================================
# Helpers
# ===================================================================
def _today() -> date:
    return date.today()


def _to_date(v: Any) -> date | None:
    iso = parse_date(v)
    if not iso:
        return None
    return datetime.strptime(iso, "%Y-%m-%d").date()


def _system_default_multiplier() -> float:
    row = fetch_one(
        "SELECT config_value FROM system_config "
        "WHERE config_key='multiplier_first_offense'"
    )
    return float(row["config_value"]) if row else 2.0


def calc_days(section: str, *, td_date: Any = None,
              inspection_date: Any = None,
              override_days: int | None = None) -> int:
    """Section-aware days calculation."""
    if override_days is not None:
        return max(1, int(override_days))
    section = (section or "").strip()
    insp = _to_date(inspection_date) or _today()
    if section == "138":
        td = _to_date(td_date)
        if not td:
            raise ValueError("Section 138 requires td_date")
        delta = (insp - td).days
        return max(1, delta)
    # 135 / 126 / Other → 365 default
    return 365


# ===================================================================
# Rate master lookup
# ===================================================================
def lookup_rate_slabs(category: str,
                      as_of: Any = None) -> list[dict]:
    """Return rate-master rows for a category, ordered by slab_start."""
    rows = fetch_all(
        """SELECT * FROM rate_master
           WHERE category = ? AND status = 'active'
           ORDER BY effective_date DESC, slab_start ASC""",
        (category,),
    )
    if not rows:
        return []
    # If the user passed an `as_of` date, prefer the latest effective on/before
    target = _to_date(as_of) or _today()
    eligible = [r for r in rows if not r.get("effective_date")
                or _to_date(r["effective_date"]) <= target]
    if not eligible:
        return rows
    # Group by effective_date and keep the most recent slab set
    eligible.sort(key=lambda r: r.get("effective_date") or "", reverse=True)
    latest_eff = eligible[0].get("effective_date")
    return sorted(
        [r for r in eligible if r.get("effective_date") == latest_eff],
        key=lambda r: int(r.get("slab_start") or 0),
    )


def fixed_rate_for_category(category: str, as_of: Any = None) -> float:
    slabs = lookup_rate_slabs(category, as_of)
    if not slabs:
        return DEFAULT_FIXED_RATE
    # Most categories repeat the same fixed_charge across slabs — use first
    return float(slabs[0].get("fixed_charge") or DEFAULT_FIXED_RATE)


def ed_percent_for_category(category: str, as_of: Any = None) -> float:
    slabs = lookup_rate_slabs(category, as_of)
    if not slabs:
        return DEFAULT_ED_PERCENT
    return float(slabs[0].get("duty_percent") or DEFAULT_ED_PERCENT)


# ===================================================================
# LFHD core
# ===================================================================
def lfhd_units(load_w: float, factor: float, hours: float, days: float) -> float:
    """(L × F × H × D) / 1000  — returns units (kWh)."""
    return round(safe_float(load_w) * safe_float(factor)
                 * safe_float(hours) * safe_float(days) / 1000.0, 4)


def compute_devices(devices: list[dict], days: int) -> tuple[list[dict], float]:
    """Apply LFHD per device. If a device omits 'days', use case-level days."""
    out: list[dict] = []
    total = 0.0
    for raw in devices or []:
        L = safe_float(raw.get("load") or raw.get("L"))
        F = safe_float(raw.get("factor") or raw.get("F") or 1.0)
        H = safe_float(raw.get("hours") or raw.get("H"))
        D = safe_int(raw.get("days") or raw.get("D") or days)
        units = lfhd_units(L, F, H, D)
        out.append({
            "name": raw.get("name") or raw.get("device_name") or "",
            "L": L, "F": F, "H": H, "D": D,
            "units": units,
        })
        total += units
    return out, round(total, 4)


# ===================================================================
# Slab-wise energy charges
# ===================================================================
def apply_slabs(monthly_units: float, slabs: list[dict],
                months: float) -> dict:
    """
    Distribute *yearly* units across slabs using *monthly* slab boundaries.

    UPPCL slabs are defined per month, so we run the slab logic on
    `monthly_units` and multiply by months at the end.
    """
    if not slabs:
        # Default 3-tier fallback
        slabs = [
            {"slab_start": 0,   "slab_end": 100,  "rate_per_unit": 5.5,
             "duty_percent": DEFAULT_ED_PERCENT,  "fixed_charge": DEFAULT_FIXED_RATE},
            {"slab_start": 101, "slab_end": 200,  "rate_per_unit": 6.0,
             "duty_percent": DEFAULT_ED_PERCENT,  "fixed_charge": DEFAULT_FIXED_RATE},
            {"slab_start": 201, "slab_end": None, "rate_per_unit": 6.5,
             "duty_percent": DEFAULT_ED_PERCENT,  "fixed_charge": DEFAULT_FIXED_RATE},
        ]

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
            continue
        amount_monthly = round(consumed * rate, 4)
        amount_total   = round(amount_monthly * months, 2)
        breakdown.append({
            "slab_start": start,
            "slab_end":   end,
            "rate":       rate,
            "monthly_units":   round(consumed, 4),
            "yearly_units":    round(consumed * months, 4),
            "amount":          amount_total,
        })
        remaining -= consumed
        if remaining <= 0:
            break

    subtotal = round(sum(b["amount"] for b in breakdown), 2)
    return {"slabs": breakdown, "subtotal": subtotal}


# ===================================================================
# Top-level: full assessment
# ===================================================================
def calculate_assessment(payload: dict) -> dict:
    warnings: list[str] = []

    section = (payload.get("section") or "135").strip()
    td_date = payload.get("td_date")
    insp    = payload.get("inspection_date") or _today().isoformat()
    days = calc_days(section, td_date=td_date, inspection_date=insp,
                     override_days=payload.get("days"))
    months = round(days / 30.0, 4)

    multiplier = safe_float(payload.get("multiplier"),
                            _system_default_multiplier())

    # ------------------------------------------------ devices & units
    devices_in = payload.get("devices") or []
    devices, total_units = compute_devices(devices_in, days)
    less_unit = safe_float(payload.get("less_unit"), 0)
    if less_unit < 0:
        warnings.append("Negative less_unit ignored.")
        less_unit = 0
    total_units_after = round(max(0.0, total_units - less_unit), 4)
    monthly_units = round(total_units_after / months, 4) if months else 0

    # ------------------------------------------------ rate master lookup
    category = payload.get("category") or "LMV-1"
    slabs = lookup_rate_slabs(category, as_of=insp)
    if not slabs:
        warnings.append(f"No rate slabs found for category '{category}'. "
                        f"Using fallback defaults.")
    fixed_rate = safe_float(payload.get("fixed_rate"),
                            fixed_rate_for_category(category, insp))
    ed_percent = safe_float(payload.get("ed_percent"),
                            ed_percent_for_category(category, insp))

    # ------------------------------------------------ fixed charges
    connected_load_kw = safe_float(payload.get("connected_load_kw"), 0)
    if connected_load_kw <= 0:
        # Try to derive from total load of devices (Watts → KW)
        load_w_total = sum(d["L"] for d in devices) or 0
        connected_load_kw = round(load_w_total / 1000.0, 3)
        warnings.append(f"connected_load_kw not provided, derived as "
                        f"{connected_load_kw} KW from device loads.")
    fixed_base = round(connected_load_kw * fixed_rate * months, 2)
    fixed_final = round(fixed_base * multiplier, 2)

    # ------------------------------------------------ energy charges
    energy_block = apply_slabs(monthly_units, slabs, months)
    energy_subtotal = energy_block["subtotal"]
    energy_final = round(energy_subtotal * multiplier, 2)

    # ------------------------------------------------ ED (electricity duty)
    ed_base = energy_subtotal
    ed_amount = round(ed_base * ed_percent / 100.0, 2)

    grand_total = round(fixed_final + energy_final + ed_amount, 2)

    return {
        "section": section,
        "section_other": payload.get("section_other"),
        "inspection_date": str(insp),
        "td_date": td_date,
        "days": days,
        "months": months,
        "multiplier": multiplier,
        "less_unit": less_unit,
        "category": category,
        "devices": devices,
        "total_units_calculated": total_units,
        "total_units_after_less_unit": total_units_after,
        "monthly_units": monthly_units,
        "fixed_charges": {
            "connected_load_kw": connected_load_kw,
            "fixed_rate": fixed_rate,
            "months": months,
            "base": fixed_base,
            "multiplier": multiplier,
            "final": fixed_final,
        },
        "energy_charges": {
            "slabs": energy_block["slabs"],
            "subtotal": energy_subtotal,
            "multiplier": multiplier,
            "final": energy_final,
        },
        "electricity_duty": {
            "ed_base": ed_base,
            "ed_percent": ed_percent,
            "amount": ed_amount,
        },
        "grand_total": grand_total,
        "rate_meta": {
            "category": category,
            "slab_count": len(slabs),
            "effective_date": (slabs[0]["effective_date"]
                               if slabs and slabs[0].get("effective_date")
                               else None),
            "fixed_rate": fixed_rate,
            "ed_percent": ed_percent,
        },
        "warnings": warnings,
    }
