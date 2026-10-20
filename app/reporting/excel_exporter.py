import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.reporting.common import (
    resolve_scope,
    report_meta,
    column_plan,
    cell_value,
    sheet_title_for,
    COLUMN_LABELS
)


def create_styled_excel_report(
    extracted_data_by_schema: Dict[str, Any],
    source_documents: List[str],
    company_profile: Optional[Dict[str, Any]] = None,
    selected_fields_by_schema: Optional[Dict[str, List[str]]] = None,
    module_id: Optional[str] = None
) -> bytes:
    """
    تولید فایل اکسل تجاری با تفکیک قطعی ماژول (Scoped Reporting).
    """
    # ۱. اعمال فیلتر اسکوپ: فقط اسکیماهای مرتبط با ماژول جاری باقی می‌مانند
    module, scoped_data = resolve_scope(extracted_data_by_schema, module_id)
    meta = report_meta(module)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    comp = company_profile or {}
    comp_name = comp.get("company_name", "AZIENDA")
    vat_number = comp.get("vat_number", "")
    address = comp.get("address", "")

    header_fill = PatternFill(start_color="1E4D2B", end_color="1E4D2B", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    meta_font = Font(name="Segoe UI", size=10, italic=True, color="555555")
    calculated_fill = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
    edited_fill = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")
    
    thin_border = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC")
    )

    # شیت ۱: خلاصه ممیزی (Audit Summary)
    ws_summary = wb.create_sheet(title="RIEPILOGO_GENERALE")
    ws_summary.views.sheetView[0].showGridLines = True

    workbook_title = meta.get("workbook_title", "REPORT DOCUMENT INTELLIGENCE")
    ws_summary["A1"] = f"{workbook_title} — {comp_name.upper()}" if comp_name else workbook_title
    ws_summary["A1"].font = Font(name="Segoe UI", size=13, bold=True, color="1E4D2B")
    
    sub_parts = []
    if vat_number:
        sub_parts.append(f"P.IVA / C.F.: {vat_number}")
    if address:
        sub_parts.append(f"Sede: {address}")
    ws_summary["A2"] = " | ".join(sub_parts)
    ws_summary["A2"].font = meta_font
    
    ws_summary["A3"] = f"Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws_summary["A3"].font = meta_font

    ws_summary["A5"] = "Documenti Sorgente Inclusi:"
    ws_summary["A5"].font = Font(name="Segoe UI", size=11, bold=True)
    
    row_idx = 6
    for doc in source_documents:
        ws_summary[f"A{row_idx}"] = f"• {doc}"
        ws_summary[f"A{row_idx}"].font = data_font
        row_idx += 1

    row_idx += 1
    ws_summary[f"A{row_idx}"] = "Riepilogo Schemi Estratti:"
    ws_summary[f"A{row_idx}"].font = Font(name="Segoe UI", size=11, bold=True)
    row_idx += 1

    sum_headers = ["Schema Dati", "Totale Record", "Stato Estrazione", "Foglio Dedicato"]
    for col_i, h_text in enumerate(sum_headers, start=1):
        cell = ws_summary.cell(row=row_idx, column=col_i, value=h_text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_idx += 1
    for schema_name, data in scoped_data.items():
        recs = data.get("records", [])
        schema_obj = module.schemas.get(schema_name) if module else None
        dedicated_sheet = sheet_title_for(schema_obj, schema_name, schema_name.upper())[:31]
        
        # محاسبه واقعی وضعیت بر اساس داده‌ها
        has_uncertain = any("uncertain_required" in str(r.get("warnings", [])) for r in recs)
        has_edited = any(f.get("status") == "EDITED" for r in recs for f in r.get("fields", {}).values())
        
        if has_uncertain:
            status_desc = "Da verificare"
        elif has_edited:
            status_desc = "Verificato (Modificato)"
        else:
            status_desc = "Completato"

        ws_summary.cell(row=row_idx, column=1, value=schema_name.upper()).font = data_font
        ws_summary.cell(row=row_idx, column=2, value=len(recs)).font = data_font
        ws_summary.cell(row=row_idx, column=3, value=status_desc).font = data_font
        ws_summary.cell(row=row_idx, column=4, value=dedicated_sheet).font = data_font
        row_idx += 1

    # شیت‌های اختصاصی برای اسکیماهای معتبر
    for schema_name, data in scoped_data.items():
        schema_obj = module.schemas.get(schema_name) if module else None
        sheet_title = sheet_title_for(schema_obj, schema_name, schema_name.upper())[:31]
        long_fields = {s["field"] for s in (schema_obj.word_sections if schema_obj else [])}
        ws = wb.create_sheet(title=sheet_title)
        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"

        records = data.get("records", [])
        if not records:
            ws.cell(row=1, column=1, value="Nessun dato estratto per questo schema.").font = meta_font
            continue

        user_selected = (selected_fields_by_schema or {}).get(schema_name)
        col_plan = column_plan(schema_name, module, records, user_selected)

        # ساخت ستون‌های جدول
        headers = ["Documento Fonte", "Pagina Fonte"] + [col[1] for col in col_plan] + ["Stato Estrazione"]

        for col_i, h_name in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_i, value=h_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for r_idx, record in enumerate(records, start=2):
            src_doc = record.get("source_document") or "-"
            src_page = record.get("source_page", 1)
            fields = record.get("fields", {})

            # Documento Fonte
            d_cell = ws.cell(row=r_idx, column=1, value=src_doc)
            d_cell.font = data_font
            d_cell.border = thin_border

            # Pagina Fonte
            p_cell = ws.cell(row=r_idx, column=2, value=f"Pagina {src_page}")
            p_cell.font = meta_font
            p_cell.alignment = Alignment(horizontal="center")
            p_cell.border = thin_border

            row_status = "EXTRACTED"
            for c_idx, (fname, flabel) in enumerate(col_plan, start=3):
                fdata = fields.get(fname, {})
                f_status = fdata.get("status", "EXTRACTED")
                val_to_write = cell_value(fdata)

                if f_status == "EDITED":
                    row_status = "EDITED"
                elif f_status == "CALCULATED" and row_status != "EDITED":
                    row_status = "CALCULATED"

                cell = ws.cell(row=r_idx, column=c_idx, value=val_to_write)
                cell.font = data_font
                cell.border = thin_border

                if f_status == "CALCULATED":
                    cell.fill = calculated_fill
                elif f_status == "EDITED":
                    cell.fill = edited_fill

                if fname in long_fields:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                elif any(k in fname for k in ["data", "scadenza", "targa", "periodo"]):
                    cell.alignment = Alignment(horizontal="center")

            st_cell = ws.cell(row=r_idx, column=len(headers), value=row_status)
            color_map = {"EXTRACTED": "2E7D32", "CALCULATED": "1565C0", "EDITED": "E65100"}
            st_cell.font = Font(name="Segoe UI", size=9, bold=True, color=color_map.get(row_status, "2E7D32"))
            st_cell.alignment = Alignment(horizontal="center")
            st_cell.border = thin_border

    # تنظیم عرض ستون‌ها به صورت پویا
    for ws_item in wb.worksheets:
        for col in ws_item.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws_item.column_dimensions[col_letter].width = min(max(max_len + 4, 15), 60)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()