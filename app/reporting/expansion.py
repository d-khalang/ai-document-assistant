"""
Pure helpers that expand ONE extracted record into SEVERAL report rows, one per code (e.g. one per EER waste code).

Everything is driven by `layout.excel_expand` in schemas/*.json (code field, code regex, per-code fields), so no
document-specific value lives here. The extracted fields are plain strings written by the model, usually one entry per
code ("16.01.03: 9 t/a"); the parser is deliberately tolerant about separators (newline, ';', ',', '|', ':').

Plain dicts / primitives in, plain dicts / primitives out — no openpyxl, no Streamlit.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

_SEPARATORS = " \t\r\n:;,|=–—-•"
_NUMBER_UNIT = re.compile(
    r"^(?P<num>[-+]?\d[\d.,]*)\s*(?P<unit>[A-Za-zµ°%][A-Za-z0-9µ°%²³]*(?:\s*/\s*[A-Za-z0-9]+)?)?$"
)
_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+$")


def unit_key(field_name: str) -> str:
    """Key under which the unit of `field_name` is returned by `expand_record`."""
    return f"{field_name}__unit"


def format_code(raw: str) -> str:
    """Canonical display/matching form: 6-digit codes become 'NN.NN.NN' (hazardous '*' kept); others stay trimmed."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    star = "*" if raw.endswith("*") else ""
    if len(digits) == 6:
        return f"{digits[0:2]}.{digits[2:4]}.{digits[4:6]}{star}"
    return raw


def distinct_codes(text: Optional[str], pattern: str) -> List[str]:
    """Codes found in `text`, in order of appearance, without duplicates."""
    out: List[str] = []
    for m in re.finditer(pattern, text or ""):
        code = format_code(m.group(0))
        if code not in out:
            out.append(code)
    return out


def split_by_code(text: Optional[str], pattern: str) -> Tuple[Dict[str, str], str]:
    """
    Splits "<code> <rest> <code> <rest>..." into ({code: rest}, unkeyed_text).

    The rest of a segment runs up to the next code, with leading/trailing separators stripped. A code that appears
    several times gets its rests joined with '; '. When the text contains no code at all it is returned as unkeyed
    (a single global figure, e.g. 'Fase 1: 3000 t/a').
    """
    text = (text or "").strip()
    matches = list(re.finditer(pattern, text))
    if not matches:
        return {}, text
    keyed: Dict[str, List[str]] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        rest = text[m.end():end].strip(_SEPARATORS)
        bucket = keyed.setdefault(format_code(m.group(0)), [])
        if rest:
            bucket.append(rest)
    return {code: "; ".join(parts) for code, parts in keyed.items() if parts}, ""


def parse_number(token: str) -> Optional[float]:
    """'1.500,5' -> 1500.5, '1.500' -> 1500, '9' -> 9, '3,5' -> 3.5; None if not a number. Integral results are int."""
    t = token.strip()
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    elif _THOUSANDS.match(t):
        t = t.replace(".", "")
    try:
        n = float(t)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def split_value_unit(text: Optional[str]) -> Tuple[Any, str]:
    """'9 t/a' -> (9, 't/a'); '4' -> (4, ''); anything not of that shape is kept verbatim as the value: (text, '')."""
    s = (text or "").strip()
    if not s:
        return None, ""
    m = _NUMBER_UNIT.match(s)
    if m:
        num = parse_number(m.group("num"))
        if num is not None:
            return num, (m.group("unit") or "").strip()
    return s, ""


def expand_record(texts: Dict[str, Optional[str]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    One dict per code. Keys: cfg['code_field'] -> code; for every per-code field `f` in cfg['keyed_fields']: `f` -> value
    (number when the entry is '<number> <unit>', else the text) and, when the field declares a `unit_label`,
    `unit_key(f)` -> unit.

    A value that carries no code (one global figure) is attached to the row only when the record has a single code:
    repeating a plant-wide cap on every code would look like a per-code limit. A record without any code yields one row.
    """
    code_field, pattern = cfg["code_field"], cfg["code_pattern"]
    keyed_cfg: Dict[str, Dict[str, Any]] = cfg.get("keyed_fields") or {}

    code_text = texts.get(code_field)
    codes = distinct_codes(code_text, pattern)
    per_field: Dict[str, Tuple[Dict[str, str], str]] = {}
    for fname in keyed_cfg:
        by_code, unkeyed = split_by_code(texts.get(fname), pattern)
        per_field[fname] = (by_code, unkeyed)
        codes += [c for c in by_code if c not in codes]

    rows: List[Dict[str, Any]] = []
    for code in codes or [None]:
        row: Dict[str, Any] = {code_field: code if code is not None else ((code_text or "").strip() or None)}
        for fname, fcfg in keyed_cfg.items():
            by_code, unkeyed = per_field[fname]
            txt = by_code.get(code) if code is not None else None
            if txt is None and len(codes) <= 1:
                txt = unkeyed or None
            if fcfg.get("unit_label"):
                row[fname], row[unit_key(fname)] = split_value_unit(txt)
            else:
                row[fname] = txt
        rows.append(row)
    return rows
