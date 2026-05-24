"""
PR3 verification harness — 50 deterministic checks.

Validates PR3 deliverables and ONLY PR3 deliverables:

  Group P  PR1 + PR2 still green  (regression guard)        [01-04]
  Group Q  PR3 endpoint registration                         [05-09]
  Group R  /api/rates/categories                             [10-14]
  Group S  /api/rates/subcategories                          [15-19]
  Group T  /api/rates/condition-loads (alias of S)           [20-21]
  Group U  /api/rates/preview shape + metadata               [22-31]
  Group V  /api/rates/preview slab-wise breakdown            [32-36]
  Group W  Frontend HTML additions                            [37-44]
  Group X  Frontend CSS scoping                               [45-47]
  Group Y  Frontend JS sanity                                 [48-50]

Validates AGAINST:
  * backend.routes.rates  (4 new GET endpoints)
  * frontend/index.html   (Subcategory + readonly + preview panel)
  * frontend/static/tariff.js  +  tariff.css

Usage
-----
    python -m scripts.test_pr3
    python -m scripts.test_pr3 /tmp/raid_pr3.db

Exit code 0 on success (50/50), 1 on any failure.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------- setup
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DB_PATH = sys.argv[1] if len(sys.argv) > 1 else tempfile.mktemp(
    prefix="raid_pr3_", suffix=".db",
)
if os.path.exists(_DB_PATH):
    os.unlink(_DB_PATH)
os.environ["RAID_DB_PATH"] = _DB_PATH

# Now safe to import backend modules.
from flask import Flask  # noqa: E402

from backend import database  # noqa: E402
from backend.services import tariff_engine as te  # noqa: E402
from backend.routes.rates import bp as rates_bp  # noqa: E402

# --------------------------------------------------------------------- runner
PASSED = 0
FAILED = 0
FAILURES: list[str] = []
_COUNTER = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED, _COUNTER
    _COUNTER += 1
    if ok:
        PASSED += 1
    else:
        FAILED += 1
        FAILURES.append(
            f"  [{_COUNTER:02d}] FAIL: {label}"
            + (f"  ({detail})" if detail else "")
        )


# =====================================================================
# Group P: PR1 + PR2 regression guards (4 checks) — [01-04]
# =====================================================================
def _run_harness(name: str) -> bool:
    db = tempfile.mktemp(prefix=f"raid_{name}_regression_", suffix=".db")
    r = subprocess.run(
        [sys.executable, "-m", f"scripts.{name}", db],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    return r.returncode == 0


check("PR1 harness still passes (regression)", _run_harness("test_pr1"))
check("PR2 harness still passes (regression)", _run_harness("test_pr2"))
# 03-04: PR1/PR2 surfaces still callable
check("tariff_engine.find_applicable_rate still callable",
      callable(te.find_applicable_rate))
from backend.services import tariff_timeline_engine as tte  # noqa: E402
check("tariff_timeline_engine.calculate_timeline still callable",
      callable(tte.calculate_timeline))


# =====================================================================
# Group Q: Endpoint registration (5 checks) — [05-09]
# =====================================================================
_app = Flask("pr3_probe")
_app.register_blueprint(rates_bp)
_rules = sorted(r.rule for r in _app.url_map.iter_rules())

check("/api/rates/categories registered",
      "/api/rates/categories" in _rules)
check("/api/rates/subcategories registered",
      "/api/rates/subcategories" in _rules)
check("/api/rates/condition-loads registered",
      "/api/rates/condition-loads" in _rules)
check("/api/rates/preview registered",
      "/api/rates/preview" in _rules)
# 09: PR2 endpoints still present
check("/api/rates/upload-schedule (PR2) still registered",
      "/api/rates/upload-schedule" in _rules)


# =====================================================================
# Setup test data — used by Groups R, S, T, U, V
# =====================================================================
database.init_schema()

# Seed deterministic tariff_rates rows for the test:
#   Category LMV-1, condition_load=domestic — 2 slabs, schedule "S25"
#   Category LMV-1, condition_load=industrial — 1 unbounded slab
#   Category LMV-2, condition_load=commercial — 1 unbounded slab
#   Category LMV-9, condition_load=domestic — 1 row but EXPIRED (effective_to in past)
with database.standalone_connection() as _c:
    _c.execute("DELETE FROM tariff_rates")
    _c.execute(te._RATE_INSERT_SQL, (
        "LMV-1", 0, 100, 5.50, 110.0, 5.0, "Domestic - First slab",
        "S25", "2025-04-01", "2026-03-31", "active", "test", None,
        "domestic", "First 100 units", 0.0, 20.0, "2025-04-01", "2026-03-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "LMV-1", 101, None, 6.50, 110.0, 5.0, "Domestic - Above 100",
        "S25", "2025-04-01", "2026-03-31", "active", "test", None,
        "domestic", "Above 100 units", 0.0, 20.0, "2025-04-01", "2026-03-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "LMV-1", 0, None, 7.25, 200.0, 7.5, "Industrial flat",
        "S25", "2025-04-01", "2026-03-31", "active", "test", None,
        "industrial", "Flat", 50.0, 50.0, "2025-04-01", "2026-03-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "LMV-2", 0, None, 7.25, 150.0, 7.5, "Commercial flat",
        "S25", "2025-04-01", "2026-03-31", "active", "test", None,
        "commercial", "Flat", 0.0, 30.0, "2025-04-01", "2026-03-31",
    ))
    # Expired row — should be filtered out by date filter
    _c.execute(te._RATE_INSERT_SQL, (
        "LMV-9", 0, None, 9.99, 250.0, 5.0, "Old expired",
        "S22", "2022-04-01", "2023-03-31", "active", "test", None,
        "domestic", "Flat", 0.0, 0.0, "2022-04-01", "2023-03-31",
    ))
    _c.commit()


# =====================================================================
# Group R: /api/rates/categories (5 checks) — [10-14]
# =====================================================================
_client = _app.test_client()
_resp = _client.get("/api/rates/categories?as_of_date=2025-10-15")
check("/categories returns 200",                _resp.status_code == 200)
_payload = _resp.get_json() or {}
_data = (_payload.get("data") or {})
_cats = _data.get("categories") or []
_cat_names = {c.get("category") for c in _cats}

check("/categories includes LMV-1",  "LMV-1" in _cat_names)
check("/categories includes LMV-2",  "LMV-2" in _cat_names)
check("/categories EXCLUDES expired LMV-9",
      "LMV-9" not in _cat_names,
      detail=f"got cats={sorted(_cat_names)}")
# subcategory_count: LMV-1 has BOTH domestic and industrial → 2
_lmv1 = next((c for c in _cats if c.get("category") == "LMV-1"), {})
check("/categories LMV-1 subcategory_count == 2",
      _lmv1.get("subcategory_count") == 2,
      detail=f"got={_lmv1}")


# =====================================================================
# Group S: /api/rates/subcategories (5 checks) — [15-19]
# =====================================================================
_resp = _client.get("/api/rates/subcategories?category=LMV-1&as_of_date=2025-10-15")
check("/subcategories?category=LMV-1 returns 200", _resp.status_code == 200)
_subs = ((_resp.get_json() or {}).get("data") or {}).get("subcategories") or []
_sub_vals = {s.get("value") for s in _subs}
check("/subcategories LMV-1 includes 'domestic'",   "domestic"   in _sub_vals)
check("/subcategories LMV-1 includes 'industrial'", "industrial" in _sub_vals)

# Missing category -> 400
_resp_bad = _client.get("/api/rates/subcategories")
check("/subcategories without category -> 400",
      _resp_bad.status_code == 400)

# Unknown category -> 200 with empty list
_resp_empty = _client.get("/api/rates/subcategories?category=NOPE")
_subs_empty = ((_resp_empty.get_json() or {}).get("data") or {}).get("subcategories") or []
check("/subcategories unknown category -> empty list",
      _resp_empty.status_code == 200 and _subs_empty == [],
      detail=f"len={len(_subs_empty)}")


# =====================================================================
# Group T: /api/rates/condition-loads (alias) (2 checks) — [20-21]
# =====================================================================
_resp_a = _client.get(
    "/api/rates/condition-loads?category=LMV-1&as_of_date=2025-10-15")
_resp_b = _client.get(
    "/api/rates/subcategories?category=LMV-1&as_of_date=2025-10-15")
check("/condition-loads returns 200", _resp_a.status_code == 200)
check("/condition-loads returns same payload as /subcategories",
      _resp_a.get_json() == _resp_b.get_json())


# =====================================================================
# Group U: /api/rates/preview shape + metadata (10 checks) — [22-31]
# =====================================================================
_resp = _client.get(
    "/api/rates/preview?category=LMV-1&condition_load=domestic"
    "&as_of_date=2025-10-15")
check("/preview returns 200",  _resp.status_code == 200)
_pv = ((_resp.get_json() or {}).get("data") or {})

check("/preview has slabs list",       isinstance(_pv.get("slabs"), list))
check("/preview slabs non-empty",      len(_pv.get("slabs") or []) > 0)
check("/preview returns schedule_name == 'S25'",
      _pv.get("schedule_name") == "S25",
      detail=f"got={_pv.get('schedule_name')}")
check("/preview returns condition_text non-empty",
      bool(_pv.get("condition_text")))
check("/preview returns fixed_charge",
      _pv.get("fixed_charge") == 110.0,
      detail=f"got={_pv.get('fixed_charge')}")
check("/preview returns duty_percent",
      _pv.get("duty_percent") == 5.0,
      detail=f"got={_pv.get('duty_percent')}")
check("/preview returns meter_rent",
      _pv.get("meter_rent") == 20.0,
      detail=f"got={_pv.get('meter_rent')}")
check("/preview returns rebate",
      _pv.get("rebate") == 0.0,
      detail=f"got={_pv.get('rebate')}")
check("/preview slab[0].rate_per_unit == 5.50",
      _pv["slabs"][0].get("rate_per_unit") == 5.50,
      detail=f"got={_pv['slabs'][0]}")


# =====================================================================
# Group V: /api/rates/preview slab-wise breakdown (5 checks) — [32-36]
# =====================================================================
# 150 monthly_units against slabs [0..100 @5.50, 101..∞ @6.50].
# Slab capacity uses the UPPCL convention: cap = end - start + 1
# (slab "0..100" inclusively contains 101 unit-values), matching how
# calculator.apply_slabs() in services/calculator.py works. So:
#   slab 1 takes min(150, 101) = 101 units * 5.50 = 555.50
#   slab 2 takes the remaining 49 units      * 6.50 = 318.50
#   monthly_subtotal = 874.00
_resp = _client.get(
    "/api/rates/preview?category=LMV-1&condition_load=domestic"
    "&as_of_date=2025-10-15&units=150")
_pv = ((_resp.get_json() or {}).get("data") or {})
_preview = _pv.get("preview") or {}
_break = _preview.get("slab_breakdown") or []

check("/preview?units=150 returns preview block",
      isinstance(_preview, dict) and len(_break) >= 2)
check("slab_breakdown[0].units == 101 (UPPCL inclusive convention)",
      _break and _break[0].get("units") == 101,
      detail=f"break[0]={_break[0] if _break else None}")
check("slab_breakdown[0].amount == 555.5",
      _break and abs(_break[0].get("amount", 0) - 555.5) < 0.01)
check("slab_breakdown[1].units == 49",
      len(_break) > 1 and _break[1].get("units") == 49,
      detail=f"break[1]={_break[1] if len(_break) > 1 else None}")
check("slab_breakdown monthly_subtotal == 874.0",
      abs((_preview.get("monthly_subtotal") or 0) - 874.0) < 0.01,
      detail=f"got={_preview.get('monthly_subtotal')}")


# =====================================================================
# Group W: Frontend HTML additions (8 checks) — [37-44]
# =====================================================================
_html_path = _REPO_ROOT / "frontend" / "index.html"
_html = _html_path.read_text(encoding="utf-8")

check("HTML keeps existing #f_category dropdown",
      'id="f_category"' in _html)
check("HTML adds #f_subcategory dropdown (PR3 NEW)",
      'id="f_subcategory"' in _html)
check("HTML adds readonly #f_condition_text (PR3 NEW)",
      'id="f_condition_text"' in _html and 'readonly' in _html)
check("HTML adds hidden #f_condition_load (PR3 NEW)",
      'id="f_condition_load"' in _html
      and 'type="hidden"' in _html)
check("HTML adds #lbl_supply id so CSS can hide it",
      'id="lbl_supply"' in _html)
check("HTML keeps the #f_supply <select> in DOM (so save_case keeps working)",
      'id="f_supply"' in _html)
check("HTML adds tariff.js script tag",
      'src="/frontend/static/tariff.js"' in _html)
check("HTML adds tariff.css link tag",
      'href="/frontend/static/tariff.css"' in _html)


# =====================================================================
# Group X: Frontend CSS scoping (3 checks) — [45-47]
# =====================================================================
_css = (_REPO_ROOT / "frontend" / "static" / "tariff.css").read_text(
    encoding="utf-8")

check("tariff.css hides #lbl_supply with display:none",
      "#lbl_supply" in _css and re.search(r"#lbl_supply\s*\{[^}]*display:\s*none",
                                          _css))
check("tariff.css scopes preview rules under #panel-new-case",
      ".tariff-preview" in _css and "#panel-new-case .tariff-preview" in _css)
# Sanity: NO global selector for input or select that would leak
_global_input = re.search(r"^\s*input\s*\{", _css, re.MULTILINE)
check("tariff.css does NOT define unscoped global input/select rules",
      _global_input is None,
      detail="tariff.css has unscoped 'input { … }' rule" if _global_input else "")


# =====================================================================
# Group Y: Frontend JS sanity (3 checks) — [48-50]
# =====================================================================
_js = (_REPO_ROOT / "frontend" / "static" / "tariff.js").read_text(
    encoding="utf-8")

check("tariff.js calls /api/rates/categories",
      "/api/rates/categories" in _js)
check("tariff.js calls /api/rates/subcategories",
      "/api/rates/subcategories" in _js)
check("tariff.js wires up #f_category change listener",
      'addEventListener("change"' in _js
      and "#f_category" in _js
      and "#f_subcategory" in _js)


# =====================================================================
# Report
# =====================================================================
print()
print("=" * 60)
print(f"PR3 verification: {PASSED}/{PASSED + FAILED} passed")
print("=" * 60)
if FAILURES:
    print()
    print("FAILURES:")
    for line in FAILURES:
        print(line)
    sys.exit(1)
else:
    print()
    print(f"ALL PR3 CHECKS PASSED  ({PASSED}/{PASSED + FAILED})")
    sys.exit(0)
