---
inclusion: always
---

# विद्युत चोरी रेड प्रबंधन सिस्टम — Project Specification

## Project Overview
Comprehensive Excel + Python based Raid Management System for managing electricity-theft cases (UPPCL workflow). System works offline with an Excel/VBA frontend and a Python Flask + SQLite backend. All legal documents (notices, slips) are auto-generated with Krutidev Hindi font preservation.

**Local working directory on user's Windows machine:** `D:\raid tool\`
**Sandbox / GitHub mirror:** this repository

## Architecture
- **Frontend Layer:** Excel `.xlsm` with VBA macros (HTTP API client)
- **Backend:** Python Flask service on `http://localhost:5000`
- **Database:** SQLite with optimized indexes
- **Documents:** `python-docx` (Word) + ReportLab (PDF)
- **Cloud Sync:** Google Drive API (Phase 4)

## Master Data Sources
1. **ALL DATA.xlsx** — 8,956 historical cases (Krutidev Hindi text). Fields: `div no, Name, father name, village, Account Id, Date, assessment, FIR, dhara`
2. **raid excell 2526 Copy.xlsx** — 24,195 active cases. Fields: `ONLINE NO, div no, Name, father name, village, connection no, L/F/H/D per device, assessment total, notice tracking`
3. **raid_master_data.xlsx** — 69,163 consumer master records. Fields: `ACCT_ID, DIV_CODE, NAME, FATHER_NAME, ADDRESS, SUPPLY_TYPE, LOAD, LOAD_UNIT, MOBILE_NO, CON_STATUS`
4. **device list.xlsx** — 38 pre-defined devices across categories (Lighting, Cooling, Heating, Washing, Kitchen, Pumping, Electronics, Misc)
5. **slab_rates.xlsx** — 24 rate structures across LMV-1 to LMV-9. Fields: `Category, SlabStart, SlabEnd, RatePerUnit, FixedCharge, DutyPercent, Condition, EffectiveDate`
6. **Account Mapping Sheet** (to be built) — links old↔new account numbers via SC Number

## Core Calculation Rules

### LFHD Formula
```
Units = (Load × Factor × Hours × Days) / 1000
```
Devices are unlimited per case. Each device's L, F, H, D are individually editable.

### Section-wise Days
- **Section 135** (Theft): default 365 days
- **Section 138** (TD): TD date → current date (precise)
- **Section 126** (UUE): special provision
- **Other**: 365 default, manually overridable

### Assessment Components
- **Fixed Charges** = ConnectedLoad × FixedRate × Months × Multiplier
- **Energy Charges** = slab-wise (0–100, 101–200, 201+) × rate × Multiplier
- **Electricity Duty (ED)** = EnergyChargesBase × ED%  (5% / 7.5% / 0% per category)
- **Less Unit** (optional): subtract 1 year's consumed units; section visible in notice **only if entry exists**

### Multiplier Logic
- First offense: **2×** (default, editable)
- Repeat offense (≥2 cases): **6×** (default, editable)

### Section 152 Compounding (LT) — IMPORTANT BUSINESS RULE
- Charged "per KW or part thereof"
- **Always round UP** to next integer KW
- Example: load 2122 W = 2.122 KW → billable **3 KW**
- Justification text auto-inserted in order:
> "निरीक्षण के समय उपभोक्ता परिसर पर 2122 Watt अर्थात लगभग 2.122 KW भार पाया गया, जो 2 KW से अधिक होकर अतिरिक्त भाग (part thereof) में आता है। अतः धारा 152 में वर्णित 'per KW or part thereof' प्रावधान के अनुसार Compounding की गणना 3 KW के आधार पर की गई है।"

## Offense Detection (Multi-Level Priority)
1. **Direct Account Number** (95% confidence)
2. **SC Number cross-reference** (90%)
3. **Old↔New account mapping** (85%)
4. **Fuzzy Name + Father + Village** with Krutidev compatibility (70%)

Validation: minimum 1-day gap between cases, location consistency.

## Document Generation Catalog
1. **Provisional Notice — Consumer Copy** (full transparency, slab-wise breakdown, device names visible)
2. **Provisional Notice — Office Copy** (LFHD focus, device names hidden)
3. **Section 3 Notice** (30-day demand, +₹25 admin fee)
4. **Section 5 Notice** (Revenue Recovery via Collector/Tehsildar)
5. **Thanedari Copy** (Police, SE office, Corporate advocate)
6. **Envelope** (printer-optimized address)
7. **Deposit Slip** (with mandatory reminder text about submitting receipt copy to Khand office)

All templates use Krutidev font; placeholders use `«FIELD»` style; static text preserved.

### Mail Merge Field Catalog (excerpt)
**Core:** `«Div_no» «ONLINE_NO» «disno» «ESIFO» «CH_no» «dis_date» «Date» «ASSESMENT_TOTAL» «date1» «time11» «revice»`

**Sec 3:** `«div_no» «NAME» «father_nane» «USER_NAME» «USERS_FATHER» «VILLAGE» «post» «pin_code» «conaction_no» «sec3_no» «sec3_date» «sec3_amaunt» «total_sec3»`

**Sec 5:** `«rc_number» «letter_number» «current_date» «consumer_name» «consumer_father» «village» «post_office» «tehsil» «district» «outstanding_amount» «checking_report_number» «checking_date» «demand_notice_number» «demand_notice_date» «grid_number» «grid_date»`

**Consumer-copy calc:** `«DEVICE_n_NAME» «DEVICE_n_LOAD» «DEVICE_n_UNITS» «CONNECTED_LOAD» «FIXED_RATE» «MONTHS» «FIXED_AMOUNT» «SLAB_n_UNITS» «SLAB_n_RATE» «SLAB_n_AMOUNT» «TOTAL_UNITS» «ED_RATE_PERCENT» «ED_AMOUNT» «FINAL_FIXED_CHARGES» «FINAL_ENERGY_CHARGES» «FINAL_ED_CHARGES»`

**Office-copy LFHD:** `«L_n» «F_n» «H_n» «D_n» «UNITS_n» «TOTAL_CALCULATED_UNITS» «SUMMARY_FIXED» «SUMMARY_ENERGY» «SUMMARY_ED» «SUMMARY_TOTAL»`

**Other:** `«MOBILE_NO» «ACCOUNT_ID» «CONNECTION_LOAD» «SUPPLY_TYPE» «FIR_NUMBER» «SECTION» «COMPOUNDING_AMOUNT» «JE_NAME» «CHECKING_TYPE» «SUB_SUBSTATION» «CATEGORY» «TD_DATE» «LANDMARK»`

## Legal Compliance Timeline
- **Day 0:** Raid date
- **Day 7:** Provisional notice payment deadline
- **Day 15:** Appeal submission deadline
- **Day 45:** Section 3 notice dispatch
- **Day 90:** Section 5 notice dispatch

## Payment Components
- Assessment Amount
- Compounding Charges (Section 152, per-KW round-up)
- Shaman (settlement) Amount — if legally permissible
- Admin Charges (₹25 for Section 3)

Payment modes: full / partial / installment. NOC auto-generated only on full settlement.
Mandatory reminder text on Deposit Slip:
> "यह धनराशि जमा करने के उपरान्त प्राप्त रसीद की छायाप्रति खण्ड कार्यालय के राजस्व निर्धारण पटल पर अवश्य जमा करा दें जिससे भविष्य की कार्यवाही जैसे पोर्टल पर अपलोड करना पत्र निर्गत् करना आदि हो सके"

## Database Schema (15 tables)
`consumers, historical_cases, current_cases, device_master, rate_master, account_mapping, offense_summary, raid_cases, payments, inquiries, notices, documents, system_config, case_revisions, appeals, audit_log`

## Color Coding (UI)
- **Green** = Paid / Cleared
- **Yellow** = Pending notice / Approaching deadline / Partial payment
- **Red** = Unpaid / Overdue
- **Blue** = Partial / Ongoing transaction

## Search Capabilities
Multi-parameter: Account, Name, Address, FIR, Division, Checking number. Date range max 15 days. Status, division, officer, amount filters.

## Phase Plan
- **Phase 1 (Wk 1–2):** DB schema, master-data import, Flask APIs, Excel skeleton — ✅ DONE
- **Phase 2 (Wk 3–4):** Offense detection, LFHD calc, template system, provisional notice generation — ✅ DONE
- **Phase 3 (Wk 5–6):** Payment, notice timeline, inquiry, search — ✅ DONE
- **Phase 4 (Wk 7–8):** Google Drive backup, reporting, optimization, training — ✅ DONE

## Current Status (when handed off to Kiro)
- Excel UI: 95% — RaidSystem.xlsm with VBA macros, LFHD calculations, slab billing
- Python backend: 80% — basic Flask, DB connectivity, `/api/health`, `/api/search_consumer`, `/api/save_case`, `/api/add_sample_data`
- Database: 90% — core tables in place
- API comm: 85%
- **Master Data Import: 60% — BUG: HTTP 500 on `/api/import_all_master_data` (column mapping mismatch)** ← Top priority fix
- Document Generation: 0%

## Final Status (after Kiro implementation)
- Excel VBA frontend: ✅ 15 modules + starter `RaidSystem.xlsx` (9 sheets, 20 named ranges)
- Python backend: ✅ 55 routes across 11 blueprints (health, master, consumer, case, document, payment, inquiry, notice, device_rate, backup, reports)
- Database: ✅ 16 tables, 20+ indexes, online-backup-API safe snapshots
- API comm: ✅ uniform `{ ok, data, meta }` envelope, global JSON error handler
- Master Data Import: ✅ structured ImportReport, per-row error isolation, English/Hindi/Krutidev column tolerance
- Document Generation: ✅ 9 default `.docx` templates with `{{ FIELD }}` placeholders + autogen fallback
- Section 152 Compounding: ✅ per-KW-or-part-thereof round-UP rule with auto Hindi justification
- Offense Detection: ✅ 4-level priority (account / SC / mapping / fuzzy)
- Backup: ✅ local zip (DB online-backup + master_data + docs) + optional Google Drive
- Reports: ✅ cases.xlsx, payments.xlsx, notices.xlsx, dashboard.pdf
- Smoke test: ✅ 15/15 green via `bash scripts/smoke_test.sh`

## User Environment
- Windows 11 Pro, Ryzen 5 5300G, 8 GB RAM
- Python with Flask, pandas, openpyxl, python-docx, reportlab
- Excel with macros enabled (Trust Center → enable VBA)
