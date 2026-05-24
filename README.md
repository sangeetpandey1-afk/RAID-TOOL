# विद्युत चोरी रेड प्रबंधन सिस्टम / Raid Management System

UPPCL-style electricity theft case management system. **Excel + Python (Flask + SQLite)** offline architecture with auto-generated legal notices, multi-level offense detection, LFHD-based assessment, and Section 152 compounding (per-KW or part-thereof, round-up).

> Full project specification: see [`.kiro/steering/project-spec.md`](./.kiro/steering/project-spec.md)

---

## Quick Start (Windows — User's machine)

### 1. Prerequisites
- **Python 3.10+** ([download](https://www.python.org/downloads/))
- **Microsoft Excel** with macros enabled (Trust Center → Macro Settings → Enable VBA)

### 2. Clone & Install
```cmd
git clone https://github.com/sangeetpandey1-afk/RAID-TOOL.git
cd RAID-TOOL
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Place Master-Data Files
Copy these Excel files into the `master_data/` folder (any of the variants are accepted):

| Required content                  | Accepted file names | Sample to compare against |
|----------------------------------|---------------------|--------------------------|
| Consumer master (69 k records)   | `raid_master_data.xlsx` | [`master_data/SAMPLE_raid_master_data.xlsx`](./master_data/SAMPLE_raid_master_data.xlsx) |
| Historical cases (8956 records)  | `ALL DATA.xlsx`, `all_data.xlsx` | [`master_data/SAMPLE_all_data.xlsx`](./master_data/SAMPLE_all_data.xlsx) |
| Active cases (24 k records)      | `raid excell 2526 Copy.xlsx`, `current_cases.xlsx` | [`master_data/SAMPLE_raid_excell_2526.xlsx`](./master_data/SAMPLE_raid_excell_2526.xlsx) |
| Device master                    | `device list.xlsx`, `device_list.xlsx` | [`master_data/SAMPLE_device_list.xlsx`](./master_data/SAMPLE_device_list.xlsx) |
| Rate slabs                       | `slab_rates.xlsx` | [`master_data/SAMPLE_slab_rates.xlsx`](./master_data/SAMPLE_slab_rates.xlsx) |
| Account mapping (optional)       | `account_mapping.xlsx` | [`master_data/SAMPLE_account_mapping.xlsx`](./master_data/SAMPLE_account_mapping.xlsx) |

> 📑 **Open the SAMPLE workbooks first** to see the exact column headings and data shape the importer expects.
> Full column-by-column reference (including all accepted synonyms) is in [`master_data/SAMPLE_README.md`](./master_data/SAMPLE_README.md).
> To regenerate the samples after editing: `python scripts/generate_sample_excels.py`.

### 4. Initialize DB & Run Backend
```cmd
python -m backend.app
```
Server starts on `http://localhost:5000`. The DB (`raid_database.db`) is created automatically on first run.

### 5. Import Master Data
Once the server is up, hit:
```cmd
curl -X POST http://localhost:5000/api/import_all_master_data
```
or use the **"Import Master Data"** button in the Excel UI.

---

## API Reference (Phase 1)

| Endpoint                                  | Method | Purpose |
|-------------------------------------------|--------|---------|
| `/api/health`                             | GET    | Health check |
| `/api/import_all_master_data`             | POST   | Import all Excel master files (the buggy endpoint — now fixed with column-mapping flexibility) |
| `/api/import_master/<type>`               | POST   | Import a single master file (`consumers`, `historical`, `current`, `devices`, `rates`, `mapping`) |
| `/api/consumers/search?q=...&account=...` | GET    | Multi-parameter consumer search |
| `/api/consumers/<account>`                | GET    | Get full consumer profile + offense history |
| `/api/devices`                            | GET    | List device master |
| `/api/rates?category=LMV-1`               | GET    | Get rate slabs for a category |
| `/api/cases`                              | POST   | Save / update a raid case |
| `/api/cases/<case_id>`                    | GET    | Retrieve a case (incl. revisions) |
| `/api/cases/search`                       | GET    | Multi-parameter case search |
| `/api/cases/<case_id>/calculate`          | POST   | Run LFHD + assessment calculation |
| `/api/cases/<case_id>/compounding`        | POST   | Section 152 compounding (round-up KW) |
| `/api/cases/<case_id>/offense-check`      | GET    | Multi-level offense detection |
| `/api/cases/<case_id>/document/<type>`    | GET    | Generate document (provisional_consumer, provisional_office, section3, section5, thanedari, deposit_slip, envelope) |
| `/api/cases/<case_id>/payments`           | GET/POST | Payment list / record new payment |
| `/api/cases/<case_id>/inquiries`          | GET/POST | Inquiry log |
| `/api/cases/<case_id>/notices`            | GET/POST | Notice tracker |

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
├── backend/
│   ├── app.py                  # Flask main entry
│   ├── config.py               # Paths, ports, defaults
│   ├── database.py             # SQLite schema + connection
│   ├── routes/                 # HTTP routes (blueprints)
│   │   ├── health.py
│   │   ├── master_data.py      # Master-data import (FIXED)
│   │   ├── consumer.py
│   │   ├── case.py
│   │   ├── document.py
│   │   ├── payment.py
│   │   ├── inquiry.py
│   │   └── notice.py
│   ├── services/               # Business logic
│   │   ├── importer.py         # Robust column-mapping importer
│   │   ├── calculator.py       # LFHD + slab-wise assessment
│   │   ├── compounding.py      # Section 152 (per-KW round-up)
│   │   ├── offense_detector.py # 4-level matching
│   │   └── doc_generator.py    # python-docx templates
│   └── models/
│       └── schema.sql          # Reference schema
├── frontend/
│   └── RaidSystem_README.md    # VBA module reference
├── master_data/                # Place Excel master files here (gitignored)
├── templates/                  # Word .docx templates with «PLACEHOLDERS»
├── docs/                       # Generated documents (runtime, gitignored)
├── backup/                     # Backups (gitignored)
├── logs/                       # Server logs (gitignored)
├── requirements.txt
└── .kiro/steering/project-spec.md   # Full functional spec
```

---

## Key Business Rules

### Section 152 Compounding (LT)
> Charged "per KW or part thereof" — billable KW is **always rounded UP**.
> Example: 2122 W → 2.122 KW → **3 KW** billable.

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
| SQLite schema (15 tables) | ✅ |
| Flask app skeleton | ✅ |
| Master data importer (fixes HTTP 500) | ✅ |
| Consumer search | ✅ |
| LFHD + slab assessment | ✅ |
| Section 152 compounding | ✅ |
| Offense detection (4-level) | ✅ |
| Case management | ✅ |
| Document generation foundation | ✅ |
| Payment / Inquiry / Notice | ✅ |
| Excel VBA refresh | ⏳ Phase 2 |
| Google Drive backup | ⏳ Phase 4 |

---

## License & Audience
Internal tool for UPPCL/electricity-board officers. Hindi (Krutidev) document support throughout.
