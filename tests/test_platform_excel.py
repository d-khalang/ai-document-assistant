import io
import openpyxl
import pytest
from app.reporting.platform_excel_exporter import create_platform_excel_report


@pytest.mark.offline
def test_platform_excel_4_sheets_structure():
    sample_docs = [{"filename": "bolletta_test.pdf"}]
    sample_extracted_all = {
        "energy_utility": {
            "energy_bill": {
                "records": [{
                    "source_document": "bolletta_test.pdf",
                    "source_page": 1,
                    "fields": {
                        "codice_pod": {"raw_value": "IT001E123", "normalized_value": "IT001E123", "status": "EXTRACTED"},
                        "consumo_kwh": {"raw_value": "1000", "normalized_value": 1000.0, "status": "EXTRACTED"},
                        "data_scadenza": {"raw_value": "2026-11-30", "normalized_value": "2026-11-30", "status": "EXTRACTED"}
                    }
                }]
            }
        }
    }
    company_prof = {"company_name": "Studio & Impresa S.r.l.", "address": "Torino"}

    excel_bytes = create_platform_excel_report(
        documents=sample_docs,
        extracted_data_all_modules=sample_extracted_all,
        company_profile=company_prof
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Dashboard & KPI" in wb.sheetnames
    assert "Registro Documenti" in wb.sheetnames
    assert "Scadenze & Azioni" in wb.sheetnames
    assert "Dati Energy Bill" in wb.sheetnames