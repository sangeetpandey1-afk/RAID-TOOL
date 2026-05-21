#!/usr/bin/env python3
"""
Full end-to-end test of the RAID system using Flask test client.
Tests every major flow without needing a running server.
"""
import json
import sys
import os

# Use a fresh test DB
os.environ["RAID_DB_PATH"] = "/tmp/raid_test.db"
if os.path.exists("/tmp/raid_test.db"):
    os.remove("/tmp/raid_test.db")

# Suppress import logs
import logging
logging.getLogger().setLevel(logging.ERROR)

PASS, FAIL = "PASS", "FAIL"
results = []


def test(name, condition, details=""):
    status = PASS if condition else FAIL
    results.append((status, name, details))
    icon = "[OK]" if condition else "[XX]"
    print(f"{icon} {name}")
    if details and not condition:
        print(f"     -> {details}")
    return condition


def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")



# ============================================================
section("1. APP STARTUP")
# ============================================================
from backend.app import app
client = app.test_client()
test("App starts without errors", app is not None)
_n_routes = len(list(app.url_map.iter_rules()))
test("Has 70+ routes registered", _n_routes >= 70, f"got {_n_routes} routes")


# ============================================================
section("2. HEALTH CHECK")
# ============================================================
r = client.get("/api/health")
test("GET /api/health returns 200", r.status_code == 200, f"status={r.status_code}")
test("Health response is JSON", r.is_json)


# ============================================================
section("3. CREATE A CASE")
# ============================================================
case_payload = {
    "account_number": "TEST/12345",
    "name": "Test Consumer",
    "father_name": "Test Father",
    "village": "Test Village",
    "mobile": "9876543210",
    "user_name": "Test User",
    "user_father": "Test Father",
    "section": "135",
    "inspection_date": "2025-05-21",
    "checking_type": "Regular",
    "je_name": "JE Test",
    "connected_load_kw": 2.5,
    "devices": [
        {"name": "Bulb", "L": 100, "F": 1, "H": 8, "D": 365},
        {"name": "Fan", "L": 75, "F": 1, "H": 12, "D": 365},
    ],
    "multiplier": 2,
}
r = client.post("/api/cases", json=case_payload)
test("POST /api/cases creates case", r.status_code == 200, f"status={r.status_code}")
case_data = r.get_json() if r.is_json else {}
case_id = case_data.get("data", {}).get("case", {}).get("case_id", "")
test(f"Case ID generated", bool(case_id), f"case_id={case_id}")
total_assessment = case_data.get("data", {}).get("case", {}).get("total_assessment", 0)
test(f"Assessment calculated (₹{total_assessment})", total_assessment > 0)


# ============================================================
section("4. SEARCH CASES")
# ============================================================
r = client.get(f"/api/cases/search?q=Test")
test("Search by name works", r.status_code == 200)
data = r.get_json().get("data", []) if r.is_json else []
test("Search returns the case", len(data) >= 1, f"found {len(data)}")

r = client.get(f"/api/cases/search?status=open")
test("Filter by status works", r.status_code == 200)


# ============================================================
section("5. GET CASE WITH FULL DETAILS")
# ============================================================
r = client.get(f"/api/cases/{case_id}")
test("GET case detail returns 200", r.status_code == 200)
body = r.get_json().get("data", {}) if r.is_json else {}
test("Has payment_summary", "payment_summary" in body)
test("Has inquiry_summary", "inquiry_summary" in body)
test("Has timeline", "timeline" in body)
test("Has documents list", "documents" in body)


# ============================================================
section("6. COMPOUNDING - MANUAL")
# ============================================================
r = client.post(f"/api/cases/{case_id}/compounding", json={"amount": 18000})
test("Manual compounding sets ₹18000", r.status_code == 200)
body = r.get_json().get("data", {}) if r.is_json else {}
test("Mode is 'manual'", body.get("mode") == "manual")
test("Amount stored correctly", body.get("compounding_amount") == 18000)


# ============================================================
section("7. COMPOUNDING - AUTO CALCULATION")
# ============================================================
r = client.post(f"/api/cases/{case_id}/compounding", json={"load_w": 2122})
test("Auto compounding works", r.status_code == 200)
body = r.get_json().get("data", {}) if r.is_json else {}
test("billable_kw = ceil(2.122) = 3", body.get("billable_kw") == 3)


# ============================================================
section("8. ADD INQUIRY")
# ============================================================
r = client.post(f"/api/cases/{case_id}/inquiries", json={
    "caller_name": "Ram Prasad",
    "mobile_number": "9876543210",
    "relationship": "self",
    "amount_quoted": 12000,
    "remarks": "Inquiry test",
})
test("Add inquiry works", r.status_code == 200)


# ============================================================
section("9. RECORD PAYMENT (full)")
# ============================================================
# Set total_assessment + compounding so balance check works
r = client.get(f"/api/cases/{case_id}")
case_data = r.get_json().get("data", {}).get("case", {})
total = (case_data.get("total_assessment") or 0) + (case_data.get("compounding_amount") or 0)

r = client.post(f"/api/cases/{case_id}/payments", json={
    "amount": total,
    "payment_type": "full",
    "component": "assessment",
    "receipt_number": "TEST-RCP-001",
    "payment_method": "cash",
})
test("Payment recorded", r.status_code == 200)
body = r.get_json().get("data", {}) if r.is_json else {}
test("Marked as fully_paid", body.get("summary", {}).get("fully_paid") == True)
test("Case status -> paid", body.get("case_status") == "paid")
test("NOC auto-generated", body.get("noc") is not None)


# ============================================================
section("10. APPEAL FILING")
# ============================================================
r = client.post(f"/api/cases/{case_id}/appeals", json={
    "appellant_name": "Test Appellant",
    "appellant_relation": "self",
    "appeal_reason": "Assessment too high",
})
test("Appeal filed", r.status_code == 200)
appeal_id = r.get_json().get("data", {}).get("appeal_id") if r.is_json else None
test(f"Appeal ID generated", appeal_id is not None)

# List appeals
r = client.get(f"/api/cases/{case_id}/appeals")
test("List appeals works", r.status_code == 200)


# ============================================================
section("11. APPEAL PROCEEDING")
# ============================================================
if appeal_id:
    r = client.post(f"/api/cases/{case_id}/appeals/{appeal_id}/proceedings", json={
        "officer_name": "SDO",
        "summary": "Heard the consumer",
        "order_passed": "Reduce devices",
        "outcome": "partial_relief",
    })
    test("Add proceeding works", r.status_code == 200)


# ============================================================
section("12. APPEAL REVISION")
# ============================================================
if appeal_id:
    r = client.post(f"/api/cases/{case_id}/appeals/{appeal_id}/revise", json={
        "multiplier": 2,
        "less_unit": 100,
        "revised_by": "SDO",
    })
    test("Revision after appeal works", r.status_code == 200)


# ============================================================
section("13. DOCUMENT GENERATION")
# ============================================================
for kind in ["provisional_consumer", "section3", "noc", "envelope"]:
    r = client.post(f"/api/cases/{case_id}/document/{kind}")
    test(f"Generate {kind}", r.status_code == 200)


# ============================================================
section("14. DOCUMENT PREVIEW (HTML)")
# ============================================================
r = client.get(f"/api/cases/{case_id}/preview/section3")
test("Generate+preview section3", r.status_code in (200, 302))


# ============================================================
section("15. DOCUMENT COMBINE (all in one)")
# ============================================================
r = client.get(f"/api/cases/{case_id}/documents/combine")
test("Combine all documents", r.status_code == 200,
     f"status={r.status_code}, ct={r.content_type}")
test("Returns docx file", "wordprocessing" in (r.content_type or ""))


# ============================================================
section("16. EXCEL EXPORT")
# ============================================================
r = client.get("/api/export/cases")
test("Export cases as Excel", r.status_code in (200, 404))  # 404 if empty after filter


# ============================================================
section("17. MOBILE UI")
# ============================================================
r = client.get("/mobile/")
test("Mobile app page loads", r.status_code == 200)
test("Returns HTML", "html" in (r.content_type or "").lower())

r = client.get("/mobile/qr")
test("QR page loads", r.status_code == 200)


# ============================================================
section("18. UPLOAD CATEGORIES")
# ============================================================
r = client.get("/api/upload/categories")
test("Upload categories endpoint", r.status_code == 200)
cats = r.get_json().get("data", {}).get("categories", []) if r.is_json else []
test(f"Has 12 categories", len(cats) == 12, f"got {len(cats)}")


# ============================================================
section("19. OFFENSE COUNT")
# ============================================================
r = client.get("/api/offense_count/TEST12345")
test("Offense count endpoint", r.status_code == 200, f"status={r.status_code}")


# ============================================================
section("FINAL RESULTS")
# ============================================================
total = len(results)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = total - passed

print(f"\nTotal:  {total}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")

if failed:
    print("\nFAILURES:")
    for s, n, d in results:
        if s == FAIL:
            print(f"  - {n}: {d}")
    sys.exit(1)
else:
    print("\nALL TESTS PASSED!")
    sys.exit(0)
