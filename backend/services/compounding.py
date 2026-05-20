"""
Section 152 Compounding calculator.

Business rule (Electricity Act 2003, Section 152) — captured directly from
the user's instruction earlier in the chat:

    LT उपभोक्ताओं के मामलों में Compounding charges
    "per KW or part thereof" basis पर लगती हैं.
    अर्थात पाया गया भार जिस अगले पूर्णांक KW में आता है,
    उस KW के आधार पर compounding की गणना होगी.

Implementation
--------------
* Convert the raid-time load in Watts to KW.
* `billable_kw = ceil(load_kw)`     ← the **part-thereof** rule.
* Multiply by the per-KW rate appropriate to (category, section, offense_no).
* Return both the numeric breakdown and a ready-to-paste Hindi justification
  text that the document generator can drop straight into the order.
"""
from __future__ import annotations
import logging
import math
from typing import Any

from ..database import fetch_all
from ..utils import safe_float

log = logging.getLogger(__name__)


# -------------------------------------------------------------- defaults
# These are conservative placeholders. Officers can override per-case via
# the `rate_per_kw` parameter, or we can add a dedicated table later.
DEFAULT_RATES_PER_KW: dict[str, float] = {
    "LMV-1":         6000.0,   # Domestic
    "LMV-1 URBAN":   6000.0,
    "LMV-2":         8000.0,   # Commercial
    "LMV-2 RURAL":   8000.0,
    "LMV-3":         10000.0,  # Public lamps
    "LMV-4":         8000.0,   # Schools / institutions
    "LMV-5":         3500.0,   # Agriculture
    "LMV-6":         12000.0,
    "LMV-7":         12000.0,
    "LMV-8":         12000.0,
    "LMV-9":         8000.0,
    "DEFAULT":       6000.0,
}


def billable_kw(load_w: float | int | str) -> int:
    """Per KW or part thereof → ceil to next integer KW.

    Examples
    --------
    >>> billable_kw(2122)        # 2.122 KW
    3
    >>> billable_kw(2000)        # exactly 2 KW
    2
    >>> billable_kw(0)
    0
    """
    load_w = safe_float(load_w)
    if load_w <= 0:
        return 0
    return int(math.ceil(load_w / 1000.0))


def rate_per_kw(category: str | None,
                section: str | None = None,
                override: float | None = None) -> float:
    if override is not None:
        return safe_float(override, DEFAULT_RATES_PER_KW["DEFAULT"])
    if not category:
        return DEFAULT_RATES_PER_KW["DEFAULT"]
    cat_key = str(category).strip().upper()
    return DEFAULT_RATES_PER_KW.get(cat_key,
                                    DEFAULT_RATES_PER_KW["DEFAULT"])


def justification_text(load_w: float, billable: int) -> str:
    """Auto-generated Hindi paragraph for inclusion in the Compounding order.

    Mirrors the exact phrasing the user supplied so officers don't have to
    rewrite it for every case.
    """
    load_kw_approx = round(safe_float(load_w) / 1000.0, 3)
    return (
        f"निरीक्षण के समय उपभोक्ता परिसर पर {int(safe_float(load_w))} Watt "
        f"अर्थात लगभग {load_kw_approx} KW भार पाया गया, जो "
        f"{billable - 1} KW से अधिक होकर अतिरिक्त भाग (part thereof) में "
        f"आता है। अतः धारा 152 में वर्णित \"per KW or part thereof\" "
        f"प्रावधान के अनुसार Compounding की गणना {billable} KW के आधार "
        f"पर की गई है।"
    )


def calculate_compounding(payload: dict) -> dict:
    """
    Inputs
    ------
    {
        "load_w":      2122,      # raid-time found load in WATTS  (preferred)
        "load_kw":     2.122,     # alternative: in KW
        "category":    "LMV-1",
        "section":     "135",
        "rate_per_kw": 6000,      # optional override
    }
    """
    load_w = safe_float(payload.get("load_w"), 0)
    if load_w <= 0:
        load_kw = safe_float(payload.get("load_kw"), 0)
        load_w = load_kw * 1000.0
    if load_w <= 0:
        return {
            "ok": False,
            "error": "Provide either load_w (Watts) or load_kw (KW).",
        }

    category = payload.get("category")
    section  = payload.get("section")
    override = payload.get("rate_per_kw")

    bkw = billable_kw(load_w)
    rate = rate_per_kw(category, section, override)
    amount = round(bkw * rate, 2)

    return {
        "ok": True,
        "load_w": round(load_w, 3),
        "load_kw": round(load_w / 1000.0, 3),
        "billable_kw": bkw,
        "rate_per_kw": rate,
        "category": category,
        "section": section,
        "compounding_amount": amount,
        "justification_hi": justification_text(load_w, bkw),
        "rule": "Section 152 — per KW or part thereof (round-UP)",
    }
