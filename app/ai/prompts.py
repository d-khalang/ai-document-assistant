import os
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Optional, Tuple
from app.extraction.registry import SchemaDef, resolve_schema


@dataclass(frozen=True)
class ChatStructuredContext:
    """کانتکست ساختاریافته چت: متن داده‌ها (DOCUMENT CONTEXT) و راهنمای دامنه (دستورالعمل) به‌صورت جدا."""
    text: str = ""
    guidelines: Tuple[str, ...] = ()


def build_document_structured_context(schema: Optional[SchemaDef], records: Optional[List[Any]]) -> str:
    """
    ساخت کانتکست ساختاریافته از داده‌ها و متادیتای استخراج‌شده/محاسبه‌شده سند.
    این تابع کاملاً پویا بوده و از روی فیلدهای تعریف‌شده در schema.fields و schema.computed حرکت می‌کند.
    برای مقادیر محاسبه‌شده ترجیحاً raw_value (حاوی توضیحات قانون و ماه‌ها) و برای سایر فیلدها normalized_value
    یا raw_value را به همراه برچسب رسمی و وضعیت فیلد قالب‌بندی می‌کند.
    در صورت نبود رکورد یا خالی بودن فیلدها، رشته خالی بازمی‌گرداند.
    """
    if not records or not isinstance(records, list):
        return ""
    if not schema or not getattr(schema, "fields", None):
        return ""

    lines = ["--- DATI ESTRATTI E METADATI DEL DOCUMENTO ---"]
    item_count = 0

    for idx, rec in enumerate(records):
        fields = rec.get("fields") if (isinstance(rec, dict) and isinstance(rec.get("fields"), dict)) else rec
        if not isinstance(fields, dict):
            continue

        if len(records) > 1:
            doc_info = rec.get("source_document") if isinstance(rec, dict) else None
            page_info = rec.get("source_page") if isinstance(rec, dict) else None
            suffix = []
            if doc_info:
                suffix.append(str(doc_info))
            if page_info:
                suffix.append(f"pag. {page_info}")
            tag = f" — {', '.join(suffix)}" if suffix else ""
            lines.append(f"[Record {idx + 1}{tag}]")

        # پیمایش کاملاً پویا بر اساس فیلدهای تعریف‌شده در schema.fields
        for fname, fdef in schema.fields.items():
            fdata = fields.get(fname)
            if fdata is None:
                continue

            if isinstance(fdata, dict):
                status = fdata.get("status") or "EXTRACTED"
                if status == "MISSING":
                    continue
                raw_val = fdata.get("raw_value")
                norm_val = fdata.get("normalized_value")
                if status == "CALCULATED" and raw_val:
                    val = raw_val
                elif raw_val and "(" in str(raw_val):
                    val = raw_val
                elif norm_val is not None and str(norm_val).strip() != "":
                    val = norm_val
                elif raw_val is not None and str(raw_val).strip() != "":
                    val = raw_val
                else:
                    val = None
            else:
                val = fdata
                status = "EXTRACTED"

            if val is None or str(val).strip() == "" or str(val).strip().lower() in ("null", "none"):
                continue

            label = fdef.label if fdef and hasattr(fdef, "label") and fdef.label else fname
            lines.append(f"• {label}: {str(val).strip()} (Stato: {status})")
            item_count += 1

        # پشتیبانی از فیلدهای محاسباتی تعریف‌شده در schema.computed
        if hasattr(schema, "computed") and schema.computed:
            for cname, cdef in schema.computed.items():
                cdata = fields.get(cname)
                if cdata is None:
                    continue

                if isinstance(cdata, dict):
                    status = cdata.get("status") or "CALCULATED"
                    if status == "MISSING":
                        continue
                    raw_val = cdata.get("raw_value")
                    norm_val = cdata.get("normalized_value")
                    val = raw_val if (raw_val is not None and str(raw_val).strip() != "") else norm_val
                else:
                    val = cdata
                    status = "CALCULATED"

                if val is None or str(val).strip() == "" or str(val).strip().lower() in ("null", "none"):
                    continue

                clabel = cdef.label if cdef and hasattr(cdef, "label") and cdef.label else cname
                lines.append(f"• {clabel}: {str(val).strip()} (Stato: {status})")
                item_count += 1

    if item_count == 0:
        return ""

    lines.append("-----------------------------------------------")
    return "\n".join(lines)


def _is_active_document(source_document: Any, active_documents: set) -> bool:
    src = str(source_document or "").strip()
    return any(src == a or os.path.basename(src) == os.path.basename(a) for a in active_documents)


def build_chat_structured_context(
    payload: Optional[Dict[str, Dict[str, Any]]],
    active_documents: Optional[Iterable[str]] = None
) -> ChatStructuredContext:
    """
    تابع خالص: ساخت کانتکست ساختاریافته چت از payload رکوردها (خروجی collect_payload).
    فقط رکوردهای اسناد فعال لحاظ می‌شوند (اگر لیست اسناد فعال خالی باشد، همه رکوردها).
    راهنماهای دامنه فقط از schema.chat_guidelines اسکیماهایی جمع می‌شوند که واقعاً در کانتکست حضور دارند.
    اسکیماهای ناشناخته (مثلاً پس از Hot Reload) نادیده گرفته می‌شوند.
    """
    active = {str(a).strip() for a in (active_documents or [])}
    blocks: List[str] = []
    guidelines: List[str] = []

    for mid, schemas in (payload or {}).items():
        for sname, sdata in (schemas or {}).items():
            recs = (sdata or {}).get("records") or []
            if active:
                recs = [r for r in recs if isinstance(r, dict) and _is_active_document(r.get("source_document"), active)]
            if not recs:
                continue
            try:
                schema = resolve_schema(sname, mid)
            except ValueError:
                continue
            block = build_document_structured_context(schema, recs)
            if not block:
                continue
            blocks.append(block)
            for g in schema.chat_guidelines:
                if g not in guidelines:
                    guidelines.append(g)

    return ChatStructuredContext("\n\n".join(blocks), tuple(guidelines))


def build_rag_prompt(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    structured_context: str = "",
    domain_guidelines: Optional[Iterable[str]] = None
) -> str:
    """
    ساخت پرامپت مهندسی‌شده RAG با تفکیک دقیق دستورالعمل، زمینه سند، و سوال کاربر.
    شامل قانون اکید عدم حدس زدن، شفافیت منشأ داده‌ها (Provenance) و پشتیبانی از متادیتای ساختاریافته.
    متن‌های اختصاصی دامنه فقط از طریق domain_guidelines (schemas/*.json → chat.guidelines) وارد می‌شوند.
    """
    context_parts = []
    if structured_context and structured_context.strip():
        context_parts.append(structured_context.strip())

    if retrieved_chunks:
        context_blocks = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            meta = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
            page_num = chunk.get("page_number") or meta.get("page_number") or "N/A"
            doc_name = chunk.get("document_name") or meta.get("document_name")

            header = f"Source {i} | Page: {page_num}"
            if doc_name and doc_name != "unknown":
                header += f" | Doc: {doc_name}"

            block = (
                f"[{header}]:\n"
                f"{chunk.get('text', '').strip()}"
            )
            context_blocks.append(block)
        context_parts.append("\n\n".join(context_blocks))
    elif not context_parts:
        context_parts.append("No relevant context found in the uploaded document.")

    context_str = "\n\n".join(context_parts)

    guideline_lines = [f"- {g.strip()}" for g in (domain_guidelines or []) if g and g.strip()]
    domain_section = (
        "\nLINEE GUIDA SPECIFICHE DEL DOMINIO:\n" + "\n".join(guideline_lines) + "\n"
        if guideline_lines else ""
    )

    prompt = f"""You are a helpful and precise AI Document Assistant.
Your task is to answer the user's question STRICTLY based on the provided document context below.

CRITICAL INSTRUCTIONS:
1. Answer using ONLY facts directly mentioned in the document context.
2. If the document context does not contain enough information to answer the question, clearly state:
   "The uploaded document does not provide enough information to answer this question."
3. Do NOT make assumptions, extrapolate, or fabricate information.
4. Mention the relevant page number(s) if applicable when referencing facts.

REGOLE DI TRASPARENZA SULLA PROVENIENZA DEI DATI:
- Se l'informazione richiesta deriva da un campo contrassegnato con '(Stato: CALCULATED)', specifica esplicitamente all'utente che il dato (es. data di scadenza, validità o calcolo) NON è stampato testualmente sul documento, ma è stato calcolato deterministicamente dal sistema applicando le normative di settore vigenti e le regole configurate per la tipologia di documento.
- Se l'informazione è contrassegnata con '(Stato: EXTRACTED)', indicala come dato testuale presente nel documento.
- Se l'informazione è contrassegnata con '(Stato: EDITED)', indicala come dato verificato o corretto manualmente da un operatore.
{domain_section}
---
DOCUMENT CONTEXT:
{context_str}
---

USER QUESTION:
{query}

ANSWER:"""

    return prompt
