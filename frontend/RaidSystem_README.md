# Excel VBA Frontend — RaidSystem.xlsm

This folder contains everything needed to build the **Excel + VBA** front-end
for the Raid Management System. The Excel UI talks to the Python Flask backend
running locally on `http://127.0.0.1:5000`.

## Folder layout

```
frontend/
├── RaidSystem_README.md     ← (this file)
├── build_xlsm.py            ← builds the starter .xlsx with sheet structure
├── vba/
│   ├── modConfig.bas        ← API base URL + named-range helpers
│   ├── modJson.bas          ← Minimal JSON encoder/decoder
│   ├── modApiClient.bas     ← HTTP client wrapper (MSXML2.XMLHTTP60)
│   ├── modUtils.bas         ← Common helpers (cell I/O, message boxes)
│   ├── modCalculator.bas    ← Live LFHD calc via /api/calculate
│   ├── modCaseSave.bas      ← Save case via /api/cases
│   ├── modConsumerSearch.bas← Consumer search (fuzzy)
│   ├── modOffense.bas       ← Offense check
│   ├── modDocuments.bas     ← Generate notices / slips / orders
│   ├── modPayment.bas       ← Record payment
│   ├── modImport.bas        ← Master-data import (the FIXED endpoint)
│   ├── modReports.bas       ← Trigger Excel/PDF reports
│   ├── modBackup.bas        ← Trigger backup-now
│   └── ThisWorkbook.cls     ← Workbook_Open: ping backend, show health
```

## One-time setup

1. Make sure the backend is running:
   ```cmd
   cd D:\raid tool
   python -m backend.app
   ```
2. Build the starter workbook:
   ```cmd
   python frontend\build_xlsm.py
   ```
   This creates `frontend\RaidSystem.xlsx` with all sheets and named ranges.
3. Open the file in Excel and immediately **Save As → Excel Macro-Enabled
   Workbook (.xlsm)**.
4. Press **Alt+F11** to open the VBA editor.
5. In the VBE: **File → Import File...** for each of the 12 `.bas` modules
   from `vba/` and the `ThisWorkbook.cls`.
6. Save the workbook. Re-open it — the **Health** cell on the Dashboard
   sheet should show `OK` and the route count from the backend.

## Sheet quick reference

| Sheet         | Purpose |
|---------------|---------|
| **Dashboard** | Health status, summary KPIs, action buttons |
| **Inputs**    | Case header (consumer info, section, date, J.E.) |
| **Devices**   | LFHD device entries (load, factor, hours, days) |
| **Calc**      | Read-only assessment breakdown (slabs, ED, total) |
| **Search**    | Consumer search panel with results table |
| **Cases**     | Saved case list (paged) |
| **Payments**  | Payment history for selected case |
| **Notices**   | Notice timeline & status |
| **Settings**  | API base URL, default category, multipliers |

## Named ranges used by VBA

| Name              | Cell reference        | Purpose |
|-------------------|-----------------------|---------|
| `nrApiBase`       | `Settings!B2`         | Base URL (default `http://127.0.0.1:5000`) |
| `nrAccount`       | `Inputs!B3`           | Account number |
| `nrName`          | `Inputs!B4`           | Consumer name |
| `nrFather`        | `Inputs!B5`           | Father name |
| `nrVillage`       | `Inputs!B6`           | Village |
| `nrPost`          | `Inputs!B7`           | Post office |
| `nrPin`           | `Inputs!B8`           | Pin |
| `nrMobile`        | `Inputs!B9`           | Mobile |
| `nrSection`       | `Inputs!B10`          | Section (135/138/126/Other) |
| `nrInspectionDate`| `Inputs!B11`          | Inspection date |
| `nrCategory`      | `Inputs!B12`          | LMV-1 / LMV-2 etc |
| `nrLoadKW`        | `Inputs!B13`          | Connected load (kW) |
| `nrJE`            | `Inputs!B14`          | J.E. name |
| `nrSubStation`    | `Inputs!B15`          | Sub-substation |
| `nrCheckingType`  | `Inputs!B16`          | Vigilance / Routine |
| `nrCurrentCaseId` | `Cases!B1`            | Last saved case_id |
| `nrCalcTotal`     | `Calc!B25`            | Grand total mirror |

## Buttons (Form Controls)

The build script adds button **placeholder cells** with the macro name in
`G:H` columns. After importing the VBA, right-click each marker cell, choose
**Insert Button**, and link it to the macro shown next to the cell.

| Sheet     | Macro name                | Caption |
|-----------|---------------------------|---------|
| Dashboard | `CheckHealth`             | Refresh Health |
| Dashboard | `ImportAllMaster`         | Import Master Data |
| Dashboard | `RunBackup`               | Backup Now |
| Dashboard | `ExportCases`             | Export Cases (xlsx) |
| Dashboard | `ExportDashboardPDF`      | Dashboard PDF |
| Inputs    | `LiveCalc`                | Live Calculate |
| Inputs    | `SaveCase`                | Save Case |
| Inputs    | `OffenseCheck`            | Offense Check |
| Inputs    | `GenerateAllDocuments`    | Generate All Docs |
| Search    | `SearchConsumer`          | Search |
| Cases     | `RefreshCases`            | Refresh List |
| Payments  | `RecordPayment`           | Record Payment |
| Notices   | `AddProvisionalNotice`    | Add Provisional Notice |

## Tested with

- Excel 2019 / Excel 365 (Windows)
- VBA references required: **none** (uses late-bound `MSXML2.XMLHTTP60` and
  `Scripting.Dictionary`)
- Network: backend on `localhost:5000` (no firewall changes needed)

## Troubleshooting

* **"Health: NETWORK ERROR"** — backend not running. Start it with
  `python -m backend.app`.
* **"HTTP 500" on import** — should not happen after Phase 1 fix; check
  `logs/server.log` for the full traceback.
* **Hindi text shows as boxes** — Excel cell font must be set to a Krutidev /
  Kruti Dev font for legacy text, or to Mangal/Nirmala UI for Unicode Hindi.
  The build script defaults Hindi columns to `Mangal`.
