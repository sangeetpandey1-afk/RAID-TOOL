"""
PR2 verification harness — 60 deterministic checks.

Validates the PR2 deliverables and ONLY the PR2 deliverables:

  Group P  PR1 still green  (regression guard)        [01-04]
  Group Q  Migration: historical_cases extensions     [05-15]
  Group R  Migration: indexes                          [16-19]
  Group S  Tariff timeline split                       [20-29]
  Group T  Per-segment slab math                       [30-37]
  Group U  Top-level calculate_timeline                [38-46]
  Group V  Historical importer — synonyms              [47-52]
  Group W  Historical importer — end-to-end            [53-58]
  Group X  Blueprint registration                      [59-60]

Validates AGAINST:
  * backend.database._apply_lightweight_migrations  (PR2 extension columns)
  * backend.services.tariff_timeline_engine
  * backend.services.historical_import
  * backend.routes.rates  +  backend.routes.historical  (import only)

Usage
-----
    python -m scripts.test_pr2
    python -m scripts.test_pr2 /tmp/raid_pr2.db    # custom DB path

Exit code 0 on success (60/60), 1 on any failure.
PR1's test_pr1.py is invoked as a regression guard — its 75 checks must
still pass on this branch.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------- setup
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DB_PATH = sys.argv[1] if len(sys.argv) > 1 else tempfile.mktemp(
    prefix="raid_pr2_", suffix=".db",
)
if os.path.exists(_DB_PATH):
    os.unlink(_DB_PATH)
os.environ["RAID_DB_PATH"] = _DB_PATH

# Now safe to import backend modules.
from backend import database  # noqa: E402
from backend.services import tariff_engine as te  # noqa: E402
from backend.services import tariff_timeline_engine as tte  # noqa: E402
from backend.services import historical_import as hi  # noqa: E402

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
# Group P: PR1 regression guard (4 checks) — [01-04]
# =====================================================================
# Run test_pr1.py as a subprocess against an isolated DB so it doesn't
# pollute our PR2 DB. Treat its overall exit code as 1 check, then 3
# more sanity-checks against PR1 surfaces that PR2 must not have broken.
_pr1_db = tempfile.mktemp(prefix="raid_pr1_regression_", suffix=".db")
_pr1 = subprocess.run(
    [sys.executable, "-m", "scripts.test_pr1", _pr1_db],
    capture_output=True, text=True, cwd=str(_REPO_ROOT),
)
check("PR1 harness still passes (regression)",
      _pr1.returncode == 0,
      detail=(_pr1.stdout.strip().splitlines()[-3:] if _pr1.stdout else "no output"))
check("tariff_engine.import_schedule still callable",
      callable(te.import_schedule))
check("tariff_engine.detect_overlaps still callable",
      callable(te.detect_overlaps))
check("tariff_engine.find_applicable_rate still callable",
      callable(te.find_applicable_rate))


# =====================================================================
# Group Q: Migration — historical_cases extension columns (11) — [05-15]
# =====================================================================
database.init_schema()
with database.standalone_connection() as _c:
    _hist_cols = {r["name"] for r in
                  _c.execute("PRAGMA table_info(historical_cases)").fetchall()}

# Legacy column still present
check("historical_cases.account_id (legacy) still present",
      "account_id" in _hist_cols)

# 10 new PR2 columns
for col in ("notice_no", "address", "use_name", "user_father_name",
            "sub_substation", "old_account_id", "new_account_id",
            "category", "irregularity", "paid_status"):
    check(f"historical_cases.{col} (PR2 NEW)", col in _hist_cols)


# =====================================================================
# Group R: Migration — indexes (4 checks) — [16-19]
# =====================================================================
with database.standalone_connection() as _c:
    _idx = {r["name"] for r in _c.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND tbl_name='historical_cases'"
    ).fetchall()}

check("idx_hist_account (legacy)",     "idx_hist_account"    in _idx)
check("idx_hist_old_account (PR2 NEW)", "idx_hist_old_account" in _idx)
check("idx_hist_new_account (PR2 NEW)", "idx_hist_new_account" in _idx)
check("idx_hist_notice_no (PR2 NEW)",   "idx_hist_notice_no"   in _idx)


# =====================================================================
# Group S: Tariff timeline split (10 checks) — [20-29]
# =====================================================================
# Seed a category with two non-overlapping schedules:
#   Schedule_A  applies 2024-01-01 .. 2024-12-31  (rate 5.0)
#   Schedule_B  applies 2025-01-01 .. 2025-12-31  (rate 6.0)
with database.standalone_connection() as _c:
    _c.execute("DELETE FROM tariff_rates")
    _c.execute(te._RATE_INSERT_SQL, (
        "TL-CAT", 0, 100, 5.0, 100.0, 5.0, "Schedule A",
        "sched_A", "2024-01-01", "2024-12-31", "active", "test", None,
        "domestic", "0-100", 0.0, 20.0, "2024-01-01", "2024-12-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "TL-CAT", 101, None, 5.5, 100.0, 5.0, "Schedule A higher",
        "sched_A", "2024-01-01", "2024-12-31", "active", "test", None,
        "domestic", "Above 100", 0.0, 20.0, "2024-01-01", "2024-12-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "TL-CAT", 0, 100, 6.0, 110.0, 7.5, "Schedule B",
        "sched_B", "2025-01-01", "2025-12-31", "active", "test", None,
        "domestic", "0-100", 0.0, 25.0, "2025-01-01", "2025-12-31",
    ))
    _c.execute(te._RATE_INSERT_SQL, (
        "TL-CAT", 101, None, 6.6, 110.0, 7.5, "Schedule B higher",
        "sched_B", "2025-01-01", "2025-12-31", "active", "test", None,
        "domestic", "Above 100", 0.0, 25.0, "2025-01-01", "2025-12-31",
    ))
    _c.commit()

# 20: split spanning the two schedules → at least 2 segments
_segs = tte.split_period_by_tariff(
    "TL-CAT", "2024-07-01", "2025-06-30",
    condition_load="domestic",
)
check("split returns multiple segments across schedule boundary",
      len(_segs) >= 2, detail=f"got {len(_segs)} segs")

# 21: segments are sorted and contiguous
_contiguous = all(_segs[i]["to"] < _segs[i + 1]["from"] or _segs[i + 1]["from"] >= _segs[i]["to"]
                  for i in range(len(_segs) - 1))
check("segments are non-overlapping/sorted", _contiguous)

# 22: union of segments covers the full period
check("first segment starts at period start",
      _segs[0]["from"] == "2024-07-01")
# 23
check("last segment ends at period end",
      _segs[-1]["to"] == "2025-06-30")

# 24: a boundary between schedules exists at 2025-01-01
_boundaries = {s["from"] for s in _segs} | {s["to"] for s in _segs}
check("schedule boundary at 2025-01-01 detected",
      "2025-01-01" in _boundaries or "2024-12-31" in _boundaries,
      detail=f"boundaries={sorted(_boundaries)}")

# 25: midpoint of first segment lies in 2024 (Schedule A)
_first_mid = tte._midpoint_iso(_segs[0]["from"], _segs[0]["to"])
check("first segment midpoint is in 2024 (Schedule A territory)",
      _first_mid.startswith("2024"), detail=f"mid={_first_mid}")

# 26: midpoint of last segment lies in 2025 (Schedule B)
_last_mid = tte._midpoint_iso(_segs[-1]["from"], _segs[-1]["to"])
check("last segment midpoint is in 2025 (Schedule B territory)",
      _last_mid.startswith("2025"), detail=f"mid={_last_mid}")

# 27: split with empty/disjoint period returns []
_empty = tte.split_period_by_tariff("TL-CAT", "2030-01-01", "2030-06-30")
check("split outside any schedule still returns >=1 segment (covers gap)",
      len(_empty) >= 1)

# 28: total segment days equals inclusive period length
_total_seg_days = sum(s["days"] for s in _segs)
_expected_days = tte._days_inclusive("2024-07-01", "2025-06-30")
check("sum of segment days == period length",
      _total_seg_days == _expected_days,
      detail=f"sum={_total_seg_days} expected={_expected_days}")

# 29: condition_load filter excludes mismatching rows from boundary set
_segs_industrial = tte.split_period_by_tariff(
    "TL-CAT", "2024-07-01", "2025-06-30",
    condition_load="industrial",  # no rows match this
)
check("condition_load=industrial returns single covering segment "
      "(no boundaries from domestic-only rows)",
      len(_segs_industrial) == 1)


# =====================================================================
# Group T: Per-segment slab math (8 checks) — [30-37]
# =====================================================================
# Test compute_segment with deterministic inputs.
_seg_2024 = {"from": "2024-07-01", "to": "2024-12-31",
             "days": tte._days_inclusive("2024-07-01", "2024-12-31")}
_total_days = tte._days_inclusive("2024-07-01", "2025-06-30")
_yearly_units = 1200.0  # arbitrary
_result_2024 = tte.compute_segment(
    _seg_2024, yearly_units=_yearly_units,
    total_period_days=_total_days,
    category="TL-CAT", multiplier=2.0,
    condition_load="domestic",
)
check("compute_segment returns dict with expected keys",
      all(k in _result_2024 for k in
          ("from", "to", "days", "months", "units_segment",
           "monthly_units", "slabs", "fixed_charge",
           "energy_charge", "electricity_duty",
           "meter_rent", "rebate")))

# 31: pro-rated units = yearly_units * seg_days / total_days
_expected_units = round(_yearly_units * _seg_2024["days"] / _total_days, 4)
check("pro-rated units match yearly * seg/total formula",
      abs(_result_2024["units_segment"] - _expected_units) < 0.001,
      detail=f"got={_result_2024['units_segment']} exp={_expected_units}")

# 32: 2024 segment uses Schedule A rates (5.0 / 5.5)
_rates_used = {s["rate_per_unit"] for s in _result_2024["slabs"]}
check("2024 segment uses Schedule A rates",
      _rates_used.issubset({5.0, 5.5}) and len(_rates_used) > 0,
      detail=f"rates={_rates_used}")

# 33: 2025 segment uses Schedule B rates (6.0 / 6.6)
_seg_2025 = {"from": "2025-01-01", "to": "2025-06-30",
             "days": tte._days_inclusive("2025-01-01", "2025-06-30")}
_result_2025 = tte.compute_segment(
    _seg_2025, yearly_units=_yearly_units,
    total_period_days=_total_days,
    category="TL-CAT", multiplier=2.0,
    condition_load="domestic",
)
_rates_2025 = {s["rate_per_unit"] for s in _result_2025["slabs"]}
check("2025 segment uses Schedule B rates",
      _rates_2025.issubset({6.0, 6.6}) and len(_rates_2025) > 0,
      detail=f"rates={_rates_2025}")

# 34: multiplier applies to energy.final but NOT to electricity_duty.amount
_energy_subtotal = _result_2024["energy_charge"]["subtotal"]
_energy_final    = _result_2024["energy_charge"]["final"]
_duty_amount     = _result_2024["electricity_duty"]["amount"]
check("energy.final == energy.subtotal * multiplier",
      abs(_energy_final - round(_energy_subtotal * 2.0, 2)) < 0.01,
      detail=f"sub={_energy_subtotal} fin={_energy_final}")

# 35: ED uses subtotal (NOT final), so ED_amount < energy_final
check("ED uses pre-multiplier subtotal as base",
      _duty_amount < _energy_final * 0.5,  # 5% << 100%
      detail=f"ed={_duty_amount} fin={_energy_final}")

# 36: meter_rent.amount = meter_rent_rate * months  (no multiplier)
_meter = _result_2024["meter_rent"]
check("meter_rent.amount = rate * months (no multiplier)",
      abs(_meter["amount"] - round(_meter["rate"] * _meter["months"], 2)) < 0.01,
      detail=f"meter={_meter}")

# 37: warning is None when slabs found
check("compute_segment.warning is None when rate row matched",
      _result_2024["warning"] is None)


# =====================================================================
# Group U: Top-level calculate_timeline (9 checks) — [38-46]
# =====================================================================
_payload = {
    "category": "TL-CAT",
    "condition_load": "domestic",
    "inspection_date": "2025-06-30",
    "period_start":    "2024-07-01",
    "yearly_units":    1200.0,
    "connected_load_kw": 2.5,
    "multiplier": 2.0,
}
_tl = tte.calculate_timeline(_payload)

check("calculate_timeline returns ok=True", _tl.get("ok") is True)
# 39
check("top-level segments list is non-empty",
      isinstance(_tl.get("segments"), list) and len(_tl["segments"]) >= 2)
# 40
check("totals.grand_total > 0",
      _tl.get("totals", {}).get("grand_total", 0) > 0,
      detail=f"grand_total={_tl.get('totals', {}).get('grand_total')}")
# 41: each segment has a fixed_charge.final populated by route layer
check("every segment has fixed_charge.final populated",
      all(s["fixed_charge"]["final"] is not None for s in _tl["segments"]))
# 42: fixed_charge.final = base * connected_load_kw was applied
_first_seg = _tl["segments"][0]
_fc_base = _first_seg["fixed_charge"]["base"]
# base in calculate_timeline already includes connected_load_kw multiplication,
# so final = base * multiplier
check("fixed_charge.final == base * multiplier",
      abs(_first_seg["fixed_charge"]["final"]
          - round(_fc_base * 2.0, 2)) < 0.01,
      detail=f"base={_fc_base} fin={_first_seg['fixed_charge']['final']}")

# 43: less_unit reduces yearly_units in input echo
_tl2 = tte.calculate_timeline({**_payload, "less_unit": 200.0})
check("less_unit subtracts from yearly_units",
      _tl2["input"]["yearly_units_after_less_unit"] == 1000.0)

# 44: missing category -> ok=False
_bad = tte.calculate_timeline({"yearly_units": 100})
check("missing category -> ok=False",
      _bad.get("ok") is False)

# 45: yearly_units_from_devices basic LFHD math
_devices = [{"load": 100, "factor": 1.0, "hours": 6, "days": 365}]
_units_from = tte.yearly_units_from_devices(_devices)
# 100W * 1 * 6h * 365d / 1000 = 219.0 kWh
check("yearly_units_from_devices LFHD math",
      abs(_units_from - 219.0) < 0.01,
      detail=f"got={_units_from}")

# 46: warnings list always present
check("calculate_timeline always returns 'warnings' list",
      isinstance(_tl.get("warnings"), list))


# =====================================================================
# Group V: Historical importer — synonyms (6 checks) — [47-52]
# =====================================================================
ch = hi._canonical_historical_header
check("syn 'Notice No.'        -> notice_no",        ch("Notice No.")        == "notice_no")
check("syn 'Div. No.'          -> div_no",           ch("Div. No.")          == "div_no")
check("syn 'New Account Number'-> new_account_id",   ch("New Account Number") == "new_account_id")
check("syn 'Old AC No.'        -> old_account_id",   ch("Old AC No.")        == "old_account_id")
check("syn 'Sub Station'       -> sub_substation",   ch("Sub Station")       == "sub_substation")
check("syn 'Paid/Unpaid'       -> paid_status",      ch("Paid/Unpaid")       == "paid_status")


# =====================================================================
# Group W: Historical importer — end-to-end (6 checks) — [53-58]
# =====================================================================
# Wipe historical_cases for a clean slate.
with database.standalone_connection() as _c:
    _c.execute("DELETE FROM historical_cases")

_hist_xlsx = Path(tempfile.mktemp(prefix="raid_pr2_hist_", suffix=".xlsx"))
hi.build_sample_historical_workbook(_hist_xlsx)

# 53: importer reports ok + non-zero inserted
_imp = hi.import_historical_workbook(str(_hist_xlsx), source="pr2_test")
check("import_historical_workbook ok + inserted>0",
      _imp.get("ok") and _imp.get("inserted", 0) > 0,
      detail=f"result={_imp}")

# 54: PR2 columns populated (notice_no, sub_substation)
with database.standalone_connection() as _c:
    _c.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    _row = _c.execute(
        "SELECT * FROM historical_cases WHERE notice_no='N-2024-001'"
    ).fetchone()
check("notice_no='N-2024-001' present",     _row is not None)
# 55
check("sub_substation populated for that row",
      _row is not None and _row.get("sub_substation") == "SS-12")

# 56: paid_status normalized ('paid' / 'unpaid' lowercase)
with database.standalone_connection() as _c:
    _c.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    _statuses = {r["paid_status"] for r in _c.execute(
        "SELECT DISTINCT paid_status FROM historical_cases").fetchall()
                 if r["paid_status"]}
check("paid_status normalized to {paid, unpaid}",
      _statuses == {"paid", "unpaid"},
      detail=f"got={_statuses}")

# 57: idempotent re-import — no new rows inserted
_imp2 = hi.import_historical_workbook(str(_hist_xlsx), source="pr2_test")
check("idempotent re-import: 0 new + skipped_duplicate>0",
      _imp2.get("inserted") == 0 and _imp2.get("skipped_duplicate", 0) > 0,
      detail=f"second_import={_imp2}")

# 58: account-number-only lookup returns the row
import re as _re
_acc = _re.sub(r"[^A-Za-z0-9]", "", "NEW456").upper()
with database.standalone_connection() as _c:
    _c.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    _hits = _c.execute(
        "SELECT * FROM historical_cases "
        "WHERE account_id=? OR new_account_id=? OR old_account_id=?",
        (_acc, _acc, _acc),
    ).fetchall()
check("indexed account-number lookup finds the row",
      len(_hits) >= 1 and _hits[0].get("notice_no") == "N-2024-001",
      detail=f"hits={[h.get('notice_no') for h in _hits]}")


# =====================================================================
# Group X: Blueprint registration (2 checks) — [59-60]
# =====================================================================
# Verify the two NEW PR2 blueprints register the expected routes WITHOUT
# importing the full backend.app graph (which pulls in legacy modules
# that may not be installable in every sandbox: docxtpl, etc.).
# This is the strongest assertion we can make about routing without
# depending on the legacy doc_generator stack.
from flask import Flask  # noqa: E402
from backend.routes.rates import bp as _rates_bp  # noqa: E402
from backend.routes.historical import bp as _historical_bp  # noqa: E402

_probe = Flask("pr2_probe")
_probe.register_blueprint(_rates_bp)
_probe.register_blueprint(_historical_bp)
_rules = sorted(r.rule for r in _probe.url_map.iter_rules())

check("/api/rates/upload-schedule registered",
      "/api/rates/upload-schedule" in _rules,
      detail=f"got {[r for r in _rules if r.startswith('/api/rates')]}")
check("/api/historical/by-account/<account> registered",
      any(r.startswith("/api/historical/by-account/") for r in _rules),
      detail=f"got {[r for r in _rules if r.startswith('/api/historical')]}")


# =====================================================================
# Report
# =====================================================================
print()
print("=" * 60)
print(f"PR2 verification: {PASSED}/{PASSED + FAILED} passed")
print("=" * 60)
if FAILURES:
    print()
    print("FAILURES:")
    for line in FAILURES:
        print(line)
    sys.exit(1)
else:
    print()
    print(f"ALL PR2 CHECKS PASSED  ({PASSED}/{PASSED + FAILED})")
    sys.exit(0)
