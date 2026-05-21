"""
Appeal & Proceedings routes.

Flow:
1. Consumer files appeal → POST /api/cases/<id>/appeals
2. Proceedings (sunwai) log → POST /api/cases/<id>/appeals/<appeal_id>/proceedings
3. Upload PDF of proceedings → POST /api/cases/<id>/appeals/<appeal_id>/upload
4. Revision after appeal → POST /api/cases/<id>/appeals/<appeal_id>/revise
5. Final notice with revised amount → generate document as usual
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, request

from .. import config
from ..database import audit, execute, fetch_all, fetch_one
from ..services import calculator
from ..utils import (envelope_error, envelope_ok, from_json_str, get_json_body,
                     parse_date, safe_float, to_json_str)

log = logging.getLogger(__name__)
bp = Blueprint("appeal", __name__, url_prefix="/api")


# ===================================================================
# 1. FILE AN APPEAL
# ===================================================================
@bp.post("/cases/<case_id>/appeals")
def file_appeal(case_id: str):
    """
    File a new appeal for a case.

    JSON body:
      - appellant_name: who filed
      - appellant_relation: self|relative|advocate|other
      - appeal_date: date of appeal (default today)
      - appeal_reason: reason text
    """
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")

    body = get_json_body(request)
    if not body.get("appellant_name"):
        return envelope_error("appellant_name required", status=400)

    cur = execute(
        """INSERT INTO appeals
              (case_id, appeal_date, appellant_name, appellant_relation,
               appeal_reason, supporting_documents, appeal_status)
           VALUES (?,?,?,?,?,?,?)""",
        (case_id,
         parse_date(body.get("appeal_date")) or date.today().isoformat(),
         body["appellant_name"],
         body.get("appellant_relation", "self"),
         body.get("appeal_reason", ""),
         to_json_str(body.get("appeal_grounds") or []),
         "received"),
    )

    execute(
        "UPDATE raid_cases SET case_status='appealed', updated_at=datetime('now') "
        "WHERE case_id=?", (case_id,))

    audit(body.get("user", "system"), "APPEAL_FILED", "appeals",
          str(cur.lastrowid), new=body)

    return envelope_ok({
        "appeal_id": cur.lastrowid,
        "case_id": case_id,
        "status": "received",
        "message": "Appeal filed / अपील दर्ज हुई",
    })


# ===================================================================
# 2. LIST APPEALS FOR A CASE
# ===================================================================
@bp.get("/cases/<case_id>/appeals")
def list_appeals(case_id: str):
    appeals = fetch_all(
        "SELECT * FROM appeals WHERE case_id=? ORDER BY appeal_date DESC",
        (case_id,))
    result = []
    for a in appeals:
        ad = dict(a)
        docs = fetch_all(
            """SELECT id, document_type, document_name, file_size, created_at
               FROM documents WHERE case_id=? AND document_type LIKE ?
               ORDER BY created_at DESC""",
            (case_id, f"appeal_proceeding_{a['id']}%"))
        ad["proceedings_docs"] = [dict(d) for d in docs]
        ad["proceedings_count"] = len(docs)
        result.append(ad)

    return envelope_ok({
        "case_id": case_id,
        "total_appeals": len(result),
        "appeals": result,
    })


# ===================================================================
# 3. ADD PROCEEDING (karywahi log)
# ===================================================================
@bp.post("/cases/<case_id>/appeals/<int:appeal_id>/proceedings")
def add_proceeding(case_id: str, appeal_id: int):
    """
    Log a hearing/proceeding.

    JSON body:
      - proceeding_date, summary, next_date, order_passed,
        officer_name, outcome (pending|partial_relief|full_relief|dismissed|adjourned)
    """
    appeal = fetch_one("SELECT * FROM appeals WHERE id=? AND case_id=?",
                       (appeal_id, case_id))
    if not appeal:
        return envelope_error("Appeal not found", status=404)

    body = get_json_body(request)
    proceeding_text = (
        f"दिनांक: {body.get('proceeding_date', date.today().isoformat())}\n"
        f"अधिकारी: {body.get('officer_name', '')}\n"
        f"विवरण: {body.get('summary', '')}\n"
        f"आदेश: {body.get('order_passed', '')}\n"
        f"अगली तिथि: {body.get('next_date', 'N/A')}\n"
        f"परिणाम: {body.get('outcome', 'pending')}")

    existing = appeal["review_comments"] or ""
    sep = "\n---\n" if existing else ""
    updated = existing + sep + proceeding_text

    outcome = body.get("outcome", "pending")
    new_status = appeal["appeal_status"]
    if outcome in ("full_relief", "dismissed"):
        new_status = outcome
    elif outcome == "partial_relief":
        new_status = "partial_relief"
    elif outcome == "adjourned":
        new_status = "under_review"

    execute(
        """UPDATE appeals SET review_comments=?, review_date=?, appeal_status=?
           WHERE id=?""",
        (updated, parse_date(body.get("proceeding_date")) or date.today().isoformat(),
         new_status, appeal_id))

    audit(body.get("user", "system"), "PROCEEDING", "appeals",
          str(appeal_id), new=body)

    return envelope_ok({
        "appeal_id": appeal_id,
        "appeal_status": new_status,
        "message": "Proceeding recorded / कार्यवाही दर्ज हुई",
    })


# ===================================================================
# 4. UPLOAD PDF — proceedings / orders
# ===================================================================
@bp.post("/cases/<case_id>/appeals/<int:appeal_id>/upload")
def upload_appeal_document(case_id: str, appeal_id: int):
    """Upload PDF/document for appeal proceedings."""
    appeal = fetch_one("SELECT * FROM appeals WHERE id=? AND case_id=?",
                       (appeal_id, case_id))
    if not appeal:
        return envelope_error("Appeal not found", status=404)

    if "file" not in request.files:
        return envelope_error("No file provided", status=400)

    file = request.files["file"]
    if not file or file.filename == "":
        return envelope_error("Empty file", status=400)

    ext = Path(file.filename).suffix.lower()
    if ext not in config.ALLOWED_UPLOAD_EXTENSIONS:
        return envelope_error(f"Type not allowed. Use: {sorted(config.ALLOWED_UPLOAD_EXTENSIONS)}", status=400)

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > config.MAX_UPLOAD_SIZE_BYTES:
        return envelope_error(f"Max {config.MAX_UPLOAD_SIZE_MB} MB", status=413)

    case_dir = config.UPLOADS_DIR / case_id / "appeals"
    case_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    safe_name = "".join(c if (c.isalnum() or c in "._-") else "_"
                        for c in os.path.basename(file.filename)) or "file"
    stored = f"appeal_{appeal_id}_{ts}_{uid}_{safe_name}"
    fp = case_dir / stored
    file.save(str(fp))
    actual_size = fp.stat().st_size

    mime_map = {".pdf": "application/pdf", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".png": "image/png",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    mime = mime_map.get(ext, "application/octet-stream")

    cur = execute(
        """INSERT INTO documents
              (case_id, document_type, document_name, file_path,
               file_size, mime_type, uploaded_by, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, f"appeal_proceeding_{appeal_id}", safe_name,
         str(fp), actual_size, mime,
         request.form.get("uploaded_by", "system"), "active"))

    log.info("Appeal doc: %s for appeal %d, case %s", safe_name, appeal_id, case_id)

    return envelope_ok({
        "doc_id": cur.lastrowid,
        "appeal_id": appeal_id,
        "file_name": safe_name,
        "file_size": actual_size,
        "message": "Document uploaded / कार्यवाही दस्तावेज अपलोड हुआ",
    })


# ===================================================================
# 5. REVISE AFTER APPEAL — new calculation → final notice ready
# ===================================================================
@bp.post("/cases/<case_id>/appeals/<int:appeal_id>/revise")
def revise_after_appeal(case_id: str, appeal_id: int):
    """
    Revise assessment after appeal. Recalculates and updates case.

    JSON body (overrides):
      - devices: updated device list
      - multiplier: changed (e.g. 6→2)
      - less_unit: new value
      - connected_load_kw: corrected load
      - section: changed section
      - reason: revision reason
      - revised_by: officer name
    """
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404)
    appeal = fetch_one("SELECT * FROM appeals WHERE id=? AND case_id=?",
                       (appeal_id, case_id))
    if not appeal:
        return envelope_error("Appeal not found", status=404)

    body = get_json_body(request)
    overrides = body.get("overrides") or body
    revised_by = body.get("revised_by", "appeal_officer")

    current_devices = from_json_str(case.get("devices_json")) or []
    consumer = (fetch_one("SELECT * FROM consumers WHERE id=?",
                          (case["consumer_id"],))
                if case.get("consumer_id") else {}) or {}

    calc_payload = {
        "section": overrides.get("section") or case.get("section"),
        "td_date": overrides.get("td_date") or case.get("td_date"),
        "inspection_date": case.get("inspection_date"),
        "category": overrides.get("category") or consumer.get("category"),
        "connected_load_kw": safe_float(overrides.get("connected_load_kw")) or safe_float(case.get("connected_load_kw")),
        "devices": overrides.get("devices") or current_devices,
        "less_unit": safe_float(overrides.get("less_unit")) if overrides.get("less_unit") is not None else safe_float(case.get("less_unit")),
        "multiplier": safe_float(overrides.get("multiplier")) or safe_float(case.get("multiplier")),
    }

    new_assessment = calculator.calculate_assessment(calc_payload)
    new_total = new_assessment.get("grand_total", 0)
    old_total = safe_float(case.get("total_assessment"))

    # Revision record
    last = fetch_one(
        "SELECT MAX(revision_number) AS m FROM case_revisions WHERE case_id=?",
        (case_id,))
    next_rev = (last["m"] or 0) + 1

    execute(
        """INSERT INTO case_revisions
              (case_id, revision_number, revision_reason,
               original_assessment, revised_assessment, revised_by,
               revision_details, approval_status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, next_rev, f"appeal_{appeal_id}", old_total, new_total,
         revised_by, to_json_str({
             "appeal_id": appeal_id, "overrides": overrides,
             "new_assessment": new_assessment,
         }), "approved"))

    # Update live case
    execute(
        """UPDATE raid_cases SET
              assessment_json=?, total_assessment=?, multiplier=?,
              devices_json=?, less_unit=?, case_status='revised',
              updated_at=datetime('now')
           WHERE case_id=?""",
        (to_json_str(new_assessment), new_total, calc_payload["multiplier"],
         to_json_str(calc_payload["devices"]), calc_payload["less_unit"],
         case_id))

    # Update appeal
    execute("UPDATE appeals SET appeal_status='resolved', revision_triggered=1 WHERE id=?",
            (appeal_id,))

    audit(revised_by, "APPEAL_REVISION", "raid_cases", case_id,
          new={"appeal_id": appeal_id, "old": old_total, "new": new_total})

    return envelope_ok({
        "revision_number": next_rev,
        "appeal_id": appeal_id,
        "original_assessment": old_total,
        "revised_assessment": new_total,
        "relief_given": round(old_total - new_total, 2),
        "new_assessment": new_assessment,
        "case_status": "revised",
        "message": f"₹{old_total:,.2f} → ₹{new_total:,.2f} (Relief: ₹{old_total - new_total:,.2f})",
        "next_step": f"Final notice: POST /api/cases/{case_id}/document/section3",
    })
