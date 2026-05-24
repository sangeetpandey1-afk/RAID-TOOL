# विद्युत चोरी रेड प्रबंधन सिस्टम / Raid Management System

UPPCL-style electricity theft case management system. **Modern Web UI + Python (Flask + SQLite)** offline architecture with auto-generated legal notices, multi-level offense detection, LFHD-based assessment, and Section 152 compounding (per-KW or part-thereof, round-up).

> Full project specification: see [`.kiro/steering/project-spec.md`](./.kiro/steering/project-spec.md)

---

## ✨ Features

- **🌐 Web UI** — Tailwind CSS + vanilla JS, runs in any browser, no Excel needed
- **📊 Dashboard** — Stats, timeline alerts (sec 3/5 due, overdue, appeal window)
- **➕ Raid Entry Form** — Three-tier layout (Consumer / LFHD / History) with live calculation
- **🔍 Multi-parameter Search** — Account / SC / fuzzy name / village
- **📚 Offense Detection** — 4-level (account → SC → mapping → fuzzy) with auto-multiplier
- **⚡ LFHD Calculator** — Section-aware (135=365d, 138=TD-to-today), slab-wise rates
- **💸 Section 152 Compounding** — Per-KW or part-thereof round-up + Hindi justification
- **📄 Document Generation** — 9 kinds (provisional consumer/office, sec 3, sec 5, thanedari, envelope, deposit slip, compounding order, NOC) with auto-fallback when no template
- **💰 Payment Tracking** — Multi-component (assessment / compounding / shaman / admin), auto-NOC eligibility
- **📞 Inquiry Log** — Caller history per case
- **📨 Notice Tracker** — Provisional / Sec 3 / Sec 5 with auto-derived due dates
- **🛂 Master Data Importer** — Robust column-mapping, handles Hindi/Krutidev/English

---

## 🚀 Quick Start (Windows)

### 1. Prerequisites
- **Python 3.10+** ([download](https://www.python.org/downloads/))
- A modern **web browser** (Chrome / Edge / Firefox)

### 2. Clone & Install
```cmd
git clone https://github.com/sangeetpandey1-afk/RAID-TOOL.git
cd RAID-TOOL
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run
```cmd
python -m backend.app
```

Server starts on `http://localhost:5000`. **Open `http://localhost:5000/` in your browser** — you'll be redirected to the web app.

### 4. Place & Import Master-Data Files
Drop these Excel files into `master_data/` folder:

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

Then go to **Master Data → Import All Master Data** in the UI, or via curl:
```cmd
curl -X POST http://localhost:5000/api/import_all_master_data
```

---

## 🖥️ Web UI Tour

| URL                          | Page              | Purpose |
|------------------------------|-------------------|---------|
| `/` or `#/dashboard`         | Dashboard         | Stats + timeline alerts + recent activity |
| `#/new-raid`                 | New Raid Entry    | Three-tier form: Consumer + LFHD + History |
| `#/cases`                    | Case Search       | Multi-parameter list with filters |
| `#/case/<case_id>`           | Case Detail       | Tabs: Overview / Assessment / Payments / Inquiries / Notices / Documents / Revisions |
| `#/consumers`                | Consumer Search   | Multi-level matcher (account / SC / fuzzy name) |
| `#/consumer/<account>`       | Consumer Profile  | Full record + offense history |
| `#/master-data`              | Master Data       | Import status + devices + rate categories |
| `#/settings`                 | Settings          | System config + health + templates |

---

## 🧰 API Reference (44 routes)

All responses use a uniform envelope:
```json
{ "ok": true, "data": { ... }, "meta": { ... } }
```

### Health & system
- `GET /api/health`
- `GET /api/system/config`

### Master data
- `GET /api/master_files` — Diagnostic: which files were detected
- `POST /api/import_all_master_data` — Import everything available
- `POST /api/import_master/<kind>` — Import one (kinds: consumers, historical, current, devices, rates, mapping)

### Consumers
- `GET /api/consumers/search?account=&sc=&q=&name=&father=&village=&limit=&threshold=`
- `GET /api/consumers/<account>` — Profile + offense history + inquiries
- `GET /api/consumers/<account>/offense-check?name=&father=&village=`

### Devices & rates
- `GET /api/devices?category=`
- `GET /api/devices/categories`
- `GET /api/rates?category=`
- `GET /api/rates/categories`

### Cases
- `POST /api/cases` — Save / update case
- `GET /api/cases/<case_id>` — Full case bundle
- `GET /api/cases` and `GET /api/cases/search` — List with filters
- `POST /api/calculate` and `POST /api/cases/<id>/calculate` — Live LFHD calc
- `POST /api/compounding` and `POST /api/cases/<id>/compounding` — Section 152
- `GET /api/cases/<id>/offense-check`
- `POST /api/cases/<id>/revise` — Post-appeal revision

### Documents
- `GET /api/document/kinds`
- `POST /api/cases/<id>/document/<kind>` — Generate (saves to `docs/<case_id>/`)
- `GET /api/documents/<doc_id>` — Download
- `POST /api/templates/migrate-legacy` — Convert `«FIELD»` → `{{ FIELD }}`

### Payments / Inquiries / Notices
- `GET|POST /api/cases/<id>/payments`
- `DELETE /api/payments/<id>`
- `GET /api/payments/recent?limit=`
- `GET|POST /api/cases/<id>/inquiries`
- `GET /api/inquiries/recent?limit=`
- `GET /api/inquiries/by-mobile/<mobile>`
- `GET|POST /api/cases/<id>/notices`
- `PATCH /api/notices/<id>`
- `GET /api/notices/overdue`

### Dashboard
- `GET /api/dashboard/summary`
- `GET /api/dashboard/timeline-alerts`

---

## Project Structure

```
RAID-TOOL/
├── backend/
│   ├── app.py                  # Flask main entry (also serves /app/* frontend)
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
│   │   ├── notice.py
│   │   └── device_rate.py
│   ├── services/               # Business logic
│   │   ├── importer.py         # Robust column-mapping importer
│   │   ├── calculator.py       # LFHD + slab-wise assessment
│   │   ├── compounding.py      # Section 152 (per-KW round-up)
│   │   ├── matcher.py          # 4-level offense detection
│   │   └── doc_generator.py    # python-docx templates + autogen
│   └── models/
│       └── schema.sql          # Reference schema
├── frontend/                   # Modern web UI (vanilla JS + Tailwind CDN)
│   ├── index.html              # App shell
│   ├── css/styles.css
│   └── js/
│       ├── api.js              # Single API client
│       ├── state.js            # In-memory cache
│       ├── components.js       # Toast, modal, formatters
│       ├── app.js              # Hash router
│       └── views/
│           ├── dashboard.js
│           ├── raid-form.js    # Three-tier raid entry form
│           ├── cases.js
│           ├── case-detail.js  # Tabs: payments/inquiries/notices/docs
│           ├── consumers.js
│           ├── master-data.js
│           └── settings.js
├── master_data/                # Place Excel master files here (gitignored)
├── templates/                  # Word .docx templates with «PLACEHOLDERS» or {{ PLACEHOLDERS }}
├── docs/                       # Generated documents (runtime, gitignored)
├── backup/                     # Backups (gitignored)
├── logs/                       # Server logs (gitignored)
├── scripts/
│   └── smoke_test.sh           # End-to-end backend test
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
| SQLite schema (16 tables) | ✅ |
| Flask app skeleton | ✅ |
| Master data importer (fixes HTTP 500) | ✅ |
| Consumer search | ✅ |
| LFHD + slab assessment | ✅ |
| Section 152 compounding | ✅ |
| Offense detection (4-level) | ✅ |
| Case management | ✅ |
| Document generation foundation | ✅ |
| Payment / Inquiry / Notice | ✅ |
| **Web UI (HTML + JS + Tailwind)** | ✅ |
| Google Drive backup | ⏳ Phase 4 |

---

## License & Audience
Internal tool for UPPCL/electricity-board officers. Hindi (Krutidev) document support throughout.
