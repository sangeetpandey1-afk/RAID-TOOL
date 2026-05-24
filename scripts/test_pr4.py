"""
PR4 verification harness — 50 deterministic checks.

Validates PR4 deliverables and ONLY PR4 deliverables:

  Group P  PR1 + PR2 + PR3 regression guards          [01-03]
  Group Q  services/offense_lookup invariants         [04-15]
  Group R  Indexed lookup hits all 3 account columns  [16-20]
  Group S  /api/offense routes + responses            [21-28]
  Group T  Frontend HTML additions                     [29-36]
  Group U  Frontend CSS scoping                        [37-40]
  Group V  Frontend JS sanity                          [41-45]
  Group W  Account-number-only invariant               [46-50]

Validates AGAINST:
  * backend.services.offense_lookup
  * backend.routes.offense
  * frontend/index.html (#offenseVerify card additions)
  * frontend/static/offense_verify.{js,css}

Usage
-----
    python -m scripts.test_pr4
    python -m scripts.test_pr4 /tmp/raid_pr4.db

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
    prefix="raid_pr4_", suffix=".db",
)
if os.path.exists(_DB_PATH):
    os.unlink(_DB_PATH)
os.environ["RAID_DB_PATH"] = _DB_PATH

# Now safe to import backend modules.
from flask import Flask  # noqa: E402

from backend import database  # noqa: E402
from backend.services import offense_lookup as ol  # noqa: E402
from backend.routes.offense import bp as offense_bp  # noqa: E402

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
# Group P: regression guards (3 checks) — [01-03]
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
check("PR3 harness still passes (regression)", _run_harness("test_pr3"))


# =====================================================================
# Setup test data — used by Groups Q, R, W
# =====================================================================
database.init_schema()

# Seed deterministic historical_cases rows. Notice the variety:
#   - 2 rows on canonical account "AC100" (one OLD + one NEW field)
#   - 1 row whose ONLY account-bearing field is `account_id` (legacy)
#   - 1 row whose ONLY account-bearing field is `new_account_id`
#   - 1 row whose ONLY account-bearing field is `old_account_id`
#   - 1 unrelated row that should NEVER match (different account)
_FIELDS = (
    "div_no, name, father_name, village, account_id, "
    "case_date, assessment_amount, fir_number, section, source, "
    "notice_no, address, use_name, user_father_name, sub_substation, "
    "old_account_id, new_account_id, category, irregularity, paid_status"
)
_PLACEHOLDERS = ",".join(["?"] * 20)
_INSERT_SQL = (
    f"INSERT INTO historical_cases ({_FIELDS}) VALUES ({_PLACEHOLDERS})"
)

with database.standalone_connection() as _c:
    _c.execute("DELETE FROM historical_cases")
    # Row 1 — both account fields set, AC100
    _c.execute(_INSERT_SQL, (
        "DIV-1", "RAM KUMAR", "SHYAM LAL", "VILLAGE-A", "AC100",
        "2024-05-12", 12500.0, None, "135", "test",
        "N-2024-001", "VPO RAMPUR", "RAM KUMAR", "SHYAM LAL", "SS-12",
        "OLD-AC100", "AC100", "LMV-1", "Direct theft", "unpaid",
    ))
    # Row 2 — same account, different notice
    _c.execute(_INSERT_SQL, (
        "DIV-1", "RAM KUMAR", "SHYAM LAL", "VILLAGE-A", "AC100",
        "2025-01-04", 8000.0, None, "138", "test",
        "N-2025-007", "VPO RAMPUR", "RAM KUMAR", "SHYAM LAL", "SS-12",
        "OLD-AC100", "AC100", "LMV-1", "Meter tampering", "paid",
    ))
    # Row 3 — only legacy account_id has the value (account ABC1)
    _c.execute(_INSERT_SQL, (
        "DIV-2", "GEETA DEVI", "MOHAN LAL", "VILLAGE-B", "ABC1",
        "2025-06-20", 5500.0, None, "135", "test",
        "N-2025-101", "VPO MOHANGANJ", "GEETA DEVI", "MOHAN LAL", "SS-08",
        None, None, "LMV-1", "—", "unpaid",
    ))
    # Row 4 — only NEW_ACCOUNT_ID has the value (account NEW2)
    _c.execute(_INSERT_SQL, (
        "DIV-2", "AJAY SINGH", "BIRENDRA SINGH", "VILLAGE-C", None,
        "2025-08-15", 21500.0, None, "135", "test",
        "N-2025-019", "VPO AJAYPUR", "AJAY SINGH", "BIRENDRA SINGH", "SS-15",
        None, "NEW2", "LMV-2", "Commercial use on domestic", "unpaid",
    ))
    # Row 5 — only OLD_ACCOUNT_ID has the value (account OLD3)
    _c.execute(_INSERT_SQL, (
        "DIV-3", "POOJA RANI", "RAVI KUMAR", "VILLAGE-D", None,
        "2024-11-01", 3000.0, None, "135", "test",
        "N-2024-099", "VPO POOJANGAR", "POOJA RANI", "RAVI KUMAR", "SS-04",
        "OLD3", None, "LMV-1", "—", "paid",
    ))
    # Row 6 — UNRELATED account, must never match
    _c.execute(_INSERT_SQL, (
        "DIV-9", "RAM KUMAR", "SHYAM LAL", "VILLAGE-A", "ZZZ999",
        "2024-09-09", 99999.0, None, "135", "test",
        "N-2024-999", "VPO ZZZ", "RAM KUMAR", "SHYAM LAL", "SS-99",
        None, None, "LMV-1", "Direct theft", "paid",
    ))
    _c.commit()


# =====================================================================
# Group Q: offense_lookup invariants (12 checks) — [04-15]
# =====================================================================
# 04: empty input -> safe empty result
_e = ol.lookup_by_account("")
check("empty account -> matched_count=0",
      _e.get("matched_count") == 0
      and _e.get("rows") == [])
# 05: account normalization strips punctuation + uppercases
_n = ol._normalize_account("ac-100")
check("_normalize_account('ac-100') == 'AC100'",
      _n == "AC100")

# 06: account that doesn't exist -> 0 hits, suggested_multiplier == 2
_z = ol.lookup_by_account("DOES_NOT_EXIST")
check("missing account: matched_count=0",  _z["matched_count"] == 0)
# 07
check("missing account: suggested_multiplier == 2.0",
      _z["suggested_multiplier"] == 2.0)
# 08
check("missing account: is_repeat == False", _z["is_repeat"] is False)

# 09: AC100 -> 2 hits
_h = ol.lookup_by_account("AC100")
check("AC100 -> matched_count == 2",
      _h["matched_count"] == 2,
      detail=f"got={_h['matched_count']} rows={[r.get('notice_no') for r in _h['rows']]}")
# 10
check("AC100 -> is_repeat == True",   _h["is_repeat"] is True)
# 11: with PR1 multipliers in system_config (2 / 6, threshold 2),
#     1 prior + current = 2 total -> repeat -> 6
check("AC100 (1+ prior) -> suggested_multiplier == 6.0",
      _h["suggested_multiplier"] == 6.0,
      detail=f"got={_h['suggested_multiplier']}")

# 12: rows ordered by case_date DESC (newest first)
_dates = [r["case_date"] for r in _h["rows"]]
check("rows ordered case_date DESC",
      _dates == sorted(_dates, reverse=True),
      detail=f"dates={_dates}")

# 13: ALL 15 PR4 display fields present in every row
PR4_FIELDS = {
    "notice_no", "div_no", "case_date", "name", "father_name",
    "use_name", "user_father_name", "address", "sub_substation",
    "assessment_amount", "old_account_id", "new_account_id",
    "category", "irregularity", "paid_status",
}
check("every row exposes all 15 PR4 display fields",
      all(PR4_FIELDS.issubset(set(r.keys())) for r in _h["rows"]),
      detail=f"missing on first row: "
             f"{PR4_FIELDS - set(_h['rows'][0].keys()) if _h['rows'] else PR4_FIELDS}")

# 14: total_assessment correctly summed (12500 + 8000 = 20500)
check("total_assessment summed across rows",
      abs(_h["total_assessment"] - 20500.0) < 0.01,
      detail=f"got={_h['total_assessment']}")

# 15: first/last offense dates correct
check("first/last offense dates correct",
      _h["first_offense_date"] == "2024-05-12"
      and _h["last_offense_date"]  == "2025-01-04",
      detail=f"first={_h['first_offense_date']} last={_h['last_offense_date']}")


# =====================================================================
# Group R: indexed lookup matches all 3 account columns (5) — [16-20]
# =====================================================================
# 16: legacy account_id-only row (ABC1)
_r1 = ol.lookup_by_account("ABC1")
check("legacy account_id column hit (ABC1)",
      _r1["matched_count"] == 1
      and _r1["rows"][0]["notice_no"] == "N-2025-101")
# 17: new_account_id-only row (NEW2)
_r2 = ol.lookup_by_account("NEW2")
check("new_account_id-only column hit (NEW2)",
      _r2["matched_count"] == 1
      and _r2["rows"][0]["notice_no"] == "N-2025-019")
# 18: old_account_id-only row (OLD3)
_r3 = ol.lookup_by_account("OLD3")
check("old_account_id-only column hit (OLD3)",
      _r3["matched_count"] == 1
      and _r3["rows"][0]["notice_no"] == "N-2024-099")
# 19: account formatting variations all normalize to same canonical form
_r4a = ol.lookup_by_account("AC-100")
_r4b = ol.lookup_by_account("ac/100")
_r4c = ol.lookup_by_account("AC 100")
check("normalized lookups for AC-100 / ac/100 / 'AC 100' all match AC100",
      _r4a["matched_count"] == 2
      and _r4b["matched_count"] == 2
      and _r4c["matched_count"] == 2)
# 20: EXPLAIN QUERY PLAN names at least one of our indexes
_plan = ol.explain_lookup_plan("AC100")
_plan_text = " ".join(str(r.get("detail") or "") for r in _plan)
check("EXPLAIN QUERY PLAN references hist account index",
      ("idx_hist_account"     in _plan_text
       or "idx_hist_old_account" in _plan_text
       or "idx_hist_new_account" in _plan_text),
      detail=f"plan={_plan_text}")


# =====================================================================
# Group S: /api/offense routes (8 checks) — [21-28]
# =====================================================================
_app = Flask("pr4_probe")
_app.register_blueprint(offense_bp)
_rules = sorted(r.rule for r in _app.url_map.iter_rules())

check("/api/offense/lookup registered",
      "/api/offense/lookup" in _rules)
check("/api/offense/multiplier-suggest registered",
      "/api/offense/multiplier-suggest" in _rules)
check("/api/offense/explain-plan registered",
      "/api/offense/explain-plan" in _rules)

_client = _app.test_client()

# 24: /lookup without account -> 400
_resp = _client.get("/api/offense/lookup")
check("/lookup without account -> 400",
      _resp.status_code == 400)

# 25: /lookup hits AC100 -> JSON envelope ok=True with 2 rows
_resp = _client.get("/api/offense/lookup?account=AC100")
_payload = _resp.get_json() or {}
_data = (_payload.get("data") or {})
check("/lookup?account=AC100 -> 200 + 2 rows",
      _resp.status_code == 200
      and _payload.get("ok") is True
      and _data.get("matched_count") == 2)

# 26: response includes suggested_multiplier
check("/lookup response includes suggested_multiplier",
      isinstance(_data.get("suggested_multiplier"), (int, float)))

# 27: /multiplier-suggest gives the same value
_resp = _client.get("/api/offense/multiplier-suggest?account=AC100")
_data2 = ((_resp.get_json() or {}).get("data") or {})
check("/multiplier-suggest matches /lookup's suggested_multiplier",
      _data2.get("suggested_multiplier") == _data.get("suggested_multiplier"))

# 28: /explain-plan returns plan rows + indexes_seen list
_resp = _client.get("/api/offense/explain-plan")
_data3 = ((_resp.get_json() or {}).get("data") or {})
check("/explain-plan returns plan_rows list",
      isinstance(_data3.get("plan_rows"), list)
      and len(_data3.get("plan_rows") or []) > 0)


# =====================================================================
# Group T: Frontend HTML additions (8 checks) — [29-36]
# =====================================================================
_html = (_REPO_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

check("HTML adds #offenseVerify card",
      'id="offenseVerify"' in _html)
check("HTML uses data-state attribute (5-state machine)",
      'data-state="empty"' in _html)
check("HTML #offenseVerify lives near #f_account, NOT in a different panel",
      _html.find('id="f_account"') < _html.find('id="offenseVerify"')
      < _html.find('id="panel-cases"'))
check("HTML adds #ovStatus span",
      'id="ovStatus"' in _html)
check("HTML adds #ovToggle button (expand/collapse)",
      'id="ovToggle"' in _html)
check("HTML adds #ovBody container",
      'id="ovBody"' in _html)
check("HTML adds offense_verify.js script tag",
      'src="/frontend/static/offense_verify.js"' in _html)
check("HTML adds offense_verify.css link tag",
      'href="/frontend/static/offense_verify.css"' in _html)


# =====================================================================
# Group U: Frontend CSS scoping (4 checks) — [37-40]
# =====================================================================
_css = (_REPO_ROOT / "frontend" / "static" / "offense_verify.css").read_text(
    encoding="utf-8")

check("offense_verify.css scopes EVERY rule under #offenseVerify",
      _css.count("#offenseVerify") >= 5
      and re.search(r"^\s*\.[a-z]", _css, re.MULTILINE) is None,
      detail="found unscoped class selector at top level")
check("offense_verify.css defines [data-state='hits'] state",
      '[data-state="hits"]' in _css)
check("offense_verify.css defines [data-state='no_hits'] state",
      '[data-state="no_hits"]' in _css)
# 40: Sanity: no GLOBAL input/select/button rule that could leak
_global_input = re.search(r"^\s*input\s*\{", _css, re.MULTILINE)
_global_btn = re.search(r"^\s*button\s*\{", _css, re.MULTILINE)
check("offense_verify.css has no unscoped global element rules",
      _global_input is None and _global_btn is None)


# =====================================================================
# Group V: Frontend JS sanity (5 checks) — [41-45]
# =====================================================================
_js = (_REPO_ROOT / "frontend" / "static" / "offense_verify.js").read_text(
    encoding="utf-8")

check("offense_verify.js calls /api/offense/lookup",
      "/api/offense/lookup" in _js)
check("offense_verify.js binds debounced #f_account input listener",
      "#f_account" in _js
      and 'addEventListener("input"' in _js
      and "DEBOUNCE_MS" in _js)
check("offense_verify.js renders all 15 PR4 display fields in TARGET_FIELDS",
      all(f'"{k}"' in _js for k in PR4_FIELDS),
      detail="missing in TARGET_FIELDS: "
             + repr([k for k in PR4_FIELDS if ('"' + k + '"') not in _js]))
check("offense_verify.js wires #ovApplyMult to fill #f_multiplier",
      'ovApplyMult' in _js and '#f_multiplier' in _js
      and '#chk_multiplier' in _js)
# 45: Hard invariant — JS does NOT call any name/fuzzy lookup API
_forbidden = ("fuzzy_match", "name=", "father=", "village=", "/api/search",
              "/api/consumers/")
_offending = [t for t in _forbidden if t in _js]
check("offense_verify.js does NOT call name/fuzzy lookup endpoints",
      not _offending,
      detail=f"forbidden tokens found: {_offending}")


# =====================================================================
# Group W: Account-number-only invariant (5 checks) — [46-50]
# =====================================================================
# 46: Looking up the unrelated row's NAME ('RAM KUMAR') as if it were an
#     account must NOT match it. Verifies the lookup never falls back to
#     name. Account normalization will strip the space → "RAMKUMAR".
_w1 = ol.lookup_by_account("RAM KUMAR")
check("name as account -> 0 hits (account-only invariant)",
      _w1["matched_count"] == 0,
      detail=f"got={[r.get('notice_no') for r in _w1['rows']]}")

# 47: Looking up a father-name as account -> 0 hits
_w2 = ol.lookup_by_account("SHYAM LAL")
check("father-name as account -> 0 hits",
      _w2["matched_count"] == 0)

# 48: Looking up a village as account -> 0 hits
_w3 = ol.lookup_by_account("VILLAGE-A")
check("village as account -> 0 hits",
      _w3["matched_count"] == 0)

# 49: services/offense_lookup.py source contains NO rapidfuzz / fuzz IMPORT
#     OR call. Docstring mentions of "no fuzzy" are allowed and welcomed.
_svc_src = (_REPO_ROOT / "backend" / "services" /
            "offense_lookup.py").read_text(encoding="utf-8")
_forbidden_patterns = (
    re.compile(r"^\s*(from\s+rapidfuzz|import\s+rapidfuzz)", re.MULTILINE),
    re.compile(r"\bfuzz\.", ),                # fuzz.token_set_ratio etc.
    re.compile(r"\bfuzzy_match\s*\("),         # any fuzzy_match() call
)
_offending = [p.pattern for p in _forbidden_patterns if p.search(_svc_src)]
check("offense_lookup source contains no fuzzy / rapidfuzz import or call",
      not _offending,
      detail=f"forbidden patterns matched: {_offending}")

# 50: SQL is parameterized with exactly 3 placeholders = the 3 indexed
#     account columns. No LIKE on name fields.
_sql = ol._LOOKUP_SQL
check("lookup SQL uses 3 placeholders + has no LIKE / name match",
      _sql.count("?") == 3
      and " LIKE " not in _sql.upper()
      and "father_name" not in _sql.split("WHERE")[1].upper().lower(),
      detail=f"sql_where={_sql.split('WHERE')[1] if 'WHERE' in _sql else 'no WHERE'}")


# =====================================================================
# Report
# =====================================================================
print()
print("=" * 60)
print(f"PR4 verification: {PASSED}/{PASSED + FAILED} passed")
print("=" * 60)
if FAILURES:
    print()
    print("FAILURES:")
    for line in FAILURES:
        print(line)
    sys.exit(1)
else:
    print()
    print(f"ALL PR4 CHECKS PASSED  ({PASSED}/{PASSED + FAILED})")
    sys.exit(0)
