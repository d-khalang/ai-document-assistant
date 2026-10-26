"""Offline checks for the deterministic progress helpers (presentation only) and the extraction progress hook."""
import pytest

from app.extraction import extractor
from app.ui import theme
from app.ui.theme import PIPELINE_STAGES, batch_message, progress_percent, show_pipeline_stage


@pytest.mark.offline
@pytest.mark.parametrize("done,total,start,end,expected", [
    (0, 4, 0, 100, 0), (1, 4, 0, 100, 25), (2, 4, 0, 100, 50), (4, 4, 0, 100, 100),
    (1, 3, 20, 40, 27), (3, 3, 20, 40, 40), (2, 3, 0, 90, 60),
    (5, 4, 0, 100, 100), (-1, 4, 0, 100, 0),            # clamped
    (1, 0, 0, 100, 0), (1, 0, 20, 40, 20),              # nothing to do -> start of the band, never a division error
])
def test_progress_percent_is_clamped_and_maps_into_a_band(done, total, start, end, expected):
    assert progress_percent(done, total, start, end) == expected


@pytest.mark.offline
def test_batch_message_is_formal_italian_with_explicit_percentage():
    msg = batch_message("Elaborazione", 2, 4, 50, "bolletta.pdf: indicizzazione vettoriale in corso")
    assert msg == "Elaborazione: documento 2 di 4 (50%) — bolletta.pdf: indicizzazione vettoriale in corso"


@pytest.mark.offline
def test_pipeline_has_the_five_requested_milestones_in_order():
    assert [pct for pct, _ in PIPELINE_STAGES] == [20, 40, 70, 90, 100]
    assert all(label for _, label in PIPELINE_STAGES)


class _Slot:
    def __init__(self):
        self.progress_args = None
        self.caption_text = None

    def progress(self, value, text=None):
        self.progress_args = (value, text)

    def caption(self, text):
        self.caption_text = text


@pytest.mark.offline
def test_show_pipeline_stage_sets_bar_and_label_beneath():
    bar, cap = _Slot(), _Slot()
    show_pipeline_stage(bar, cap, 2)
    assert bar.progress_args == (0.7, "Fase 3 di 5 — 70%")
    assert cap.caption_text == PIPELINE_STAGES[2][1]
    show_pipeline_stage(bar, cap, 1, percent=27, detail="documento 1 di 3")
    assert bar.progress_args == (0.27, "Fase 2 di 5 — 27%")
    assert cap.caption_text.endswith("— documento 1 di 3")
    show_pipeline_stage(bar, cap, 4)
    assert bar.progress_args[0] == 1.0


@pytest.mark.offline
def test_progress_css_is_slim_rounded_green_and_animated(monkeypatch):
    calls = []
    monkeypatch.setattr(theme.st, "markdown", lambda body, **kw: calls.append(body))
    theme.inject_custom_css()
    css = calls[0]
    block = css[css.index('[data-testid="stProgress"] [role="progressbar"] {'):]
    block = block[:block.index("[data-testid=\"stProgress\"] +")]
    for needle in ("height:10px", "border-radius:999px", "overflow:hidden", "#EBF0E6", "#8CC63F", "#7DB531",
                   "transition:transform .35s ease-in-out"):
        assert needle in block


@pytest.mark.offline
def test_extract_for_documents_reports_progress_after_every_document(monkeypatch):
    def fake(pages, schema_name, module_id=None, source_document=None):
        if source_document == "bad.pdf":
            raise ValueError("boom")
        return {"module_id": "m", "records": [{"source_document": source_document}]}

    monkeypatch.setattr(extractor, "extract_structured_data", fake)
    seen = []
    result = extractor.extract_for_documents(
        {"a.pdf": [], "bad.pdf": [], "c.pdf": []}, "s", module_id="m",
        on_progress=lambda done, total, doc, err: seen.append((done, total, doc, err)))
    assert seen == [(1, 3, "a.pdf", None), (2, 3, "bad.pdf", "boom"), (3, 3, "c.pdf", None)]
    assert result["total_records"] == 2 and result["errors"] == {"bad.pdf": "boom"}
    # the hook is optional: the historical call signature keeps working
    assert extractor.extract_for_documents({"a.pdf": []}, "s", module_id="m")["total_records"] == 1
