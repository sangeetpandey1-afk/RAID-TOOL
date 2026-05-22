"""
Historical-import service — parses .xlsx / .xls / .csv uploads of OLD
raid data and inserts them into the existing ``historical_cases`` table.

Why this is its own service
---------------------------
The existing ``services/importer.py`` handles regular master-data files
that live on the operator's hard disk under ``master_data/``.  The
historical-import flow is different:

* triggered by an HTTP file upload (multipart/form-data),
* a one-off file the operator chooses,
* needs an idempotent dedup mechanism so the operator can re-upload
  the same workbook any number of times without creating duplicates,
* must produce a per-row summary (imported / duplicates / skipped /
  errors) for the UI.

Keeping this file isolated means we never accidentally change the
behaviour of the well-tested master-data importer.

Public API
----------
* ``parse_file(file_path) -> ParsedFile``        # extract rows + headers
* ``import_rows(conn, rows, source_filename) -> ImportSummary``
* ``import_file(conn, file_path, source_filename) -> ImportSummary``
   - convenience wrapper combining the two

Schema dependency
-----------------
The route registers the migrations below in ``database.py``:

    historical_cases.old_case_ref       TEXT
    historical_cases.compounding_amount REAL
    historical_cases.dedup_key          TEXT  + UNIQUE INDEX

A row is uniquely identified by::

    dedup_key = normalize_account(account_id) | case_date | normalize(old_case_ref)
                | f"{assessment_amount:.2f}"

so re-uploading an identical workbook is a no-op.

Required columns
----------------
The operator's source files vary wildly.  Header matching is therefore
synonym-driven, case-insensitive, and tolerant of Hindi labels.  Only
the New Account Number is *required*; everything else is optional.

    account_id           = REQUIRED
    case_date            = optional  (parsed via utils.parse_date)
    assessment_amount    = optional
    compounding_amount   = optional
    old_case_ref         = optional
    fir_number           = optional
    section              = optional
    name / father / village / div_no = optional, stored if present so
                            the legacy reports / matcher.py keep
                            something to display.

Any other Excel column is preserved in ``raw_payload`` (JSON) but
otherwise ignored.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from ..utils import (
    normalize_account, normalize_text, safe_float, parse_date, to_json_str,
)

log = logging.getLogger(__name__)


__all__ = [
    "ParsedFile",
    "ImportSummary",
    "parse_file",
    "import_rows",
    "import_file",
    "make_dedup_key",
    "COLUMN_SYNONYMS",
]


# ---------------------------------------------------------------------
# Column-header synonym map  (lowercased on lookup)
#
# The keys are the canonical fields the historical_cases table holds;
# the values are every header text the importer should treat as that
# field.  Add new aliases freely — this is plain data.
# ---------------------------------------------------------------------

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "account_id": [
        "account", "account no", "account number", "acct", "acct no",
        "new account", "new account no", "new account number",
        "connection no", "connection number", "connection",
        "खाता संख्या", "अकाउंट", "एकाउंट",
    ],
    "old_case_ref": [
        "old case", "old case ref", "old case reference",
        "old case no", "old case number", "case ref", "case reference",
        "previous case", "prev case", "old ref",
        "पुराना केस", "पुराना संदर्भ",
    ],
    "case_date": [
        "date", "case date", "raid date", "inspection date",
        "checking date", "raid/inspection date", "raid / inspection date",
        "तारीख", "दिनांक",
    ],
    "assessment_amount": [
        "assessment", "assessment amount", "assessed amount",
        "amount", "amount assessed", "raid amount",
        "assessment ₹", "assessment rs", "assessment (rs)",
        "निर्धारण राशि", "राशि",
    ],
    "compounding_amount": [
        "compounding", "compounding amount",
        "compounding rs", "compound amount", "compound",
        "compound amount ₹", "section 152 amount",
        "शमन राशि",
    ],
    "fir_number": [
        "fir", "fir no", "fir number", "fir #",
        "एफआईआर",
    ],
    "section": [
        "section", "dhara", "धारा", "act section",
    ],
    "name": ["name", "consumer name", "नाम", "उपभोक्ता नाम"],
    "father_name": [
        "father", "father name", "father's name", "fathers name",
        "father / husband", "पिता का नाम", "पिता",
    ],
    "village": ["village", "ward", "ग्राम", "मोहल्ला"],
    "div_no":  ["div", "div no", "division", "division no", "div code", "डिविजन"],
}


# ---------------------------------------------------------------------
# Public dataclasses (serialise straight to envelope_ok)
# ---------------------------------------------------------------------

@dataclass
class ParsedFile:
    source_file:    str
    sheet_name:     str | None
    total_rows:     int
    column_mapping: dict[str, str]            # canonical_field -> original_header
    rows:           list[dict[str, Any]]      # already-canonicalised rows
    extra_headers:  list[str]                 # headers we did NOT recognise

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Don't ship every row when the caller asks for a quick parse summary
        d["rows_count"] = len(d.pop("rows"))
        return d


@dataclass
class RowError:
    row_num: int
    reason:  str

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row_num, "reason": self.reason}


@dataclass
class ImportSummary:
    source_file: str
    sheet_name:  str | None = None
    total_rows:  int = 0
    imported:    int = 0
    duplicates:  int = 0
    skipped:     int = 0
    errors:      list[RowError] = field(default_factory=list)
    duration_ms: int = 0
    column_mapping: dict[str, str] = field(default_factory=dict)
    extra_headers:  list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file":    self.source_file,
            "sheet_name":     self.sheet_name,
            "total_rows":     self.total_rows,
            "imported":       self.imported,
            "duplicates":     self.duplicates,
            "skipped":        self.skipped,
            "errors":         [e.to_dict() for e in self.errors],
            "duration_ms":    self.duration_ms,
            "column_mapping": self.column_mapping,
            "extra_headers":  self.extra_headers,
        }


# ---------------------------------------------------------------------
# Dedup key
# ---------------------------------------------------------------------

def make_dedup_key(account_id: str | None,
                   case_date: str | None,
                   old_case_ref: str | None,
                   assessment_amount: Any) -> str:
    """Stable canonical fingerprint of a historical row.

    Used as the column ``historical_cases.dedup_key`` with a UNIQUE
    index, so ``INSERT OR IGNORE`` silently drops repeated rows on
    re-upload.  Order of fields is deliberately fixed; do NOT reorder
    without bumping the migration logic.
    """
    parts = [
        normalize_account(account_id),
        (case_date or "").strip(),
        normalize_text(old_case_ref or ""),
        f"{safe_float(assessment_amount):.2f}",
    ]
    raw = "|".join(parts)
    # Hash to keep the column compact and constant-width regardless of
    # the original strings' lengths (Hindi text + long refs can blow
    # past 200 chars otherwise).
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------

def _build_inverse_synonyms() -> dict[str, str]:
    """Lowercased header text -> canonical field name."""
    out: dict[str, str] = {}
    for canonical, aliases in COLUMN_SYNONYMS.items():
        for a in aliases:
            out[a.strip().lower()] = canonical
    return out


_INVERSE_SYNONYMS = _build_inverse_synonyms()


def _canonical_header(raw_header: str) -> str | None:
    """Map an Excel header to a canonical field name, or None if unknown."""
    if raw_header is None:
        return None
    key = str(raw_header).strip().lower()
    if not key:
        return None
    return _INVERSE_SYNONYMS.get(key)


# ---------------------------------------------------------------------
# File parsers
# ---------------------------------------------------------------------

def _read_xlsx(path: Path) -> tuple[list[list[Any]], str]:
    """Read the FIRST sheet of an .xlsx / .xls workbook."""
    # Lazy import — pandas is heavy and only needed when a workbook
    # actually arrives.  CSV files take the lighter path below.
    import pandas as pd  # noqa: WPS433
    df = pd.read_excel(path, sheet_name=0, dtype=object, header=0)
    sheet_name = df.attrs.get("sheet_name") or "Sheet1"
    rows: list[list[Any]] = [list(df.columns)]
    for _, row in df.iterrows():
        rows.append([
            (None if pd.isna(v) else v) for v in row.tolist()
        ])
    return rows, sheet_name


def _read_csv(path: Path) -> tuple[list[list[Any]], str]:
    """Read a CSV with a tolerant DictReader."""
    rows: list[list[Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for r in reader:
            rows.append([(c if c != "" else None) for c in r])
    return rows, path.stem


def _read_any(path: Path) -> tuple[list[list[Any]], str]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        return _read_xlsx(path)
    if suffix in (".csv", ".txt"):
        return _read_csv(path)
    raise ValueError(
        f"Unsupported file extension: {suffix!r}. "
        f"Supported: .xlsx, .xls, .xlsm, .csv"
    )


def parse_file(path: str | Path) -> ParsedFile:
    """Read the file from disk and produce a list of canonicalised rows.

    Each row in ``ParsedFile.rows`` is a dict whose keys are the
    canonical column names (``account_id``, ``case_date``, ...).
    Any unknown columns are dropped from the per-row dict but
    preserved verbatim in ``raw_payload`` (built later in import_rows).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Historical import file missing: {p}")

    raw_rows, sheet_name = _read_any(p)
    if not raw_rows:
        return ParsedFile(
            source_file=p.name, sheet_name=sheet_name,
            total_rows=0, column_mapping={}, rows=[], extra_headers=[],
        )

    headers = raw_rows[0]
    column_mapping: dict[str, str] = {}    # canonical -> original
    extra_headers: list[str] = []
    canonical_per_index: list[str | None] = []

    for h in headers:
        canonical = _canonical_header(h)
        canonical_per_index.append(canonical)
        if canonical and canonical not in column_mapping:
            column_mapping[canonical] = str(h)
        elif not canonical and h is not None and str(h).strip():
            extra_headers.append(str(h))

    parsed: list[dict[str, Any]] = []
    for raw in raw_rows[1:]:
        canonical_row: dict[str, Any] = {}
        # Always preserve the original header->value mapping for raw_payload
        original: dict[str, Any] = {}
        for i, value in enumerate(raw):
            if i >= len(headers):
                continue
            original_header = headers[i]
            if original_header is None:
                continue
            original[str(original_header)] = value
            canonical = canonical_per_index[i]
            if canonical:
                canonical_row[canonical] = value
        canonical_row["__raw__"] = original
        parsed.append(canonical_row)

    return ParsedFile(
        source_file=p.name,
        sheet_name=sheet_name,
        total_rows=len(parsed),
        column_mapping=column_mapping,
        rows=parsed,
        extra_headers=extra_headers,
    )


# ---------------------------------------------------------------------
# Importer (DB-side)
# ---------------------------------------------------------------------

# Columns we INSERT explicitly.  The schema's other columns (id,
# imported_at, source) take their declared defaults.
_INSERT_SQL = """
    INSERT OR IGNORE INTO historical_cases (
        div_no, name, father_name, village,
        account_id, case_date, assessment_amount,
        fir_number, section,
        old_case_ref, compounding_amount,
        raw_payload, dedup_key, source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _row_is_blank(row: dict[str, Any]) -> bool:
    """A fully-blank row (all canonical fields empty) is silently skipped."""
    keys = ("account_id", "case_date", "assessment_amount",
            "old_case_ref", "fir_number", "name", "father_name", "village")
    return all(
        row.get(k) is None or str(row.get(k)).strip() == ""
        for k in keys
    )


def import_rows(conn: sqlite3.Connection,
                rows: Iterable[dict[str, Any]],
                source_filename: str,
                *,
                sheet_name: str | None = None,
                column_mapping: dict[str, str] | None = None,
                extra_headers: list[str] | None = None) -> ImportSummary:
    """Insert canonicalised rows into ``historical_cases``.

    Rules
    -----
    * Missing/blank New Account Number    -> skipped (recorded as error).
    * Fully-blank row                    -> skipped (no error, common in
                                          spreadsheets with trailing blanks).
    * INSERT OR IGNORE on dedup_key      -> existing rows count as duplicates.
    * Date parsing failures              -> stored as None, NOT an error
                                          (date is optional per spec).

    Returns a populated ``ImportSummary``.  No exception escapes this
    function unless the DB connection itself fails — every per-row
    issue becomes an entry in ``summary.errors``.
    """
    started = time.monotonic()
    summary = ImportSummary(
        source_file=source_filename,
        sheet_name=sheet_name,
        column_mapping=column_mapping or {},
        extra_headers=extra_headers or [],
    )

    rows_list = list(rows)
    summary.total_rows = len(rows_list)

    inserts: list[tuple] = []

    for idx, row in enumerate(rows_list, start=2):  # +2: header is row 1
        if _row_is_blank(row):
            summary.skipped += 1
            continue

        account_id = row.get("account_id")
        if not account_id or not str(account_id).strip():
            summary.skipped += 1
            summary.errors.append(RowError(
                row_num=idx,
                reason="missing New Account Number",
            ))
            continue

        case_date_raw = row.get("case_date")
        case_date = parse_date(case_date_raw) if case_date_raw else None

        assessment = (
            safe_float(row.get("assessment_amount"))
            if row.get("assessment_amount") not in (None, "") else None
        )
        compounding = (
            safe_float(row.get("compounding_amount"))
            if row.get("compounding_amount") not in (None, "") else None
        )

        old_case_ref = row.get("old_case_ref")
        if old_case_ref is not None:
            old_case_ref = str(old_case_ref).strip() or None

        dedup = make_dedup_key(
            account_id=str(account_id),
            case_date=case_date,
            old_case_ref=old_case_ref,
            assessment_amount=assessment,
        )

        raw_payload = to_json_str(row.get("__raw__") or {})

        inserts.append((
            (str(row["div_no"]).strip()      if row.get("div_no")      else None),
            (str(row["name"]).strip()        if row.get("name")        else None),
            (str(row["father_name"]).strip() if row.get("father_name") else None),
            (str(row["village"]).strip()     if row.get("village")     else None),
            str(account_id).strip(),
            case_date,
            assessment,
            (str(row["fir_number"]).strip()  if row.get("fir_number")  else None),
            (str(row["section"]).strip()     if row.get("section")     else None),
            old_case_ref,
            compounding,
            raw_payload,
            dedup,
            "historical_import",
        ))

    if inserts:
        # Run all inserts in a single transaction for speed.
        cursor = conn.cursor()
        try:
            for record in inserts:
                cursor.execute(_INSERT_SQL, record)
                # cursor.rowcount is 1 on insert, 0 on IGNORE-as-duplicate.
                if cursor.rowcount == 1:
                    summary.imported += 1
                else:
                    summary.duplicates += 1
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            log.exception("Historical import failed for %s", source_filename)
            summary.errors.append(RowError(
                row_num=0,
                reason=f"DB error: {type(e).__name__}: {e}",
            ))

    summary.duration_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "Historical import: file=%s total=%d imported=%d duplicates=%d "
        "skipped=%d errors=%d duration=%dms",
        source_filename, summary.total_rows, summary.imported,
        summary.duplicates, summary.skipped, len(summary.errors),
        summary.duration_ms,
    )
    return summary


def import_file(conn: sqlite3.Connection,
                file_path: str | Path,
                source_filename: str | None = None) -> ImportSummary:
    """Convenience: parse_file + import_rows in one call."""
    parsed = parse_file(file_path)
    return import_rows(
        conn,
        parsed.rows,
        source_filename or parsed.source_file,
        sheet_name=parsed.sheet_name,
        column_mapping=parsed.column_mapping,
        extra_headers=parsed.extra_headers,
    )
