"""
Historical-import / offense-history HTTP routes.

Endpoints
---------
POST /api/historical/import
        multipart/form-data, field name "file"
        body may also carry an optional plain ?source=<label>
        Returns: ImportSummary as JSON envelope.

GET  /api/historical/offenses?account_number=<acct>
        Returns the strict offense summary (count, suggested
        multiplier, warning level, recent records).

GET  /api/historical/offenses/<account_number>
        Path-style alias of the query-string endpoint.

GET  /api/historical/stats
        Lightweight aggregate stats for the Historical Import panel
        (total rows, distinct accounts, last-import timestamp).

Safety notes
------------
* This blueprint never touches ``raid_cases`` — historical and live
  data stay strictly separate per the project owner's rule.
* The import endpoint writes the upload to a temp file in
  ``logs/`` (which is already a gitignored writable folder), runs the
  importer, then deletes the temp file.  Original filename is
  preserved in the summary for audit.
* No fuzzy matching anywhere on this blueprint.  Lookups use
  ``services/offense_history.py`` which is account-only.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from flask import Blueprint, request

from .. import config
from ..database import get_connection, fetch_all, fetch_one
from ..services import historical_import, offense_history
from ..utils import envelope_ok, envelope_error

log = logging.getLogger(__name__)
bp = Blueprint("historical", __name__, url_prefix="/api/historical")


_ALLOWED_EXT = {".xlsx", ".xls", ".xlsm", ".csv", ".txt"}
_MAX_BYTES = 25 * 1024 * 1024   # 25 MB hard cap on a single upload


# ---------------------------------------------------------------------
# POST /api/historical/import
# ---------------------------------------------------------------------

@bp.post("/import")
def import_historical_upload():
    """Upload an Excel / CSV file of OLD historical raid data."""
    if "file" not in request.files:
        return envelope_error(
            "No file uploaded — send the workbook in form field 'file'.",
            status=400, code="NO_FILE",
        )

    fs = request.files["file"]
    if not fs.filename:
        return envelope_error(
            "Empty filename in upload.", status=400, code="NO_FILENAME",
        )

    suffix = Path(fs.filename).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        return envelope_error(
            f"Unsupported file type {suffix!r}. "
            f"Allowed: {sorted(_ALLOWED_EXT)}",
            status=400, code="BAD_EXT",
        )

    # Persist to a real path on disk so pandas/openpyxl can read it
    # (Werkzeug's FileStorage is a SpooledTemporaryFile in some configs
    # which trips up older xlrd builds).
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = config.LOGS_DIR / "historical_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_stub = "".join(c for c in fs.filename if c.isalnum() or c in "._-") or "upload"
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    tmp_path = tmp_dir / f"{timestamp}-{safe_stub}"

    try:
        fs.save(str(tmp_path))
        size = tmp_path.stat().st_size
        if size > _MAX_BYTES:
            return envelope_error(
                f"File is {size:,} bytes which exceeds the {_MAX_BYTES:,}-byte"
                f" upload limit. Split the workbook and try again.",
                status=413, code="TOO_LARGE",
            )

        conn = get_connection()
        summary = historical_import.import_file(
            conn, tmp_path, source_filename=fs.filename,
        )
        return envelope_ok({"summary": summary.to_dict()})

    except FileNotFoundError as e:
        return envelope_error(str(e), status=404, code="FILE_MISSING")
    except ValueError as e:
        # Raised by historical_import._read_any() for unsupported extensions
        return envelope_error(str(e), status=400, code="BAD_FILE")
    except Exception as e:  # noqa: BLE001
        log.exception("Historical import crashed for %s", fs.filename)
        return envelope_error(
            f"{type(e).__name__}: {e}",
            status=500, code="IMPORT_FAILED",
        )
    finally:
        # Best-effort cleanup; never fail the response over this.
        try:
            if tmp_path.exists():
                os.remove(tmp_path)
        except OSError:
            log.warning("Could not delete temp upload %s", tmp_path)


# ---------------------------------------------------------------------
# GET /api/historical/offenses
# ---------------------------------------------------------------------

def _summary_for(account_number: str | None):
    if not account_number or not str(account_number).strip():
        return envelope_error(
            "Missing account_number.", status=400, code="NO_ACCOUNT",
        )

    conn = get_connection()
    cfg_rows = fetch_all("SELECT config_key, config_value FROM system_config")
    cfg = {r["config_key"]: r["config_value"] for r in cfg_rows}

    summary = offense_history.offense_summary(
        conn, account_number, system_config=cfg,
        include_records=True, record_limit=25,
    )
    return envelope_ok(summary)


@bp.get("/offenses")
def offenses_query():
    """Account-only offense lookup. ?account_number=XYZ."""
    return _summary_for(request.args.get("account_number"))


@bp.get("/offenses/<path:account_number>")
def offenses_path(account_number: str):
    """Path-style alias — convenient for browser inspection."""
    return _summary_for(account_number)


# ---------------------------------------------------------------------
# GET /api/historical/stats
# ---------------------------------------------------------------------

@bp.get("/stats")
def historical_stats():
    """Aggregate stats for the Historical Import panel.

    Cheap to compute (the table is fully indexed on account_id) and
    safe to call frequently.  Returns a lightweight envelope:

        {
          "total_rows":          12345,
          "distinct_accounts":     987,
          "rows_with_dates":     11000,
          "earliest_date":       "2014-04-01",
          "latest_date":         "2025-09-30",
          "last_import_at":      "2026-05-22T11:08:42",
          "by_source": [ {"source": "...", "rows": ...}, ... ]
        }
    """
    total = fetch_one(
        "SELECT COUNT(*) AS c FROM historical_cases"
    ) or {"c": 0}
    distinct = fetch_one(
        "SELECT COUNT(DISTINCT account_id) AS c "
        "FROM historical_cases WHERE account_id IS NOT NULL "
        "AND TRIM(account_id) <> ''"
    ) or {"c": 0}
    dated = fetch_one(
        "SELECT COUNT(*) AS c FROM historical_cases "
        "WHERE case_date IS NOT NULL AND TRIM(case_date) <> ''"
    ) or {"c": 0}
    minmax = fetch_one(
        "SELECT MIN(case_date) AS mn, MAX(case_date) AS mx "
        "FROM historical_cases WHERE case_date IS NOT NULL "
        "AND TRIM(case_date) <> ''"
    ) or {"mn": None, "mx": None}
    last = fetch_one(
        "SELECT MAX(imported_at) AS t FROM historical_cases"
    ) or {"t": None}
    by_source = fetch_all(
        "SELECT COALESCE(source, '(unknown)') AS source, "
        "COUNT(*) AS rows FROM historical_cases "
        "GROUP BY source ORDER BY rows DESC LIMIT 20"
    )

    return envelope_ok({
        "total_rows":        int(total.get("c") or 0),
        "distinct_accounts": int(distinct.get("c") or 0),
        "rows_with_dates":   int(dated.get("c") or 0),
        "earliest_date":     minmax.get("mn"),
        "latest_date":       minmax.get("mx"),
        "last_import_at":    last.get("t"),
        "by_source":         by_source,
    })
