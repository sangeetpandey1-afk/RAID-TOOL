"""Document generation HTTP routes."""
from __future__ import annotations
import logging
from pathlib import Path

from flask import Blueprint, Response, request, send_file

from ..services import doc_generator, html_doc
from ..utils import envelope_error, envelope_ok, get_json_body

log = logging.getLogger(__name__)
bp = Blueprint("document", __name__, url_prefix="/api")


# ===================================================================
# Catalog
# ===================================================================
@bp.get("/document/kinds")
def document_kinds():
    return envelope_ok({
        "kinds":          doc_generator.VALID_KINDS,
        "notice_bundle":  doc_generator.NOTICE_BUNDLE,
        "templates": {
            k: str(doc_generator.config.TEMPLATES_DIR / v)
            for k, v in doc_generator.KIND_TO_TEMPLATE.items()
        },
        "html_templates": {
            k: str(doc_generator.config.TEMPLATES_DIR / "html" / v)
            for k, v in html_doc.KIND_TO_HTML.items()
        },
    })


# ===================================================================
# DOCX generation (single)
# ===================================================================
@bp.post("/cases/<case_id>/document/<kind>")
def generate_document(case_id: str, kind: str):
    """Generate a .docx document. Optional JSON body with extra placeholders."""
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


# ===================================================================
# Bulk generation — "Generate All Notices" button
# ===================================================================
@bp.post("/cases/<case_id>/documents/generate-all")
def generate_all_documents(case_id: str):
    """
    Generate every document in ``NOTICE_BUNDLE`` for a case in one call.
    Continues on individual failures and returns a per-kind report.
    """
    body = get_json_body(request) or {}
    extra = body.get("extra") or {}
    user  = body.get("user", "system")
    kinds = body.get("kinds") or doc_generator.NOTICE_BUNDLE

    results: list[dict] = []
    ok_count = 0
    for kind in kinds:
        try:
            res = doc_generator.generate(case_id, kind, extra=extra, user=user)
            results.append({
                "kind": kind, "ok": True,
                "file_name": res["file_name"],
                "file_path": res["file_path"],
                "doc_id":    res["id"],
                "preview":   f"/api/cases/{case_id}/document/{kind}/preview",
                "download":  f"/api/documents/{res['id']}",
            })
            ok_count += 1
        except LookupError as e:
            return envelope_error(str(e), status=404, code="NOT_FOUND")
        except Exception as e:  # noqa: BLE001
            log.exception("Generate failed for %s/%s", case_id, kind)
            results.append({"kind": kind, "ok": False, "error": str(e)})

    return envelope_ok({
        "case_id":    case_id,
        "total":      len(results),
        "ok":         ok_count,
        "failed":     len(results) - ok_count,
        "results":    results,
    })


# ===================================================================
# HTML preview / print
# ===================================================================
@bp.get("/cases/<case_id>/document/<kind>/preview")
def document_preview(case_id: str, kind: str):
    """
    Render a print-ready HTML version of a document.

    Officers open this URL in a new browser tab and use the built-in
    ``Print`` button (or Ctrl+P) to produce a clean A4 printout. The
    template comes from ``templates/html/<kind>.html``.
    """
    if kind not in html_doc.KIND_TO_HTML:
        return envelope_error(
            f"Unknown HTML kind '{kind}'. "
            f"Valid: {list(html_doc.KIND_TO_HTML.keys())}",
            status=400, code="BAD_KIND")
    try:
        ctx = doc_generator.build_case_context(case_id, extra=request.args.to_dict())
    except LookupError as e:
        return envelope_error(str(e), status=404, code="NOT_FOUND")

    try:
        html = html_doc.render_html(kind, ctx)
    except (FileNotFoundError, ValueError) as e:
        return envelope_error(str(e), status=500, code="HTML_RENDER")

    return Response(html, status=200,
                    headers={"Content-Type": "text/html; charset=utf-8"})


# ===================================================================
# Stream a previously-generated file
# ===================================================================
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


# ===================================================================
# Legacy «FIELD» migration
# ===================================================================
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
