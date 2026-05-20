"""Shared utilities: response envelopes, parsing, normalization."""
from __future__ import annotations
import json
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from flask import jsonify


# ------------------------------------------------------------- envelopes
def envelope_ok(data: Any = None, meta: dict | None = None, status: int = 200):
    payload: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def envelope_error(message: str, status: int = 400, *,
                   code: str | None = None, details: str | None = None):
    payload: dict[str, Any] = {"ok": False, "error": message}
    if code:
        payload["code"] = code
    if details:
        payload["details"] = details
    return jsonify(payload), status


# ------------------------------------------------------------- text utils
def normalize_text(s: Any) -> str:
    """Lowercase, NFKC-normalize, collapse whitespace. None-safe."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def normalize_account(acct: Any) -> str:
    """Account numbers — strip non-alphanumeric, uppercase."""
    if acct is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(acct)).upper()


def safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s not in ("", "-", "nan", "NaN") else default
    except (TypeError, ValueError):
        return default


def safe_int(v: Any, default: int = 0) -> int:
    return int(safe_float(v, default))


def parse_date(v: Any) -> str | None:
    """Best-effort date parser → ISO yyyy-mm-dd string, else None."""
    if v is None or v == "":
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    fmts = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
            "%d-%b-%Y", "%d %b %Y", "%d.%m.%Y", "%m/%d/%Y")
    for f in fmts:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # pandas Timestamp / numpy datetime64 fall here as repr
    try:
        return datetime.fromisoformat(s.split("T")[0]).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------- request body helpers
def get_json_body(req) -> dict:
    """Tolerant JSON parser — accepts empty bodies as {}."""
    if not req.data:
        return {}
    try:
        return req.get_json(force=True, silent=False) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid JSON body: {e}")


def to_json_str(v: Any) -> str | None:
    if v is None:
        return None
    return json.dumps(v, ensure_ascii=False, default=str)


def from_json_str(s: Any) -> Any:
    if s in (None, ""):
        return None
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None
