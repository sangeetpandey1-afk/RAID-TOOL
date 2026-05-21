# विद्युत चोरी रेड प्रबंधन सिस्टम / Raid Management System

UPPCL-style electricity theft case management system. **Excel + Python (Flask + SQLite)** offline architecture with auto-generated legal notices, multi-level offense detection, LFHD-based assessment, and Section 152 compounding (per-KW or part-thereof, round-up).

> Full project specification: see [`.kiro/steering/project-spec.md`](./.kiro/steering/project-spec.md)

---

## Quick Start (Windows — single-click)

### 1. Prerequisites
- **Python 3.10+** — [download](https://www.python.org/downloads/) and tick
  **"Add Python to PATH"** during install.
- (Optional) **Microsoft Excel** if you want the macro front-end too. The
  browser UI does **not** need Excel.

### 2. Get the code
```cmd
git clone https://github.com/sangeetpandey1-afk/RAID-TOOL.git
cd RAID-TOOL
```

### 3. Install — double-click `install.bat`
The installer creates a local `venv\`, installs every Python dependency,
generates the 9 Word templates, builds the Excel starter workbook, and
warms up the SQLite schema. It is safe to re-run.

### 4. Run — double-click `run.bat`
Activates the venv, opens **http://localhost:5000/** in your default
browser, and runs the Flask backend in the same console window.

> Press **Ctrl+C** in the console window to stop the server.

That's it. The browser UI now has six tabs:

| Tab        | What you can do |
|------------|-----------------|
| Dashboard  | KPIs, import master data, backup, timeline alerts |
| New Case   | Consumer info + LFHD devices + live calc + save case + offense check + generate all 9 documents |
| Cases      | List, filter, open a case, record payments, add notices |
| Search     | Multi-field consumer search with one-click "Use" → fills New Case |
| Backup     | Backup now, list backups, download zip |
| Reports    | Generate cases.xlsx / payments.xlsx / notices.xlsx / dashboard.pdf and download |

### 5. (Optional) Place Master-Data Files
Copy these Excel files into the `master_data\` folder (any variant works):

| Required content                  | Accepted file names |
|----------------------------------|---------------------|
| Consumer master (69 k records)   | `raid_master_data.xlsx` |
| Historical cases (8956 records)  | `ALL DATA.xlsx`, `all_data.xlsx` |
| Active cases (24 k records)      | `raid excell 2526 Copy.xlsx`, `current_cases.xlsx` |
| Device master                    | `device list.xlsx`, `device_list.xlsx` |
| Rate slabs                       | `slab_rates.xlsx` |
| Account mapping (optional)       | `account_mapping.xlsx` |

Then click **"Import Master Data"** on the Dashboard tab (or
`POST /api/import_all_master_data`).

### 6. (Optional) Excel VBA Front-end
If you also want the Excel macro UI:

1. In Excel: *File → Options → Trust Center → Trust Center Settings →
   Macro Settings → ✅ "Trust access to the VBA project object model"*.
2. Double-click `install_vba.bat`.
3. Open the generated `frontend\RaidSystem.xlsm`.

The VBA UI talks to the same `/api/*` endpoints, so the browser and Excel
front-ends can be used interchangeably.

---

## Manual install (if you prefer)
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python scripts\generate_default_templates.py
python frontend\build_xlsm.py
python -m backend.app
```
Then open http://localhost:5000/ in your browser.

---

## API Reference

55 routes across 11 blueprints. Highlights:

### Health & system
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | DB ok? routes registered? table counts |
| `/api/system/config` | GET | Defaults (multipliers, timeline days) |
| `/api/dashboard/summary` | GET | Headline KPIs (cases by status, today payments) |
| `/api/dashboard/timeline-alerts` | GET | Provisional/Sec3/Sec5/appeal-window alerts |

### Master data
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/import_all_master_data` | POST | Import every Excel file in `master_data/` (the previously-broken endpoint, now returns a structured `ImportReport`) |
| `/api/import_master/<kind>` | POST | Single-file import (`consumers`, `historical`, `current`, `devices`, `rates`, `mapping`) |
| `/api/master_files` | GET | Diagnostic: which files were detected |
| `/api/devices` / `/api/devices/categories` | GET | Device master |
| `/api/rates` / `/api/rates/categories` | GET | Slab rates |

### Consumers
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/consumers/search` | GET | Multi-param fuzzy search (account / name / village / father) |
| `/api/consumers/<account>` | GET | Profile + offense history |
| `/api/consumers/<account>/offense-check` | GET | 4-level offense detection |

### Cases & calculation
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/cases` | GET/POST | List / create-or-update |
| `/api/cases/<case_id>` | GET | Full case incl. revisions |
| `/api/cases/search` | GET | Multi-param case search |
| `/api/cases/<case_id>/revise` | POST | Revise & audit |
| `/api/cases/<case_id>/calculate` / `/api/calculate` | POST | LFHD + slab assessment |
| `/api/cases/<case_id>/compounding` / `/api/compounding` | POST | Section 152 round-up |
| `/api/cases/<case_id>/offense-check` | GET | Offense history |

### Documents
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/cases/<case_id>/document/<kind>` | POST | Generate one document (9 kinds available) |
| `/api/document/kinds` | GET | List supported kinds |
| `/api/documents/<doc_id>` | GET | Download a previously-generated file |
| `/api/templates/migrate-legacy` | POST | One-shot `«FIELD»` → `{{ FIELD }}` rewrite |

### Payments / Inquiries / Notices
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/cases/<case_id>/payments` | GET/POST | Payment list / record |
| `/api/payments/recent` | GET | Recent payments across cases |
| `/api/cases/<case_id>/inquiries` | GET/POST | Inquiry log |
| `/api/inquiries/by-mobile/<m>` / `/api/inquiries/recent` | GET | Inquiry filters |
| `/api/cases/<case_id>/notices` | GET/POST | Notice timeline |
| `/api/notices/<id>` | GET | Single notice |
| `/api/notices/overdue` | GET | All overdue notices |

### Backup & restore (Phase 4)
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/backup/status` | GET | Drive enabled? last backup? |
| `/api/backup/now` | POST | Create local zip + best-effort Drive upload |
| `/api/backup/list` | GET | List existing backups |
| `/api/backup/download/<name>` | GET | Download a backup zip |
| `/api/backup/restore` | POST | Restore from zip (current DB renamed to `*.before_restore_<ts>`) |

### Reports & exports (Phase 4)
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/reports/cases.xlsx` | GET | Cases (filter `status`, `from`, `to`) |
| `/api/reports/payments.xlsx` | GET | Payments (filter `from`, `to`) |
| `/api/reports/notices.xlsx` | GET | Notice timeline |
| `/api/reports/dashboard.pdf` | GET | One-page A4 KPI dashboard |
| `/api/reports/list` | GET | List generated reports |
| `/api/reports/download/<name>` | GET | Download a report file |

All responses use a uniform envelope:
```json
{ "ok": true, "data": { ... }, "meta": { ... } }
```
On error:
```json
{ "ok": false, "error": "human readable message", "details": "...", "code": "ERR_X" }
```

---

## Project Structure

```
RAID-TOOL/
├── install.bat                 # One-click Windows installer (venv + deps + templates + xlsx)
├── run.bat                     # One-click launcher (server + browser auto-open)
├── install_vba.bat             # Optional: bulk-import VBA modules into RaidSystem.xlsm
├── backend/
│   ├── app.py                  # Flask main entry — 59 routes, 11 blueprints, serves /frontend/
│   ├── config.py               # Paths, ports, defaults, business rules
│   ├── database.py             # SQLite schema + connection
│   ├── routes/                 # HTTP routes (blueprints)
│   │   ├── health.py
│   │   ├── master_data.py      # Master-data import (FIXED — no more HTTP 500)
│   │   ├── consumer.py
│   │   ├── case.py
│   │   ├── document.py
│   │   ├── payment.py
│   │   ├── inquiry.py
│   │   ├── notice.py
│   │   ├── device_rate.py
│   │   ├── backup.py           # Phase 4
│   │   └── reports.py          # Phase 4
│   ├── services/
│   │   ├── importer.py         # Robust column-mapping importer
│   │   ├── calculator.py       # LFHD + slab-wise assessment
│   │   ├── compounding.py      # Section 152 (per-KW round-up)
│   │   ├── matcher.py          # 4-level offense detection
│   │   ├── doc_generator.py    # python-docx / docxtpl
│   │   ├── backup.py           # Phase 4
│   │   └── reports.py          # Phase 4
│   └── models/schema.sql
├── frontend/
│   ├── index.html              # Browser UI entry point (served at /frontend/)
│   ├── static/
│   │   ├── styles.css          # Offline-first styles, no CDN
│   │   └── app.js              # Vanilla JS, fetch API
│   ├── RaidSystem_README.md    # VBA setup guide
│   ├── RaidSystem.xlsx         # Starter workbook (built by install.bat)
│   ├── build_xlsm.py           # Regenerator script
│   ├── import_vba.vbs          # Bulk VBA importer (used by install_vba.bat)
│   └── vba/                    # 15 VBA modules + ThisWorkbook.cls
├── templates/                  # 9 default .docx templates with {{ FIELD }}
├── master_data/                # Place Excel master files here (gitignored)
├── docs/                       # Generated documents (runtime, gitignored)
├── backup/                     # Backups + reports/<name> (gitignored)
├── logs/                       # Server logs (gitignored)
├── scripts/
│   ├── smoke_test.sh           # End-to-end curl smoke test (23 sections)
│   └── generate_default_templates.py
├── requirements.txt
└── .kiro/steering/project-spec.md
```

---

## Key Business Rules

### Section 152 Compounding (LT)
> Charged "per KW or part thereof" — billable KW is **always rounded UP**.
> Example: 2122 W → 2.122 KW → **3 KW** billable.

Auto-generated Hindi justification:
> "निरीक्षण के समय उपभोक्ता परिसर पर 2122 Watt अर्थात लगभग 2.122 KW भार पाया गया, जो 2 KW से अधिक होकर अतिरिक्त भाग (part thereof) में आता है। अतः धारा 152 में वर्णित 'per KW or part thereof' प्रावधान के अनुसार Compounding की गणना 3 KW के आधार पर की गई है।"

### Assessment Multiplier
- First offense → **2×** (editable)
- Repeat offense (≥ 2 prior cases) → **6×** (editable)

### LFHD
```
Units_per_device = (L × F × H × D) / 1000
Total_Units      = Σ Units_per_device
```

### Section-wise days
- Sec 135 → 365 days default
- Sec 138 → from `td_date` to today
- Sec 126 / Other → 365 default, editable

### Legal Timeline
| Day | Event |
|-----|-------|
| 0   | Raid |
| 7   | Provisional notice payment due |
| 15  | Appeal window closes |
| 45  | Section 3 dispatch deadline |
| 90  | Section 5 dispatch deadline |

---

## Implementation Status

| Component | Status |
|-----------|--------|
| Project spec (steering doc) | ✅ |
| Project structure | ✅ |
| SQLite schema (16 tables) | ✅ |
| Flask app skeleton | ✅ |
| Master data importer (fixes HTTP 500) | ✅ |
| Consumer search | ✅ |
| LFHD + slab assessment | ✅ |
| Section 152 compounding | ✅ |
| Offense detection (4-level) | ✅ |
| Case management (CRUD + revise + audit) | ✅ |
| Document generation (9 kinds) | ✅ |
| Default Word templates with `{{ FIELD }}` placeholders | ✅ |
| Payment / Inquiry / Notice + timeline alerts | ✅ |
| **Browser UI (`/frontend/`, 6 tabs, offline-first)** | ✅ |
| **One-click installer (`install.bat`) and launcher (`run.bat`)** | ✅ |
| Excel VBA frontend (15 modules + bulk-import script) | ✅ |
| Reports & exports (xlsx + PDF) | ✅ |
| Backup (local zip + optional Google Drive) | ✅ |
| End-to-end smoke test (23 curl checks) | ✅ |

---

## Optional: Google Drive backup

By default `/api/backup/now` produces a local zip in `backup/`. To also
upload every backup to Google Drive:

1. Uncomment the three google lines in `requirements.txt` and reinstall.
2. Create a service account in the Google Cloud console and download the
   JSON credentials.
3. Share the target Drive folder with the service account email.
4. Set environment variables before starting the backend:
   ```cmd
   set RAID_GDRIVE_CREDS=D:\raid tool\backup\service-account.json
   set RAID_GDRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQrSt
   ```
5. Restart the backend. `GET /api/backup/status` will now show
   `gdrive_enabled: true` and every `POST /api/backup/now` will upload.

When the env vars are missing or the libs aren't installed, the local zip
still works and the response simply notes `gdrive: { skipped: true,
reason: ... }`.

---

## License & Audience
Internal tool for UPPCL/electricity-board officers. Hindi (Krutidev /
Mangal / Nirmala UI) document support throughout. Hindi text round-trip
through every layer (DB, JSON, .docx).
