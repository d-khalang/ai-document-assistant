import pytest
from app.extraction.registry import resolve_schema, reload_registry, _parse_schema
from app.extraction.extractor import finalize_record
from app.alerts.deadlines import extract_deadlines_from_records


@pytest.fixture(autouse=True)
def fresh_registry():
    reload_registry()


@pytest.mark.offline
def test_training_expiry_rules_and_leap_year():
    schema = resolve_schema("personnel_training", "iso_14001")

    # 1. Preposto (24 months = 2 years)
    f_prep = {
        "data_emissione": {"normalized_value": "2023-04-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Formazione per Preposti alla sicurezza", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Preposto", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Marco Gialli", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_prep)
    assert f_prep["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert f_prep["data_scadenza_rinnovo"]["normalized_value"] == "2025-04-10"
    assert "24 mesi · preposto" in f_prep["data_scadenza_rinnovo"]["raw_value"]

    # 2. Dirigente (60 months = 5 years)
    f_dir = {
        "data_emissione": {"normalized_value": "2021-06-01", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Corso di formazione per dirigenti", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Dirigente", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Elena Bruni", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_dir)
    assert f_dir["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert f_dir["data_scadenza_rinnovo"]["normalized_value"] == "2026-06-01"
    assert "60 mesi · dirigente" in f_dir["data_scadenza_rinnovo"]["raw_value"]

    # 3. Carrelli elevatori / PLE (60 months = 5 years, leap-year 2024-02-29 -> 2029-02-28)
    f_carr = {
        "data_emissione": {"normalized_value": "2024-02-29", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Abilitazione uso carrelli elevatori semoventi (PLE)", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Carrellista", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Mario Rossi", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_carr)
    assert f_carr["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert f_carr["data_scadenza_rinnovo"]["normalized_value"] == "2029-02-28"
    assert "60 mesi · attrezzature" in f_carr["data_scadenza_rinnovo"]["raw_value"]

    # 4. Primo soccorso (36 months = 3 years)
    f_ps = {
        "data_emissione": {"normalized_value": "2022-09-15", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Aggiornamento Addetti al Primo Soccorso Aziendale", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Addetto Primo Soccorso", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Luca Bianchi", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_ps)
    assert f_ps["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert f_ps["data_scadenza_rinnovo"]["normalized_value"] == "2025-09-15"
    assert "36 mesi · primo_soccorso" in f_ps["data_scadenza_rinnovo"]["raw_value"]

    # 5. Formazione Generale (no expiry -> months: null, remains MISSING)
    f_gen = {
        "data_emissione": {"normalized_value": "2024-01-15", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Corso di formazione generale dei lavoratori (D.Lgs. 81/08)", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Lavoratore", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Paolo Neri", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_gen)
    assert f_gen["data_scadenza_rinnovo"]["status"] == "MISSING"
    assert f_gen["data_scadenza_rinnovo"]["normalized_value"] is None


@pytest.mark.offline
def test_training_expiry_preserves_extracted_and_edited():
    schema = resolve_schema("personnel_training", "iso_14001")

    # EXTRACTED value must never be overwritten by derived_dates
    f_extracted = {
        "data_emissione": {"normalized_value": "2023-05-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Preposto alla sicurezza", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"normalized_value": "2027-10-31", "raw_value": "31/10/2027", "status": "EXTRACTED"},
        "nominativo_dipendente": {"normalized_value": "Anna Verdi", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_extracted)
    assert f_extracted["data_scadenza_rinnovo"]["status"] == "EXTRACTED"
    assert f_extracted["data_scadenza_rinnovo"]["normalized_value"] == "2027-10-31"

    # EDITED value must never be overwritten by derived_dates
    f_edited = {
        "data_emissione": {"normalized_value": "2023-05-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Preposto alla sicurezza", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"normalized_value": "2026-01-01", "raw_value": "01/01/2026", "status": "EDITED"},
        "nominativo_dipendente": {"normalized_value": "Anna Verdi", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_edited)
    assert f_edited["data_scadenza_rinnovo"]["status"] == "EDITED"
    assert f_edited["data_scadenza_rinnovo"]["normalized_value"] == "2026-01-01"


@pytest.mark.offline
def test_training_expiry_integration_with_deadline_alerts():
    schema = resolve_schema("personnel_training", "iso_14001")

    record = {
        "source_document": "attestato_carrello_2024.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {"normalized_value": "Mario Rossi", "status": "EXTRACTED"},
            "corso_descrizione": {"normalized_value": "Corso Carrellisti e Conduzione Muletto", "status": "EXTRACTED"},
            "ruolo_corso": {"normalized_value": "Carrellista", "status": "EXTRACTED"},
            "riferimento_normativo": {"normalized_value": "art 73 D.Lgs 81/08", "status": "EXTRACTED"},
            "data_emissione": {"normalized_value": "2024-02-29", "status": "EXTRACTED"},
            "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        }
    }

    # Step A: Run deterministic calculation on the record
    finalize_record(schema, record["fields"])
    assert record["fields"]["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert record["fields"]["data_scadenza_rinnovo"]["normalized_value"] == "2029-02-28"

    # Step B: Pass calculated record to the deadline extraction engine
    deadlines = extract_deadlines_from_records("iso_14001", "personnel_training", [record])
    assert len(deadlines) == 1

    dl = deadlines[0]
    assert dl["module_id"] == "iso_14001"
    assert dl["schema_name"] == "personnel_training"
    assert dl["field_name"] == "data_scadenza_rinnovo"
    assert dl["due_date"] == "2029-02-28"
    assert dl["description"] == "Mario Rossi — Corso Carrellisti e Conduzione Muletto"
    assert dl["thresholds"] == [60, 30, 15]
    assert dl["source_document"] == "attestato_carrello_2024.pdf"
    assert dl["source_page"] == 1
    assert len(dl["id"]) == 36  # Valid UUID5


@pytest.mark.offline
def test_training_expiry_edge_cases_and_warnings():
    schema = resolve_schema("personnel_training", "iso_14001")

    # 1. Base date missing -> target remains MISSING, no crash
    f_nobase = {
        "data_emissione": {"normalized_value": None, "status": "MISSING"},
        "corso_descrizione": {"normalized_value": "Corso Carrellisti", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Test", "status": "EXTRACTED"},
    }
    finalize_record(schema, f_nobase)
    assert f_nobase["data_scadenza_rinnovo"]["status"] == "MISSING"

    # 2. No matching rule and no default -> warning "derived_no_rule:data_scadenza_rinnovo"
    f_norule = {
        "data_emissione": {"normalized_value": "2024-01-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Seminario sconosciuto di archeologia", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": None, "status": "MISSING"},
        "riferimento_normativo": {"normalized_value": None, "status": "MISSING"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Test", "status": "EXTRACTED"},
    }
    warns_norule = finalize_record(schema, f_norule)
    assert f_norule["data_scadenza_rinnovo"]["status"] == "MISSING"
    assert "derived_no_rule:data_scadenza_rinnovo" in warns_norule

    # 3. Ambiguous conflict at same priority -> warning "derived_ambiguous:data_scadenza"
    ambiguous_schema = _parse_schema("test_mod", "test_schema", {
        "fields": {
            "title": {"type": "string", "label": "Title"},
            "issue_date": {"type": "date", "label": "Issue Date"},
            "expiry_date": {"type": "date", "label": "Expiry Date"},
        },
        "derived_dates": {
            "expiry_date": {
                "base_field": "issue_date",
                "text_fields": ["title"],
                "rules": [
                    {"id": "rule_a", "keywords": ["conflict"], "months": 12, "priority": 10},
                    {"id": "rule_b", "keywords": ["conflict"], "months": 24, "priority": 10},
                ]
            }
        }
    }, "dummy.json")

    f_ambig = {
        "issue_date": {"normalized_value": "2024-01-01", "status": "EXTRACTED"},
        "title": {"normalized_value": "Corso conflict aziendale", "status": "EXTRACTED"},
        "expiry_date": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
    }
    warns_ambig = finalize_record(ambiguous_schema, f_ambig)
    assert f_ambig["expiry_date"]["status"] == "MISSING"
    assert "derived_ambiguous:expiry_date" in warns_ambig


@pytest.mark.offline
def test_hr_training_certificate_schema_derived_dates():
    schema = resolve_schema("training_certificate", "hr_training")
    assert schema is not None
    assert schema.sheet_title == "Attestati Formazione"

    record = {
        "source_document": "attestato_preposto.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {"normalized_value": "Giulia Neri", "status": "EXTRACTED"},
            "titolo_corso": {"normalized_value": "Corso di Aggiornamento per la figura del Preposto", "status": "EXTRACTED"},
            "ruolo_corso": {"normalized_value": "Preposto alla sicurezza", "status": "EXTRACTED"},
            "data_emissione": {"normalized_value": "2024-05-15", "status": "EXTRACTED"},
            "data_scadenza": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        }
    }

    # Step A: Deterministic derived date calculation
    finalize_record(schema, record["fields"])
    assert record["fields"]["data_scadenza"]["status"] == "CALCULATED"
    assert record["fields"]["data_scadenza"]["normalized_value"] == "2026-05-15"
    assert "24 mesi · preposto" in record["fields"]["data_scadenza"]["raw_value"]

    # Step B: Deadline extraction for hr_training module
    deadlines = extract_deadlines_from_records("hr_training", "training_certificate", [record])
    assert len(deadlines) == 1
    dl = deadlines[0]
    assert dl["module_id"] == "hr_training"
    assert dl["schema_name"] == "training_certificate"
    assert dl["field_name"] == "data_scadenza"
    assert dl["due_date"] == "2026-05-15"
    assert dl["description"] == "Giulia Neri — Corso di Aggiornamento per la figura del Preposto"
    assert dl["thresholds"] == [90, 60, 30, 15, 7]


