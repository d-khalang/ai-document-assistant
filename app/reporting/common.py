"""
Common reporting utilities, metadata resolvers, and backward-compatible column mappings.
Decouples word_exporter from excel_exporter and guarantees strict module scoping.
"""
from typing import Any, Dict, List, Optional, Tuple
from app.extraction.registry import ModuleDef, SchemaDef, get_module, load_registry, resolve_schema

GENERIC_REPORT = {
    "workbook_title": "REPORT DOCUMENT INTELLIGENCE",
    "doc_title": "RAPPORTO DI ESTRAZIONE DOCUMENTALE",
    "doc_subtitle": "",
    "filename_prefix": "REPORT",
    "signoff": [
        {"label": "Verificato da: {name}", "profile_key": None},
        {"label": "Approvato da: {name}", "profile_key": None}
    ],
}

_EMPTY_TOKENS = {"", "-", "null", "none", "n/a"}


def split_items(val: Any, sep: str = "\n") -> List[str]:
    s = "" if val is None else str(val).strip()
    if s.lower() in _EMPTY_TOKENS:
        return []
    return [
        p.strip(" -•\t")
        for p in s.split(sep)
        if p.strip(" -•\t") and p.strip(" -•\t").lower() not in _EMPTY_TOKENS
    ]


def sheet_title_for(schema: Optional[SchemaDef], sname: str, fallback: str) -> str:
    return (schema.sheet_title if schema and schema.sheet_title else fallback)


def resolve_scope(
    data_by_schema: Dict[str, Any],
    module_id: Optional[str] = None
) -> Tuple[Optional[ModuleDef], Dict[str, Any]]:
    """
    بررسی و فیلتر داده‌ها: فقط اسکیماهایی که متعلق به ماژول جاری هستند در خروجی قرار می‌گیرند.
    مانع از نفوذ داده‌های ماژول‌های دیگر به گزارش اکسل یا ورد می‌شود.
    """
    if module_id:
        module = get_module(module_id)
        filtered_data = {n: d for n, d in data_by_schema.items() if n in module.schemas}
        return module, filtered_data

    # برای فراخوانی‌های قدیمی بدون module_id
    all_mods = load_registry()
    owners = {m.module_id for n in data_by_schema for m in all_mods.values() if n in m.schemas}
    if len(owners) == 1:
        return get_module(list(owners)[0]), dict(data_by_schema)
    return None, dict(data_by_schema)


def report_meta(module: Optional[ModuleDef]) -> Dict[str, Any]:
    """دریافت متادیتای گزارش و سربرگ‌ها از تنظیمات ماژول."""
    return {**GENERIC_REPORT, **(module.report if module else {})}


def signoff_labels(meta: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    """تولید برچسب‌های کادر امضا بر اساس پروفایل شرکت."""
    prof = profile or {}
    out = []
    for s in meta.get("signoff", []):
        pkey = s.get("profile_key")
        val = prof.get(pkey, "") if pkey else ""
        out.append(s["label"].format(name=val))
    return out


def column_plan(
    schema_name: str,
    module: Optional[ModuleDef],
    records: List[Dict[str, Any]],
    selected: Optional[List[str]] = None
) -> List[Tuple[str, str]]:
    """
    تعیین ترتیب دقیق ستون‌ها و عناوین آن‌ها بر اساس اسکیما و انتخاب کاربر.
    خروجی: لیستی از توپل‌های (field_name, field_label).
    """
    try:
        schema: Optional[SchemaDef] = resolve_schema(schema_name, module.module_id if module else None)
    except Exception:
        schema = None

    if schema:
        names = schema.ordered_field_names()
        labels = schema.all_labels()
    else:
        names = list(records[0].get("fields", {}).keys()) if records else []
        labels = {}

    if selected:
        names = [n for n in names if n in selected] or names

    return [(n, labels.get(n, n.replace("_", " ").title())) for n in names]


def cell_value(fdata: Dict[str, Any]) -> Any:
    """استخراج مقدار قابل نمایش از دیکشنری فیلد."""
    v = fdata.get("normalized_value")
    return v if v is not None else fdata.get("raw_value")


def build_legacy_column_labels() -> Dict[str, str]:
    """تولید دیکشنری تخت برچسب‌های ستون برای حفظ سازگاری کدهای گذشته."""
    out = {
        "source_page": "Pagina Fonte",
        "source_document": "Documento Fonte"
    }
    for m in load_registry().values():
        for s in m.schemas.values():
            out.update(s.all_labels())
    return out


# نگهداری برای کدهای قدیمی که COLUMN_LABELS را مستقیماً می‌خواندند
COLUMN_LABELS = build_legacy_column_labels()