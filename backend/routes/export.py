"""Export routes — download data as Excel (Summary + Detailed sheets)."""
from __future__ import annotations
import io
import logging
from datetime import date, datetime

from flask import Blueprint, request, send_file

from .. import config
from ..database import fetch_all, fetch_one
from ..utils import envelope_error, envelope_ok, safe_float, safe_int, parse_date

log = logging.getLogger(__name__)
bp = Blueprint("export", __name__, url_prefix="/api/export")


def _to_excel_bytes(summary_data: list[dict], detailed_data: list[dict],
                    summary_title: str = "Summary",
                    detailed_title: str = "Detailed") -> bytes:
    """Create Excel workbook with Summary + Detailed sheets, return as bytes."""
    import pandas as pd

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name=summary_title, index=False)
        if detailed_data:
            df_detail = pd.DataFrame(detailed_data)
            df_detail.to_excel(writer, sheet_name=detailed_title, index=False)
    output.seek(0)
    return output.getvalue()


# ===================================================================
# GET /api/export/cases — Export all/filtered cases
# ===================================================================
@bp.get("/cases")
def export_cases():
    """
    Export cases as Excel with Summary + Detailed sheets.

    Query params (same as /api/cases/search):
        status, section, from_date, to_date, q, div_no, je_name
        format: xlsx (default)
    """
    args = request.args
    where = []
    params = []

    if args.get("q"):
        like = f"%{args['q']}%"
        where.append("(account_number LIKE ? OR user_name LIKE ? OR fir_number LIKE ?)")
        params += [like, like, like]
    if args.get("status"):
        where.append("case_status=?")
        params.append(args["status"])
    if args.get("section"):
        where.append("section=?")
        params.append(args["section"])
    if args.get("je_name"):
        where.append("je_name=?")
        params.append(args["je_name"])
    fr = parse_date(args.get("from_date"))
    to = parse_date(args.get("to_date"))
    if fr:
        where.append("inspection_date >= ?")
        params.append(fr)
    if to:
        where.append("inspection_date <= ?")
        params.append(to)

    where_clause = "WHERE " + " AND ".join(where) if where else ""

    rows = fetch_all(
        f"""SELECT * FROM raid_cases {where_clause}
            ORDER BY inspection_date DESC""",
        params,
    )

    if not rows:
        return envelope_error("No data to export", status=404, code="NO_DATA")

    # Build Detailed sheet
    detailed = []
    for r in rows:
        detailed.append({
            "Case ID": r["case_id"],
            "Online No": r["online_no"] or "",
            "Account No": r["account_number"] or "",
            "Name": r["user_name"] or "",
            "Father Name": r["user_father"] or "",
            "Section": r["section"] or "",
            "Inspection Date": r["inspection_date"] or "",
            "J.E.": r["je_name"] or "",
            "Sub Station": r["sub_substation"] or "",
            "Connected Load (KW)": r["connected_load_kw"] or "",
            "Total Assessment": r["total_assessment"] or 0,
            "Compounding": r["compounding_amount"] or 0,
            "FIR No": r["fir_number"] or "",
            "Status": r["case_status"] or "",
            "Multiplier": r["multiplier"] or "",
            "Offense Count": r["offense_count"] or 1,
            "Created": r["created_at"] or "",
        })

    # Build Summary sheet
    total_cases = len(rows)
    total_assessment = sum(safe_float(r["total_assessment"]) for r in rows)
    total_compounding = sum(safe_float(r["compounding_amount"]) for r in rows)
    status_counts = {}
    section_counts = {}
    for r in rows:
        st = r["case_status"] or "unknown"
        status_counts[st] = status_counts.get(st, 0) + 1
        sec = r["section"] or "unknown"
        section_counts[sec] = section_counts.get(sec, 0) + 1

    summary = [
        {"Metric": "Total Cases", "Value": total_cases},
        {"Metric": "Total Assessment (₹)", "Value": f"{total_assessment:,.2f}"},
        {"Metric": "Total Compounding (₹)", "Value": f"{total_compounding:,.2f}"},
        {"Metric": "---", "Value": "---"},
        {"Metric": "STATUS WISE", "Value": ""},
    ]
    for st, cnt in sorted(status_counts.items()):
        summary.append({"Metric": f"  {st}", "Value": cnt})
    summary.append({"Metric": "---", "Value": "---"})
    summary.append({"Metric": "SECTION WISE", "Value": ""})
    for sec, cnt in sorted(section_counts.items()):
        summary.append({"Metric": f"  Section {sec}", "Value": cnt})

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "All Cases")
    filename = f"raid_cases_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )


# ===================================================================
# GET /api/export/historical — Export historical cases
# ===================================================================
@bp.get("/historical")
def export_historical():
    """Export historical_cases table as Excel."""
    rows = fetch_all(
        "SELECT * FROM historical_cases ORDER BY case_date DESC", ()
    )
    if not rows:
        return envelope_error("No historical data", status=404, code="NO_DATA")

    detailed = []
    for r in rows:
        detailed.append({
            "ID": r["id"],
            "Div No": r["div_no"] or "",
            "Name": r["name"] or "",
            "Father Name": r["father_name"] or "",
            "Village": r["village"] or "",
            "Account ID": r["account_id"] or "",
            "Date": r["case_date"] or "",
            "Assessment": r["assessment_amount"] or 0,
            "FIR": r["fir_number"] or "",
            "Section": r["section"] or "",
            "Source": r["source"] or "",
        })

    total = len(rows)
    total_amt = sum(safe_float(r["assessment_amount"]) for r in rows)
    summary = [
        {"Metric": "Total Historical Cases", "Value": total},
        {"Metric": "Total Assessment (₹)", "Value": f"{total_amt:,.2f}"},
        {"Metric": "Export Date", "Value": date.today().isoformat()},
    ]

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "Historical Cases")
    filename = f"historical_cases_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )


# ===================================================================
# GET /api/export/payments — Export payments
# ===================================================================
@bp.get("/payments")
def export_payments():
    """Export payments with case info."""
    rows = fetch_all(
        """SELECT p.*, r.user_name, r.account_number, r.section
           FROM payments p
           JOIN raid_cases r ON r.case_id = p.case_id
           ORDER BY p.payment_date DESC""", ()
    )
    if not rows:
        return envelope_error("No payment data", status=404, code="NO_DATA")

    detailed = []
    for r in rows:
        detailed.append({
            "Case ID": r["case_id"],
            "Account No": r["account_number"] or "",
            "Consumer": r["user_name"] or "",
            "Section": r["section"] or "",
            "Payment Type": r["payment_type"] or "",
            "Component": r["component"] or "",
            "Amount (₹)": r["amount"] or 0,
            "Payment Date": r["payment_date"] or "",
            "Receipt No": r["receipt_number"] or "",
            "Method": r["payment_method"] or "",
            "Remarks": r["remarks"] or "",
        })

    total_amt = sum(safe_float(r["amount"]) for r in rows)
    summary = [
        {"Metric": "Total Payments", "Value": len(rows)},
        {"Metric": "Total Amount (₹)", "Value": f"{total_amt:,.2f}"},
        {"Metric": "Export Date", "Value": date.today().isoformat()},
    ]

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "Payments")
    filename = f"payments_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )


# ===================================================================
# GET /api/export/consumers — Export consumer master
# ===================================================================
@bp.get("/consumers")
def export_consumers():
    """Export consumer master data."""
    rows = fetch_all("SELECT * FROM consumers ORDER BY name", ())
    if not rows:
        return envelope_error("No consumer data", status=404, code="NO_DATA")

    detailed = []
    for r in rows:
        detailed.append({
            "Account No": r["account_number"] or "",
            "Name": r["name"] or "",
            "Father Name": r["father_name"] or "",
            "Village": r["village"] or "",
            "Address": r["address"] or "",
            "Mobile": r["mobile"] or "",
            "Category": r["category"] or "",
            "Supply Type": r["supply_type"] or "",
            "Load": r["load_value"] or "",
            "Sub Station": r["sub_substation"] or "",
            "Division": r["div_code"] or "",
            "SC No": r["sc_number"] or "",
            "Status": r["connection_status"] or "",
        })

    summary = [
        {"Metric": "Total Consumers", "Value": len(rows)},
        {"Metric": "Export Date", "Value": date.today().isoformat()},
    ]

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "Consumers")
    filename = f"consumers_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )


# ===================================================================
# GET /api/export/offense_report — Export repeat offenders
# ===================================================================
@bp.get("/offense_report")
def export_offense_report():
    """Export offense summary — who is repeat offender."""
    rows = fetch_all(
        """SELECT * FROM offense_summary
           WHERE total_offenses >= 1
           ORDER BY total_offenses DESC, total_assessment DESC""", ()
    )
    if not rows:
        return envelope_error("No offense data", status=404, code="NO_DATA")

    detailed = []
    for r in rows:
        detailed.append({
            "Consumer Key": r["consumer_key"] or "",
            "Total Offenses": r["total_offenses"] or 0,
            "First Offense": r["first_offense_date"] or "",
            "Last Offense": r["last_offense_date"] or "",
            "Total Assessment (₹)": r["total_assessment"] or 0,
            "Repeat Offender?": "YES (6x)" if (r["total_offenses"] or 0) >= 2 else "NO (2x)",
        })

    repeat_count = sum(1 for r in rows if (r["total_offenses"] or 0) >= 2)
    summary = [
        {"Metric": "Total Offenders", "Value": len(rows)},
        {"Metric": "Repeat Offenders (>=2 cases)", "Value": repeat_count},
        {"Metric": "First-time Offenders", "Value": len(rows) - repeat_count},
        {"Metric": "Export Date", "Value": date.today().isoformat()},
    ]

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "Offense Report")
    filename = f"offense_report_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )


# ===================================================================
# GET /api/export/notices — Export notice tracking
# ===================================================================
@bp.get("/notices")
def export_notices():
    """Export notices with case info."""
    rows = fetch_all(
        """SELECT n.*, r.user_name, r.account_number
           FROM notices n
           JOIN raid_cases r ON r.case_id = n.case_id
           ORDER BY n.created_at DESC""", ()
    )
    if not rows:
        return envelope_error("No notice data", status=404, code="NO_DATA")

    detailed = []
    for r in rows:
        detailed.append({
            "Case ID": r["case_id"],
            "Account No": r["account_number"] or "",
            "Consumer": r["user_name"] or "",
            "Notice Type": r["notice_type"] or "",
            "Notice No": r["notice_number"] or "",
            "Dispatch Date": r["dispatch_date"] or "",
            "Due Date": r["due_date"] or "",
            "Amount (₹)": r["amount"] or 0,
            "Status": r["status"] or "",
        })

    summary = [
        {"Metric": "Total Notices", "Value": len(rows)},
        {"Metric": "Export Date", "Value": date.today().isoformat()},
    ]

    excel_bytes = _to_excel_bytes(summary, detailed, "Summary", "Notices")
    filename = f"notices_{date.today().isoformat()}.xlsx"

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.document",
    )
