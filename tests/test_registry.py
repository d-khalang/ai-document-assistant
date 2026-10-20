from dataclasses import dataclass
from typing import List, Optional
import pytest
from app.extraction.registry import (
    list_modules,
    get_module,
    build_legacy_schemas,
    reload_registry,
    resolve_schema,
    _parse_schema,
    FieldDef,
    ExpiryRule,
    DerivedDateDef
)
from app.extraction.calculators import compute_value, ComputedDef, compute_expiry_date, ExpiryResult
from app.extraction.extractor import normalize_field, finalize_record
from app.extraction.normalizer import normalize_date, keyword_matches, normalize_key


@pytest.mark.offline
def test_schema_registry_loading():
    modules = reload_registry()
    assert len(modules) >= 3
    assert "iso_14001" in modules
    assert "fleet_fuel_expenses" in modules
    assert "general_documents" in modules

    iso = get_module("iso_14001")
    assert iso.model == "gemini-3.6-flash"


@pytest.mark.offline
def test_legacy_shim():
    legacy = build_legacy_schemas()
    for name in ["scadenziario", "vehicle_fuel", "utility_consumption", "personnel_training", "regulatory_authorization", "general"]:
        assert name in legacy


@pytest.mark.offline
def test_deterministic_calculators():
    c_ratio = ComputedDef(name="consumo", op="ratio", inputs=["litri", "km"], label="Consumo", scale=100.0, decimals=2)
    assert compute_value(c_ratio, {"litri": 250.0, "km": 2000.0}) == 12.5
    assert compute_value(c_ratio, {"litri": 250.0, "km": 0.0}) is None

    c_sum = ComputedDef(name="totale", op="sum", inputs=["a", "b"], label="Totale")
    assert compute_value(c_sum, {"a": 10.5, "b": 20.25}) == 30.75

    c_diff = ComputedDef(name="delta", op="diff", inputs=["a", "b"], label="Delta")
    assert compute_value(c_diff, {"a": 50.0, "b": 20.0}) == 30.0

    c_prod = ComputedDef(name="molt", op="product", inputs=["a", "b"], label="Moltiplicazione")
    assert compute_value(c_prod, {"a": 5.0, "b": 4.0}) == 20.0


@dataclass
class DummyRule:
    id: str
    keywords: List[str]
    months: Optional[int]
    priority: int = 1


@pytest.mark.offline
def test_compute_expiry_date_and_leap_year():
    rules = [
        DummyRule(id="carrello_elevatore", keywords=["carrell*", "muletto"], months=60, priority=2),
        DummyRule(id="primo_soccorso", keywords=["primo soccorso*"], months=36, priority=1),
        DummyRule(id="generale", keywords=["formazione generale"], months=None, priority=1),
    ]

    # Leap year: 2024-02-29 + 60 months (5 years) -> 2029-02-28
    res_leap = compute_expiry_date("2024-02-29", "Corso abilitazione carrellisti e muletto", rules)
    assert res_leap.reason == "ok"
    assert res_leap.rule_id == "carrello_elevatore"
    assert res_leap.months == 60
    assert res_leap.iso_date == "2029-02-28"

    # Primo soccorso: 2023-05-15 + 36 months -> 2026-05-15
    res_ps = compute_expiry_date("2023-05-15", "Attestato di Primo Soccorso Aziendale", rules)
    assert res_ps.reason == "ok"
    assert res_ps.rule_id == "primo_soccorso"
    assert res_ps.months == 36
    assert res_ps.iso_date == "2026-05-15"

    # Formazione generale: no expiry
    res_gen = compute_expiry_date("2024-01-10", "Attestato formazione generale dei lavoratori", rules)
    assert res_gen.reason == "no_expiry"
    assert res_gen.rule_id == "generale"
    assert res_gen.iso_date is None

    # Default fallback
    res_def = compute_expiry_date("2024-01-10", "Corso sconosciuto", rules, default_months=24)
    assert res_def.reason == "ok"
    assert res_def.rule_id == "default"
    assert res_def.months == 24
    assert res_def.iso_date == "2026-01-10"

    # No rule matched and no default
    res_none = compute_expiry_date("2024-01-10", "Corso sconosciuto", rules)
    assert res_none.reason == "no_rule"
    assert res_none.iso_date is None

    # Invalid / missing base date
    assert compute_expiry_date(None, "carrello", rules).reason == "no_base_date"
    assert compute_expiry_date("invalid-date", "carrello", rules).reason == "no_base_date"


@pytest.mark.offline
def test_date_and_field_normalizers():
    f_ente = FieldDef(name="ente_formatore", type="string", label="Ente")
    assert normalize_field(f_ente, "3R International")["status"] == "EXTRACTED"
    assert normalize_field(f_ente, ["item 1", "item 2"])["normalized_value"] == "item 1\nitem 2"

    assert normalize_date("31 luglio 2026") == "2026-07-31"
    assert normalize_date("15 October 2026") == "2026-10-15"
    assert normalize_date("04/11/2026") == "2026-11-04"

    f_date = FieldDef(name="scadenza", type="date", label="Scadenza")
    assert normalize_field(f_date, "31/02/2026")["status"] == "UNCERTAIN"


@pytest.mark.offline
def test_regulatory_authorization_layout_and_fields():
    reload_registry()
    schema = resolve_schema("regulatory_authorization", "iso_14001")
    assert schema.sheet_title == "Dettagli File"
    assert schema.report_title == "RAPPORTO DI AUTORIZZAZIONE E PRESCRIZIONI AMBIENTALI"
    other_schema = resolve_schema("scadenziario", "iso_14001")
    assert other_schema.report_title == "RAPPORTO DI CONFORMITÀ E AUDIT"
    assert len(schema.word_sections) == 2
    assert "numero_atto_protocollo" in schema.word_header_fields
    assert schema.word_table_fields == [
        "elenco_codici_eer",
        "quantitativi_movimentabili",
        "quantitativi_deposito",
    ]

    ordered = schema.ordered_field_names()
    idx_eer = ordered.index("elenco_codici_eer")
    assert ordered[idx_eer + 1] == "quantitativi_movimentabili"
    assert ordered[idx_eer + 2] == "quantitativi_deposito"

    with pytest.raises(ValueError, match="word_sections invalid"):
        _parse_schema(
            "test_mod",
            "bad_schema",
            {
                "fields": {"f1": {"type": "string", "label": "F1"}},
                "layout": {
                    "word_sections": [{"title": "Bad", "field": "nonexistent_field", "style": "table"}]
                },
            },
            "test.json",
        )


@pytest.mark.offline
def test_derived_dates_schema_validation():
    base_fields = {
        "corso": {"type": "string", "label": "Corso"},
        "data_emissione": {"type": "date", "label": "Data Emissione"},
        "data_scadenza": {"type": "date", "label": "Data Scadenza"},
    }

    # 1. Target not in fields
    with pytest.raises(ValueError, match="target 'nonexistent' must be an existing date field"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "nonexistent": {"base_field": "data_emissione", "rules": []}
            }
        }, "t.json")

    # 2. Target not a date field
    with pytest.raises(ValueError, match="target 'corso' must be an existing date field"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "corso": {"base_field": "data_emissione", "rules": []}
            }
        }, "t.json")

    # 3. Base field not in fields
    with pytest.raises(ValueError, match="base_field 'missing_date' must be an existing date field"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "data_scadenza": {"base_field": "missing_date", "rules": []}
            }
        }, "t.json")

    # 4. Base field not a date field
    with pytest.raises(ValueError, match="base_field 'corso' must be an existing date field"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "data_scadenza": {"base_field": "corso", "rules": []}
            }
        }, "t.json")

    # 5. Text field not in fields
    with pytest.raises(ValueError, match="text_field 'bad_text' not in fields"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "data_scadenza": {"base_field": "data_emissione", "text_fields": ["bad_text"], "rules": []}
            }
        }, "t.json")

    # 6. Duplicate rule id
    with pytest.raises(ValueError, match="rule id duplicate or missing: 'dup_rule'"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "data_scadenza": {
                    "base_field": "data_emissione",
                    "rules": [
                        {"id": "dup_rule", "keywords": ["k1"], "months": 12},
                        {"id": "dup_rule", "keywords": ["k2"], "months": 24},
                    ]
                }
            }
        }, "t.json")

    # 7. Negative months in rule
    with pytest.raises(ValueError, match="rule 'r1' months must be positive int or null"):
        _parse_schema("m", "s", {
            "fields": base_fields,
            "derived_dates": {
                "data_scadenza": {
                    "base_field": "data_emissione",
                    "rules": [
                        {"id": "r1", "keywords": ["k1"], "months": -12}
                    ]
                }
            }
        }, "t.json")

    # 8. Valid derived_dates definition parses cleanly
    parsed = _parse_schema("m", "s", {
        "fields": base_fields,
        "derived_dates": {
            "data_scadenza": {
                "base_field": "data_emissione",
                "text_fields": ["corso"],
                "default_months": 60,
                "rules": [
                    {"id": "carrello", "keywords": ["carrell*"], "months": 60, "priority": 1, "ref": "Accordo CSR"}
                ]
            }
        }
    }, "t.json")
    assert "data_scadenza" in parsed.derived
    ddef = parsed.derived["data_scadenza"]
    assert ddef.target == "data_scadenza"
    assert ddef.base_field == "data_emissione"
    assert ddef.default_months == 60
    assert len(ddef.rules) == 1
    assert ddef.rules[0].id == "carrello"
    assert ddef.rules[0].ref == "Accordo CSR"


@pytest.mark.offline
def test_personnel_training_derived_dates_integration():
    reload_registry()
    schema = resolve_schema("personnel_training", "iso_14001")
    assert "data_scadenza_rinnovo" in schema.derived
    assert "ruolo_corso" in schema.fields

    # Case 1: Carrellisti (60 months) -> leap year calculation (2024-02-29 + 60 months = 2029-02-28)
    fields1 = {
        "data_emissione": {"normalized_value": "2024-02-29", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Abilitazione carrelli elevatori semoventi (muletto)", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Carrellista", "status": "EXTRACTED"},
        "riferimento_normativo": {"normalized_value": "art 73 D.Lgs 81/08", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Mario Rossi", "status": "EXTRACTED"},
    }
    warns1 = finalize_record(schema, fields1)
    assert fields1["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert fields1["data_scadenza_rinnovo"]["normalized_value"] == "2029-02-28"
    assert "60 mesi · attrezzature" in fields1["data_scadenza_rinnovo"]["raw_value"]

    # Case 2: Preposto (24 months)
    fields2 = {
        "data_emissione": {"normalized_value": "2023-05-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Corso di formazione per preposti", "status": "EXTRACTED"},
        "ruolo_corso": {"normalized_value": "Preposto", "status": "EXTRACTED"},
        "riferimento_normativo": {"normalized_value": None, "status": "MISSING"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Luigi Bianchi", "status": "EXTRACTED"},
    }
    warns2 = finalize_record(schema, fields2)
    assert fields2["data_scadenza_rinnovo"]["status"] == "CALCULATED"
    assert fields2["data_scadenza_rinnovo"]["normalized_value"] == "2025-05-10"
    assert "24 mesi · preposto" in fields2["data_scadenza_rinnovo"]["raw_value"]

    # Case 3: Already EXTRACTED / EDITED -> NEVER overwritten
    fields3 = {
        "data_emissione": {"normalized_value": "2023-05-10", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Preposto", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"normalized_value": "2028-12-31", "raw_value": "31/12/2028", "status": "EDITED"},
        "nominativo_dipendente": {"normalized_value": "Anna Verdi", "status": "EXTRACTED"},
    }
    finalize_record(schema, fields3)
    assert fields3["data_scadenza_rinnovo"]["status"] == "EDITED"
    assert fields3["data_scadenza_rinnovo"]["normalized_value"] == "2028-12-31"

    # Case 4: Formazione generale (months = null -> no expiry)
    fields4 = {
        "data_emissione": {"normalized_value": "2024-01-15", "status": "EXTRACTED"},
        "corso_descrizione": {"normalized_value": "Corso di formazione generale dei lavoratori", "status": "EXTRACTED"},
        "data_scadenza_rinnovo": {"raw_value": None, "normalized_value": None, "status": "MISSING"},
        "nominativo_dipendente": {"normalized_value": "Paolo Neri", "status": "EXTRACTED"},
    }
    finalize_record(schema, fields4)
    assert fields4["data_scadenza_rinnovo"]["status"] == "MISSING"
    assert fields4["data_scadenza_rinnovo"]["normalized_value"] is None
