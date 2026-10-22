from typing import List, Dict, Any, Optional
from app.extraction.registry import SchemaDef


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


def build_rag_prompt(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    structured_context: str = ""
) -> str:
    """
    ساخت پرامپت مهندسی‌شده RAG با تفکیک دقیق دستورالعمل، زمینه سند، و سوال کاربر.
    شامل قانون اکید عدم حدس زدن، شفافیت منشأ داده‌ها (Provenance) و پشتیبانی از متادیتای ساختاریافته.
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

    prompt = f"""You are a helpful and precise AI Document Assistant.
Your task is to answer the user's question STRICTLY based on the provided document context below.

CRITICAL INSTRUCTIONS:
1. Answer using ONLY facts directly mentioned in the document context.
2. If the document context does not contain enough information to answer the question, clearly state:
   "The uploaded document does not provide enough information to answer this question."
3. Do NOT make assumptions, extrapolate, or fabricate information.
4. Mention the relevant page number(s) if applicable when referencing facts.

REGOLE DI TRASPARENZA SULLA PROVENIENZA DEI DATI:
- Se l'informazione richiesta deriva da un campo contrassegnato con '(Stato: CALCULATED)', specifica esplicitamente all'utente che il dato (es. data di scadenza, validità o calcolo) NON è stampato testualmente sul documento, ma è stato calcolato deterministicamente dal sistema applicando le normative di settore vigenti e la periodicità prevista per la tipologia di corso/atto.
- Se l'informazione è contrassegnata con '(Stato: EXTRACTED)', indicala come dato testuale presente nel documento.
- Se un corso risulta senza scadenza (es. formazione generale con credito permanente), chiarisci che per legge la formazione non è soggetta ad aggiornamento periodico.

---
DOCUMENT CONTEXT:
{context_str}
---

USER QUESTION:
{query}

ANSWER:"""

    return prompt
