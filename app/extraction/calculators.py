"""Deterministic mathematical calculations on extracted fields (Whitelist-only)."""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
from dateutil.relativedelta import relativedelta
from app.extraction.normalizer import keyword_matches
from app.extraction.registry import ComputedDef


def compute_value(cdef: ComputedDef, numbers: Dict[str, Optional[float]]) -> Optional[float]:
    """
    محاسبه کاملاً قطعی مقادیر مشتق‌شده با عملگرهای مجاز.
    در صورت ناقص بودن هر یک از ورودی‌ها، مقدار None (Missing) برگردانده می‌شود.
    """
    vals = [numbers.get(i) for i in cdef.inputs]
    if any(v is None for v in vals):
        return None

    if cdef.op == "ratio":
        num, den = vals[0], vals[1]
        if den <= 0 or num < 0:
            return None
        return round((num / den) * cdef.scale, cdef.decimals)

    elif cdef.op == "sum":
        total = sum(vals)
        return round(total * cdef.scale, cdef.decimals)

    elif cdef.op == "diff":
        diff = vals[0] - vals[1]
        return round(diff * cdef.scale, cdef.decimals)

    elif cdef.op == "product":
        prod = 1.0
        for v in vals:
            prod *= v
        return round(prod * cdef.scale, cdef.decimals)

    raise ValueError(f"Unsupported op: {cdef.op}")


@dataclass(frozen=True)
class ExpiryResult:
    iso_date: Optional[str]
    reason: str          # "ok" | "no_base_date" | "no_rule" | "ambiguous" | "no_expiry"
    rule_id: Optional[str] = None
    months: Optional[int] = None


def compute_expiry_date(issue_iso: Optional[str], text: str, rules: list, default_months: Optional[int] = None) -> ExpiryResult:
    try:
        base = date.fromisoformat(issue_iso) if isinstance(issue_iso, str) else None
    except ValueError:
        base = None
    if base is None:
        return ExpiryResult(None, "no_base_date")

    hits = [r for r in rules if any(keyword_matches(k, text) for k in r.keywords)]
    if hits:
        top = max(r.priority for r in hits)
        best = [r for r in hits if r.priority == top]
        if len({r.months for r in best}) > 1:
            return ExpiryResult(None, "ambiguous")
        months, rid = best[0].months, best[0].id
    elif default_months:
        months, rid = default_months, "default"
    else:
        return ExpiryResult(None, "no_rule")

    if months is None:
        return ExpiryResult(None, "no_expiry", rid)
    return ExpiryResult((base + relativedelta(months=months)).isoformat(), "ok", rid, months)
