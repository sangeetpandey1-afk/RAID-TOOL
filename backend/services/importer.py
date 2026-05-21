"""
Robust Excel master-data importer.

Why this exists
---------------
The user's previous backend was returning HTTP 500 on
``/api/import_all_master_data`` because column names in the Excel files don't
match the column names in the SQLite schema literally — they may be:
* upper / lower / mixed case
* with extra spaces, punctuation, unicode lookalikes
* in Hindi or Krutidev font
* renamed by the data team between versions

This importer normalizes column names aggressively and uses a synonym
registry so a single target field can be filled from any of several source
columns. Every row is wrapped in its own try/except so a single bad row never
aborts the whole import — instead the row goes into an error report.

Public API
----------
* ``ImportReport`` — dataclass returned for every operation
* ``find_master_file(kind)`` — locate Excel file in ``master_data/``
* ``import_consumers / import_historical / import_current /
    import_devices / import_rates / import_account_mapping``
* ``import_all`` — runs every available file
"""
from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .. import config
from ..database import get_connection, standalone_connection
from ..utils import (normalize_account, parse_date, safe_float, safe_int,
                     to_json_str)

log = logging.getLogger(__name__)


# ===================================================================
# ImportReport — uniform return type
# ===================================================================
@dataclass
class ImportReport:
    kind: str
    file_path: str | None = None
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)   # [{row,reason}]
    warnings: list[str] = field(default_factory=list)
    column_mapping: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "file_path": self.file_path,
            "total_rows": self.total_rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "error_count": len(self.errors),
            "errors_sample": self.errors[:10],
            "warnings": self.warnings,
            "column_mapping": self.column_mapping,
            "duration_ms": self.duration_ms,
        }


# ===================================================================
# Column-name normalization
# ===================================================================
def _norm_col(name: Any) -> str:
    """Make column names comparable: lowercase, alnum-only."""
    if name is None:
        return ""
    s = str(name)
    # Replace common separators with space, then strip non-alnum
    s = re.sub(r"[\s_\-./()\[\]]+", "", s)
    return s.lower()


def _build_column_map(df_columns: Iterable[Any],
                      synonyms: dict[str, list[str]]) -> dict[str, str]:
    """
    Map ``target_field -> actual_dataframe_column``.

    synonyms = { "name": ["name", "consumer name", "customer name"], ... }
    Lookup is done on the normalized form of both keys and synonyms.
    """
    norm_to_orig: dict[str, str] = {_norm_col(c): str(c) for c in df_columns}
    mapping: dict[str, str] = {}
    for target, candidates in synonyms.items():
        for cand in candidates:
            key = _norm_col(cand)
            if key in norm_to_orig:
                mapping[target] = norm_to_orig[key]
                break
    return mapping


def _row_get(row: pd.Series, mapping: dict[str, str], target: str) -> Any:
    """Return the value of ``row`` at the mapped column, or None."""
    actual = mapping.get(target)
    if not actual:
        return None
    val = row.get(actual)
    if pd.isna(val):
        return None
    return val


# ===================================================================
# File discovery
# ===================================================================
FILE_PATTERNS: dict[str, list[str]] = {
    "consumers":  ["raid_master_data", "consumer_master", "raid master data",
                   "consumers", "master_data", "raidmasterdata"],
    "historical": ["all data", "all_data", "alldata", "historical",
                   "historical_cases", "purana", "purane case", "old cases",
                   "raid data", "past cases", "notice data"],
    "current":    ["raid excell 2526", "raid_excell_2526", "current_cases",
                   "raidexcell", "active_cases", "raid excel"],
    "devices":    ["device list", "device_list", "devices", "device master",
                   "device_master", "devicelist"],
    "rates":      ["slab_rates", "slab rates", "rates", "rate_master",
                   "ratemaster", "tariff", "tariff_slabs"],
    "mapping":    ["account_mapping", "account mapping", "acct_mapping",
                   "old_new_mapping"],
}


def find_master_file(kind: str) -> Path | None:
    """Locate the first Excel file in ``master_data/`` matching ``kind``."""
    if kind not in FILE_PATTERNS:
        raise ValueError(f"Unknown master kind: {kind}")
    patterns = [_norm_col(p) for p in FILE_PATTERNS[kind]]
    candidates: list[Path] = []
    for f in config.MASTER_DATA_DIR.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".xlsx", ".xls", ".xlsm"):
            continue
        if f.name.startswith("~$"):  # Excel lock file
            continue
        norm = _norm_col(f.stem)
        if any(p in norm for p in patterns):
            candidates.append(f)
    if not candidates:
        return None
    # Pick the largest file (most data) or alphabetically first as tiebreak
    candidates.sort(key=lambda p: (-p.stat().st_size, p.name))
    return candidates[0]


def _read_excel(path: Path, sheet: int | str | None = 0) -> pd.DataFrame:
    """Robust Excel reader that strips header whitespace."""
    df = pd.read_excel(path, sheet_name=sheet, dtype=object, engine="openpyxl")
    if isinstance(df, dict):
        # Multi-sheet — pick first non-empty
        for sheet_name, sub in df.items():
            if not sub.empty:
                df = sub
                break
        else:
            raise ValueError(f"No non-empty sheet in {path.name}")
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ===================================================================
# Synonym registries
# ===================================================================
CONSUMER_SYNONYMS: dict[str, list[str]] = {
    "account_number":  ["acct_id", "account_id", "account no", "account number",
                        "acctno", "acno", "k_no", "kno", "service no",
                        "connection_no", "consumer_id"],
    "name":            ["name", "consumer_name", "customer_name", "उपभोक्ता",
                        "उपभोक्ता का नाम", "नाम"],
    "father_name":     ["father_name", "fathername", "father", "fatherhusband",
                        "father/husband", "पिता", "पिता का नाम"],
    "address":         ["address", "addr", "premises", "पता"],
    "village":         ["village", "ward", "mohalla", "ग्राम"],
    "landmark":        ["landmark", "near", "नजदीक"],
    "post_office":     ["post", "post_office", "po", "डाकघर"],
    "pin_code":        ["pin", "pin_code", "pincode", "zip"],
    "tehsil":          ["tehsil", "tehsheel", "tahsil", "तहसील"],
    "district":        ["district", "जिला"],
    "mobile":          ["mobile_no", "mobile", "phone", "contact", "मोबाइल"],
    "load_value":      ["load", "connected_load", "load_kw", "sanctioned_load"],
    "load_unit":       ["load_unit", "loadunit", "unit"],
    "supply_type":     ["supply_type", "supplytype", "supply"],
    "category":        ["category", "tariff_category", "rate_category", "lmv"],
    "sub_substation":  ["sub_substation", "substation", "sub_station", "ss"],
    "connection_status": ["con_status", "connection_status", "status",
                          "conn_status"],
    "div_code":        ["div_code", "div_no", "division", "division_code",
                        "divcode", "divno"],
    "sc_number":       ["sc_no", "sc_number", "service_connection",
                        "service_no", "scno"],
}

HISTORICAL_SYNONYMS: dict[str, list[str]] = {
    "div_no":          ["div_no", "divno", "division", "div", "div. no",
                        "div.no", "div no."],
    "name":            ["name", "consumer_name", "नाम"],
    "father_name":     ["father_name", "fathername", "father", "father name",
                        "पिता", "पिता का नाम"],
    "village":         ["village", "ग्राम", "address"],
    "account_id":      ["account_id", "acct_id", "account_no", "acno", "k_no",
                        "old_ac_no", "old ac no", "old ac no.",
                        "new_ac_no", "new ac no", "new ac no."],
    "case_date":       ["date", "case_date", "raid_date", "inspection_date",
                        "तिथि", "दिनांक"],
    "assessment_amount": ["assessment", "assessment_amount", "amount",
                          "assesement", "assesment", "raashi", "राशि"],
    "fir_number":      ["fir", "fir_no", "fir_number", "एफआईआर"],
    "section":         ["dhara", "section", "धारा", "irregularity",
                        "irregularity type"],
    "notice_no":       ["notice_no", "notice no", "notice no.", "sr",
                        "sr no", "sr."],
    "use_name":        ["use_name", "use name", "user name", "user_name"],
    "user_father":     ["user_father_name", "user father name",
                        "user_father", "users father"],
    "sub_station":     ["sub_station", "sub station", "substation", "ss"],
    "old_ac_no":       ["old_ac_no", "old ac no", "old ac no.",
                        "old_account", "old account"],
    "new_ac_no":       ["new_ac_no", "new ac no", "new ac no.",
                        "new_account", "new account"],
    "category":        ["category", "catgary", "cat", "lmv"],
    "payment_status":  ["paid/unpaid", "paid_unpaid", "payment_status",
                        "pay_status", "paid", "unpaid"],
}

CURRENT_SYNONYMS: dict[str, list[str]] = {
    "online_no":       ["online_no", "online no", "onlineno", "online_number"],
    "div_no":          ["div_no", "divno", "division"],
    "name":            ["name", "consumer_name", "नाम"],
    "father_name":     ["father_name", "father", "पिता"],
    "village":         ["village", "ग्राम"],
    "connection_no":   ["connection_no", "conn_no", "account_id", "acno"],
    "inspection_date": ["date", "inspection_date", "raid_date", "dis_date",
                        "checking_date", "तिथि"],
    "section":         ["section", "dhara", "धारा"],
    "total_assessment":["assessment_total", "assessment", "total", "amount"],
    "notice_status":   ["notice_status", "notice", "notice_state"],
    "payment_status":  ["payment_status", "paystatus", "paid", "pay_state"],
}

DEVICE_SYNONYMS: dict[str, list[str]] = {
    "device_name":     ["device_name", "device", "name", "equipment",
                        "equipment_name", "उपकरण"],
    "category":        ["category", "type", "group", "श्रेणी"],
    "default_load":    ["load", "default_load", "wattage", "watts", "watt",
                        "load_w", "power"],
    "default_factor":  ["factor", "default_factor", "diversity", "df", "f"],
    "default_hours":   ["hours", "default_hours", "h", "duration"],
    "default_days":    ["days", "default_days", "d"],
    "unit":            ["unit", "uom"],
}

RATE_SYNONYMS: dict[str, list[str]] = {
    "category":        ["category", "tariff_category", "lmv", "rate_category"],
    "slab_start":      ["slabstart", "slab_start", "from", "from_unit",
                        "lower_limit", "min_units"],
    "slab_end":        ["slabend", "slab_end", "to", "to_unit",
                        "upper_limit", "max_units"],
    "rate_per_unit":   ["rateperunit", "rate_per_unit", "rate", "tariff",
                        "energy_rate"],
    "fixed_charge":    ["fixedcharge", "fixed_charge", "fixed", "fixed_rate",
                        "monthly_fixed"],
    "duty_percent":    ["dutypercent", "duty_percent", "duty", "ed",
                        "ed_percent", "electricity_duty"],
    "condition":       ["condition", "remark", "remarks", "note"],
    "effective_date":  ["effectivedate", "effective_date", "from_date",
                        "valid_from"],
    "end_date":        ["enddate", "end_date", "to_date", "valid_to"],
}

MAPPING_SYNONYMS: dict[str, list[str]] = {
    "old_account":     ["old_account", "old_acno", "old_acct_id",
                        "previous_account"],
    "new_account":     ["new_account", "new_acno", "new_acct_id",
                        "current_account", "account"],
    "sc_number":       ["sc_no", "sc_number", "service_connection"],
    "consumer_name":   ["name", "consumer_name", "customer_name"],
    "father_name":     ["father_name", "father"],
    "village":         ["village"],
    "effective_date":  ["effective_date", "from_date", "date"],
    "status":          ["status", "active", "is_active"],
}


# ===================================================================
# Generic per-row processor
# ===================================================================
def _process_table(
    *,
    kind: str,
    file_path: Path,
    df: pd.DataFrame,
    synonyms: dict[str, list[str]],
    required: list[str],
    upsert_fn,                # callable(conn, row_dict, raw_dict) -> str ("inserted"|"updated"|"skipped")
    progress_label: str = "",
) -> ImportReport:
    import time
    started = time.time()
    rep = ImportReport(kind=kind, file_path=str(file_path),
                       total_rows=len(df))

    if df.empty:
        rep.warnings.append("File is empty (0 rows).")
        rep.duration_ms = int((time.time() - started) * 1000)
        return rep

    mapping = _build_column_map(df.columns, synonyms)
    rep.column_mapping = mapping

    # Surface unmapped required fields up-front instead of crashing later
    missing = [f for f in required if f not in mapping]
    if missing:
        rep.warnings.append(
            f"Required columns missing from sheet: {missing}. "
            f"Available columns: {list(df.columns)}"
        )
        # Don't bail — continue and let upsert_fn skip rows that lack values.

    with standalone_connection() as conn:
        for idx, row in df.iterrows():
            try:
                # Build the target dict
                values: dict[str, Any] = {}
                for tgt in synonyms.keys():
                    values[tgt] = _row_get(row, mapping, tgt)

                # Snapshot raw row for traceability
                raw = {str(k): (None if pd.isna(v) else v)
                       for k, v in row.items()}

                outcome = upsert_fn(conn, values, raw)
                if outcome == "inserted":
                    rep.inserted += 1
                elif outcome == "updated":
                    rep.updated += 1
                else:
                    rep.skipped += 1

            except Exception as e:  # noqa: BLE001
                rep.errors.append({
                    "row": int(idx) + 2,  # +2 = excel row (header + 1-index)
                    "reason": f"{type(e).__name__}: {e}",
                })
                rep.skipped += 1

        conn.commit()

    rep.duration_ms = int((time.time() - started) * 1000)
    log.info("Import %s: %s", kind, rep.to_dict())
    return rep


# ===================================================================
# Per-table upsert functions
# ===================================================================
def _upsert_consumer(conn, v: dict, raw: dict) -> str:
    acct = normalize_account(v.get("account_number"))
    if not acct:
        return "skipped"
    existing = conn.execute(
        "SELECT id FROM consumers WHERE account_number=?", (acct,)
    ).fetchone()
    payload = (
        v.get("name") and str(v["name"]).strip() or None,
        v.get("father_name") and str(v["father_name"]).strip() or None,
        v.get("address") and str(v["address"]).strip() or None,
        v.get("village") and str(v["village"]).strip() or None,
        v.get("landmark") and str(v["landmark"]).strip() or None,
        v.get("post_office") and str(v["post_office"]).strip() or None,
        v.get("pin_code") and str(v["pin_code"]).strip() or None,
        v.get("tehsil") and str(v["tehsil"]).strip() or None,
        v.get("district") and str(v["district"]).strip() or None,
        v.get("mobile") and str(v["mobile"]).strip() or None,
        safe_float(v.get("load_value")) or None,
        v.get("load_unit") and str(v["load_unit"]).strip() or None,
        v.get("supply_type") and str(v["supply_type"]).strip() or None,
        v.get("category") and str(v["category"]).strip() or None,
        v.get("sub_substation") and str(v["sub_substation"]).strip() or None,
        v.get("connection_status") and str(v["connection_status"]).strip() or None,
        v.get("div_code") and str(v["div_code"]).strip() or None,
        v.get("sc_number") and str(v["sc_number"]).strip() or None,
        to_json_str(raw),
    )
    if existing:
        conn.execute(
            """UPDATE consumers SET
                  name=?, father_name=?, address=?, village=?, landmark=?,
                  post_office=?, pin_code=?, tehsil=?, district=?, mobile=?,
                  load_value=?, load_unit=?, supply_type=?, category=?,
                  sub_substation=?, connection_status=?, div_code=?,
                  sc_number=?, raw_payload=?,
                  updated_at=datetime('now')
               WHERE account_number=?""",
            payload + (acct,),
        )
        return "updated"
    conn.execute(
        """INSERT INTO consumers
              (name, father_name, address, village, landmark, post_office,
               pin_code, tehsil, district, mobile, load_value, load_unit,
               supply_type, category, sub_substation, connection_status,
               div_code, sc_number, raw_payload, account_number)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        payload + (acct,),
    )
    return "inserted"


def _upsert_historical(conn, v: dict, raw: dict) -> str:
    name = v.get("name")
    acct = v.get("account_id") or v.get("old_ac_no") or v.get("new_ac_no")
    if not name and not acct:
        return "skipped"

    # Use new_ac_no as primary account if available, fallback to old
    primary_acct = normalize_account(v.get("new_ac_no")) or normalize_account(v.get("old_ac_no")) or normalize_account(acct)

    conn.execute(
        """INSERT INTO historical_cases
              (div_no, name, father_name, village, account_id,
               case_date, assessment_amount, fir_number, section,
               raw_payload, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,'historical')""",
        (
            v.get("div_no") and str(v["div_no"]).strip() or None,
            name and str(name).strip() or None,
            v.get("father_name") and str(v["father_name"]).strip() or None,
            v.get("village") and str(v["village"]).strip() or None,
            primary_acct or None,
            parse_date(v.get("case_date")),
            safe_float(v.get("assessment_amount")) or None,
            v.get("fir_number") and str(v["fir_number"]).strip() or None,
            v.get("section") and str(v["section"]).strip() or None,
            to_json_str(raw),
        ),
    )

    # Update offense_summary for repeat-offense detection
    if primary_acct or (name and v.get("father_name") and v.get("village")):
        consumer_key = primary_acct or f"{name}|{v.get('father_name')}|{v.get('village')}"
        consumer_key = consumer_key.strip().lower() if consumer_key else None
        if consumer_key:
            existing_off = conn.execute(
                "SELECT * FROM offense_summary WHERE consumer_key=?",
                (consumer_key,)
            ).fetchone()
            case_dt = parse_date(v.get("case_date"))
            assessment = safe_float(v.get("assessment_amount")) or 0

            if existing_off:
                conn.execute(
                    """UPDATE offense_summary SET
                          total_offenses = total_offenses + 1,
                          first_offense_date = MIN(COALESCE(first_offense_date, ?), COALESCE(?, first_offense_date)),
                          last_offense_date = MAX(COALESCE(last_offense_date, ?), COALESCE(?, last_offense_date)),
                          total_assessment = total_assessment + ?,
                          updated_at = datetime('now')
                       WHERE consumer_key=?""",
                    (case_dt, case_dt, case_dt, case_dt, assessment, consumer_key),
                )
            else:
                conn.execute(
                    """INSERT INTO offense_summary
                          (consumer_key, total_offenses, first_offense_date,
                           last_offense_date, total_assessment)
                       VALUES (?, 1, ?, ?, ?)""",
                    (consumer_key, case_dt, case_dt, assessment),
                )

    return "inserted"


def _upsert_current(conn, v: dict, raw: dict) -> str:
    online = v.get("online_no")
    if online:
        existing = conn.execute(
            "SELECT id FROM current_cases WHERE online_no=?",
            (str(online).strip(),),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE current_cases SET
                      div_no=?, name=?, father_name=?, village=?, connection_no=?,
                      inspection_date=?, section=?, total_assessment=?,
                      notice_status=?, payment_status=?, raw_payload=?,
                      imported_at=datetime('now')
                   WHERE online_no=?""",
                (
                    v.get("div_no") and str(v["div_no"]).strip() or None,
                    v.get("name") and str(v["name"]).strip() or None,
                    v.get("father_name") and str(v["father_name"]).strip() or None,
                    v.get("village") and str(v["village"]).strip() or None,
                    normalize_account(v.get("connection_no")) or None,
                    parse_date(v.get("inspection_date")),
                    v.get("section") and str(v["section"]).strip() or None,
                    safe_float(v.get("total_assessment")) or None,
                    v.get("notice_status") and str(v["notice_status"]).strip() or None,
                    v.get("payment_status") and str(v["payment_status"]).strip() or None,
                    to_json_str(raw),
                    str(online).strip(),
                ),
            )
            return "updated"
    conn.execute(
        """INSERT INTO current_cases
              (online_no, div_no, name, father_name, village, connection_no,
               inspection_date, section, total_assessment,
               notice_status, payment_status, raw_payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            online and str(online).strip() or None,
            v.get("div_no") and str(v["div_no"]).strip() or None,
            v.get("name") and str(v["name"]).strip() or None,
            v.get("father_name") and str(v["father_name"]).strip() or None,
            v.get("village") and str(v["village"]).strip() or None,
            normalize_account(v.get("connection_no")) or None,
            parse_date(v.get("inspection_date")),
            v.get("section") and str(v["section"]).strip() or None,
            safe_float(v.get("total_assessment")) or None,
            v.get("notice_status") and str(v["notice_status"]).strip() or None,
            v.get("payment_status") and str(v["payment_status"]).strip() or None,
            to_json_str(raw),
        ),
    )
    return "inserted"


def _upsert_device(conn, v: dict, _raw: dict) -> str:
    name = v.get("device_name")
    if not name:
        return "skipped"
    name = str(name).strip()
    existing = conn.execute(
        "SELECT id FROM device_master WHERE device_name=?", (name,)
    ).fetchone()
    payload = (
        v.get("category") and str(v["category"]).strip() or None,
        safe_float(v.get("default_load")) or None,
        safe_float(v.get("default_factor"), 1.0),
        safe_float(v.get("default_hours"), 8),
        safe_int(v.get("default_days"), 365),
        v.get("unit") and str(v["unit"]).strip() or "Nos",
    )
    if existing:
        conn.execute(
            """UPDATE device_master SET
                  category=?, default_load=?, default_factor=?,
                  default_hours=?, default_days=?, unit=?
               WHERE device_name=?""",
            payload + (name,),
        )
        return "updated"
    conn.execute(
        """INSERT INTO device_master
              (category, default_load, default_factor, default_hours,
               default_days, unit, device_name)
           VALUES (?,?,?,?,?,?,?)""",
        payload + (name,),
    )
    return "inserted"


def _upsert_rate(conn, v: dict, _raw: dict) -> str:
    cat = v.get("category")
    if not cat:
        return "skipped"
    cat = str(cat).strip()
    slab_start = safe_int(v.get("slab_start"), 0)
    slab_end_raw = v.get("slab_end")
    slab_end = safe_int(slab_end_raw) if slab_end_raw not in (None, "", "∞", "Inf", "inf") else None
    conn.execute(
        """INSERT INTO rate_master
              (category, slab_start, slab_end, rate_per_unit, fixed_charge,
               duty_percent, condition, effective_date, end_date)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            cat, slab_start, slab_end,
            safe_float(v.get("rate_per_unit")),
            safe_float(v.get("fixed_charge")),
            safe_float(v.get("duty_percent")),
            v.get("condition") and str(v["condition"]).strip() or None,
            parse_date(v.get("effective_date")),
            parse_date(v.get("end_date")),
        ),
    )
    return "inserted"


def _upsert_mapping(conn, v: dict, _raw: dict) -> str:
    if not (v.get("old_account") or v.get("new_account")):
        return "skipped"
    conn.execute(
        """INSERT INTO account_mapping
              (old_account, new_account, sc_number, consumer_name,
               father_name, village, effective_date, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            normalize_account(v.get("old_account")) or None,
            normalize_account(v.get("new_account")) or None,
            v.get("sc_number") and str(v["sc_number"]).strip() or None,
            v.get("consumer_name") and str(v["consumer_name"]).strip() or None,
            v.get("father_name") and str(v["father_name"]).strip() or None,
            v.get("village") and str(v["village"]).strip() or None,
            parse_date(v.get("effective_date")),
            v.get("status") and str(v["status"]).strip() or "active",
        ),
    )
    return "inserted"


# ===================================================================
# Public per-table import functions
# ===================================================================
def import_consumers(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("consumers")
    if not path:
        return ImportReport(kind="consumers",
                            warnings=["No consumer master file found in master_data/"])
    df = _read_excel(path)
    return _process_table(
        kind="consumers", file_path=path, df=df,
        synonyms=CONSUMER_SYNONYMS,
        required=["account_number"],
        upsert_fn=_upsert_consumer,
    )


def import_historical(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("historical")
    if not path:
        return ImportReport(kind="historical",
                            warnings=["No historical file found in master_data/"])
    df = _read_excel(path)
    return _process_table(
        kind="historical", file_path=path, df=df,
        synonyms=HISTORICAL_SYNONYMS,
        required=[],
        upsert_fn=_upsert_historical,
    )


def import_current(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("current")
    if not path:
        return ImportReport(kind="current",
                            warnings=["No current-cases file found in master_data/"])
    df = _read_excel(path)
    return _process_table(
        kind="current", file_path=path, df=df,
        synonyms=CURRENT_SYNONYMS,
        required=[],
        upsert_fn=_upsert_current,
    )


def import_devices(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("devices")
    if not path:
        return ImportReport(kind="devices",
                            warnings=["No device-list file found in master_data/ "
                                      "(default 40 devices already seeded)"])
    df = _read_excel(path)
    return _process_table(
        kind="devices", file_path=path, df=df,
        synonyms=DEVICE_SYNONYMS,
        required=["device_name"],
        upsert_fn=_upsert_device,
    )


def import_rates(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("rates")
    if not path:
        return ImportReport(kind="rates",
                            warnings=["No slab-rates file found in master_data/"])
    df = _read_excel(path)
    return _process_table(
        kind="rates", file_path=path, df=df,
        synonyms=RATE_SYNONYMS,
        required=["category"],
        upsert_fn=_upsert_rate,
    )


def import_account_mapping(path: Path | None = None) -> ImportReport:
    path = path or find_master_file("mapping")
    if not path:
        return ImportReport(kind="mapping",
                            warnings=["No account_mapping file found "
                                      "(optional)."])
    df = _read_excel(path)
    return _process_table(
        kind="mapping", file_path=path, df=df,
        synonyms=MAPPING_SYNONYMS,
        required=[],
        upsert_fn=_upsert_mapping,
    )


def import_all() -> dict[str, dict]:
    """Run every importer; return a kind→report dict.

    Each importer is wrapped in its own try/except so one bad file never
    stops the others.
    """
    runners = [
        ("consumers",  import_consumers),
        ("historical", import_historical),
        ("current",    import_current),
        ("devices",    import_devices),
        ("rates",      import_rates),
        ("mapping",    import_account_mapping),
    ]
    out: dict[str, dict] = {}
    for kind, fn in runners:
        try:
            out[kind] = fn().to_dict()
        except Exception as e:  # noqa: BLE001
            log.exception("Import failed for %s", kind)
            out[kind] = ImportReport(
                kind=kind,
                errors=[{"row": 0, "reason": f"{type(e).__name__}: {e}"}],
            ).to_dict()
    return out


def list_master_files() -> dict[str, str | None]:
    """Diagnostic: which file would be picked for each kind?"""
    return {kind: (str(p) if p else None)
            for kind, p in ((k, find_master_file(k)) for k in FILE_PATTERNS)}
