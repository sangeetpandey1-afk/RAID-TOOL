"""Report & export endpoints."""
from __future__ import annotations
import logging
from flask import Blueprint, request, send_from_directory

from ..services import reports as reports_svc
from ..utils import envelope_error, envelope_ok

log = logging.getLogger(__name__)

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@bp.get("/cases.xlsx")
def export_cases():
    out = reports_svc.cases_xlsx(
        status=request.args.get("status"),
        from_date=request.args.get("from"),
        to_date=request.args.get("to"),
    )
    return envelope_ok({
        "file":     out.name,
        "size":     out.stat().st_size,
        "download": f"/api/reports/download/{out.name}",
    })


@bp.get("/payments.xlsx")
def export_payments():
    out = reports_svc.payments_xlsx(
        from_date=request.args.get("from"),
        to_date=request.args.get("to"),
    )
    return envelope_ok({
        "file":     out.name,
        "size":     out.stat().st_size,
        "download": f"/api/reports/download/{out.name}",
    })


@bp.get("/notices.xlsx")
def export_notices():
    out = reports_svc.notices_xlsx()
    return envelope_ok({
        "file":     out.name,
        "size":     out.stat().st_size,
        "download": f"/api/reports/download/{out.name}",
    })


@bp.get("/dashboard.pdf")
def export_dashboard():
    out = reports_svc.dashboard_pdf()
    return envelope_ok({
        "file":     out.name,
        "size":     out.stat().st_size,
        "download": f"/api/reports/download/{out.name}",
    })


@bp.get("/list")
def list_all():
    items = reports_svc.list_reports()
    return envelope_ok(items, meta={"count": len(items)})


@bp.get("/download/<name>")
def download(name: str):
    if "/" in name or "\\" in name or ".." in name:
        return envelope_error("Invalid name", status=400, code="BAD_NAME")
    target = reports_svc.REPORTS_DIR / name
    if not target.exists():
        return envelope_error("Report not found", status=404,
                              code="NOT_FOUND")
    return send_from_directory(reports_svc.REPORTS_DIR, name,
                               as_attachment=True)
