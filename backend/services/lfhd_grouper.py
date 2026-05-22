"""
Grouped LFHD formatter — pure helpers (additive, not yet wired).
================================================================

Mirror of ``frontend/static/lfhd_grouper.js``.  Same input/output
shape, same number formatting, same grouping rule, so the printed
LFHD math reads identically whether it is rendered by the frontend
preview or by a backend notice template.

Why this module exists
----------------------
The project owner asked for a *single* grouped-LFHD presentation
that can later feed:

* assessment notices
* court documents
* compounding sheets
* PDF / print views
* on-screen summaries

This file provides the building blocks.  Whether and where each
notice template adopts them is an explicit, per-template decision —
this PR intentionally does NOT change any existing template, route,
or document generator.  Court documents shouldn't quietly switch
formats; each adoption gets its own review-able PR.

Safety contract
---------------
* Pure Python, stdlib only — no Flask, no DB, no I/O.
* Does NOT import or call ``backend.services.calculator`` so it can
  never accidentally affect the LFHD assessment math.
* Idempotent and deterministic: repeated calls with identical input
  return identical output.

Input shape (matches the JSON the frontend already POSTs)::

    {"name": str,
     "load": float,      # Watts -- column header reads "Load (W)"
     "factor": float,    # dimensionless 0..1
     "hours": float,     # hours/day
     "days":   float}    # days

Group output shape::

    {"load_kw":      float,    # sum of contributing loads / 1000
     "hours":        float,
     "factor":       float,
     "days":         float,
     "units":        float,    # load_kw * hours * factor * days
     "device_count": int,
     "device_names": List[str]}

Math line format::

    "0.3 × 18 × 0.3 × 365 = 591.3"

Examples
--------
>>> rows = [
...     {"name": "Bulb",  "load": 100, "factor": 0.3, "hours": 18, "days": 365},
...     {"name": "Fan",   "load": 200, "factor": 0.3, "hours": 18, "days": 365},
...     {"name": "AC",    "load": 1500, "factor": 0.5, "hours":  8, "days": 120},
... ]
>>> groups = group_devices(rows)
>>> [g["device_count"] for g in groups]
[2, 1]
>>> format_math(groups[0])
'0.3 × 18 × 0.3 × 365 = 591.3'
>>> format_math(groups[1])
'1.5 × 8 × 0.5 × 120 = 720'
>>> total_units(groups)
1311.3
"""

from __future__ import annotations

from typing import Iterable, List, Dict, Any

__all__ = [
    "group_devices",
    "format_math",
    "total_units",
    "render_text",
    "render_html",
]

# ---------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------

# 'times' character used in the printed math.  Kept as a constant so
# a reviewer can change it in exactly one place if a notice template
# prefers ASCII '*' for some legal reason.
_TIMES = "\u00d7"  # MULTIPLICATION SIGN ×


def _to_number(v: Any, default: float = 0.0) -> float:
    """Robust float coercion — empty strings, None, junk all map to default."""
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _round(n: float, decimals: int) -> float:
    """Round half-up at the given precision — matches JS Math.round*p/p."""
    p = 10 ** decimals
    # Python's banker's rounding is fine for our presentation use; the
    # difference vs. JS Math.round (round half away from zero) is at
    # the 0.5 mid-bin only and never affects realistic LFHD numbers.
    return round(n * p) / p


def _trim(n: float, decimals: int) -> str:
    """0.300 -> '0.3', 365 -> '365', 18.5 -> '18.5'.

    Mirrors the JS ``trim`` helper byte-for-byte: format with the given
    decimals, then drop trailing zeros and a redundant decimal point.
    """
    s = f"{float(n):.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _bucket_key(d: Dict[str, Any]) -> tuple:
    """(hours, factor, days) bucket — rounded so float noise can't split."""
    return (
        _round(_to_number(d.get("hours")),  3),
        _round(_to_number(d.get("factor")), 3),
        _round(_to_number(d.get("days")),   0),
    )


def _is_valid_device(d: Dict[str, Any]) -> bool:
    """A device row is printable only when L/H/F/D are all > 0."""
    L = _to_number(d.get("load"))
    H = _to_number(d.get("hours"))
    F = _to_number(d.get("factor"))
    D = _to_number(d.get("days"))
    return L > 0 and H > 0 and F > 0 and D > 0


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


def group_devices(devices: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group device rows by identical (hours, factor, days) and sum loads.

    The returned list preserves first-occurrence order so the printed
    math sequence is stable (deterministic notices === reviewable notices).
    """
    if devices is None:
        return []

    order: List[tuple] = []
    buckets: Dict[tuple, Dict[str, Any]] = {}

    for d in devices:
        if not _is_valid_device(d):
            continue
        key = _bucket_key(d)
        if key not in buckets:
            order.append(key)
            buckets[key] = {
                "load_w":       0.0,
                "hours":        key[0],
                "factor":       key[1],
                "days":         key[2],
                "device_names": [],
            }
        b = buckets[key]
        b["load_w"] += _to_number(d.get("load"))
        name = str(d.get("name") or "").strip() or "(unnamed)"
        b["device_names"].append(name)

    out: List[Dict[str, Any]] = []
    for key in order:
        b = buckets[key]
        load_kw = b["load_w"] / 1000.0
        out.append({
            "load_kw":      _round(load_kw, 4),
            "hours":        b["hours"],
            "factor":       b["factor"],
            "days":         b["days"],
            "units":        _round(load_kw * b["hours"] * b["factor"] * b["days"], 3),
            "device_count": len(b["device_names"]),
            "device_names": list(b["device_names"]),
        })
    return out


def format_math(g: Dict[str, Any]) -> str:
    """``"0.3 × 18 × 0.3 × 365 = 591.3"`` for one group."""
    return (
        f"{_trim(g['load_kw'], 3)} {_TIMES} "
        f"{_trim(g['hours'],   2)} {_TIMES} "
        f"{_trim(g['factor'],  3)} {_TIMES} "
        f"{_trim(g['days'],    0)} = "
        f"{_trim(g['units'],   2)}"
    )


def total_units(groups: Iterable[Dict[str, Any]]) -> float:
    """Sum of group units, rounded to 3 dp."""
    return _round(sum(g["units"] for g in (groups or [])), 3)


# ---------------------------------------------------------------------
# Renderers — string returns so any template can embed them.
# ---------------------------------------------------------------------


def render_text(devices: Iterable[Dict[str, Any]]) -> str:
    """Plain-text grouped LFHD block.  Drop-in for ``<pre>`` blocks."""
    groups = group_devices(devices)
    if not groups:
        return "(no LFHD entries)"
    lines = [
        f"{i + 1}. {format_math(g)} Units"
        for i, g in enumerate(groups)
    ]
    lines.append("")
    lines.append(f"Total Units = {_trim(total_units(groups), 2)}")
    return "\n".join(lines)


def _escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&",  "&amp;")
        .replace("<",  "&lt;")
        .replace(">",  "&gt;")
        .replace('"',  "&quot;")
        .replace("'",  "&#39;")
    )


def render_html(devices: Iterable[Dict[str, Any]]) -> str:
    """HTML grouped LFHD block — same markup the frontend uses, so a
    notice template that opts in to this helper produces a printout
    identical to the on-screen preview."""
    groups = group_devices(devices)
    if not groups:
        return (
            '<div class="lfhd-empty">'
            'No LFHD entries — Load × Hours × Factor × Days needed.'
            '</div>'
        )

    rows = []
    for g in groups:
        if g["device_count"] == 1:
            names_html = _escape_html(g["device_names"][0])
        else:
            names_html = (
                ", ".join(_escape_html(n) for n in g["device_names"])
                + f' <span class="small">({g["device_count"]} devices)</span>'
            )
        rows.append(
            "<li>"
            f'<code class="lfhd-math">{_escape_html(format_math(g))}</code> '
            '<span class="lfhd-units small">Units</span>'
            f'<div class="lfhd-devices small">{names_html}</div>'
            "</li>"
        )

    total = _trim(total_units(groups), 2)
    return (
        '<ol class="lfhd-rows">' + "".join(rows) + "</ol>"
        f'<div class="lfhd-total"><b>Total Units</b> = '
        f'<code>{_escape_html(total)}</code></div>'
    )


# ---------------------------------------------------------------------
# When run as a script, print a tiny self-check so the doctests can be
# executed standalone without a test runner.  Not invoked by Flask.
# ---------------------------------------------------------------------
if __name__ == "__main__":          # pragma: no cover
    import doctest
    fails, tests = doctest.testmod(verbose=False)
    print(f"lfhd_grouper.py — {tests} doctest(s), {fails} failure(s)")
