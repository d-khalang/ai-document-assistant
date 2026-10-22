import pytest
from app.extraction.registry import resolve_schema, reload_registry
from app.extraction.extractor import finalize_record
from app.ai.prompts import (
    ChatStructuredContext,
    build_chat_structured_context,
    build_document_structured_context,
    build_rag_prompt,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    reload_registry()


@pytest.mark.offline
def test_build_document_structured_context_extracted_and_calculated():
    schema = resolve_schema("training_certificate", "hr_training")
    assert schema is not None

    record = {
        "source_document": "attestato_preposto_mario_rossi.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {
                "raw_value": "Mario Rossi",
                "normalized_value": "Mario Rossi",
                "status": "EXTRACTED",
            },
            "titolo_corso": {
                "raw_value": "Corso di formazione per Preposti",
                "normalized_value": "Corso di formazione per Preposti",
                "status": "EXTRACTED",
            },
            "data_emissione": {
                "raw_value": "2024-05-15",
                "normalized_value": "2024-05-15",
                "status": "EXTRACTED",
            },
            "data_scadenza": {
                "raw_value": "2026-05-15 (24 mesi · preposto)",
                "normalized_value": "2026-05-15",
                "status": "CALCULATED",
            },
        },
    }

    context = build_document_structured_context(schema, [record])

    # Header and footer verification
    assert "--- DATI ESTRATTI E METADATI DEL DOCUMENTO ---" in context
    assert "-----------------------------------------------" in context

    # EXTRACTED field check
    assert "• Dipendente / Lavoratore: Mario Rossi (Stato: EXTRACTED)" in context
    assert "• Data Rilascio Attestato: 2024-05-15 (Stato: EXTRACTED)" in context

    # CALCULATED field check (must contain the 24 months, preposto rule id and CALCULATED status)
    assert "• Data Scadenza / Rinnovo: 2026-05-15 (24 mesi · preposto) (Stato: CALCULATED)" in context


@pytest.mark.offline
def test_build_document_structured_context_with_live_calculation():
    schema = resolve_schema("training_certificate", "hr_training")

    # A record before calculation
    record = {
        "source_document": "attestato_carrello.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {"normalized_value": "Giulia Neri", "status": "EXTRACTED"},
            "titolo_corso": {"normalized_value": "Abilitazione Guida Carrelli Elevatori", "status": "EXTRACTED"},
            "ruolo_corso": {"normalized_value": "Carrellista", "status": "EXTRACTED"},
            "data_emissione": {"normalized_value": "2024-02-29", "status": "EXTRACTED"},
            "data_scadenza": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        },
    }

    # Step A: Perform deterministic calculation
    finalize_record(schema, record["fields"])
    assert record["fields"]["data_scadenza"]["status"] == "CALCULATED"
    assert "60 mesi · attrezzature" in record["fields"]["data_scadenza"]["raw_value"]

    # Step B: Build structured context
    context = build_document_structured_context(schema, [record])

    assert "• Dipendente / Lavoratore: Giulia Neri (Stato: EXTRACTED)" in context
    assert "• Data Scadenza / Rinnovo: 2029-02-28 (60 mesi · attrezzature) (Stato: CALCULATED)" in context


@pytest.mark.offline
def test_build_document_structured_context_empty_and_edge_cases():
    schema = resolve_schema("training_certificate", "hr_training")

    # 1. Empty records list
    assert build_document_structured_context(schema, []) == ""
    assert build_document_structured_context(schema, None) == ""

    # 2. None schema
    assert build_document_structured_context(None, [{"fields": {}}]) == ""

    # 3. Record with only MISSING or empty fields
    record_missing = {
        "fields": {
            "nominativo_dipendente": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
            "titolo_corso": {"raw_value": "", "normalized_value": "", "status": "MISSING"},
        }
    }
    assert build_document_structured_context(schema, [record_missing]) == ""


@pytest.mark.offline
def test_build_document_structured_context_multiple_records():
    schema = resolve_schema("training_certificate", "hr_training")

    records = [
        {
            "source_document": "doc1.pdf",
            "source_page": 1,
            "fields": {
                "nominativo_dipendente": {"normalized_value": "Dipendente 1", "status": "EXTRACTED"},
            },
        },
        {
            "source_document": "doc2.pdf",
            "source_page": 2,
            "fields": {
                "nominativo_dipendente": {"normalized_value": "Dipendente 2", "status": "EXTRACTED"},
            },
        },
    ]

    context = build_document_structured_context(schema, records)
    assert "[Record 1 — doc1.pdf, pag. 1]" in context
    assert "[Record 2 — doc2.pdf, pag. 2]" in context
    assert "• Dipendente / Lavoratore: Dipendente 1 (Stato: EXTRACTED)" in context
    assert "• Dipendente / Lavoratore: Dipendente 2 (Stato: EXTRACTED)" in context


@pytest.mark.offline
def test_build_rag_prompt_with_structured_context_and_provenance_rules():
    schema = resolve_schema("training_certificate", "hr_training")
    record = {
        "source_document": "attestato_mario_rossi.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {"normalized_value": "Mario Rossi", "status": "EXTRACTED"},
            "titolo_corso": {"normalized_value": "Corso Preposti", "status": "EXTRACTED"},
            "data_emissione": {"normalized_value": "2024-05-15", "status": "EXTRACTED"},
            "data_scadenza": {
                "raw_value": "2026-05-15 (24 mesi · preposto)",
                "normalized_value": "2026-05-15",
                "status": "CALCULATED",
            },
        },
    }
    struct_ctx = build_document_structured_context(schema, [record])
    chunks = [
        {
            "text": "Si attesta che Mario Rossi ha superato la prova finale del corso.",
            "page_number": 1,
            "document_name": "attestato_mario_rossi.pdf",
        }
    ]

    prompt = build_rag_prompt("Qual è la data di scadenza del corso?", chunks, structured_context=struct_ctx)

    # 1. Structured context block is present in prompt
    assert "--- DATI ESTRATTI E METADATI DEL DOCUMENTO ---" in prompt
    assert "• Data Scadenza / Rinnovo: 2026-05-15 (24 mesi · preposto) (Stato: CALCULATED)" in prompt

    # 2. Structured context is positioned before chunks
    struct_pos = prompt.find("--- DATI ESTRATTI E METADATI DEL DOCUMENTO ---")
    chunk_pos = prompt.find("Si attesta che Mario Rossi ha superato la prova finale del corso.")
    assert struct_pos != -1
    assert chunk_pos != -1
    assert struct_pos < chunk_pos

    # 3. Provenance guidelines are present in prompt
    assert "REGOLE DI TRASPARENZA SULLA PROVENIENZA DEI DATI:" in prompt
    assert "(Stato: CALCULATED)" in prompt
    assert "calcolato deterministicamente dal sistema applicando le normative di settore vigenti" in prompt
    assert "(Stato: EXTRACTED)" in prompt

    # 4. Generic prompt carries no domain-specific wording
    assert "LINEE GUIDA SPECIFICHE DEL DOMINIO:" not in prompt
    assert "Se un corso risulta senza scadenza" not in prompt

    # 5. Domain guidelines come from the schema (chat.guidelines) and sit before DOCUMENT CONTEXT
    guided = build_rag_prompt("Qual è la data di scadenza del corso?", chunks,
                              structured_context=struct_ctx, domain_guidelines=schema.chat_guidelines)
    assert "LINEE GUIDA SPECIFICHE DEL DOMINIO:" in guided
    assert "Se un corso risulta senza scadenza" in guided
    assert "non è soggetta ad aggiornamento periodico" in guided
    assert guided.find("LINEE GUIDA SPECIFICHE DEL DOMINIO:") < guided.find("DOCUMENT CONTEXT:")

    # 6. Backward compatibility without structured_context
    simple_prompt = build_rag_prompt("Qual è il nome?", chunks)
    assert "REGOLE DI TRASPARENZA SULLA PROVENIENZA DEI DATI:" in simple_prompt
    assert "Si attesta che Mario Rossi ha superato la prova finale del corso." in simple_prompt


def _rec(doc, name, page=1):
    return {
        "source_document": doc,
        "source_page": page,
        "fields": {"nominativo_dipendente": {"normalized_value": name, "status": "EXTRACTED"}},
    }


@pytest.mark.offline
def test_build_chat_structured_context_filters_active_documents_and_collects_guidelines():
    payload = {
        "hr_training": {"training_certificate": {"records": [
            _rec("attestato_a.pdf", "Anna Bianchi"),
            _rec("C:/uploads/attestato_b.pdf", "Bruno Verdi"),   # basename match
            _rec("rimosso.pdf", "Carlo Neri"),                   # not active
        ]}},
        "iso_14001": {"personnel_training": {"records": [
            _rec("attestato_a.pdf", "Anna Bianchi"),
        ]}},
    }
    ctx = build_chat_structured_context(payload, ["attestato_a.pdf", "attestato_b.pdf"])

    assert isinstance(ctx, ChatStructuredContext)
    assert "Anna Bianchi" in ctx.text
    assert "Bruno Verdi" in ctx.text
    assert "Carlo Neri" not in ctx.text
    assert ctx.text.count("--- DATI ESTRATTI E METADATI DEL DOCUMENTO ---") == 2
    # Same guideline declared by both schemas is deduplicated
    assert len(ctx.guidelines) == 1
    assert "Se un corso risulta senza scadenza" in ctx.guidelines[0]


@pytest.mark.offline
def test_build_chat_structured_context_edge_cases():
    # Empty / missing payload
    assert build_chat_structured_context(None) == ChatStructuredContext()
    assert build_chat_structured_context({}, ["x.pdf"]) == ChatStructuredContext()

    # No active documents -> all records are used
    payload = {"hr_training": {"training_certificate": {"records": [_rec("x.pdf", "Dario Gialli")]}}}
    assert "Dario Gialli" in build_chat_structured_context(payload, []).text

    # Active filter excludes everything -> empty context and no guidelines
    assert build_chat_structured_context(payload, ["altro.pdf"]) == ChatStructuredContext()

    # Schema without chat.guidelines contributes data but no guidelines
    energy = {"energy_utility": {"energy_bill": {"records": [{
        "source_document": "bolletta.pdf", "source_page": 1,
        "fields": {"fornitore": {"normalized_value": "eVISO", "status": "EXTRACTED"}},
    }]}}}
    ctx = build_chat_structured_context(energy, ["bolletta.pdf"])
    assert "eVISO" in ctx.text
    assert ctx.guidelines == ()

    # Unknown module/schema (e.g. removed after hot reload) is skipped, not raised
    ghost = {"ghost_module": {"ghost_schema": {"records": [_rec("x.pdf", "Ezio")]}}}
    assert build_chat_structured_context(ghost, ["x.pdf"]) == ChatStructuredContext()


