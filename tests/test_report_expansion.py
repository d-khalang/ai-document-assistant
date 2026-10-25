"""Offline checks for the per-code row expansion helpers (pure functions, no workbook needed)."""
import pytest

from app.extraction.registry import _parse_schema, reload_registry, resolve_schema
from app.reporting.expansion import (
    distinct_codes, expand_record, format_code, parse_number, split_by_code, split_value_unit, unit_key,
)

CFG = resolve_schema("regulatory_authorization", "iso_14001").excel_expand
PATTERN = CFG["code_pattern"]


@pytest.mark.offline
def test_codes_are_found_in_any_common_notation_and_deduplicated():
    text = "16 01 03, 160104*; 16.01.03 e 17.04.05"
    assert distinct_codes(text, PATTERN) == ["16.01.03", "16.01.04*", "17.04.05"]
    assert format_code("16 01 03") == "16.01.03" and format_code("R13") == "R13"


@pytest.mark.offline
def test_split_by_code_handles_newline_semicolon_and_global_text():
    keyed, unkeyed = split_by_code("16.01.03: 9 t/a\n16.01.04*: 1 t/a; 17.04.05 - 3 t/a", PATTERN)
    assert keyed == {"16.01.03": "9 t/a", "16.01.04*": "1 t/a", "17.04.05": "3 t/a"} and unkeyed == ""
    assert split_by_code("Fase 1: 3000 t/a", PATTERN) == ({}, "Fase 1: 3000 t/a")
    assert split_by_code("16.01.03: R13\n16.01.03: R12", PATTERN)[0] == {"16.01.03": "R13; R12"}


@pytest.mark.offline
@pytest.mark.parametrize("text,expected", [
    ("9 t/anno", (9, "t/anno")), ("4", (4, "")), ("1.500 t/a", (1500, "t/a")), ("3,5 t", (3.5, "t")),
    ("1.500,5 kg", (1500.5, "kg")), ("Fase 1: 3000 t/a", ("Fase 1: 3000 t/a", "")), ("", (None, "")),
    ("9 t/a (Fase 1)", ("9 t/a (Fase 1)", "")),
])
def test_value_unit_split_is_tolerant_and_never_drops_text(text, expected):
    assert split_value_unit(text) == expected
    assert parse_number("abc") is None


@pytest.mark.offline
def test_expand_record_builds_one_row_per_code_and_adds_codes_only_present_in_quantities():
    rows = expand_record({
        "elenco_codici_eer": "16.01.03",
        "quantitativi_movimentabili": "16.01.03: 9 t/a; 16.01.99: 2 t/a",
        "quantitativi_deposito": "16.01.03: 4 t",
        "operazioni_trattamento": "16.01.03: R13",
    }, CFG)
    assert [r["elenco_codici_eer"] for r in rows] == ["16.01.03", "16.01.99"]
    assert rows[0]["quantitativi_movimentabili"] == 9 and rows[0][unit_key("quantitativi_movimentabili")] == "t/a"
    assert rows[1]["quantitativi_deposito"] is None and rows[1]["operazioni_trattamento"] is None


@pytest.mark.offline
def test_global_figure_is_attached_only_when_there_is_a_single_code_and_no_code_yields_one_row():
    single = expand_record({"elenco_codici_eer": "16.01.03", "quantitativi_deposito": "150 t"}, CFG)
    assert single[0]["quantitativi_deposito"] == 150 and single[0][unit_key("quantitativi_deposito")] == "t"
    none = expand_record({"elenco_codici_eer": "tutti i rifiuti non pericolosi", "operazioni_trattamento": "R13"}, CFG)
    assert len(none) == 1 and none[0]["elenco_codici_eer"] == "tutti i rifiuti non pericolosi"
    assert none[0]["operazioni_trattamento"] == "R13"
    assert expand_record({}, CFG)[0]["elenco_codici_eer"] is None


@pytest.mark.offline
def test_excel_expand_and_hide_status_layout_are_validated():
    reload_registry()
    base = {"f1": {"type": "string"}, "f2": {"type": "string"}}
    for bad in (
        {"excel_expand": {"code_field": "nope", "code_pattern": r"\d+"}},
        {"excel_expand": {"code_field": "f1", "code_pattern": "("}},
        {"excel_expand": {"code_field": "f1", "code_pattern": r"\d+", "keyed_fields": {"zzz": {}}}},
        {"excel_expand": {"code_field": "f1", "code_pattern": r"\d+", "keyed_fields": {"f2": {"unit_label": ""}}}},
        {"hide_status_column": "yes"},
    ):
        with pytest.raises(ValueError):
            _parse_schema("m", "s", {"fields": base, "layout": bad}, "t.json")
    ok = _parse_schema("m", "s", {"fields": base, "layout": {
        "hide_status_column": True,
        "excel_expand": {"code_field": "f1", "code_pattern": r"\d+", "keyed_fields": {"f2": {"unit_label": "U"}}}}}, "t.json")
    assert ok.hide_status_column and ok.excel_expand["code_field"] == "f1"
