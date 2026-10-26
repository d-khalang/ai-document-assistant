"""
Deterministic time-series aggregation of consumption / cost records (energy bills, fuel, utilities).

Pure functions over plain dicts: no Streamlit, no openpyxl, no model calls. Which schemas take part, which field gives
the period, which fields are quantities or costs and which one splits the series (POD, plate, utility type...) is declared
in `schemas/*.json -> analytics` (validated in `registry._parse_schema`); nothing domain-specific lives here.

Zero-hallucination rules:
- Only fields with status EXTRACTED / EDITED / CALCULATED and a real number are summed; nothing is estimated or filled.
- A record is placed in the month where its period ENDS. A period longer than `max_span_months` (default 2) cannot be
  attributed to a month without apportioning, so it is left out and counted in `records_unplaced`.
- Year-over-year deltas compare ONLY the months that have data in both years, so a partial year is never compared with a
  full one.
- Missing months stay `None` (never 0).
"""
import calendar
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.normalizer import SUPPORTED_MONTHS, normalize_number
from app.extraction.registry import SchemaDef, resolve_schema

OK_STATUSES = ("EXTRACTED", "EDITED", "CALCULATED")
MONTH_ABBR = ("Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic")
MONTH_FULL = ("Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto",
              "Settembre", "Ottobre", "Novembre", "Dicembre")
NO_DIMENSION = "Non specificato"
DEFAULT_MAX_SPAN_MONTHS = 2
KINDS = ("quantity", "cost")

YearMonth = Tuple[int, int]

_DMY = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-]((?:19|20)\d{2})(?!\d)")
_YMD = re.compile(r"(?<!\d)((?:19|20)\d{2})[/.\-](\d{1,2})[/.\-](\d{1,2})(?!\d)")
_YM = re.compile(r"(?<![\d/.\-])((?:19|20)\d{2})[/\-](\d{1,2})(?![\d/.\-])")
_MY = re.compile(r"(?<![\d/.\-])(\d{1,2})[/\-.]((?:19|20)\d{2})(?![\d/.\-])")
_WORD = re.compile(r"[^\W\d_]+|(?<!\d)(?:19|20)\d{2}(?!\d)")
_FULL_MONTH_NAMES = [n for n in SUPPORTED_MONTHS if len(n) > 3]


# ----------------------------------------------------------------------------- result types
@dataclass(frozen=True)
class Series:
    """One line of the matrix: 12 monthly values per year (None = no data), annual totals and monthly averages."""
    name: str
    values: Dict[int, Tuple[Optional[float], ...]]
    totals: Dict[int, float]
    monthly_avg: Dict[int, float]
    months_with_data: Dict[int, int]


@dataclass(frozen=True)
class YoY:
    """`year` vs `base_year` computed on the months present in BOTH years."""
    year: int
    base_year: int
    months_compared: int
    value: float
    base_value: float
    delta: float
    delta_pct: Optional[float]      # None when the base is 0


@dataclass(frozen=True)
class MetricMatrix:
    field: str
    label: str
    kind: str                       # quantity | cost
    unit: str
    years: Tuple[int, ...]
    total: Series                   # all dimensions summed (same unit by construction)
    by_dimension: Tuple[Series, ...]
    yoy: Tuple[YoY, ...]
    peak: Optional[Tuple[int, int, float]]   # (year, month, value) of the highest monthly total
    grand_total: float
    n_records: int


@dataclass(frozen=True)
class ConsumptionAnalysis:
    module_id: str
    schema_name: str
    label: str
    dimension_label: Optional[str]
    matrices: Tuple[MetricMatrix, ...]
    records_used: int
    records_unplaced: int           # had values but no parseable period, or a period too long for one month
    records_spanning: int           # placed in their end month although the period covers two months
    period_first: YearMonth
    period_last: YearMonth


# ----------------------------------------------------------------------------- formatting helpers
def month_label(month: int, full: bool = False) -> str:
    return (MONTH_FULL if full else MONTH_ABBR)[month - 1]


def period_label(ym: YearMonth) -> str:
    return f"{month_label(ym[1], full=True)} {ym[0]}"


def format_it(value: Optional[float], decimals: int = 2) -> str:
    """Italian number format: 1.234,50 (None -> '-')."""
    if value is None:
        return "-"
    return f"{value:,.{decimals}f}".replace(",", "§").replace(".", ",").replace("§", ".")


# ----------------------------------------------------------------------------- period parsing
def _ym_index(ym: YearMonth) -> int:
    return ym[0] * 12 + ym[1] - 1


def _valid(year: int, month: int) -> bool:
    return 1990 <= year <= 2100 and 1 <= month <= 12


def _valid_day(year: int, month: int, day: int) -> bool:
    """A real calendar day: 31/02 is rejected, so an impossible date never lands in a month."""
    return _valid(year, month) and 1 <= day <= calendar.monthrange(year, month)[1]


def _month_of_token(token: str) -> Optional[int]:
    t = token.lower()
    if t in SUPPORTED_MONTHS:
        return SUPPORTED_MONTHS[t]
    if len(t) >= 4:     # 'sett', 'dicem'... but never a plain word: must be the start of a full month name
        for name in _FULL_MONTH_NAMES:
            if name.startswith(t):
                return SUPPORTED_MONTHS[name]
    return None


def _from_words(text: str) -> Optional[Tuple[YearMonth, YearMonth]]:
    """'Settembre 2025', 'Luglio - Agosto 2025', 'Dicembre 2024 - Gennaio 2025'. A month without any year is not guessed."""
    entries: List[Tuple[str, int]] = []
    for tok in _WORD.findall(text):
        if tok.isdigit():
            entries.append(("y", int(tok)))
        else:
            m = _month_of_token(tok)
            if m:
                entries.append(("m", m))
    if not any(k == "m" for k, _ in entries):
        return None
    resolved: List[YearMonth] = []
    pending: List[int] = []                      # months still waiting for the year that follows them
    for kind, val in entries:
        if kind == "m":
            pending.append(val)
        elif pending:
            last = pending[-1]
            for m in pending[:-1]:               # 'Nov - Gen 2025' -> Nov 2024 (a later month number means the year before)
                resolved.append((val if m <= last else val - 1, m))
            resolved.append((val, last))
            pending = []
    if pending or not resolved:
        return None
    pts = [p for p in resolved if _valid(*p)]
    if len(pts) != len(resolved):
        return None
    return min(pts, key=_ym_index), max(pts, key=_ym_index)


def parse_period(value: Any) -> Optional[Tuple[YearMonth, YearMonth]]:
    """
    (start, end) as (year, month) pairs, or None when the text does not name a month with certainty.
    Accepts dates (ISO, dd/mm/yyyy), timestamps ('2025-01-01 00:00:00', '2025-01-01T08:30:00Z', datetime objects),
    ranges of dates, 'YYYY-MM', 'MM/YYYY' and month names with a year ('Settembre 2025', 'Luglio - Agosto 2025').
    """
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return (value.year, value.month), (value.year, value.month)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()

    points: List[YearMonth] = []
    for d, m, y in _DMY.findall(text):
        if _valid_day(int(y), int(m), int(d)):
            points.append((int(y), int(m)))
    for y, m, d in _YMD.findall(text):
        if _valid_day(int(y), int(m), int(d)):
            points.append((int(y), int(m)))
    if not points:
        points = [(int(y), int(m)) for y, m in _YM.findall(text) if _valid(int(y), int(m))]
    if not points:
        points = [(int(y), int(m)) for m, y in _MY.findall(text) if _valid(int(y), int(m))]
    if points:
        return min(points, key=_ym_index), max(points, key=_ym_index)
    return _from_words(text)


# ----------------------------------------------------------------------------- field access
def _raw(fdata: Any) -> Any:
    if not isinstance(fdata, dict) or fdata.get("status", "EXTRACTED") not in OK_STATUSES:
        return None
    v = fdata.get("normalized_value")
    return v if v is not None else fdata.get("raw_value")


def _period_raw(fdata: Any) -> Any:
    """
    Value of a period field. Unlike the metric values, a period whose strict date normalization failed (UNCERTAIN, e.g. a
    timestamp stored before the normalizer learned to strip the time part) is still read from its raw text: only the
    month is needed and `parse_period` is deterministic and rejects impossible dates, so nothing is guessed.
    """
    if not isinstance(fdata, dict) or fdata.get("status") == "MISSING":
        return None
    v = fdata.get("normalized_value")
    return v if v is not None else fdata.get("raw_value")


def _number(fdata: Any) -> Optional[float]:
    v = _raw(fdata)
    if isinstance(v, str):
        v = normalize_number(v)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _text(fdata: Any) -> str:
    v = _raw(fdata)
    return " ".join(str(v).split()) if v is not None else ""


# ----------------------------------------------------------------------------- aggregation
def _series(name: str, cells: Dict[YearMonth, List[float]], years: Tuple[int, ...]) -> Series:
    values: Dict[int, Tuple[Optional[float], ...]] = {}
    totals: Dict[int, float] = {}
    avgs: Dict[int, float] = {}
    counts: Dict[int, int] = {}
    for y in years:
        row = tuple(math.fsum(cells[(y, m)]) if (y, m) in cells else None for m in range(1, 13))
        present = [v for v in row if v is not None]
        values[y] = row
        counts[y] = len(present)
        if present:
            totals[y] = math.fsum(present)
            avgs[y] = totals[y] / len(present)
    return Series(name, values, totals, avgs, counts)


def _yoy(total: Series, years: Tuple[int, ...]) -> Tuple[YoY, ...]:
    out: List[YoY] = []
    for y in years:
        if y - 1 not in total.values:
            continue
        common = [m for m in range(12) if total.values[y][m] is not None and total.values[y - 1][m] is not None]
        if not common:
            continue
        cur = math.fsum(total.values[y][m] for m in common)
        base = math.fsum(total.values[y - 1][m] for m in common)
        out.append(YoY(y, y - 1, len(common), cur, base, cur - base, (cur - base) / abs(base) * 100 if base else None))
    return tuple(out)


def _peak(total: Series, years: Tuple[int, ...]) -> Optional[Tuple[int, int, float]]:
    best: Optional[Tuple[int, int, float]] = None
    for y in years:
        for m, v in enumerate(total.values[y], start=1):
            if v is not None and (best is None or v > best[2]):
                best = (y, m, v)
    return best


def analyze_records(module_id: str, schema: SchemaDef, records: List[Dict[str, Any]]) -> Optional[ConsumptionAnalysis]:
    """Aggregates the records of ONE schema according to `schema.analytics`; None when nothing can be placed."""
    cfg = schema.analytics
    if not cfg:
        return None
    labels = schema.all_labels()
    max_span = int(cfg.get("max_span_months", DEFAULT_MAX_SPAN_MONTHS))
    dim_field = cfg.get("dimension_field")
    metrics = cfg["metrics"]

    # (metric index, unit key) -> dimension key -> (year, month) -> [values]
    acc: Dict[Tuple[int, str], Dict[str, Dict[YearMonth, List[float]]]] = {}
    unit_names: Dict[Tuple[int, str], str] = {}
    dim_names: Dict[str, str] = {}
    counts: Dict[Tuple[int, str], int] = {}
    used = unplaced = spanning = 0
    placed: List[YearMonth] = []

    for rec in records or []:
        fields = rec.get("fields") or {}
        values = [(i, _number(fields.get(m["field"]))) for i, m in enumerate(metrics)]
        values = [(i, v) for i, v in values if v is not None]
        if not values:
            continue                                     # nothing to aggregate in this record
        period = None
        for pf in cfg["period_fields"]:
            period = parse_period(_period_raw(fields.get(pf)))
            if period:
                break
        if period is None:
            unplaced += 1
            continue
        start, end = period
        span = _ym_index(end) - _ym_index(start) + 1
        if span > max_span:
            unplaced += 1
            continue
        used += 1
        spanning += span > 1
        placed.append(end)
        dim = (_text(fields.get(dim_field)) if dim_field else "") or (NO_DIMENSION if dim_field else "")
        dim_names.setdefault(dim.casefold(), dim)
        for i, v in values:
            m = metrics[i]
            unit = m.get("unit") or (_text(fields.get(m["unit_field"])) if m.get("unit_field") else "")
            key = (i, unit.casefold())
            unit_names.setdefault(key, unit)
            acc.setdefault(key, {}).setdefault(dim.casefold(), {}).setdefault(end, []).append(v)
            counts[key] = counts.get(key, 0) + 1

    if not acc:
        return None

    matrices: List[MetricMatrix] = []
    for key in sorted(acc, key=lambda k: (k[0], k[1])):
        i, _ = key
        m = metrics[i]
        by_dim = acc[key]
        years = tuple(sorted({y for cells in by_dim.values() for (y, _) in cells}))
        merged: Dict[YearMonth, List[float]] = {}
        for cells in by_dim.values():
            for ym, vals in cells.items():
                merged.setdefault(ym, []).extend(vals)
        total = _series("", merged, years)
        dims: Tuple[Series, ...] = ()
        if dim_field:
            order = sorted(by_dim, key=lambda d: (dim_names[d] == NO_DIMENSION, d))
            dims = tuple(_series(dim_names[d], by_dim[d], years) for d in order)
        matrices.append(MetricMatrix(
            field=m["field"], label=m.get("label") or labels.get(m["field"], m["field"]), kind=m["kind"],
            unit=unit_names[key], years=years, total=total, by_dimension=dims, yoy=_yoy(total, years),
            peak=_peak(total, years), grand_total=math.fsum(total.totals.values()), n_records=counts[key],
        ))

    return ConsumptionAnalysis(
        module_id=module_id, schema_name=schema.name, label=schema.label,
        dimension_label=(cfg.get("dimension_label") or labels.get(dim_field, dim_field)) if dim_field else None,
        matrices=tuple(matrices), records_used=used, records_unplaced=unplaced, records_spanning=spanning,
        period_first=min(placed, key=_ym_index), period_last=max(placed, key=_ym_index),
    )


def analyze_payload(payload: Dict[str, Dict[str, Any]]) -> List[ConsumptionAnalysis]:
    """
    `payload` = {module_id: {schema_name: {"records": [...]}}}. Schemas without an `analytics` block, unknown schemas and
    schemas whose records carry no usable period/value are skipped silently, so documents without consumption data just
    produce an empty list.
    """
    out: List[ConsumptionAnalysis] = []
    for mid, schemas in (payload or {}).items():
        for sname, sdata in (schemas or {}).items():
            try:
                schema = resolve_schema(sname, mid)
            except Exception:
                continue
            if not schema.analytics:
                continue
            analysis = analyze_records(mid, schema, (sdata or {}).get("records") or [])
            if analysis:
                out.append(analysis)
    return out
