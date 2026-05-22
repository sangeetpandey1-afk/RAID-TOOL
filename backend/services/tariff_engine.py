"""
Tariff engine — schedule + rate import, lookup, and overlap detection.

Sits alongside ``services/historical_import.py`` (which handles old
offense data) and follows the same patterns:

* pure stdlib + sqlite3, no Flask import,
* tolerant column-header synonym matching (English + Hindi),
* dataclasses for response shapes,
* ``INSERT OR IGNORE``-style idempotency where it makes sense,
* logs everything to ``backend.services.tariff_engine``.

Public API
----------
* ``parse_rates_file(path) -> ParsedFile``
* ``import_schedule(conn, schedule_meta, parsed) -> ImportResult``
* ``list_schedules(conn) -> list[dict]``
* ``get_schedule(conn, schedule_id, include_rates=True) -> dict | None``
* ``find_applicable_rate(conn, **filters) -> dict | None``
* ``detect_overlap(conn, effective_from, effective_to,
                   exclude_id=None) -> list[dict]``
* ``set_active(conn, schedule_id, is_active) -> bool``
* ``build_sample_workbook(out_path) -> str``

Database dependency
-------------------
The route registers two new tables via ``database.py``::

    tariff_schedules(id, schedule_name, effective_from, effective_to,
                     uploaded_at, is_active, source_file, notes)
    tariff_rates(id, schedule_id, category, subcategory, supply_type,
                 load_from, load_to, unit_from, unit_to, fixed_charge,
                 energy_charge, minimum_charge, duty_percent,
                 multiplier_default)

Naming note
-----------
The project owner's spec calls the second table "rate_master" but the
existing legacy ``rate_master`` table (used by services/calculator.py)
has a fundamentally different schema.  Replacing it would break the
live LFHD calculator, so we name the new table ``tariff_rates``.  A
future PR can opt the calculator into reading from this table; until
then both tables coexist peacefully.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from ..utils import (
    normalize_text, safe_float, parse_date, to_json_str,
)

log = logging.getLogger(__name__)


__all__ = [
    "ParsedFile",
    "ImportResult",
    "ScheduleMeta",
    "COLUMN_SYNONYMS",
    "parse_rates_file",
    "import_schedule",
    "list_schedules",
    "get_schedule",
    "find_applicable_rate",
    "detect_overlap",
    "set_active",
    "build_sample_workbook",
]


# ---------------------------------------------------------------------
# Header synonyms — case-insensitive match
# ---------------------------------------------------------------------

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "category": [
        "category", "cat", "rate cat", "rate category",
        "श्रेणी", "वर्ग",
    ],
    "subcategory": [
        "subcategory", "sub category", "sub-category", "sub cat",
        "subdivision", "rural/urban", "urban/rural",
        "उपश्रेणी",
    ],
    "supply_type": [
        "supply type", "supply", "tariff type",
        "आपूर्ति प्रकार",
    ],
    "load_from": [
        "load from", "min load", "load min", "load (from)",
        "kw from", "from (kw)",
    ],
    "load_to": [
        "load to", "max load", "load max", "load (to)",
        "kw to", "to (kw)",
    ],
    "unit_from": [
        "unit from", "slab start", "slab from", "min units",
        "from units", "from (units)",
    ],
    "unit_to": [
        "unit to", "slab end", "slab to", "max units",
        "to units", "to (units)",
    ],
    "fixed_charge": [
        "fixed charge", "fixed", "fixed rs", "fixed (rs)",
        "fixed/month", "fixed per month",
        "स्थिर शुल्क",
    ],
    "energy_charge": [
        "energy charge", "rate", "rate per unit", "energy rate",
        "rs/unit", "rs per unit", "₹/unit", "₹ per unit",
        "ऊर्जा शुल्क", "दर",
    ],
    "minimum_charge": [
        "minimum charge", "min charge", "minimum",
        "न्यूनतम शुल्क",
    ],
    "duty_percent": [
        "duty", "duty %", "duty percent", "electricity duty",
        "ed %", "electricity duty %", "विद्युत शुल्क",
    ],
    "multiplier_default": [
        "multiplier", "default multiplier", "mult", "मल्टीप्लायर",
    ],
}


_REQUIRED_FIELDS = ("category", "energy_charge")


# ---------------------------------------------------------------------
# Dataclasses — JSON-serialisable response shapes
# ---------------------------------------------------------------------

@dataclass
class ParsedFile:
    source_file:    str
    sheet_name:     str | None
    total_rows:     int
    column_mapping: dict[str, str]
    rows:           list[dict[str, Any]]
    extra_headers:  list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rows_count"] = len(d.pop("rows"))
        return d


@dataclass
class RowError:
    row_num: int
    reason:  str

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row_num, "reason": self.reason}


@dataclass
class ScheduleMeta:
    schedule_name:  str
    effective_from: str | None = None
    effective_to:   str | None = None
    notes:          str | None = None
    source_file:    str | None = None


@dataclass
class ImportResult:
    schedule_id:    int | None = None
    schedule_name:  str = ""
    effective_from: str | None = None
    effective_to:   str | None = None
    source_file:    str | None = None
    total_rows:     int = 0
    inserted:       int = 0
    skipped:        int = 0
    errors:         list[RowError] = field(default_factory=list)
    overlaps:       list[dict[str, Any]] = field(default_factory=list)
    duration_ms:    int = 0
    column_mapping: dict[str, str] = field(default_factory=dict)
    extra_headers:  list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["errors"] = [e.to_dict() if isinstance(e, RowError) else e
                       for e in d["errors"]]
        return d


# ---------------------------------------------------------------------
# File reading (xlsx / xls / csv)
# ---------------------------------------------------------------------

def _build_inverse_synonyms() -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, aliases in COLUMN_SYNONYMS.items():
        for a in aliases:
            out[a.strip().lower()] = canonical
    return out


_INVERSE_SYNONYMS = _build_inverse_synonyms()


def _canonical_header(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    return _INVERSE_SYNONYMS.get(key) if key else None


def _read_xlsx(path: Path) -> tuple[list[list[Any]], str]:
    import pandas as pd  # lazy import — heavy
    df = pd.read_excel(path, sheet_name=0, dtype=object, header=0)
    sheet_name = df.attrs.get("sheet_name") or "Sheet1"
    rows: list[list[Any]] = [list(df.columns)]
    for _, row in df.iterrows():
        rows.append([(None if pd.isna(v) else v) for v in row.tolist()])
    return rows, sheet_name


def _read_csv(path: Path) -> tuple[list[list[Any]], str]:
    rows: list[list[Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.reader(f):
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


def parse_rates_file(path: str | Path) -> ParsedFile:
    """Read a tariff workbook from disk and produce canonicalised rows.

    Each row is a dict with canonical keys
    (``category``, ``subcategory``, ``supply_type``, ``load_from`` ...).
    Unknown columns are dropped from the dict but preserved in the
    ``__raw__`` field, similar to historical_import.parse_file.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Tariff file missing: {p}")

    raw_rows, sheet_name = _read_any(p)
    if not raw_rows:
        return ParsedFile(
            source_file=p.name, sheet_name=sheet_name,
            total_rows=0, column_mapping={}, rows=[], extra_headers=[],
        )

    headers = raw_rows[0]
    column_mapping: dict[str, str] = {}
    extra_headers: list[str] = []
    canonical_per_index: list[str | None] = []

    for h in headers:
        canonical = _canonical_header(h)
        canonical_per_index.append(canonical)
        if canonical and canonical not in column_mapping:
            column_mapping[canonical] = str(h)
        elif (not canonical) and h is not None and str(h).strip():
            extra_headers.append(str(h))

    parsed: list[dict[str, Any]] = []
    for raw in raw_rows[1:]:
        canonical_row: dict[str, Any] = {}
        original: dict[str, Any] = {}
        for i, value in enumerate(raw):
            if i >= len(headers):
                continue
            original_header = headers[i]
            if original_header is None:
                continue
            original[str(original_header)] = value
            c = canonical_per_index[i]
            if c:
                canonical_row[c] = value
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
# Overlap detection
# ---------------------------------------------------------------------

def _date_or_none(s: Any) -> str | None:
    """ISO yyyy-mm-dd or None — uses utils.parse_date for tolerance."""
    return parse_date(s) if s not in (None, "") else None


def detect_overlap(conn: sqlite3.Connection,
                   effective_from: str | None,
                   effective_to: str | None,
                   exclude_id: int | None = None) -> list[dict]:
    """Return active schedules whose date window overlaps the given range.

    Both ends may be None (= open-ended).  Overlap is detected with the
    standard interval-intersection rule::

        a.from <= b.to  AND  a.to >= b.from

    NULL bounds are treated as ``-infinity`` / ``+infinity`` so an
    open-ended schedule is considered to span everything that follows
    its start (or precedes its end).
    """
    f = _date_or_none(effective_from)
    t = _date_or_none(effective_to)

    sql = (
        "SELECT id, schedule_name, effective_from, effective_to, is_active "
        "FROM tariff_schedules WHERE is_active = 1"
    )
    params: list[Any] = []
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(int(exclude_id))

    rows = conn.execute(sql, params).fetchall()

    def _intersects(a_from, a_to, b_from, b_to) -> bool:
        # Treat NULLs as open-ended.
        # a_from <= b_to AND a_to >= b_from
        if a_from is not None and b_to is not None and a_from > b_to:
            return False
        if a_to is not None and b_from is not None and a_to < b_from:
            return False
        return True

    out: list[dict] = []
    for r in rows:
        rd = dict(r) if not isinstance(r, dict) else r
        if _intersects(rd.get("effective_from"), rd.get("effective_to"), f, t):
            out.append(rd)
    return out


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------

_RATE_INSERT_SQL = """
    INSERT INTO tariff_rates (
        schedule_id, category, subcategory, supply_type,
        load_from, load_to, unit_from, unit_to,
        fixed_charge, energy_charge, minimum_charge, duty_percent,
        multiplier_default
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _is_blank_rate_row(row: dict[str, Any]) -> bool:
    keys = ("category", "subcategory", "supply_type",
            "energy_charge", "fixed_charge", "minimum_charge",
            "load_from", "load_to", "unit_from", "unit_to")
    return all(
        row.get(k) is None or str(row.get(k)).strip() == ""
        for k in keys
    )


def import_schedule(conn: sqlite3.Connection,
                    meta: ScheduleMeta,
                    parsed: ParsedFile,
                    *,
                    conflict_strategy: str = "warn") -> ImportResult:
    """Insert the schedule + rate rows.

    Parameters
    ----------
    meta
        Schedule-level metadata supplied by the operator.
    parsed
        Output of ``parse_rates_file`` — each row is a canonicalised dict.
    conflict_strategy
        ``"warn"``    -> just report overlaps in result.overlaps (default).
        ``"replace"`` -> deactivate (is_active=0) any overlapping schedule
                         before inserting the new one.
        ``"keep_both"`` -> don't deactivate anything; just import.
        ``"cancel"``  -> abort the import if any overlap exists; the
                         result has schedule_id=None and overlaps populated.

    The schedule row + rate rows are written in a single transaction;
    on any DB error everything rolls back and the schedule_id is left
    unset.
    """
    started = time.monotonic()
    f = _date_or_none(meta.effective_from)
    t = _date_or_none(meta.effective_to)

    overlaps = detect_overlap(conn, f, t)

    result = ImportResult(
        schedule_name=meta.schedule_name,
        effective_from=f,
        effective_to=t,
        source_file=meta.source_file,
        total_rows=parsed.total_rows,
        column_mapping=parsed.column_mapping,
        extra_headers=parsed.extra_headers,
        overlaps=overlaps,
    )

    if overlaps and conflict_strategy == "cancel":
        result.duration_ms = int((time.monotonic() - started) * 1000)
        log.info("Tariff import cancelled — overlaps with %d schedule(s)",
                 len(overlaps))
        return result

    cursor = conn.cursor()
    try:
        if overlaps and conflict_strategy == "replace":
            ids = [int(o["id"]) for o in overlaps]
            placeholders = ",".join("?" * len(ids))
            cursor.execute(
                f"UPDATE tariff_schedules SET is_active=0 "
                f"WHERE id IN ({placeholders})", ids,
            )
            log.info("Tariff import: deactivated %d overlapping schedule(s)",
                     len(ids))

        cursor.execute(
            "INSERT INTO tariff_schedules "
            "(schedule_name, effective_from, effective_to, source_file, "
            " notes, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (meta.schedule_name, f, t, meta.source_file, meta.notes),
        )
        sched_id = cursor.lastrowid
        result.schedule_id = sched_id

        for idx, row in enumerate(parsed.rows, start=2):
            if _is_blank_rate_row(row):
                result.skipped += 1
                continue

            missing = [k for k in _REQUIRED_FIELDS
                       if row.get(k) is None or str(row.get(k)).strip() == ""]
            if missing:
                result.skipped += 1
                result.errors.append(RowError(
                    row_num=idx,
                    reason=f"missing required field(s): {', '.join(missing)}",
                ))
                continue

            cursor.execute(_RATE_INSERT_SQL, (
                sched_id,
                str(row.get("category") or "").strip() or None,
                str(row.get("subcategory") or "").strip() or None,
                str(row.get("supply_type") or "").strip() or None,
                _opt_float(row.get("load_from")),
                _opt_float(row.get("load_to")),
                _opt_float(row.get("unit_from")),
                _opt_float(row.get("unit_to")),
                safe_float(row.get("fixed_charge")),
                safe_float(row.get("energy_charge")),
                safe_float(row.get("minimum_charge")),
                safe_float(row.get("duty_percent")),
                safe_float(row.get("multiplier_default"), 2.0),
            ))
            result.inserted += 1

        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        log.exception("Tariff import failed for %s", meta.schedule_name)
        result.errors.append(RowError(
            row_num=0,
            reason=f"DB error: {type(e).__name__}: {e}",
        ))
        result.schedule_id = None

    result.duration_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "Tariff import: schedule_id=%s name=%r rows=%d inserted=%d "
        "skipped=%d errors=%d duration=%dms",
        result.schedule_id, meta.schedule_name, result.total_rows,
        result.inserted, result.skipped, len(result.errors),
        result.duration_ms,
    )
    return result


def _opt_float(v: Any) -> float | None:
    """Like safe_float but returns None for blank/missing input."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Listing & lookup
# ---------------------------------------------------------------------

def list_schedules(conn: sqlite3.Connection) -> list[dict]:
    """Schedules + per-schedule rate-row count + category list."""
    rows = conn.execute(
        "SELECT s.id, s.schedule_name, s.effective_from, s.effective_to, "
        "       s.uploaded_at, s.is_active, s.source_file, s.notes, "
        "       (SELECT COUNT(*) FROM tariff_rates r WHERE r.schedule_id=s.id) "
        "         AS row_count, "
        "       (SELECT GROUP_CONCAT(DISTINCT category) FROM tariff_rates r "
        "         WHERE r.schedule_id=s.id) AS categories "
        "FROM tariff_schedules s "
        "ORDER BY COALESCE(s.effective_from, s.uploaded_at) DESC, s.id DESC"
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        rd = dict(r) if not isinstance(r, dict) else r
        cats = rd.get("categories") or ""
        rd["categories"] = sorted(set(c.strip() for c in cats.split(",") if c.strip())) \
            if cats else []
        out.append(rd)
    return out


def get_schedule(conn: sqlite3.Connection,
                 schedule_id: int,
                 *,
                 include_rates: bool = True) -> dict | None:
    head = conn.execute(
        "SELECT id, schedule_name, effective_from, effective_to, "
        "       uploaded_at, is_active, source_file, notes "
        "FROM tariff_schedules WHERE id = ?", (int(schedule_id),)
    ).fetchone()
    if not head:
        return None
    head = dict(head) if not isinstance(head, dict) else head

    if include_rates:
        rates = conn.execute(
            "SELECT id, category, subcategory, supply_type, "
            "       load_from, load_to, unit_from, unit_to, "
            "       fixed_charge, energy_charge, minimum_charge, "
            "       duty_percent, multiplier_default "
            "FROM tariff_rates WHERE schedule_id = ? "
            "ORDER BY category, subcategory, COALESCE(unit_from, 0)",
            (int(schedule_id),)
        ).fetchall()
        head["rates"] = [dict(r) if not isinstance(r, dict) else r
                         for r in rates]
    return head


def find_applicable_rate(conn: sqlite3.Connection,
                         category: str,
                         *,
                         subcategory: str | None = None,
                         supply_type: str | None = None,
                         load_kw: float | None = None,
                         units: float | None = None,
                         on_date: str | None = None) -> dict | None:
    """Return the single rate row that best matches the supplied filters.

    Selection logic
    ---------------
    1. Pick the **active** schedule whose date window contains ``on_date``
       (if supplied), preferring the most recently uploaded one as a
       tiebreaker.  When ``on_date`` is None, prefer the latest active
       schedule.
    2. Within that schedule, filter rate rows by ``category`` (required)
       and the optional ``subcategory`` / ``supply_type`` / ``load_kw``
       / ``units`` constraints.  Each optional filter only narrows
       further — missing data on either side of the comparison is
       treated as "no constraint" rather than a mismatch.
    3. Among matching rows, prefer the most-specific one — i.e. rows
       whose subcategory + load band + unit band are all populated.

    Returns None if no schedule or no matching rate row is found.
    """
    if not category or not str(category).strip():
        return None
    cat = str(category).strip()
    on = _date_or_none(on_date) if on_date else None

    # Step 1 — pick the schedule.
    schedules_sql = (
        "SELECT id, schedule_name, effective_from, effective_to "
        "FROM tariff_schedules WHERE is_active = 1"
    )
    schedules = [
        (dict(r) if not isinstance(r, dict) else r)
        for r in conn.execute(schedules_sql).fetchall()
    ]
    if not schedules:
        return None

    def _covers(sch: dict) -> bool:
        if on is None:
            return True
        f, t = sch.get("effective_from"), sch.get("effective_to")
        if f and on < f:
            return False
        if t and on > t:
            return False
        return True

    candidates = [s for s in schedules if _covers(s)] or schedules
    candidates.sort(
        key=lambda s: (s.get("effective_from") or "", s.get("id") or 0),
        reverse=True,
    )
    schedule = candidates[0]

    # Step 2 — pull all rate rows for category in that schedule.
    rates = [
        (dict(r) if not isinstance(r, dict) else r)
        for r in conn.execute(
            "SELECT * FROM tariff_rates "
            "WHERE schedule_id = ? AND category = ?",
            (schedule["id"], cat),
        ).fetchall()
    ]
    if not rates:
        return None

    def _match(r: dict) -> bool:
        if subcategory and r.get("subcategory"):
            if normalize_text(r["subcategory"]) != normalize_text(subcategory):
                return False
        if supply_type and r.get("supply_type"):
            if normalize_text(r["supply_type"]) != normalize_text(supply_type):
                return False
        if load_kw is not None:
            lf, lt = r.get("load_from"), r.get("load_to")
            if lf is not None and load_kw < lf - 1e-9:
                return False
            if lt is not None and load_kw > lt + 1e-9:
                return False
        if units is not None:
            uf, ut = r.get("unit_from"), r.get("unit_to")
            if uf is not None and units < uf - 1e-9:
                return False
            if ut is not None and units > ut + 1e-9:
                return False
        return True

    matched = [r for r in rates if _match(r)]
    if not matched:
        return None

    def _specificity(r: dict) -> int:
        """Higher = more specific."""
        score = 0
        if r.get("subcategory"): score += 8
        if r.get("supply_type"): score += 4
        if r.get("load_from") is not None or r.get("load_to") is not None:
            score += 2
        if r.get("unit_from") is not None or r.get("unit_to") is not None:
            score += 1
        return score

    matched.sort(key=_specificity, reverse=True)
    chosen = matched[0]
    chosen = dict(chosen)
    chosen["schedule_id"] = schedule["id"]
    chosen["schedule_name"] = schedule.get("schedule_name")
    chosen["effective_from"] = schedule.get("effective_from")
    chosen["effective_to"] = schedule.get("effective_to")
    return chosen


# ---------------------------------------------------------------------
# Activate / deactivate
# ---------------------------------------------------------------------

def set_active(conn: sqlite3.Connection,
               schedule_id: int,
               is_active: bool) -> bool:
    cur = conn.execute(
        "UPDATE tariff_schedules SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, int(schedule_id)),
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------
# Sample workbook
# ---------------------------------------------------------------------

_SAMPLE_HEADERS = [
    "Category", "Subcategory", "Supply Type",
    "Load From", "Load To", "Unit From", "Unit To",
    "Fixed Charge", "Energy Charge", "Minimum Charge",
    "Duty %", "Multiplier",
]

_SAMPLE_ROWS = [
    ["LMV-1", "Urban", "Domestic",     None, 4.0,  0,   100, 110, 5.50, 50, 5, 2],
    ["LMV-1", "Urban", "Domestic",     None, 4.0,  101, 200, 110, 6.00, 50, 5, 2],
    ["LMV-1", "Urban", "Domestic",     None, 4.0,  201, None, 110, 6.50, 50, 5, 2],
    ["LMV-1", "Rural", "Domestic",     None, 4.0,  None, None, 100, 4.00, 30, 5, 2],
    ["LMV-2", "Urban ≤4KW", "Commercial", None, 4.0, None, None, 175, 7.50, 100, 8, 2],
    ["LMV-2", "Urban >4KW", "Commercial", 4.0, None, None, None, 250, 8.40, 200, 8, 2],
    ["LMV-2", "Rural", "Commercial",   None, None, None, None, 150, 6.50, 75, 8, 2],
    ["LMV-5", "Rural", "Agriculture",  None, None, None, None, 80,  3.50, 30, 0, 2],
]


def build_sample_workbook(out_path: str | Path) -> str:
    """Write a sample tariff workbook to ``out_path`` and return the path.

    The sample includes a header row and a handful of demonstration
    rate rows covering the project owner's example matrix
    (LMV-1 Urban, LMV-2 Urban ≤4KW, LMV-5 Rural ...).
    """
    from openpyxl import Workbook
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Tariff"
    ws.append(_SAMPLE_HEADERS)
    for row in _SAMPLE_ROWS:
        ws.append(row)
    # Light styling: bold header, freeze top row.
    from openpyxl.styles import Font
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    # Column widths roughly fitting the sample content.
    widths = [10, 14, 14, 10, 10, 10, 10, 14, 14, 14, 8, 12]
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    wb.save(str(p))
    return str(p)
