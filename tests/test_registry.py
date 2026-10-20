import pytest
from app.extraction.registry import (
    list_modules,
    get_module,
    build_legacy_schemas,
    reload_registry,
    resolve_schema,
    _parse_schema,
    FieldDef
)
from app.extraction.calculators import compute_value, ComputedDef
from app.extraction.extractor import normalize_field
from app.extraction.normalizer import normalize_date


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
