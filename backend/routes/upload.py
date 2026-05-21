"""Mobile document upload routes — scan & upload from phone camera."""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, send_file

from .. import config
from ..database import execute, fetch_all, fetch_one
from ..utils import envelope_error, envelope_ok

log = logging.getLogger(__name__)
bp = Blueprint("upload", __name__, url_prefix="/api")


def _secure_filename(filename: str) -> str:
    """Sanitize filename — keep extension, replace unsafe chars."""
    # Keep only the base name
    name = os.path.basename(filename)
    # Replace spaces and special chars
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in name)
    return safe or "unnamed"


def _allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in config.ALLOWED_UPLOAD_EXTENSIONS


def _get_mime_type(filename: str) -> str:
    """Guess MIME type from extension."""
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".bmp": "image/bmp", ".webp": "image/webp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument"
                 ".wordprocessingml.document",
    }
    return mime_map.get(ext, "application/octet-stream")


# ===================================================================
# POST /api/cases/<case_id>/upload — Upload scanned document
# ===================================================================
@bp.post("/cases/<case_id>/upload")
def upload_document(case_id: str):
    """
    Upload a scanned document (photo/PDF) for a case.

    Multipart form-data with:
      - file: the actual file (required)
      - category: one of UPLOAD_CATEGORIES (default: "other")
      - description: optional text description
      - uploaded_by: who uploaded (default: "mobile")

    Used from mobile phone camera/scanner.
    """
    # Verify case exists
    case = fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?",
                     (case_id,))
    if not case:
        return envelope_error(f"Case {case_id} not found",
                              status=404, code="NOT_FOUND")

    # Check file in request
    if "file" not in request.files:
        return envelope_error(
            "No file provided. Send multipart form with 'file' field.",
            status=400, code="NO_FILE")

    file = request.files["file"]
    if not file or file.filename == "":
        return envelope_error("Empty file", status=400, code="EMPTY_FILE")

    # Validate extension
    if not _allowed_file(file.filename):
        return envelope_error(
            f"File type not allowed. Allowed: "
            f"{', '.join(sorted(config.ALLOWED_UPLOAD_EXTENSIONS))}",
            status=400, code="INVALID_TYPE")

    # Validate size (read content-length or check after read)
    file.seek(0, 2)  # seek to end
    size = file.tell()
    file.seek(0)     # reset
    if size > config.MAX_UPLOAD_SIZE_BYTES:
        return envelope_error(
            f"File too large. Max {config.MAX_UPLOAD_SIZE_MB} MB allowed.",
            status=413, code="FILE_TOO_LARGE")

    # Get metadata from form
    category = request.form.get("category", "other")
    if category not in config.UPLOAD_CATEGORIES:
        category = "other"
    description = request.form.get("description", "")
    uploaded_by = request.form.get("uploaded_by", "mobile")

    # Create storage path: uploads/<case_id>/<timestamp>_<uuid>_<filename>
    case_dir = config.UPLOADS_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    safe_name = _secure_filename(file.filename)
    stored_name = f"{timestamp}_{unique_id}_{safe_name}"
    file_path = case_dir / stored_name

    # Save file
    file.save(str(file_path))
    actual_size = file_path.stat().st_size
    mime_type = _get_mime_type(file.filename)

    # Insert into documents table
    cur = execute(
        """INSERT INTO documents
              (case_id, document_type, document_name, file_path,
               file_size, mime_type, uploaded_by, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, category, safe_name, str(file_path),
         actual_size, mime_type, uploaded_by, "active"),
    )

    log.info("File uploaded: %s → %s (case=%s, category=%s, size=%d)",
             file.filename, stored_name, case_id, category, actual_size)

    return envelope_ok({
        "id": cur.lastrowid,
        "case_id": case_id,
        "category": category,
        "file_name": safe_name,
        "stored_name": stored_name,
        "file_size": actual_size,
        "mime_type": mime_type,
        "description": description,
        "uploaded_by": uploaded_by,
        "message": "File uploaded successfully / फाइल सफलतापूर्वक अपलोड हुई",
    })


# ===================================================================
# POST /api/cases/<case_id>/upload-multiple — Upload multiple files
# ===================================================================
@bp.post("/cases/<case_id>/upload-multiple")
def upload_multiple(case_id: str):
    """Upload multiple scanned documents at once."""
    case = fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?",
                     (case_id,))
    if not case:
        return envelope_error(f"Case {case_id} not found",
                              status=404, code="NOT_FOUND")

    files = request.files.getlist("files")
    if not files:
        return envelope_error("No files provided", status=400, code="NO_FILE")

    category = request.form.get("category", "other")
    if category not in config.UPLOAD_CATEGORIES:
        category = "other"
    uploaded_by = request.form.get("uploaded_by", "mobile")

    results = []
    errors = []

    for file in files:
        if not file or file.filename == "":
            continue

        if not _allowed_file(file.filename):
            errors.append({"file": file.filename, "error": "Invalid type"})
            continue

        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > config.MAX_UPLOAD_SIZE_BYTES:
            errors.append({"file": file.filename, "error": "Too large"})
            continue

        # Save
        case_dir = config.UPLOADS_DIR / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        safe_name = _secure_filename(file.filename)
        stored_name = f"{timestamp}_{unique_id}_{safe_name}"
        file_path = case_dir / stored_name

        file.save(str(file_path))
        actual_size = file_path.stat().st_size
        mime_type = _get_mime_type(file.filename)

        cur = execute(
            """INSERT INTO documents
                  (case_id, document_type, document_name, file_path,
                   file_size, mime_type, uploaded_by, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (case_id, category, safe_name, str(file_path),
             actual_size, mime_type, uploaded_by, "active"),
        )

        results.append({
            "id": cur.lastrowid,
            "file_name": safe_name,
            "file_size": actual_size,
            "category": category,
        })

    return envelope_ok({
        "case_id": case_id,
        "uploaded": len(results),
        "failed": len(errors),
        "files": results,
        "errors": errors,
    })


# ===================================================================
# GET /api/cases/<case_id>/documents — List all documents for a case
# ===================================================================
@bp.get("/cases/<case_id>/documents")
def list_case_documents(case_id: str):
    """List all uploaded + generated documents for a case."""
    rows = fetch_all(
        """SELECT id, case_id, document_type, document_name,
                  file_size, mime_type, uploaded_by, version,
                  status, created_at
           FROM documents
           WHERE case_id=? AND status='active'
           ORDER BY created_at DESC""",
        (case_id,),
    )
    docs = [dict(r) for r in rows]
    # Add download URL
    for d in docs:
        d["download_url"] = f"/api/documents/{d['id']}"
        # Add thumbnail URL for images
        if d.get("mime_type", "").startswith("image/"):
            d["is_image"] = True
        else:
            d["is_image"] = False

    return envelope_ok({
        "case_id": case_id,
        "total": len(docs),
        "documents": docs,
    })


# ===================================================================
# DELETE /api/documents/<doc_id> — Soft-delete a document
# ===================================================================
@bp.delete("/documents/<int:doc_id>/delete")
def delete_document(doc_id: int):
    """Soft-delete a document (mark as inactive)."""
    row = fetch_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not row:
        return envelope_error("Document not found", status=404,
                              code="NOT_FOUND")

    execute("UPDATE documents SET status='deleted' WHERE id=?", (doc_id,))
    log.info("Document soft-deleted: id=%d, file=%s", doc_id,
             row["document_name"])

    return envelope_ok({
        "id": doc_id,
        "status": "deleted",
        "message": "Document deleted / दस्तावेज हटाया गया",
    })


# ===================================================================
# GET /api/upload/categories — List valid upload categories
# ===================================================================
@bp.get("/upload/categories")
def upload_categories():
    """Return valid upload categories for the mobile UI."""
    category_labels = {
        "checking_report": "जाँच रिपोर्ट / Checking Report",
        "inspection_photo": "निरीक्षण फोटो / Inspection Photo",
        "application": "आवेदन पत्र / Application",
        "notice_served": "तामील सूचना / Notice Served",
        "payment_receipt": "भुगतान रसीद / Payment Receipt",
        "meter_photo": "मीटर फोटो / Meter Photo",
        "site_photo": "स्थल फोटो / Site Photo",
        "fir_copy": "FIR प्रति / FIR Copy",
        "appeal_document": "अपील दस्तावेज / Appeal Document",
        "id_proof": "पहचान पत्र / ID Proof",
        "correspondence": "पत्राचार / Correspondence",
        "other": "अन्य / Other",
    }
    return envelope_ok({
        "categories": [
            {"value": c, "label": category_labels.get(c, c)}
            for c in config.UPLOAD_CATEGORIES
        ],
        "max_size_mb": config.MAX_UPLOAD_SIZE_MB,
        "allowed_types": sorted(config.ALLOWED_UPLOAD_EXTENSIONS),
    })
