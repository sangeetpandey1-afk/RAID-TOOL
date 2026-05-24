"""
Historical offense routes (PR2).

Endpoints (all under /api/historical):

  POST /api/historical/upload   multipart/form-data
        fields: file, source
        action: saves uploaded xlsx to master_data/uploaded_historical/,
                calls historical_import.import_historical_workbook(),
                returns insert/skip counts + header mapping diagnostics.

  GET  /api/historical/by-account/<account>
        returns: { "account": ..., "rows": [...], "count": N }

  GET  /api/historical/list
        Optional query: ?limit=N (max 500)
        returns the most recently imported rows for diagnostics only.

PR4's offense-verification UI consumes /api/historical/by-account.
This file is ADDITIVE — no existing historical_cases endpoint is touched
(there are none in the legacy codebase; offense lookup currently lives
inside services/matcher.py).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request

from .. import config
from ..database import fetch_all
from ..services import historical_import
from ..utils import envelope_error, envelope_ok, normalize_account, safe_int

log = logging.getLogger(__name__)
bp = Blueprint("historical", __name__, url_prefix="/api/historical")


# =====================================================================
# 1. Upload
# =====================================================================
def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return name or "historical.xlsx"


@bp.post("/upload")
def upload_historical():
    if "file" not in request.files:
        return envelope_error("Missing 'file' in multipart upload",
                              status=400, code="MISSING_FILE")
    f = request.files["file"]
    if not f.filename:
        return envelope_error("Empty filename", status=400, code="EMPTY_NAME")
    if not f.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return envelope_error("File must be .xlsx / .xlsm / .xls",
                              status=400, code="BAD_TYPE")
    source_label = (request.form.get("source") or "upload").strip()

    target_dir = config.MASTER_DATA_DIR / "uploaded_historical"
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_path = target_dir / f"{ts}_{_safe_filename(f.filename)}"
    f.save(str(target_path))

    started = time.time()
    result = historical_import.import_historical_workbook(
        str(target_path), source=source_label,
    )
    duration_ms = int((time.time() - started) * 1000)

    if not result.get("ok"):
        return envelope_error(
            result.get("error", "import failed"),
            status=500, code="IMPORT_FAILED",
            details=str(result),
        )
    return envelope_ok({
        **result,
        "duration_ms": duration_ms,
    })


# =====================================================================
# 2. By-account preview (PR4 consumer)
# =====================================================================
@bp.get("/by-account/<account>")
def by_account(account: str):
    """
    Fast indexed lookup. Matches on account_id OR new_account_id OR
    old_account_id (all three indexed). Returns rows in date-DESC order.
    """
    acc = normalize_account(account)
    if not acc:
        return envelope_error("Empty account", status=400, code="EMPTY_ACCOUNT")
    rows = fetch_all(
        """SELECT id, notice_no, div_no, case_date, name, father_name,
                  use_name, user_father_name, address, village,
                  sub_substation, assessment_amount,
                  old_account_id, new_account_id, account_id,
                  category, irregularity, paid_status,
                  fir_number, section, source, imported_at
             FROM historical_cases
            WHERE account_id      = ?
               OR new_account_id  = ?
               OR old_account_id  = ?
            ORDER BY case_date DESC, id DESC""",
        (acc, acc, acc),
    )
    return envelope_ok({
        "account": acc,
        "count":   len(rows),
        "rows":    rows,
    })


# =====================================================================
# 3. Diagnostic listing
# =====================================================================
@bp.get("/list")
def list_recent():
    limit = min(500, max(1, safe_int(request.args.get("limit"), 50)))
    rows = fetch_all(
        """SELECT id, notice_no, div_no, case_date, name, father_name,
                  use_name, user_father_name, address, village,
                  sub_substation, assessment_amount,
                  old_account_id, new_account_id, account_id,
                  category, irregularity, paid_status,
                  source, imported_at
             FROM historical_cases
            ORDER BY id DESC
            LIMIT ?""",
        (limit,),
    )
    return envelope_ok({"count": len(rows), "rows": rows})
