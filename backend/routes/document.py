"""Document generation HTTP routes."""
from __future__ import annotations
from pathlib import Path

from flask import Blueprint, request, send_file

from ..services import doc_generator
from ..utils import envelope_error, envelope_ok, get_json_body

bp = Blueprint("document", __name__, url_prefix="/api")


@bp.get("/document/kinds")
def document_kinds():
    return envelope_ok({
        "kinds": doc_generator.VALID_KINDS,
        "templates": {
            k: str(doc_generator.config.TEMPLATES_DIR / v)
            for k, v in doc_generator.KIND_TO_TEMPLATE.items()
        },
    })


@bp.post("/cases/<case_id>/document/<kind>")
def generate_document(case_id: str, kind: str):
    """Generate a document. Optional JSON body with extra placeholder values."""
    body = get_json_body(request) or {}
    extra = body.get("extra", body)
    user = body.get("user", "system")
    try:
        result = doc_generator.generate(case_id, kind, extra=extra, user=user)
    except (ValueError, NotImplementedError) as e:
        return envelope_error(str(e), status=400, code="BAD_REQUEST")
    except LookupError as e:
        return envelope_error(str(e), status=404, code="NOT_FOUND")
    return envelope_ok(result)


@bp.get("/documents/<int:doc_id>")
def fetch_document(doc_id: int):
    """Stream a previously-generated document by row id."""
    from ..database import fetch_one
    row = fetch_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not row:
        return envelope_error("Document not found", status=404,
                              code="NOT_FOUND")
    p = Path(row["file_path"])
    if not p.exists():
        return envelope_error("File missing on disk", status=410,
                              code="FILE_MISSING")
    return send_file(str(p), as_attachment=True,
                     download_name=row["document_name"],
                     mimetype=row["mime_type"])


@bp.post("/templates/migrate-legacy")
def migrate_legacy():
    """Convert «FIELD» placeholders in a template file to {{ FIELD }}."""
    body = get_json_body(request) or {}
    file_name = body.get("file")
    if not file_name:
        return envelope_error("Provide JSON {\"file\": \"<template.docx>\"}",
                              status=400)
    src = doc_generator.config.TEMPLATES_DIR / file_name
    if not src.exists():
        return envelope_error(f"Template not found: {src}", status=404,
                              code="NOT_FOUND")
    backup = doc_generator.migrate_legacy_template_in_place(src)
    return envelope_ok({"migrated": str(src), "backup": str(backup)})
