"""Offline checks for the presentation-only theme helpers (no Streamlit runtime needed)."""
import pytest

from app.ui import theme
from app.ui.theme import MetricCard, render_metric_cards


@pytest.fixture
def captured(monkeypatch):
    calls = []
    monkeypatch.setattr(theme.st, "markdown", lambda body, **kw: calls.append(body))
    return calls


@pytest.mark.offline
def test_metric_cards_render_values_tone_and_escape_html(captured):
    render_metric_cards([
        MetricCard("Documenti attivi", 3, tone="green", icon="docs", info="Caricati <ora>", note="Nell'area di lavoro"),
        MetricCard("<b>Errori</b>", 2, tone="red", icon="alert", note="Da verificare"),
        MetricCard("Strano", 1, tone="purple", icon="unknown"),
    ])
    html_out = captured[0]
    assert html_out.count("class='metric-card") == 3
    assert "tone-green" in html_out and "tone-red" in html_out
    assert "tone-purple" not in html_out            # unknown tone falls back to green
    assert "&lt;b&gt;Errori&lt;/b&gt;" in html_out   # labels are escaped
    assert "<b>Errori</b>" not in html_out
    assert "Caricati &lt;ora&gt;" in html_out        # tooltip escaped
    assert "Nell&#x27;area di lavoro" in html_out


@pytest.mark.offline
def test_metric_delta_is_rendered_only_when_a_real_figure_is_supplied(captured):
    render_metric_cards([MetricCard("Indicizzati", 5, tone="blue", icon="indexed", note="Pronti per la ricerca")])
    assert "metric-note delta" not in captured[0]
    assert "Pronti per la ricerca" in captured[0]

    render_metric_cards([
        MetricCard("Indicizzati", 5, tone="blue", delta="+18% rispetto al mese scorso"),
        MetricCard("Errori", 1, tone="red", delta="+1 rispetto al mese scorso", delta_trend="down"),
    ])
    assert "▲ +18% rispetto al mese scorso" in captured[1]
    assert "▼ +1 rispetto al mese scorso" in captured[1]


@pytest.mark.offline
def test_injected_css_has_no_unresolved_placeholders(captured):
    theme.inject_custom_css()
    css = captured[0]
    assert "__HERO_ART__" not in css and "__CHEVRON" not in css
    assert css.count("data:image/svg+xml;utf8,") >= 3   # hero art + two chevron variants


@pytest.mark.offline
def test_page_header_shows_official_slogan_and_escapes_tenant(captured):
    theme.render_page_header("Titolo", "1.0.0", "<script>alert(1)</script>")
    out = captured[0]
    assert "Documenti oggi per un domani più sostenibile." in out
    assert "<script>" not in out and "&lt;script&gt;" in out


@pytest.mark.offline
def test_page_header_with_dynamic_metadata_and_module_pill(captured):
    theme.render_page_header(
        title="Document Hub & Batch Pipeline",
        version="v1.0.0",
        tenant="inambiente S.r.l.",
        subtitle="Caricamento massivo",
        module_label="Sistemi Ambientali ISO 14001",
    )
    out = captured[0]
    assert "Document Hub &amp; Batch Pipeline" in out
    assert "Caricamento massivo" in out
    assert "inambiente S.r.l." in out
    assert "Sistemi Ambientali ISO 14001" in out
    assert "v1.0.0" in out
    assert "module-pill" in out


@pytest.mark.offline
def test_operational_buttons_styled_in_css(captured):
    theme.inject_custom_css()
    css = captured[0]
    for key in ["btn_run_pipeline", "btn_rebuild_report", "btn_delete_doc", "btn_delete_all"]:
        assert f".st-key-{key}" in css
    assert "min-height:3.2rem" in css


@pytest.mark.offline
def test_css_resolves_nav_icons_dropzone_art_and_tenant_badge(captured):
    theme.inject_custom_css()
    css = captured[0]
    for placeholder in ("__NAV_ICON_RULES__", "__UPLOAD_ART__", "__TENANT_ICON"):
        assert placeholder not in css
    for i in range(1, len(theme._NAV_ICON_PATHS) + 1):
        assert f":nth-child({i})" in css                     # one icon rule per navigation card
    assert 'content:"Sfoglia file"' in css                 # native "Browse files" is replaced, not appended to
    assert "tenant-badge" in css and "tenant-dot" not in css


@pytest.mark.offline
def test_identity_modal_logo_is_inlined_and_cached(captured, monkeypatch):
    theme._logo_data_uri.cache_clear()
    uri = theme._logo_data_uri()
    assert uri.startswith("data:image/jpeg;base64,")
    assert theme._logo_data_uri() is uri                     # read from disk once

    monkeypatch.setattr(theme, "_LOGO", theme._ASSETS / "does-not-exist.jpg")
    theme._logo_data_uri.cache_clear()
    assert theme._logo_data_uri() == ""                      # missing file degrades to text-only, no exception
    theme._logo_data_uri.cache_clear()

