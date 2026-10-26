"""Schema Registry: loads modules/schemas from schemas/*.json (no domain logic in code)."""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import GEMINI_MODEL

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
FIELD_TYPES = {"string", "date", "number", "plate"}
COMPUTE_OPS = {"ratio", "sum", "diff", "product"}
DEFAULT_SYSTEM_PROMPT = (
    "You are a precise document data extraction engine. Extract structured entities with absolute "
    "fidelity to the source text. Never invent values. If a field is not present, return null."
)
DEFAULT_EXTRACTION_MODEL = GEMINI_MODEL


@dataclass
class FieldDef:
    name: str
    type: str
    label: str
    description: str = ""
    required: bool = False
    alert: Optional[Dict[str, Any]] = None


@dataclass
class ComputedDef:
    name: str
    op: str
    inputs: List[str]
    label: str = ""
    scale: float = 1.0
    decimals: int = 2
    unit: str = ""


@dataclass
class ExpiryRule:
    id: str
    keywords: List[str]
    months: Optional[int]
    priority: int = 0
    ref: str = ""


@dataclass
class DerivedDateDef:
    target: str
    base_field: str
    text_fields: List[str]
    rules: List[ExpiryRule]
    default_months: Optional[int] = None


@dataclass
class SchemaDef:
    name: str
    module_id: str
    label: str
    description: str
    fields: Dict[str, FieldDef]
    computed: Dict[str, ComputedDef] = field(default_factory=dict)
    routing: Dict[str, Any] = field(default_factory=dict)
    layout: Dict[str, Any] = field(default_factory=dict)
    derived: Dict[str, DerivedDateDef] = field(default_factory=dict)
    chat_guidelines: List[str] = field(default_factory=list)
    analytics: Dict[str, Any] = field(default_factory=dict)

    @property
    def sheet_title(self) -> Optional[str]:
        return self.layout.get("sheet_title")

    @property
    def report_title(self) -> str:
        return self.layout.get("report_title") or "RAPPORTO DI CONFORMITÀ E AUDIT"

    @property
    def word_header_fields(self) -> List[str]:
        return self.layout.get("word_header_fields") or []

    @property
    def word_table_fields(self) -> List[str]:
        return self.layout.get("word_table_fields") or []

    @property
    def word_sections(self) -> List[Dict[str, Any]]:
        return self.layout.get("word_sections") or []

    @property
    def hide_status_column(self) -> bool:
        return bool(self.layout.get("hide_status_column"))

    @property
    def excel_expand(self) -> Dict[str, Any]:
        return self.layout.get("excel_expand") or {}

    @property
    def required(self) -> List[str]:
        return [f.name for f in self.fields.values() if f.required]

    def ordered_field_names(self) -> List[str]:
        return list(self.fields) + list(self.computed)

    def all_labels(self) -> Dict[str, str]:
        labels = {n: f.label for n, f in self.fields.items()}
        labels.update({n: c.label for n, c in self.computed.items()})
        return labels


@dataclass
class ModuleDef:
    module_id: str
    label: str
    version: str
    system_prompt: str
    report: Dict[str, Any]
    schemas: Dict[str, SchemaDef]
    model: str = DEFAULT_EXTRACTION_MODEL


def _parse_schema(module_id: str, name: str, raw: Dict[str, Any], src: str) -> SchemaDef:
    fields: Dict[str, FieldDef] = {}
    for fname, fr in (raw.get("fields") or {}).items():
        ftype = fr.get("type", "string")
        if ftype not in FIELD_TYPES:
            raise ValueError(f"{src}: {name}.{fname}: invalid type '{ftype}'")
        alert = fr.get("alert")
        if alert is not None:
            th = alert.get("thresholds_days")
            if ftype != "date" or not th or not all(isinstance(t, int) and t > 0 for t in th):
                raise ValueError(f"{src}: {name}.{fname}: alert requires date type and positive int thresholds_days")
        fields[fname] = FieldDef(fname, ftype, fr.get("label") or fname.replace("_", " ").title(),
                                 fr.get("description", ""), bool(fr.get("required", False)), alert)
    if not fields:
        raise ValueError(f"{src}: schema '{name}' has no fields")

    for f in fields.values():
        for lf in (f.alert or {}).get("label_fields", []):
            if lf not in fields:
                raise ValueError(f"{src}: {name}.{f.name}: unknown label_field '{lf}'")

    computed: Dict[str, ComputedDef] = {}
    for cname, cr in (raw.get("computed") or {}).items():
        op, inputs = cr.get("op"), cr.get("inputs", [])
        if op not in COMPUTE_OPS or cname in fields:
            raise ValueError(f"{src}: {name}.{cname}: invalid op or name clash")

        min_inputs = 2
        if op in ("ratio", "diff") and len(inputs) != 2:
            raise ValueError(f"{src}: {name}.{cname}: op '{op}' requires exactly 2 inputs")
        if op in ("sum", "product") and len(inputs) < min_inputs:
            raise ValueError(f"{src}: {name}.{cname}: op '{op}' requires at least {min_inputs} inputs")

        if any(i not in fields or fields[i].type != "number" for i in inputs):
            raise ValueError(f"{src}: {name}.{cname}: all inputs must be existing number fields")

        computed[cname] = ComputedDef(cname, op, inputs, cr.get("label") or cname,
                                      float(cr.get("scale", 1)), int(cr.get("decimals", 2)), cr.get("unit", ""))

    routing = raw.get("routing") or {}
    for key in ("keywords", "strong_keywords"):
        if not all(isinstance(k, str) for k in routing.get(key, [])):
            raise ValueError(f"{src}: {name}.routing.{key} must be a list of strings")

    layout = raw.get("layout") or {}
    st_title = layout.get("sheet_title")
    if st_title and (len(st_title) > 31 or any(c in st_title for c in '[]:*?/\\')):
        raise ValueError(f"{src}: {name}.layout.sheet_title invalid for Excel")
    for list_key in ("word_header_fields", "word_table_fields"):
        for fname in layout.get(list_key, []):
            if fname not in fields and fname not in computed:
                raise ValueError(f"{src}: {name}.layout.{list_key} unknown field '{fname}'")
    for sec in layout.get("word_sections", []):
        if sec.get("field") not in fields or sec.get("style") not in ("table", "list"):
            raise ValueError(f"{src}: {name}.layout.word_sections invalid: {sec}")

    if not isinstance(layout.get("hide_status_column", False), bool):
        raise ValueError(f"{src}: {name}.layout.hide_status_column must be a boolean")
    expand = layout.get("excel_expand")
    if expand is not None:
        if expand.get("code_field") not in fields:
            raise ValueError(f"{src}: {name}.layout.excel_expand.code_field must be an existing field")
        try:
            re.compile(expand.get("code_pattern") or "")
        except (re.error, TypeError):
            raise ValueError(f"{src}: {name}.layout.excel_expand.code_pattern must be a valid regex")
        if not expand.get("code_pattern"):
            raise ValueError(f"{src}: {name}.layout.excel_expand.code_pattern is required")
        keyed = expand.get("keyed_fields") or {}
        for kname, kconf in keyed.items():
            if kname not in fields or kname == expand["code_field"]:
                raise ValueError(f"{src}: {name}.layout.excel_expand.keyed_fields unknown field '{kname}'")
            unit_label = (kconf or {}).get("unit_label")
            if unit_label is not None and not (isinstance(unit_label, str) and unit_label.strip()):
                raise ValueError(f"{src}: {name}.layout.excel_expand.keyed_fields.{kname}.unit_label invalid")

    analytics = raw.get("analytics") or {}
    if analytics:
        period_fields = analytics.get("period_fields")
        if not isinstance(period_fields, list) or not period_fields or any(f not in fields for f in period_fields):
            raise ValueError(f"{src}: {name}.analytics.period_fields must be a non-empty list of existing fields")
        dim = analytics.get("dimension_field")
        if dim is not None and dim not in fields:
            raise ValueError(f"{src}: {name}.analytics.dimension_field '{dim}' is not a field")
        max_span = analytics.get("max_span_months", 2)
        if not isinstance(max_span, int) or isinstance(max_span, bool) or max_span < 1:
            raise ValueError(f"{src}: {name}.analytics.max_span_months must be a positive int")
        metrics = analytics.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise ValueError(f"{src}: {name}.analytics.metrics must be a non-empty list")
        for met in metrics:
            if met.get("field") not in fields or fields[met["field"]].type != "number":
                raise ValueError(f"{src}: {name}.analytics.metrics field '{met.get('field')}' must be an existing number field")
            if met.get("kind") not in ("quantity", "cost"):
                raise ValueError(f"{src}: {name}.analytics.metrics '{met['field']}' kind must be 'quantity' or 'cost'")
            if met.get("unit_field") is not None and met["unit_field"] not in fields:
                raise ValueError(f"{src}: {name}.analytics.metrics '{met['field']}' unit_field is not a field")

    guidelines = (raw.get("chat") or {}).get("guidelines") or []
    if not isinstance(guidelines, list) or not all(isinstance(g, str) and g.strip() for g in guidelines):
        raise ValueError(f"{src}: {name}.chat.guidelines must be a list of non-empty strings")

    raw_derived = raw.get("derived_dates") or {}
    derived: Dict[str, DerivedDateDef] = {}
    for target_name, dconf in raw_derived.items():
        if target_name not in fields or fields[target_name].type != "date":
            raise ValueError(f"{src}: {name}.derived_dates target '{target_name}' must be an existing date field")
        base_field = dconf.get("base_field")
        if base_field not in fields or fields[base_field].type != "date":
            raise ValueError(f"{src}: {name}.derived_dates base_field '{base_field}' must be an existing date field")
        text_fields = dconf.get("text_fields") or []
        for tf in text_fields:
            if tf not in fields:
                raise ValueError(f"{src}: {name}.derived_dates text_field '{tf}' not in fields")

        rules_list: List[ExpiryRule] = []
        rule_ids = set()
        for r in dconf.get("rules", []):
            rid = r.get("id")
            if not rid or rid in rule_ids:
                raise ValueError(f"{src}: {name}.derived_dates rule id duplicate or missing: '{rid}'")
            rule_ids.add(rid)
            kw = r.get("keywords") or []
            if not kw or not all(isinstance(k, str) for k in kw):
                raise ValueError(f"{src}: {name}.derived_dates rule '{rid}' keywords must be non-empty list of strings")
            m = r.get("months")
            if m is not None and (not isinstance(m, int) or m <= 0):
                raise ValueError(f"{src}: {name}.derived_dates rule '{rid}' months must be positive int or null")
            rules_list.append(ExpiryRule(
                id=rid,
                keywords=kw,
                months=m,
                priority=int(r.get("priority", 0)),
                ref=str(r.get("ref", ""))
            ))

        def_m = dconf.get("default_months")
        if def_m is not None and (not isinstance(def_m, int) or def_m <= 0):
            raise ValueError(f"{src}: {name}.derived_dates default_months must be positive int or null")

        derived[target_name] = DerivedDateDef(
            target=target_name,
            base_field=base_field,
            text_fields=text_fields,
            rules=rules_list,
            default_months=def_m
        )

    return SchemaDef(
        name,
        module_id,
        raw.get("label") or name,
        raw.get("description", ""),
        fields,
        computed,
        routing,
        layout=layout,
        derived=derived,
        chat_guidelines=[g.strip() for g in guidelines],
        analytics=analytics,
    )

@lru_cache(maxsize=1)
def load_registry() -> Dict[str, ModuleDef]:
    modules: Dict[str, ModuleDef] = {}
    for path in sorted(SCHEMAS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        mid = raw["module_id"]
        if mid in modules:
            raise ValueError(f"{path.name}: duplicate module_id '{mid}'")
        schemas = {n: _parse_schema(mid, n, sr, path.name) for n, sr in (raw.get("schemas") or {}).items()}
        
        extraction_cfg = raw.get("extraction") or {}
        modules[mid] = ModuleDef(
            mid,
            raw.get("label", mid),
            raw.get("version", "0"),
            extraction_cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
            raw.get("report") or {},
            schemas,
            extraction_cfg.get("model") or DEFAULT_EXTRACTION_MODEL
        )
    if not modules:
        raise RuntimeError(f"No schema modules found in {SCHEMAS_DIR}")
    return modules


def reload_registry() -> Dict[str, ModuleDef]:
    """پاک‌سازی کش لودر و بارگذاری مجدد فایل‌های اسکیما از دیسک."""
    load_registry.cache_clear()
    return load_registry()


def list_modules() -> List[ModuleDef]:
    return list(load_registry().values())


def get_module(module_id: str) -> ModuleDef:
    try:
        return load_registry()[module_id]
    except KeyError:
        raise ValueError(f"Unknown module '{module_id}'. Available: {list(load_registry())}")


def resolve_schema(schema_name: str, module_id: Optional[str] = None) -> SchemaDef:
    if module_id:
        mod = get_module(module_id)
        if schema_name not in mod.schemas:
            raise ValueError(f"Schema '{schema_name}' not in module '{module_id}'")
        return mod.schemas[schema_name]
    matches = [m.schemas[schema_name] for m in load_registry().values() if schema_name in m.schemas]
    if len(matches) != 1:
        raise ValueError(f"Schema '{schema_name}' is {'ambiguous' if matches else 'unknown'}; specify module_id")
    return matches[0]


def build_legacy_schemas() -> Dict[str, Dict[str, Any]]:
    """Flat view compatible with the old AVAILABLE_SCHEMAS (first module wins on name clash)."""
    out: Dict[str, Dict[str, Any]] = {}
    for m in load_registry().values():
        for s in m.schemas.values():
            fields = {n: f"{f.type} ({f.description})" for n, f in s.fields.items()}
            fields.update({n: f"number (calcolato, {c.unit})" for n, c in s.computed.items()})
            out.setdefault(s.name, {"description": s.description, "fields": fields, "required": s.required})
    return out
