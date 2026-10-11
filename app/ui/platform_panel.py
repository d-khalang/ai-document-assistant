"""
Streamlit panel for the one-click platform workflow:

    upload -> deterministic routing -> parallel multi-module extraction -> deadline sync -> Excel report

Rules
-----
* Heavy work runs in a background thread (`pipeline.PipelineJob`); the UI only polls a thread-safe
  snapshot from an `st.fragment(run_every=...)`, so the page never freezes and other tabs stay usable.
* Worker threads never touch `st.session_state`. Results are merged here, in the script thread.
* The report is generated lazily (on click) from a payload captured at the END of the script run, so
  it always contains the latest human review edits and never costs CPU on ordinary reruns.
"""
import copy
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from app.alerts.store import deactivate_deadlines_for_documents
from app.alerts.sync import sync_deadlines
from app.config import PIPELINE_MAX_WORKERS
from app.extraction import pipeline as pl
from app.reporting.platform_excel_exporter import create_platform_excel_report

_NO_ROUTE_LABEL = "— da assegnare —"
_SKIP_LABEL = "⛔ Escludi dall'analisi"
_CONFIDENCE_LABEL = {
    "high": "Alta", "low": "Bassa — verificare", "fallback": "Generico (fallback)",
    "manual": "Manuale", "excluded": "Escluso", "none": "Non classificato",
}
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ----------------------------------------------------------------------------- state
def init_platform_state() -> None:
    """Idempotent. Call once from `initialize_session()`."""
    ss = st.session_state
    for key in ("extracted_data", "reviewed_data", "editor_version", "indexed_documents",
                "pipeline_log", "routing_overrides", "routing_cache"):
        ss.setdefault(key, {})
    ss.setdefault("pipeline_job", None)
    ss.setdefault("pipeline_summary", None)


def collect_platform_payload() -> Dict[str, Dict[str, Any]]:
    """All modules/schemas, human-reviewed rows preferred (single source for report + alerts)."""
    ss = st.session_state
    return pl.compose_payload(ss.extracted_data, ss.reviewed_data)


def _pages_by_doc() -> Dict[str, Any]:
    return {name: meta.get("pages") or [] for name, meta in st.session_state.indexed_documents.items()}


def _bump_editors(keys) -> None:
    ev = st.session_state.editor_version
    for key in keys:
        ev[key] = ev.get(key, 0) + 1


def purge_removed_documents() -> None:
    """
    Remove rows, log entries and monitored deadlines of documents that are no longer uploaded.
    (Previously only the exporters filtered them out; the data lingered and DB deadlines stayed active.)
    """
    ss = st.session_state
    removed = pl.purge_orphans(ss.extracted_data, ss.reviewed_data, ss.pipeline_log, ss.indexed_documents.keys())
    if not removed:
        return
    for name in removed:
        ss.routing_overrides.pop(name, None)
        ss.routing_cache.pop(name, None)
    _bump_editors(list(ss.editor_version))
    try:
        deactivate_deadlines_for_documents(removed)
    except Exception:  # noqa: BLE001 - housekeeping must never break the page
        pass


def _auto_plan(pages_by_doc: Dict[str, Any]) -> Dict[str, pl.RoutingDecision]:
    """Auto-routing with a per-document cache (signature = content size + rules version)."""
    cache = st.session_state.routing_cache
    version = pl.rules_version()
    out: Dict[str, pl.RoutingDecision] = {}
    for name, pages in pages_by_doc.items():
        sig = (version, len(pages), sum(len((p or {}).get("text") or "") for p in pages))
        hit = cache.get(name)
        if hit and hit[0] == sig:
            out[name] = hit[1]
        else:
            dec = pl.classify_document(name, pages)
            cache[name] = (sig, dec)
            out[name] = dec
    return out


# ----------------------------------------------------------------------------- job lifecycle
def _commit_job(job: pl.PipelineJob) -> None:
    """Merge a finished job into session state (script thread only)."""
    ss = st.session_state
    active = set(ss.indexed_documents)
    results = [r for r in job.results if r.task.filename in active]   # docs removed meanwhile are ignored
    decisions = {n: d for n, d in job.decisions.items() if n in active}

    touched = pl.merge_into_state(ss.extracted_data, ss.reviewed_data, results)
    pl.update_log(ss.pipeline_log, decisions, results)
    _bump_editors(touched)

    snap = job.snapshot()
    summary: Dict[str, Any] = {
        "tasks": len(results),
        "ok": sum(1 for r in results if r.status == "ok"),
        "empty": sum(1 for r in results if r.status == "empty"),
        "errors": {f"{r.task.filename} → {r.task.schema_name}": r.error for r in results if r.error},
        "records": sum(len(r.records) for r in results),
        "unrouted": [n for n, d in decisions.items() if not d.routes and d.confidence != "excluded"],
        "cancelled": snap.cancelled,
        "job_error": snap.error,
        "sync": None,
        "sync_error": None,
    }
    if st.session_state.get("pipeline_sync_flag", True):
        try:
            summary["sync"] = sync_deadlines(collect_platform_payload(), active)
        except Exception as exc:  # noqa: BLE001
            summary["sync_error"] = str(exc)

    ss.pipeline_job = None
    ss.pipeline_summary = summary


@st.fragment(run_every=1.0)
def _job_monitor() -> None:
    """Polls the background job. Only rendered while a job exists, so polling stops by itself."""
    job: Optional[pl.PipelineJob] = st.session_state.get("pipeline_job")
    if job is None:
        return
    snap = job.snapshot()
    total = max(snap.total, 1)
    st.progress(min(snap.done / total, 1.0), text=f"Estrazione {snap.done}/{snap.total} — {snap.last}")
    if snap.failed:
        st.caption(f":material/warning: {snap.failed} estrazioni in errore finora (il batch prosegue).")
    if not snap.finished:
        if st.button("Annulla", key="pipeline_cancel", icon=":material/cancel:"):
            job.cancel()
        return
    _commit_job(job)
    st.rerun()


def _start_job(decisions: Dict[str, pl.RoutingDecision], tasks) -> None:
    ss = st.session_state
    ss.pipeline_sync_flag = bool(ss.get("auto_sync_deadlines", True))
    # Re-routed documents (manual override): drop rows from schemas they no longer belong to.
    stale = pl.drop_stale_routes(ss.extracted_data, ss.reviewed_data, ss.pipeline_log, decisions)
    _bump_editors(stale)
    pl.update_log(ss.pipeline_log, decisions, [])
    ss.pipeline_summary = None
    if not tasks:
        ss.pipeline_summary = {"tasks": 0, "ok": 0, "empty": 0, "errors": {}, "records": 0, "sync": None,
                               "unrouted": [n for n, d in decisions.items()
                                            if not d.routes and d.confidence != "excluded"],
                               "cancelled": False, "job_error": None, "sync_error": None}
        st.rerun()
    ss.pipeline_job = pl.PipelineJob(tasks, _pages_by_doc(), decisions, max_workers=PIPELINE_MAX_WORKERS).start()
    st.rerun()


# ----------------------------------------------------------------------------- rendering
def _status_text(name: str) -> str:
    entry = st.session_state.pipeline_log.get(name)
    if not entry or not entry.get("routes"):
        return "—"
    parts = []
    for r in entry["routes"]:
        s = r.get("status")
        parts.append({"ok": f"✓ {r.get('records', 0)} record", "empty": "⚠ nessun record",
                      "error": "✗ errore"}.get(s, "… da analizzare"))
    return " · ".join(parts)


def _render_routing_table(auto: Dict[str, pl.RoutingDecision]) -> None:
    """Editable routing table; writes manual overrides to session state."""
    ss = st.session_state
    options = pl.list_route_options()
    label_to_key = {_NO_ROUTE_LABEL: "", _SKIP_LABEL: pl.SKIP_TARGET, **{lbl: k for k, lbl in options.items()}}
    key_to_label = {v: k for k, v in label_to_key.items()}

    rows = []
    for name, base in auto.items():
        dec = pl.apply_override(base, ss.routing_overrides.get(name))
        target = dec.routes[0].key if dec.routes else (pl.SKIP_TARGET if dec.confidence == "excluded" else "")
        rows.append({
            "Documento": name,
            "Confidenza": _CONFIDENCE_LABEL.get(dec.confidence, dec.confidence),
            "Segnali rilevati": ", ".join(dec.routes[0].matched[:4]) if dec.routes else "",
            "Stato": _status_text(name),
            "Schema target": key_to_label.get(target, _NO_ROUTE_LABEL),
        })
    df = pd.DataFrame(rows)
    editor_key = f"routing_editor_{abs(hash(tuple(auto)))}"
    edited = st.data_editor(
        df, key=editor_key, hide_index=True, width="stretch",
        disabled=["Documento", "Confidenza", "Segnali rilevati", "Stato"],
        column_config={"Schema target": st.column_config.SelectboxColumn(
            "Schema target", options=list(label_to_key), required=True,
            help="Modifica per forzare lo schema di estrazione di un documento.")},
    )
    new_overrides: Dict[str, str] = {}
    for _, row in edited.iterrows():
        name = row["Documento"]
        target = label_to_key.get(row["Schema target"], "")
        auto_base = auto[name]
        auto_key = auto_base.routes[0].key if auto_base.routes else ""
        if target != auto_key and (target or auto_key):
            new_overrides[name] = target if target else pl.SKIP_TARGET
    ss.routing_overrides = new_overrides


def _render_summary() -> None:
    s = st.session_state.pipeline_summary
    if not s:
        return
    if s.get("job_error"):
        st.error(f"Pipeline interrotta: {s['job_error']}")
    msg = (f"{s['ok']} analisi completate · {s['records']} record estratti"
           + (f" · {s['empty']} senza record" if s["empty"] else ""))
    (st.warning if s["errors"] or s["cancelled"] else st.success)(
        msg + (" · annullata dall'utente" if s["cancelled"] else ""))
    if s["unrouted"]:
        st.info(f"{len(s['unrouted'])} documenti non classificati: assegna lo schema nella tabella di instradamento.")
    if s["errors"]:
        with st.expander(f"{len(s['errors'])} errori di estrazione", expanded=False):
            for where, err in s["errors"].items():
                st.markdown(f"- :material/error: **{where}**: {err}")
    if s.get("sync"):
        sy = s["sync"]
        st.caption(f":material/notifications_active: Monitoraggio aggiornato: {sy['upserted']} scadenze "
                   f"({sy['modules']} moduli), {sy['deactivated']} obsolete disattivate.")
    if s.get("sync_error"):
        st.warning(f"Sincronizzazione scadenze non riuscita: {s['sync_error']}")


def render_pipeline_controls() -> None:
    """Routing table + one-click run button + live progress. Safe to call on every rerun."""
    ss = st.session_state
    if ss.pipeline_job is not None:
        _job_monitor()
        return

    pages = _pages_by_doc()
    auto = _auto_plan(pages)

    with st.expander("Instradamento documenti → schemi (modificabile)", expanded=False, icon=":material/route:"):
        st.caption("Classificazione deterministica per parole chiave dichiarate in `schemas/*.json` "
                   "(nessun LLM). Cambia lo schema target per correggere un instradamento.")
        _render_routing_table(auto)

    decisions = {n: pl.apply_override(d, ss.routing_overrides.get(n)) for n, d in auto.items()}
    pending = pl.build_tasks(decisions, ss.pipeline_log)
    pending_docs = len({t.filename for t in pending})
    unrouted = sum(1 for d in decisions.values() if not d.routes and d.confidence != "excluded")

    st.checkbox("Sincronizza le scadenze nel monitoraggio al termine", value=True, key="auto_sync_deadlines")

    if pending:
        label = f"Analizza {pending_docs} document{'o' if pending_docs == 1 else 'i'} e prepara il report"
        if st.button(label, type="primary", width="stretch", icon=":material/rocket_launch:", key="pipeline_run"):
            _start_job(decisions, pending)
    elif unrouted:
        st.info(f"{unrouted} documenti non classificati: assegna uno schema nella tabella per analizzarli.")
    else:
        st.success("Tutti i documenti sono già analizzati.", icon=":material/check_circle:")

    if decisions and st.button("Rielabora tutto da zero (sovrascrive le revisioni)", key="pipeline_force",
                               icon=":material/refresh:"):
        _start_job(decisions, pl.build_tasks(decisions, ss.pipeline_log, force=True))

    _render_summary()


def render_platform_report(slot) -> None:
    """
    Fill the reserved `slot` (created earlier in the layout) with the report download button.
    MUST be called at the end of the script run, after the review editors updated `reviewed_data`.
    """
    ss = st.session_state
    with slot:
        docs = [{"filename": n} for n in ss.indexed_documents]
        payload = collect_platform_payload()
        profile = dict(ss.company_profile)
        log = copy.deepcopy(ss.pipeline_log)
        for name, base in _auto_plan(_pages_by_doc()).items():
            dec = pl.apply_override(base, ss.routing_overrides.get(name))
            if not dec.routes:
                log[name] = {"confidence": dec.confidence, "routes": []}
            elif name not in log:
                log[name] = {"confidence": dec.confidence, "routes": [
                    {"module_id": r.module_id, "schema_name": r.schema_name, "status": "pending",
                     "records": 0, "error": None} for r in dec.routes]}

        def _build() -> bytes:   # runs on click, in a worker thread: no st.* access allowed here
            return create_platform_excel_report(
                documents=docs, extracted_data_all_modules=payload,
                company_profile=profile, processing_log=log)

        analysed = sum(1 for n in ss.indexed_documents
                       if any(r.get("status") in ("ok", "empty", "error") for r in (log.get(n) or {}).get("routes", [])))
        st.download_button(
            label="Scarica Fascicolo Gestionale Completo (.xlsx)",
            data=_build,
            file_name=f"Report_Gestionale_Completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime=_XLSX_MIME, width="stretch", icon=":material/download:",
            key="platform_report_download", on_click="ignore",
            help="Dashboard KPI, Registro Documenti, Scadenze & Azioni e un foglio dati per ogni schema.",
        )
        st.caption(f"{analysed}/{len(docs)} documenti analizzati · il file viene generato al click "
                   "con le ultime revisioni manuali.")
