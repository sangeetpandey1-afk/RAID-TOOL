"""Payment tracking routes — record, list, status, NOC trigger."""
from __future__ import annotations
import logging
from datetime import date

from flask import Blueprint, request

from ..database import audit, execute, fetch_all, fetch_one
from ..utils import (envelope_error, envelope_ok, get_json_body, parse_date,
                     safe_float)

log = logging.getLogger(__name__)
bp = Blueprint("payment", __name__, url_prefix="/api")


def _payment_summary(case_id: str) -> dict:
    case = fetch_one(
        "SELECT total_assessment, compounding_amount FROM raid_cases "
        "WHERE case_id=?",
        (case_id,),
    )
    if not case:
        return {}
    payments = fetch_all(
        "SELECT * FROM payments WHERE case_id=? ORDER BY payment_date DESC",
        (case_id,),
    )
    total_due = round(safe_float(case.get("total_assessment"))
                      + safe_float(case.get("compounding_amount")), 2)
    paid = round(sum(safe_float(p["amount"]) for p in payments), 2)
    balance = round(total_due - paid, 2)
    fully_paid = balance <= 0 and total_due > 0
    return {
        "total_due":   total_due,
        "total_paid":  paid,
        "balance":     balance,
        "fully_paid":  fully_paid,
        "payment_count": len(payments),
        "payments":    payments,
    }


@bp.get("/cases/<case_id>/payments")
def list_payments(case_id: str):
    case = fetch_one("SELECT case_id FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")
    return envelope_ok(_payment_summary(case_id))


@bp.post("/cases/<case_id>/payments")
def record_payment(case_id: str):
    case = fetch_one("SELECT * FROM raid_cases WHERE case_id=?", (case_id,))
    if not case:
        return envelope_error("Case not found", status=404, code="NOT_FOUND")

    body = get_json_body(request)
    amount = safe_float(body.get("amount"))
    if amount <= 0:
        return envelope_error("amount must be > 0", status=400,
                              code="BAD_AMOUNT")
    pay_type = body.get("payment_type", "partial")
    if pay_type not in ("full", "partial", "installment"):
        return envelope_error(
            "payment_type must be one of: full, partial, installment",
            status=400, code="BAD_PAYMENT_TYPE",
        )
    component = body.get("component", "assessment")
    if component not in ("assessment", "compounding", "shaman", "admin"):
        return envelope_error(
            "component must be one of: assessment, compounding, shaman, admin",
            status=400, code="BAD_COMPONENT",
        )

    cur = execute(
        """INSERT INTO payments
              (case_id, payment_type, component, amount, payment_date,
               receipt_number, payment_method, remarks)
           VALUES (?,?,?,?,?,?,?,?)""",
        (case_id, pay_type, component, amount,
         parse_date(body.get("payment_date")) or date.today().isoformat(),
         body.get("receipt_number"),
         body.get("payment_method", "cash"),
         body.get("remarks")),
    )

    summary = _payment_summary(case_id)

    # Auto-update case status
    new_status = case["case_status"]
    if summary.get("fully_paid"):
        new_status = "paid"
    elif summary.get("total_paid", 0) > 0:
        new_status = "partial"
    if new_status != case["case_status"]:
        execute(
            "UPDATE raid_cases SET case_status=?, updated_at=datetime('now') "
            "WHERE case_id=?",
            (new_status, case_id),
        )

    audit(body.get("user", "system"), "PAYMENT", "payments",
          str(cur.lastrowid), new={"amount": amount, "type": pay_type,
                                    "component": component})

    return envelope_ok({
        "payment_id": cur.lastrowid,
        "case_status": new_status,
        "summary": summary,
        "noc_eligible": summary.get("fully_paid", False),
    })


@bp.delete("/payments/<int:payment_id>")
def delete_payment(payment_id: int):
    """Reverse a payment (audit-logged)."""
    row = fetch_one("SELECT * FROM payments WHERE id=?", (payment_id,))
    if not row:
        return envelope_error("Payment not found", status=404,
                              code="NOT_FOUND")
    execute("DELETE FROM payments WHERE id=?", (payment_id,))
    audit("system", "DELETE_PAYMENT", "payments", str(payment_id), old=row)
    return envelope_ok({"deleted": payment_id, "summary":
                        _payment_summary(row["case_id"])})


@bp.get("/payments/recent")
def recent_payments():
    """Dashboard widget — latest N payments across all cases."""
    limit = int(request.args.get("limit", "50"))
    rows = fetch_all(
        """SELECT p.*, c.account_number, c.user_name, c.section
           FROM payments p
           JOIN raid_cases c ON c.case_id = p.case_id
           ORDER BY p.payment_date DESC, p.id DESC
           LIMIT ?""",
        (limit,),
    )
    return envelope_ok(rows, meta={"count": len(rows)})
