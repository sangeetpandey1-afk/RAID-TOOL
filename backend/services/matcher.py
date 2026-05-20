"""
Shared consumer/case matching logic.

Used by:
* consumer search route (find a consumer from partial info)
* offense detection (link a new case to the consumer's history)

Algorithm
---------
Priority-based sequential check:
  Level 1 — Direct account-number match              (confidence 0.95)
  Level 2 — SC-number cross-reference                (0.90)
  Level 3 — Old↔New account mapping lookup           (0.85)
  Level 4 — Fuzzy Name + Father + Village combo      (0.70)

Fuzzy match uses rapidfuzz.token_set_ratio so word-order and minor spelling
differences don't break it (important for Krutidev / Hindi text).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz

from ..database import fetch_all, fetch_one
from ..utils import normalize_account, normalize_text

log = logging.getLogger(__name__)


@dataclass
class MatchHit:
    source: str           # "account" | "sc" | "mapping" | "fuzzy"
    confidence: float     # 0.0 – 1.0
    consumer_id: int | None
    account_number: str | None
    name: str | None
    father_name: str | None
    village: str | None
    record: dict          # full row payload

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "consumer_id": self.consumer_id,
            "account_number": self.account_number,
            "name": self.name,
            "father_name": self.father_name,
            "village": self.village,
            "record": self.record,
        }


# ===================================================================
# Level 1 — direct account
# ===================================================================
def by_account(account: str) -> MatchHit | None:
    acct = normalize_account(account)
    if not acct:
        return None
    row = fetch_one(
        "SELECT * FROM consumers WHERE account_number = ?", (acct,)
    )
    if not row:
        return None
    return MatchHit(
        source="account", confidence=0.95,
        consumer_id=row["id"], account_number=row["account_number"],
        name=row.get("name"), father_name=row.get("father_name"),
        village=row.get("village"), record=row,
    )


# ===================================================================
# Level 2 — SC number
# ===================================================================
def by_sc_number(sc: str) -> MatchHit | None:
    sc = (sc or "").strip()
    if not sc:
        return None
    row = fetch_one(
        "SELECT * FROM consumers WHERE sc_number = ?", (sc,)
    )
    if row:
        return MatchHit(
            source="sc", confidence=0.90,
            consumer_id=row["id"], account_number=row["account_number"],
            name=row.get("name"), father_name=row.get("father_name"),
            village=row.get("village"), record=row,
        )
    # SC may also live in account_mapping
    mp = fetch_one(
        "SELECT * FROM account_mapping WHERE sc_number = ? AND status='active' "
        "ORDER BY id DESC LIMIT 1",
        (sc,),
    )
    if mp and mp.get("new_account"):
        cons = fetch_one(
            "SELECT * FROM consumers WHERE account_number = ?",
            (mp["new_account"],),
        )
        if cons:
            return MatchHit(
                source="sc", confidence=0.88,
                consumer_id=cons["id"], account_number=cons["account_number"],
                name=cons.get("name"), father_name=cons.get("father_name"),
                village=cons.get("village"), record=cons,
            )
    return None


# ===================================================================
# Level 3 — old↔new account mapping
# ===================================================================
def by_account_mapping(account: str) -> MatchHit | None:
    acct = normalize_account(account)
    if not acct:
        return None
    mp = fetch_one(
        """SELECT * FROM account_mapping
           WHERE old_account = ? OR new_account = ?
           ORDER BY id DESC LIMIT 1""",
        (acct, acct),
    )
    if not mp:
        return None
    target = mp.get("new_account") or mp.get("old_account")
    cons = fetch_one(
        "SELECT * FROM consumers WHERE account_number = ?",
        (normalize_account(target),),
    )
    if not cons:
        return None
    return MatchHit(
        source="mapping", confidence=0.85,
        consumer_id=cons["id"], account_number=cons["account_number"],
        name=cons.get("name"), father_name=cons.get("father_name"),
        village=cons.get("village"), record=cons,
    )


# ===================================================================
# Level 4 — fuzzy Name+Father+Village
# ===================================================================
def fuzzy_match(name: str, father: str | None = None,
                village: str | None = None,
                threshold: float = 0.70,
                limit: int = 10) -> list[MatchHit]:
    """Combined-field fuzzy match. Returns top-N hits above threshold."""
    name_n = normalize_text(name)
    if not name_n:
        return []
    father_n = normalize_text(father)
    village_n = normalize_text(village)

    # Pull candidates that share at least one name token (cheap pre-filter)
    first_token = name_n.split()[0]
    sql = (
        "SELECT id, account_number, name, father_name, village, address, "
        "       mobile, supply_type, category, sub_substation, div_code "
        "FROM consumers "
        "WHERE LOWER(name) LIKE ? "
        "LIMIT 5000"
    )
    candidates = fetch_all(sql, (f"%{first_token}%",))

    hits: list[MatchHit] = []
    for c in candidates:
        cand_name    = normalize_text(c.get("name"))
        cand_father  = normalize_text(c.get("father_name"))
        cand_village = normalize_text(c.get("village"))
        score_name    = fuzz.token_set_ratio(name_n, cand_name) / 100.0 if cand_name else 0
        score_father  = fuzz.token_set_ratio(father_n, cand_father) / 100.0 if father_n and cand_father else 0
        score_village = fuzz.token_set_ratio(village_n, cand_village) / 100.0 if village_n and cand_village else 0

        # Weighted score: name 50%, father 30%, village 20%
        weights = [(score_name, 0.5)]
        if father_n:  weights.append((score_father, 0.3))
        if village_n: weights.append((score_village, 0.2))
        total_w = sum(w for _, w in weights)
        composite = sum(s * w for s, w in weights) / total_w if total_w else 0

        if composite >= threshold:
            hits.append(MatchHit(
                source="fuzzy",
                confidence=round(composite * 0.7 + 0.30, 3),  # cap at ~1.0
                consumer_id=c["id"], account_number=c.get("account_number"),
                name=c.get("name"), father_name=c.get("father_name"),
                village=c.get("village"), record=c,
            ))
    hits.sort(key=lambda h: h.confidence, reverse=True)
    return hits[:limit]


# ===================================================================
# Combined search — multi-level priority
# ===================================================================
def find_consumer(*, account: str | None = None, sc_number: str | None = None,
                  name: str | None = None, father: str | None = None,
                  village: str | None = None,
                  fuzzy_threshold: float = 0.70,
                  fuzzy_limit: int = 10) -> list[MatchHit]:
    """Run all matchers in priority order. Returns dedup'd list."""
    seen: set[int] = set()
    out: list[MatchHit] = []

    def _add(hit: MatchHit | None):
        if hit and hit.consumer_id and hit.consumer_id not in seen:
            seen.add(hit.consumer_id)
            out.append(hit)

    if account:
        _add(by_account(account))
    if sc_number:
        _add(by_sc_number(sc_number))
    if account:
        _add(by_account_mapping(account))
    if name:
        for h in fuzzy_match(name, father, village,
                             threshold=fuzzy_threshold, limit=fuzzy_limit):
            _add(h)
    return out


# ===================================================================
# Offense lookup for a consumer (for multiplier decision)
# ===================================================================
def offense_history(*, account: str | None = None,
                    name: str | None = None, father: str | None = None,
                    village: str | None = None,
                    fuzzy_threshold: float = 0.70) -> dict:
    """
    Aggregate prior offenses across `historical_cases`, `current_cases`,
    and prior `raid_cases`. Returns full history + totals + multiplier.
    """
    acct = normalize_account(account) if account else None

    # 1) Direct account hits
    rows: list[dict] = []
    if acct:
        rows += [dict(r, _src="historical")
                 for r in fetch_all(
                     "SELECT * FROM historical_cases WHERE account_id = ?",
                     (acct,))]
        rows += [dict(r, _src="current")
                 for r in fetch_all(
                     "SELECT * FROM current_cases WHERE connection_no = ?",
                     (acct,))]
        rows += [dict(r, _src="raid")
                 for r in fetch_all(
                     "SELECT * FROM raid_cases WHERE account_number = ?",
                     (acct,))]

        # Account mapping bridge
        mp = fetch_all(
            """SELECT * FROM account_mapping
               WHERE old_account = ? OR new_account = ?""",
            (acct, acct),
        )
        for m in mp:
            for col in ("old_account", "new_account"):
                if m.get(col) and m[col] != acct:
                    other = normalize_account(m[col])
                    rows += [dict(r, _src="historical_via_map")
                             for r in fetch_all(
                                 "SELECT * FROM historical_cases WHERE account_id = ?",
                                 (other,))]
                    rows += [dict(r, _src="current_via_map")
                             for r in fetch_all(
                                 "SELECT * FROM current_cases WHERE connection_no = ?",
                                 (other,))]

    # 2) Fuzzy fallback (only if name provided AND no direct hits found)
    fuzzy_used = False
    if name and not rows:
        fuzzy_used = True
        # Pre-filter on first token of name
        first = normalize_text(name).split()[0] if normalize_text(name) else ""
        if first:
            cand_hist = fetch_all(
                "SELECT * FROM historical_cases WHERE LOWER(name) LIKE ? LIMIT 2000",
                (f"%{first}%",),
            )
            for c in cand_hist:
                if _fuzzy_row_match(c, name, father, village, fuzzy_threshold):
                    rows.append(dict(c, _src="historical_fuzzy"))
            cand_curr = fetch_all(
                "SELECT * FROM current_cases WHERE LOWER(name) LIKE ? LIMIT 2000",
                (f"%{first}%",),
            )
            for c in cand_curr:
                if _fuzzy_row_match(c, name, father, village, fuzzy_threshold):
                    rows.append(dict(c, _src="current_fuzzy"))

    # Dedup by (source, id)
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for r in rows:
        key = (r["_src"], r.get("id", 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    # Build aggregates
    total = len(unique)
    total_assessment = 0.0
    dates: list[str] = []
    for r in unique:
        amt = r.get("assessment_amount") or r.get("total_assessment") \
            or r.get("total_assessment_amount") or 0
        try:
            total_assessment += float(amt or 0)
        except (TypeError, ValueError):
            pass
        d = r.get("case_date") or r.get("inspection_date") \
            or r.get("created_at")
        if d:
            dates.append(str(d)[:10])
    dates.sort()

    return {
        "total_offenses": total,
        "first_offense_date": dates[0] if dates else None,
        "last_offense_date":  dates[-1] if dates else None,
        "total_previous_assessment": round(total_assessment, 2),
        "fuzzy_used": fuzzy_used,
        "history": unique,
    }


def _fuzzy_row_match(row: dict, name: str, father: str | None,
                     village: str | None, threshold: float) -> bool:
    n  = fuzz.token_set_ratio(normalize_text(row.get("name")),
                              normalize_text(name)) / 100.0
    f  = fuzz.token_set_ratio(normalize_text(row.get("father_name")),
                              normalize_text(father)) / 100.0 if father else 0
    v  = fuzz.token_set_ratio(normalize_text(row.get("village")),
                              normalize_text(village)) / 100.0 if village else 0
    weights = [(n, 0.5)]
    if father:  weights.append((f, 0.3))
    if village: weights.append((v, 0.2))
    total = sum(w for _, w in weights)
    composite = sum(s * w for s, w in weights) / total if total else 0
    return composite >= threshold
