"""Document generation HTTP routes — Download, Preview, Print."""
from __future__ import annotations
from pathlib import Path

from flask import Blueprint, request, send_file

from ..services import doc_generator
from ..database import fetch_one, fetch_all
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
    """Download a previously-generated document by row id."""
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
# PREVIEW — Show document in browser (HTML render) with Print button
# ===================================================================
@bp.get("/documents/<int:doc_id>/preview")
def preview_document(doc_id: int):
    """
    Render a .docx document as HTML for in-browser preview + print.
    No download needed — directly print from browser.
    """
    row = fetch_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not row:
        return "<h1>Document not found</h1>", 404
    p = Path(row["file_path"])
    if not p.exists():
        return "<h1>File missing on disk</h1>", 410

    # Convert .docx to HTML
    html_content = _docx_to_html(p)

    # Wrap in a printable page with controls
    page = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{row['document_name']} — Preview</title>
<style>
@media print {{
    .no-print {{ display: none !important; }}
    body {{ margin: 0; padding: 0; }}
    .doc-content {{ border: none !important; box-shadow: none !important; padding: 20mm !important; }}
}}
body {{ font-family: 'Noto Sans Devanagari', Arial, sans-serif; background: #e0e0e0; margin: 0; padding: 0; }}
.toolbar {{ position: sticky; top: 0; z-index: 100; background: linear-gradient(135deg, #667eea, #764ba2);
            padding: 12px 20px; display: flex; align-items: center; gap: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); }}
.toolbar h3 {{ color: #fff; margin: 0; font-size: 16px; flex: 1; }}
.toolbar .btn {{ padding: 8px 18px; border: none; border-radius: 6px; font-size: 14px;
                 font-weight: 700; cursor: pointer; text-decoration: none; }}
.btn-print {{ background: #4caf50; color: #fff; }}
.btn-download {{ background: #2196f3; color: #fff; }}
.btn-back {{ background: rgba(255,255,255,0.2); color: #fff; }}
.doc-content {{ max-width: 210mm; margin: 20px auto; background: #fff; padding: 25mm;
                box-shadow: 0 4px 20px rgba(0,0,0,0.15); border-radius: 4px;
                min-height: 297mm; line-height: 1.6; }}
.doc-content table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
.doc-content td, .doc-content th {{ border: 1px solid #333; padding: 6px 10px; font-size: 13px; }}
.doc-content th {{ background: #f0f0f0; font-weight: bold; }}
.doc-content h1 {{ font-size: 20px; text-align: center; margin-bottom: 10px; }}
.doc-content h2 {{ font-size: 16px; text-align: center; color: #555; margin-bottom: 15px; }}
.doc-content h3 {{ font-size: 14px; margin-top: 15px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
.doc-content p {{ margin: 6px 0; font-size: 13px; }}
</style>
</head><body>

<div class="toolbar no-print">
    <h3>{row['document_name']}</h3>
    <button class="btn btn-print" onclick="window.print()">🖨️ Print</button>
    <a class="btn btn-download" href="/api/documents/{doc_id}">⬇️ Download</a>
    <button class="btn btn-back" onclick="history.back()">← Back</button>
</div>

<div class="doc-content">
{html_content}
</div>

</body></html>"""
    return page


# ===================================================================
# PREVIEW for case — generate + preview in one step
# ===================================================================
@bp.get("/cases/<case_id>/preview/<kind>")
def preview_case_document(case_id: str, kind: str):
    """
    Generate a document for a case and show preview immediately.
    If already generated, shows the latest one.
    """
    # Check if already generated recently
    existing = fetch_one(
        """SELECT id FROM documents
           WHERE case_id=? AND document_type=? AND status='active'
           ORDER BY created_at DESC LIMIT 1""",
        (case_id, kind),
    )

    if existing:
        doc_id = existing["id"]
    else:
        # Generate new
        try:
            result = doc_generator.generate(case_id, kind, user="preview")
            doc_id = result["id"]
        except (ValueError, NotImplementedError) as e:
            return f"<h1>Error: {e}</h1>", 400
        except LookupError as e:
            return f"<h1>Case not found: {e}</h1>", 404

    # Redirect to preview
    from flask import redirect
    return redirect(f"/api/documents/{doc_id}/preview")


# ===================================================================
# LIST all documents for a case with preview/download/print links
# ===================================================================
@bp.get("/cases/<case_id>/documents/page")
def case_documents_page(case_id: str):
    """HTML page listing all documents for a case with action buttons."""
    docs = fetch_all(
        """SELECT id, document_type, document_name, file_size, created_at
           FROM documents WHERE case_id=? AND status='active'
           ORDER BY created_at DESC""",
        (case_id,),
    )

    rows_html = ""
    for d in docs:
        size_kb = (d["file_size"] or 0) / 1024
        rows_html += f"""
        <tr>
            <td>{d['document_type']}</td>
            <td>{d['document_name']}</td>
            <td>{size_kb:.1f} KB</td>
            <td>{d['created_at'] or ''}</td>
            <td>
                <a href="/api/documents/{d['id']}/preview" class="btn btn-sm btn-view">👁 Preview</a>
                <a href="/api/documents/{d['id']}" class="btn btn-sm btn-dl">⬇ Download</a>
            </td>
        </tr>"""

    # Generate buttons for each kind
    gen_buttons = ""
    for kind in doc_generator.VALID_KINDS:
        gen_buttons += f'<a href="/api/cases/{case_id}/preview/{kind}" class="btn btn-gen">{kind}</a> '

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Documents — {case_id}</title>
<style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
h1 {{ color: #333; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
th {{ background: #667eea; color: #fff; }}
.btn {{ display: inline-block; padding: 5px 12px; border-radius: 5px; text-decoration: none; font-size: 12px; font-weight: 600; margin: 2px; }}
.btn-sm {{ font-size: 11px; }}
.btn-view {{ background: #4caf50; color: #fff; }}
.btn-dl {{ background: #2196f3; color: #fff; }}
.btn-gen {{ background: #ff9800; color: #fff; padding: 8px 14px; margin: 4px; border-radius: 6px; font-size: 13px; }}
.section {{ background: #fff; padding: 16px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
</style>
</head><body>
<h1>Documents — {case_id}</h1>

<div class="section">
<h3>Generate New Document:</h3>
{gen_buttons}
</div>

<div class="section">
<h3>Existing Documents ({len(docs)}):</h3>
<table>
<tr><th>Type</th><th>File</th><th>Size</th><th>Created</th><th>Actions</th></tr>
{rows_html if rows_html else '<tr><td colspan="5" style="text-align:center;color:#999;">No documents yet</td></tr>'}
</table>
</div>

</body></html>"""


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


# ===================================================================
# Helper: Convert .docx to HTML for preview
# ===================================================================
def _docx_to_html(docx_path: Path) -> str:
    """Convert a .docx file to basic HTML for browser preview."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    try:
        doc = Document(str(docx_path))
    except Exception as e:
        return f"<p style='color:red'>Error reading document: {e}</p>"

    html_parts = []

    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "p":
            # Paragraph
            from docx.oxml.ns import qn
            pPr = element.find(qn("w:pPr"))
            style_name = ""
            if pPr is not None:
                pStyle = pPr.find(qn("w:pStyle"))
                if pStyle is not None:
                    style_name = pStyle.get(qn("w:val"), "")

            # Extract text with bold/italic
            text_parts = []
            for run in element.findall(f".//{{{element.nsmap.get('w', '')}}}r"):
                rPr = run.find(f"{{{element.nsmap.get('w', '')}}}rPr")
                t = run.find(f"{{{element.nsmap.get('w', '')}}}t")
                txt = t.text if t is not None and t.text else ""

                is_bold = False
                is_italic = False
                if rPr is not None:
                    if rPr.find(f"{{{element.nsmap.get('w', '')}}}b") is not None:
                        is_bold = True
                    if rPr.find(f"{{{element.nsmap.get('w', '')}}}i") is not None:
                        is_italic = True

                if is_bold and is_italic:
                    text_parts.append(f"<b><i>{txt}</i></b>")
                elif is_bold:
                    text_parts.append(f"<b>{txt}</b>")
                elif is_italic:
                    text_parts.append(f"<i>{txt}</i>")
                else:
                    text_parts.append(txt)

            full_text = "".join(text_parts)

            if "Heading" in style_name:
                level = "".join(c for c in style_name if c.isdigit()) or "3"
                level = min(int(level) + 1, 4)  # Heading0→h1, Heading1→h2, etc
                html_parts.append(f"<h{level}>{full_text}</h{level}>")
            elif "Title" in style_name:
                html_parts.append(f"<h1>{full_text}</h1>")
            else:
                if full_text.strip():
                    html_parts.append(f"<p>{full_text}</p>")
                else:
                    html_parts.append("<p>&nbsp;</p>")

        elif tag == "tbl":
            # Table
            html_parts.append("<table>")
            for row_el in element.findall(f".//{{{element.nsmap.get('w', '')}}}tr"):
                html_parts.append("<tr>")
                for cell_el in row_el.findall(f".//{{{element.nsmap.get('w', '')}}}tc"):
                    cell_text_parts = []
                    for p in cell_el.findall(f".//{{{element.nsmap.get('w', '')}}}p"):
                        for t in p.findall(f".//{{{element.nsmap.get('w', '')}}}t"):
                            if t.text:
                                cell_text_parts.append(t.text)
                    cell_text = " ".join(cell_text_parts)
                    html_parts.append(f"<td>{cell_text}</td>")
                html_parts.append("</tr>")
            html_parts.append("</table>")

    return "\n".join(html_parts)
