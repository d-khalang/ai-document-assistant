import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from app.ai.gemini import generate_structured_json
from app.extraction.calculators import compute_value, compute_expiry_date
from app.extraction.normalizer import normalize_date, normalize_number, normalize_plate
from app.extraction.registry import FieldDef, SchemaDef, get_module, resolve_schema

_NULL_TOKENS = {"null", "none", "", "-", "n/a"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_field(fdef: FieldDef, raw_value: Any, ok_status: str = "EXTRACTED") -> Dict[str, Any]:
    """Deterministic per-field normalization driven by the declared type in JSON schema."""
    if isinstance(raw_value, list):
        raw_value = "\n".join(str(x) for x in raw_value if x is not None)
    if raw_value is None or str(raw_value).strip().lower() in _NULL_TOKENS:
        return {"raw_value": None, "normalized_value": None, "status": "MISSING"}

    raw = str(raw_value).strip()
    if fdef.type == "date":
        norm = normalize_date(raw)
        if not _valid_iso_date(norm):
            return {"raw_value": raw, "normalized_value": None, "status": "UNCERTAIN"}
    elif fdef.type == "number":
        norm = normalize_number(raw)
        if norm is None:
            return {"raw_value": raw, "normalized_value": None, "status": "UNCERTAIN"}
    elif fdef.type == "plate":
        norm = normalize_plate(raw)
    else:
        norm = raw

    return {"raw_value": raw, "normalized_value": norm, "status": ok_status}


def apply_computed(schema: SchemaDef, fields: Dict[str, Any]) -> None:
    numbers = {n: fields.get(n, {}).get("normalized_value") for n in schema.fields}
    for cname, cdef in schema.computed.items():
        value = compute_value(cdef, numbers)
        if value is None:
            fields[cname] = {"raw_value": None, "normalized_value": None, "status": "MISSING"}
        else:
            fields[cname] = {
                "raw_value": f"{value} {cdef.unit}".strip(),
                "normalized_value": value,
                "status": "CALCULATED"
            }


def apply_derived_dates(schema: SchemaDef, fields: Dict[str, Any]) -> List[str]:
    warns = []
    for target, d in schema.derived.items():
        # مقدار چاپ‌شده یا ویرایش دستی هرگز overwrite نمی‌شود
        if (fields.get(target) or {}).get("status") in ("EXTRACTED", "EDITED", "UNCERTAIN"):
            continue
        base = fields.get(d.base_field) or {}
        base_iso = base.get("normalized_value") if base.get("status") in ("EXTRACTED", "EDITED") else None
        text = " ".join(
            str((fields.get(f) or {}).get("normalized_value") or (fields.get(f) or {}).get("raw_value") or "")
            for f in d.text_fields
        )
        res = compute_expiry_date(base_iso, text, d.rules, d.default_months)
        if res.iso_date:
            fields[target] = {
                "raw_value": f"{res.iso_date} ({res.months} mesi · {res.rule_id})",
                "normalized_value": res.iso_date,
                "status": "CALCULATED",
            }
        else:
            fields[target] = {"raw_value": None, "normalized_value": None, "status": "MISSING"}
            if res.reason in ("ambiguous", "no_rule"):
                warns.append(f"derived_{res.reason}:{target}")
    return warns


def required_warnings(schema: SchemaDef, fields: Dict[str, Any]) -> List[str]:
    out = []
    for n in schema.required:
        st = fields.get(n, {}).get("status")
        if st == "MISSING":
            out.append(f"missing_required:{n}")
        elif st == "UNCERTAIN":
            out.append(f"uncertain_required:{n}")
    return out


def finalize_record(schema: SchemaDef, fields: Dict[str, Any]) -> List[str]:
    apply_computed(schema, fields)
    derived_warns = apply_derived_dates(schema, fields)
    return required_warnings(schema, fields) + derived_warns


def _build_prompt(schema: SchemaDef, pages: List[Dict[str, Any]], doc_name: str) -> str:
    fields_spec = {n: f"{f.type} - {f.description}" for n, f in schema.fields.items()}
    corpus = "\n\n".join(
        f"--- [PAGINA {p.get('page_number', 1)}] ---\n{p['text'].strip()}"
        for p in pages if p.get("text", "").strip()
    )
    return f"""
TARGET EXTRACTION SCHEMA: '{schema.name.upper()}'
DESCRIPTION: {schema.description}
SOURCE DOCUMENT: {doc_name}

FIELDS TO EXTRACT:
{json.dumps(fields_spec, indent=2, ensure_ascii=False)}

MANDATORY RULES:
1. Identify every valid record matching this schema.
2. Put the exact textual value as found in the text into 'raw_value'. Copy dates and numbers EXACTLY as written; never reformat, convert or compute.
3. Set 'source_page' (integer) to the page where the record was found.
4. If a field is not present, set 'raw_value' to null.
5. Return a valid JSON object matching this structure:
{{
  "records": [
    {{"source_page": <integer>, "fields": {{"<field_name>": {{"raw_value": <string or null>}}}}}}
  ]
}}

DOCUMENT CONTEXT:
{corpus}
""".strip()


def extract_structured_data(pages: List[Dict[str, Any]], schema_name: str = "scadenziario",
                            module_id: Optional[str] = None, source_document: str = "") -> Dict[str, Any]:
    schema = resolve_schema(schema_name, module_id)
    module = get_module(schema.module_id)
    base = {"schema": schema.name, "module_id": module.module_id}

    if not pages:
        return {**base, "total_records": 0, "records": []}

    raw_json = generate_structured_json(
        _build_prompt(schema, pages, source_document or "n/a"),
        system_instruction=module.system_prompt,
        model=getattr(module, "model", None)
    )

    try:
        data = json.loads(raw_json)
    except Exception as e:
        raise ValueError(f"Failed to parse model JSON extraction output: {e}")

    records = []
    for rec in data.get("records") or []:
        raw_fields = rec.get("fields") or {}
        fields = {}
        for n, fdef in schema.fields.items():
            item = raw_fields.get(n)
            raw = item.get("raw_value") if isinstance(item, dict) else item
            fields[n] = normalize_field(fdef, raw)

        warnings = finalize_record(schema, fields)
        try:
            page = int(rec.get("source_page") or 1)
        except (TypeError, ValueError):
            page = 1

        records.append({
            "source_document": source_document,
            "source_page": page,
            "fields": fields,
            "warnings": warnings
        })

    return {**base, "total_records": len(records), "records": records}


def extract_for_documents(pages_by_document: Dict[str, List[Dict[str, Any]]], schema_name: str,
                          module_id: Optional[str] = None,
                          on_progress: Optional[Callable[[int, int, str, Optional[str]], None]] = None) -> Dict[str, Any]:
    """One call per document: keeps page numbers unambiguous; one failing file never stops the batch.

    `on_progress(done, total, document, error_or_None)` (optional) is called after each document, from the calling thread.
    """
    merged: Dict[str, Any] = {"schema": schema_name, "module_id": module_id, "records": [], "errors": {}}
    total = len(pages_by_document)
    for done, (doc_name, pages) in enumerate(pages_by_document.items(), start=1):
        err: Optional[str] = None
        try:
            res = extract_structured_data(pages, schema_name, module_id, source_document=doc_name)
            merged["module_id"] = res["module_id"]
            merged["records"].extend(res["records"])
        except Exception as e:
            err = str(e)
            merged["errors"][doc_name] = err
        if on_progress:
            on_progress(done, total, doc_name, err)

    merged["total_records"] = len(merged["records"])
    return merged
