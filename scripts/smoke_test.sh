#!/usr/bin/env bash
# End-to-end smoke test against a running server (default localhost:5000).
# Run with:  bash scripts/smoke_test.sh
set -e
HOST="${HOST:-http://127.0.0.1:5000}"
hr() { echo "----------- $1 -----------"; }

hr "1. health"
curl -s "$HOST/api/health" | python3 -m json.tool

hr "2. devices (sample)"
curl -s "$HOST/api/devices?category=Cooling" | python3 -m json.tool | head -40

hr "3. live calculate"
curl -s -X POST "$HOST/api/calculate" -H 'Content-Type: application/json' \
  -d '{"section":"135","category":"LMV-1","connected_load_kw":2.122,
       "devices":[
         {"name":"Bulb / LED","load":9,"factor":1,"hours":6,"days":365},
         {"name":"AC 1.5 Ton","load":1800,"factor":1,"hours":4,"days":120}
       ]}' | python3 -m json.tool

hr "4. compounding (Section 152)"
curl -s -X POST "$HOST/api/compounding" -H 'Content-Type: application/json' \
  -d '{"load_w":2122,"category":"LMV-1","section":"135"}' | python3 -m json.tool

hr "5. save case"
CASE_RESP=$(curl -s -X POST "$HOST/api/cases" -H 'Content-Type: application/json' \
  -d '{
    "account_number":"AC-TEST-001",
    "name":"राम कुमार","father_name":"श्याम कुमार","village":"रामपुर",
    "post_office":"रामपुर","pin_code":"244901","mobile":"9876543210",
    "category":"LMV-1","supply_type":"Domestic","div_code":"D-01",
    "section":"135","inspection_date":"2026-05-15",
    "checking_type":"Vigilance","je_name":"J.E. Sharma",
    "sub_substation":"33/11kV Rampur",
    "connected_load_kw":2.122,
    "devices":[
      {"name":"Bulb / LED","load":9,"factor":1,"hours":6,"days":365},
      {"name":"Ceiling Fan","load":75,"factor":1,"hours":12,"days":365},
      {"name":"AC 1.5 Ton","load":1800,"factor":1,"hours":4,"days":120}
    ],
    "calculate_compounding":true,
    "created_by":"smoke_test"
  }')
echo "$CASE_RESP" | python3 -m json.tool | head -40
CASE_ID=$(echo "$CASE_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['case']['case_id'])")
echo "Created case_id: $CASE_ID"

hr "6. fetch case"
curl -s "$HOST/api/cases/$CASE_ID" | python3 -m json.tool | head -40

hr "7. record payment (partial)"
curl -s -X POST "$HOST/api/cases/$CASE_ID/payments" -H 'Content-Type: application/json' \
  -d '{"amount":5000,"payment_type":"partial","component":"assessment",
       "receipt_number":"RC-001","payment_method":"cash","user":"test_user"}' \
  | python3 -m json.tool

hr "8. add inquiry"
curl -s -X POST "$HOST/api/cases/$CASE_ID/inquiries" -H 'Content-Type: application/json' \
  -d '{"caller_name":"Mohan","mobile_number":"9999999999","relationship":"relative",
       "amount_quoted":15000,"remarks":"Asked for settlement","user":"test_user"}' \
  | python3 -m json.tool

hr "9. add provisional notice"
curl -s -X POST "$HOST/api/cases/$CASE_ID/notices" -H 'Content-Type: application/json' \
  -d '{"notice_type":"provisional","notice_number":"PN-2025-001",
       "user":"test_user"}' | python3 -m json.tool

hr "10. generate documents"
for k in provisional_consumer provisional_office section3 deposit_slip envelope compounding_order; do
  echo "  -> $k"
  curl -s -X POST "$HOST/api/cases/$CASE_ID/document/$k" \
    -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool | head -8
done

hr "11. dashboard summary"
curl -s "$HOST/api/dashboard/summary" | python3 -m json.tool

hr "12. consumer search (fuzzy)"
curl -s "$HOST/api/consumers/search?name=राम&village=रामपुर" \
  | python3 -m json.tool | head -30

hr "13. consumer offense check"
curl -s "$HOST/api/consumers/AC-TEST-001/offense-check" | python3 -m json.tool

hr "14. master files diagnostic"
curl -s "$HOST/api/master_files" | python3 -m json.tool

hr "15. import_all (no files yet, should report cleanly, NOT 500)"
curl -s -X POST "$HOST/api/import_all_master_data" | python3 -m json.tool | head -40

hr "16. backup status"
curl -s "$HOST/api/backup/status" | python3 -m json.tool

hr "17. backup now (local zip)"
curl -s -X POST "$HOST/api/backup/now" -H 'Content-Type: application/json' -d '{}' \
  | python3 -m json.tool | head -30

hr "18. backup list"
curl -s "$HOST/api/backup/list" | python3 -m json.tool | head -20

hr "19. report — cases.xlsx"
curl -s "$HOST/api/reports/cases.xlsx" | python3 -m json.tool

hr "20. report — payments.xlsx"
curl -s "$HOST/api/reports/payments.xlsx" | python3 -m json.tool

hr "21. report — dashboard.pdf"
curl -s "$HOST/api/reports/dashboard.pdf" | python3 -m json.tool

hr "22. report list"
curl -s "$HOST/api/reports/list" | python3 -m json.tool | head -30

hr "23. document kinds"
curl -s "$HOST/api/document/kinds" | python3 -m json.tool

hr "DONE"
echo "All endpoints responded successfully."
