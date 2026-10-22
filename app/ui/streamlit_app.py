import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
from PIL import Image

FAVICON_PATH = Path(__file__).resolve().parent / "assets" / "favicon.png"
from app.ui.theme import (
    inject_custom_css,
    render_kpi_row,
    render_stat_chips,
    render_brand_header,
    render_page_header,
    render_sidebar_stats,
    section_title,
    sidebar_label,
    danger_zone_marker,
    layout_split_marker,
    loader,
    progress_bar,
)
from app.alerts.store import (
    ensure_alert_tables,
    upsert_deadline,
    get_active_deadlines,
    add_recipient,
    get_active_recipients,
    deactivate_deadlines_for_document,
    deactivate_all_deadlines,
    deactivate_recipient_by_id,
    deactivate_recipient,
    deactivate_all_recipients,
)
from app.alerts.scanner import scan_deadlines
from app.extraction.pipeline import (
    apply_results, build_routing_plan, collect_errors, collect_payload, evict_document,
    merge_result, pending_tasks, run_batch_extraction, sync_deadlines_to_db,
)
from app.alerts.deadlines import extract_deadlines_from_records
from app.alerts.dispatcher import dispatch_alerts
from app.alerts.notifiers import SmtpEmailNotifier, TwilioSmsNotifier
from app.reporting.platform_excel_exporter import create_platform_excel_report

from app.ai.gemini import generate_answer
from app.ai.prompts import build_rag_prompt, build_chat_structured_context
from app.rag.loader import load_document_content
from app.rag.chunker import split_text_into_chunks
from app.rag.embeddings import get_batch_embeddings
from app.rag.vectorstore import (
    store_chunks_in_chromadb, 
    remove_document_from_chromadb, 
    clear_chroma_collection
)
from app.rag.retriever import retrieve_relevant_chunks

from app.extraction.registry import list_modules, get_module, reload_registry
from app.extraction.extractor import extract_for_documents
from app.extraction.review import records_to_dataframe, dataframe_to_records

from app.reporting.excel_exporter import create_styled_excel_report, COLUMN_LABELS
from app.reporting.word_exporter import create_styled_word_report
from app.config import RAG_TOP_K
from app.database.database import (
    init_db,
    create_user,
    create_conversation,
    create_document,
    save_message,
    get_conversation_history,
    get_company_profile,
    update_company_profile,
)


def initialize_session():
    """Inizializzazione della sessione (idempotente)."""
    init_db()
    ensure_alert_tables()

    if "user_id" not in st.session_state:
        st.session_state.user_id = create_user()

    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = create_conversation(st.session_state.user_id)

    if "indexed_documents" not in st.session_state:
        st.session_state.indexed_documents = {}

    if "processing_errors" not in st.session_state:
        st.session_state.processing_errors = {}

    all_mods = list_modules()
    st.session_state.setdefault("active_module", all_mods[0].module_id if all_mods else "iso_14001")
    st.session_state.setdefault("extracted_data", {})
    st.session_state.setdefault("reviewed_data", {})
    st.session_state.setdefault("editor_version", {})
    st.session_state.setdefault("export_fields", {})
    st.session_state.setdefault("routing_plan", {})       # doc -> RouteDecision (automatic)
    st.session_state.setdefault("routing_overrides", {})  # doc -> (mid, schema) | None (user choice)
    st.session_state.setdefault("routed_to", {})          # doc -> route actually extracted
    st.session_state.setdefault("platform_xlsx", None)    # (bytes, datetime)
    st.session_state.setdefault("last_dispatch_result", None)

    if "company_profile" not in st.session_state:
        st.session_state.company_profile = {
            "company_name": "",
            "vat_number": "",
            "address": "",
            "rsga_name": "",
            "technical_director": ""
        }


def reset_conversation():
    st.session_state.conversation_id = create_conversation(st.session_state.user_id)


def _reset_vector_index_callback():
    clear_chroma_collection()
    st.session_state.indexed_documents.clear()
    reset_conversation()
    st.session_state.extracted_data.clear()
    st.session_state.reviewed_data.clear()
    st.session_state.confirm_reset_index = False
    st.session_state.flash_msg = "Indice vettoriale azzerato con successo!"


def remove_single_document(doc_name: str) -> None:
    """Rimuove in modo pulito e sicuro un documento da ChromaDB, stato sessione, scadenze ed estrazioni."""
    ss = st.session_state
    remove_document_from_chromadb(doc_name)
    ss.indexed_documents.pop(doc_name, None)
    ss.processing_errors.pop(doc_name, None)
    evict_document(ss.extracted_data, ss.reviewed_data, ss.editor_version, doc_name)
    deactivate_deadlines_for_document(doc_name)
    for k in ("routing_plan", "routing_overrides", "routed_to"):
        if k in ss and isinstance(ss[k], dict):
            ss[k].pop(doc_name, None)
    ss.platform_xlsx = None


def process_single_document(file) -> int:
    pages = load_document_content(file, file.name)
    if not pages:
        raise ValueError("Nessun testo leggibile estratto dal documento.")

    for p in pages:
        p["document_name"] = file.name

    chunks = split_text_into_chunks(pages, file.name)
    if not chunks:
        raise ValueError("Il documento non ha prodotto chunk validi.")

    chunk_texts = [c["text"] for c in chunks]
    embeddings = get_batch_embeddings(chunk_texts)

    remove_document_from_chromadb(file.name, collection_name="document_chunks")
    store_chunks_in_chromadb(chunks, embeddings, collection_name="document_chunks")
    doc_id = create_document(st.session_state.user_id, file.name)

    st.session_state.indexed_documents[file.name] = {
        "id": doc_id,
        "chunks": len(chunks),
        "pages": pages,
        "status": "Ready"
    }

    if file.name in st.session_state.processing_errors:
        del st.session_state.processing_errors[file.name]

    return len(chunks)


def build_export_payload(mid: str) -> Dict[str, Any]:
    out = {}
    mod_data = st.session_state.extracted_data.get(mid, {})
    for s_name, res in mod_data.items():
        reviewed = st.session_state.reviewed_data.get(mid, {}).get(s_name)
        recs = reviewed if reviewed is not None else res.get("records", [])
        out[s_name] = {**res, "records": recs, "total_records": len(recs)}
    return out


EXCLUDE_LABEL = "— Escludi dall'analisi —"


def _route_labels() -> Dict[Any, str]:
    out = {}
    for m in list_modules():
        short = m.label.split("—")[0].strip()
        for sname, s in m.schemas.items():
            out[(m.module_id, sname)] = f"{short} › {s.label} ({sname})"
    return out


def _build_platform_report(labels: Dict[Any, str], effective: Dict[str, Any]) -> None:
    ss = st.session_state
    ss.platform_xlsx = (
        create_platform_excel_report(
            documents=[{"filename": n} for n in ss.indexed_documents],
            extracted_data_all_modules=collect_payload(ss.extracted_data, ss.reviewed_data),
            company_profile=ss.company_profile,
            routing={d: labels[r] for d, r in effective.items() if r in labels},
            errors=collect_errors(ss.extracted_data),
        ),
        datetime.now(),
    )


def render_platform_pipeline(preferred_module: str) -> None:
    ss = st.session_state
    docs = ss.indexed_documents
    labels = _route_labels()
    by_label = {v: k for k, v in labels.items()}

    with st.expander(":material/auto_mode: Analisi Automatica Piattaforma (Routing & Fascicolo)", expanded=True):
        st.caption("I documenti vengono assegnati in modo deterministico al modulo/schema più adatto "
                   "(regole in schemas/*.json). È possibile correggere l'instradamento prima dell'avvio.")

        new_docs = {n: m["pages"] for n, m in docs.items() if n not in ss.routing_plan}
        if new_docs:
            ss.routing_plan.update(build_routing_plan(new_docs, preferred_module))

        rows = []
        for name in docs:
            dec = ss.routing_plan[name]
            route = ss.routing_overrides.get(name, dec.route)
            rows.append({"Documento": name, "Instradamento": labels.get(route, EXCLUDE_LABEL),
                         "Score": round(dec.score, 1), "Esito": dec.reason})

        edited = st.data_editor(
            pd.DataFrame(rows), hide_index=True, use_container_width=True,
            key=f"routing_editor_{abs(hash(tuple(docs)))}",
            column_config={"Instradamento": st.column_config.SelectboxColumn(
                options=[EXCLUDE_LABEL] + list(by_label), required=True)},
            disabled=["Documento", "Score", "Esito"],
        )

        effective: Dict[str, Any] = {}
        for _, row in edited.iterrows():
            name, route = row["Documento"], by_label.get(row["Instradamento"])
            effective[name] = route
            if route != ss.routing_plan[name].route:
                ss.routing_overrides[name] = route
            else:
                ss.routing_overrides.pop(name, None)

        c_run, c_rebuild = st.columns(2)
        run = c_run.button("Esegui analisi completa", icon=":material/play_arrow:", type="primary", use_container_width=True,
                           help="Estrae solo i documenti non ancora analizzati, sincronizza le scadenze e genera il fascicolo.")
        rebuild = c_rebuild.button("Rigenera solo fascicolo", icon=":material/refresh:", use_container_width=True,
                                   help="Ricostruisce il fascicolo Excel includendo le modifiche fatte nella griglia di revisione.")

        if run:
            for doc, route in effective.items():
                old = ss.routed_to.get(doc)
                if old and old != route:
                    evict_document(ss.extracted_data, ss.reviewed_data, ss.editor_version, doc, only_route=old)
                    ss.routed_to.pop(doc, None)

            tasks = pending_tasks(effective, ss.extracted_data)
            pages_by_doc = {n: m["pages"] for n, m in docs.items()}
            failures = {}
            if tasks:
                with st.status(f"Estrazione in corso: {len(tasks)} operazioni…", expanded=True) as status:
                    bar = st.empty()
                    progress_bar(bar, 0, len(tasks), "Analisi intelligente dei documenti")

                    def on_progress(done, total, doc, sname, err):
                        progress_bar(bar, done, total, "Analisi intelligente dei documenti")
                        st.write(f"{'✗' if err else '✓'} **{doc}** → `{sname}`" + (f" — {err}" if err else ""))
                        if err:
                            failures[doc] = err

                    results = run_batch_extraction(tasks, pages_by_doc, max_workers=3, on_progress=on_progress)
                    apply_results(ss.extracted_data, ss.reviewed_data, ss.editor_version, ss.routed_to, results)
                    status.update(label=f"Estrazione completata ({len(tasks) - len(failures)}/{len(tasks)} OK)",
                                  state="complete" if not failures else "error", expanded=bool(failures))
            else:
                st.info("Nessun documento nuovo da analizzare.")

            with loader("Generazione del fascicolo", "Sincronizzazione scadenze e creazione Excel…", "sheet"):
                payload = collect_payload(ss.extracted_data, ss.reviewed_data)
                n_dl = sync_deadlines_to_db(payload, docs.keys())
                _build_platform_report(labels, effective)
            st.success(f"Fascicolo pronto · {n_dl} scadenze sincronizzate per il monitoraggio.")
        elif rebuild:
            with loader("Rigenerazione del fascicolo", "Inclusione delle modifiche di revisione…", "sheet"):
                sync_deadlines_to_db(collect_payload(ss.extracted_data, ss.reviewed_data), docs.keys())
                _build_platform_report(labels, effective)

        if ss.platform_xlsx:
            data, ts = ss.platform_xlsx
            target_mid = preferred_module
            if not any(v.get("records") for v in build_export_payload(target_mid).values()):
                for cand_mid in ss.extracted_data:
                    if any(v.get("records") for v in build_export_payload(cand_mid).values()):
                        target_mid = cand_mid
                        break
            mod_obj = get_module(target_mid)
            prefix = mod_obj.report.get("filename_prefix", "REPORT")
            word_payload = build_export_payload(target_mid)
            word_bytes = create_styled_word_report(
                extracted_data_by_schema=word_payload,
                source_documents=list(docs),
                company_profile=ss.company_profile,
                selected_fields_by_schema=ss.export_fields.get(target_mid, {}),
                module_id=target_mid,
            )
            c_dl_xlsx, c_dl_docx = st.columns(2)
            with c_dl_xlsx:
                st.download_button(
                    label=f"Scarica Fascicolo Gestionale Completo (.xlsx) — {ts:%H:%M:%S}",
                    icon=":material/download:",
                    data=data,
                    file_name=f"Report_Gestionale_Completo_{ts:%Y%m%d_%H%M}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            with c_dl_docx:
                st.download_button(
                    label=f"Scarica Report Word ({prefix}) — {ts:%H:%M:%S}",
                    icon=":material/description:",
                    data=word_bytes,
                    file_name=f"Verbale_{prefix}_{ts:%Y%m%d_%H%M}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )



def render_ui():
    favicon = None
    try:
        if FAVICON_PATH.is_file():
            with Image.open(FAVICON_PATH) as image:
                favicon = image.copy()
    except (OSError, ValueError):
        favicon = None

    st.set_page_config(
        page_title="inambiente · Document Intelligence Platform",
        page_icon=favicon or "🌿",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_custom_css()

    initialize_session()

    flash = st.session_state.pop("flash_msg", None)
    if flash:
        st.toast(flash)

    ss = st.session_state
    modules = {m.module_id: m for m in list_modules()}
    if not modules:
        st.error("Nessun modulo operativo disponibile. Verificare schemas/*.json.")
        return

    with st.sidebar:
        render_brand_header()
        st.markdown("<div class='nav-eyebrow'>WORKSPACE</div>", unsafe_allow_html=True)
        page = st.radio(
            "Navigazione principale",
            options=[
                "📄  Document Hub & Batch Pipeline",
                "🏢  Profilo Aziendale / Tenant",
                "💬  Document Chat (RAG)",
                "📊  Estrazione & Revisione",
                "⏰  Scadenze & Allerte",
            ],
            key="workspace_page",
            label_visibility="collapsed",
        )
        st.divider()
        sidebar_label("Modulo operativo")
        selected_mod_id = st.selectbox(
            "Modulo / Standard Operativo",
            options=list(modules),
            format_func=lambda k: modules[k].label,
            key="active_module",
            help="Determina gli schemi di estrazione e i report ufficiali.",
        )
        current_module = modules[selected_mod_id]
        company_name = (ss.company_profile.get("company_name") or "").strip()
        st.markdown(
            f"<div class='tenant-mini'><span class='tenant-dot'></span><div><b>{company_name or 'Tenant non configurato'}</b>"
            f"<small>{len(ss.indexed_documents)} documenti attivi</small></div></div>",
            unsafe_allow_html=True,
        )
        with st.expander("Strumenti amministrativi", expanded=False):
            if st.button("Ricarica schemi", icon=":material/refresh:", use_container_width=True):
                reload_registry()
                st.success("Schemi aggiornati.")
                st.rerun()
            if st.button("Nuova conversazione", icon=":material/chat:", use_container_width=True):
                reset_conversation()
                st.rerun()
            danger_zone_marker()
            st.caption("L'operazione elimina l'indice vettoriale persistente.")
            confirm_reset = st.checkbox("Confermo il reset dell'indice", key="confirm_reset_index")
            st.button(
                "Reset indice vettoriale", icon=":material/delete_forever:",
                use_container_width=True, disabled=not confirm_reset,
                key="btn_reset_index", on_click=_reset_vector_index_callback,
            )

    render_page_header(current_module.label, current_module.version, company_name)

    # PAGE 1 — upload, preview, routing and batch pipeline
    if page.startswith("📄"):
        section_title("Document Hub & Batch Pipeline", "Caricamento, anteprima, routing deterministico ed esportazione del fascicolo.")
        uploaded_files = st.file_uploader(
            "Aggiungi documenti all'area di lavoro",
            type=["pdf", "docx", "xlsx", "xls", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            help="PDF digitali o scansionati, Word, Excel e immagini.",
            key="workspace_file_uploader",
        )
        if uploaded_files:
            todo = [f for f in uploaded_files if f.name not in ss.indexed_documents and f.name not in ss.processing_errors]
            if todo:
                with st.status(f"Indicizzazione di {len(todo)} documenti…", expanded=True) as status:
                    for f in todo:
                        try:
                            with loader(f"Lettura di {f.name}", "Indicizzazione e preparazione della ricerca documentale…", "orbit"):
                                count = process_single_document(f)
                            st.write(f"✓ {f.name} — {count} segmenti indicizzati")
                        except Exception as exc:
                            ss.processing_errors[f.name] = str(exc)
                            st.write(f"✕ {f.name} — {exc}")
                    status.update(label="Indicizzazione completata", state="complete", expanded=False)

        docs = ss.indexed_documents
        k1, k2, k3 = st.columns(3)
        k1.metric("Documenti attivi", len(docs))
        k2.metric("Indicizzati", sum(1 for d in docs.values() if d.get("status") == "Ready"))
        k3.metric("Errori di lettura", len(ss.processing_errors))
        if docs:
            st.markdown("#### Documenti nell'area di lavoro")
            rows = [{"Documento": n, "Pagine": len(m.get("pages", [])), "Segmenti": m.get("chunks", 0), "Stato": m.get("status", "Ready")} for n, m in docs.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            c_del_doc, c_del_btn, c_del_all = st.columns([2.5, 1, 1], gap="small")
            with c_del_doc:
                target_to_remove = st.selectbox(
                    "Seleziona documento da rimuovere",
                    options=list(docs.keys()),
                    key="sel_remove_doc",
                    label_visibility="collapsed",
                )
            with c_del_btn:
                if st.button("Elimina documento", icon=":material/delete:", use_container_width=True):
                    if target_to_remove:
                        remove_single_document(target_to_remove)
                        st.toast(f"Documento '{target_to_remove}' rimosso dall'area di lavoro.")
                        st.rerun()
            with c_del_all:
                if st.button("Svuota tutto", icon=":material/delete_sweep:", use_container_width=True):
                    for d in list(docs.keys()):
                        remove_single_document(d)
                    reset_conversation()
                    ss.extracted_data.clear()
                    ss.reviewed_data.clear()
                    st.toast("Tutti i documenti sono stati rimossi.")
                    st.rerun()

            with st.expander("🔍 Anteprima testo estratto (Opzionale)", expanded=False):
                preview_name = st.selectbox("Seleziona documento da visualizzare", options=list(docs), key="hub_preview_doc")
                pages = docs[preview_name].get("pages", [])
                if pages:
                    page_opts = list(range(len(pages)))
                    selected_page = st.selectbox("Pagina", page_opts, format_func=lambda n: f"Pagina {n + 1}", key="hub_preview_page")
                    with st.container(border=True):
                        st.caption(f"{preview_name} · pagina {selected_page + 1}")
                        st.text((pages[selected_page].get("text") or "Testo non disponibile")[:12000])
            if ss.processing_errors:
                with st.expander("Documenti con errori", expanded=True):
                    for name, error in ss.processing_errors.items():
                        st.error(f"{name}: {error}")
                    if st.button("Cancella errori", icon=":material/clear_all:", key="btn_clear_proc_errors"):
                        ss.processing_errors.clear()
                        st.rerun()
            st.divider()
            render_platform_pipeline(current_module.module_id)
        else:
            if ss.processing_errors:
                with st.expander("Documenti con errori", expanded=True):
                    for name, error in ss.processing_errors.items():
                        st.error(f"{name}: {error}")
                    if st.button("Cancella errori", icon=":material/clear_all:", key="btn_clear_proc_errors_empty"):
                        ss.processing_errors.clear()
                        st.rerun()
            st.info("Carica uno o più documenti per avviare il workspace.")

    # PAGE 2 — tenant profile
    elif page.startswith("🏢"):
        section_title("Profilo Aziendale / Tenant", "Metadati riutilizzati nelle intestazioni e nelle firme dei report ufficiali.")
        prof = ss.company_profile
        with st.container(border=True):
            st.markdown("#### Identità legale e sede")
            c1, c2 = st.columns(2, gap="large")
            with c1:
                c_name = st.text_input("Ragione sociale", value=prof.get("company_name", ""), placeholder="inambiente S.r.l.", key="tenant_company_name")
                c_vat = st.text_input("Partita IVA / Codice fiscale", value=prof.get("vat_number", ""), key="tenant_vat")
            with c2:
                c_addr = st.text_area("Sede operativa", value=prof.get("address", ""), height=100, key="tenant_address")
                c_rsga = st.text_input("Responsabile SGA / referente", value=prof.get("rsga_name", ""), key="tenant_rsga")
        with st.container(border=True):
            st.markdown("#### Direzione tecnica e firme")
            c_dir = st.text_input("Direzione tecnica / firmatario", value=prof.get("technical_director", ""), key="tenant_director")
            st.caption("I campi disponibili riflettono lo schema del profilo aziendale attualmente supportato dal database.")
        if st.button("Salva profilo aziendale", icon=":material/save:", type="primary", use_container_width=True):
            update_company_profile(c_name.strip(), c_vat.strip(), c_addr.strip(), c_rsga.strip(), c_dir.strip())
            ss.company_profile = {"company_name": c_name.strip(), "vat_number": c_vat.strip(), "address": c_addr.strip(), "rsga_name": c_rsga.strip(), "technical_director": c_dir.strip()}
            st.success("Profilo aziendale salvato.")
            st.rerun()
        st.markdown("#### Anteprima intestazione")
        with st.container(border=True):
            st.markdown(f"**{c_name.strip() or 'Ragione sociale non impostata'}**")
            st.write(c_addr.strip() or "Sede operativa non impostata")
            st.caption(f"P.IVA: {c_vat.strip() or '—'} · Responsabile SGA: {c_rsga.strip() or '—'} · Direzione tecnica: {c_dir.strip() or '—'}")

    # PAGE 3 — full-page RAG chat. Top-K remains config-driven.
    elif page.startswith("💬"):
        section_title("Document Chat", "Interroga il contenuto dei documenti attivi. Le risposte si basano sui passaggi recuperati.")
        history = get_conversation_history(ss.conversation_id)
        with st.container(height=500, border=True):
            if not history:
                st.info("La conversazione è vuota. Inserisci una domanda sui documenti indicizzati.")
            for msg in history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        query = st.chat_input("Scrivi una domanda sui documenti attivi…")
        if query:
            if not ss.indexed_documents:
                st.warning("Prima carica almeno un documento nella pagina Document Hub.")
            else:
                with loader("Ricerca nei documenti", "Recupero semantico e generazione della risposta…", "orbit"):
                    try:
                        payload = collect_payload(ss.get("extracted_data", {}), ss.get("reviewed_data", {}))
                        chat_ctx = build_chat_structured_context(payload, ss.indexed_documents)
                        chunks = retrieve_relevant_chunks(query=query, collection_name="document_chunks", top_k=RAG_TOP_K, document_names=list(ss.indexed_documents))
                        answer = generate_answer(build_rag_prompt(query, chunks, structured_context=chat_ctx.text, domain_guidelines=chat_ctx.guidelines))
                        save_message(ss.conversation_id, "user", query)
                        save_message(ss.conversation_id, "assistant", answer)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Impossibile completare la ricerca: {exc}")

    # PAGE 4 — extraction, human review, official exports
    elif page.startswith("📊"):
        mid = current_module.module_id
        section_title("Estrazione & Revisione", "Estrazione strutturata, revisione manuale e report ufficiali Excel/Word.")
        schemas = list(current_module.schemas)
        if not schemas:
            st.warning("Nessuno schema disponibile per il modulo selezionato.")
            return
        default_schema_idx = 0
        mod_extracted = ss.extracted_data.get(mid, {})
        for idx, s in enumerate(schemas):
            if mod_extracted.get(s, {}).get("records"):
                default_schema_idx = idx
                break
        schema_name = st.selectbox(
            "Schema di estrazione",
            schemas,
            index=default_schema_idx,
            format_func=lambda s: f"{current_module.schemas[s].label} — {current_module.schemas[s].description.split('.')[0]}.",
            key=f"schema_select_{mid}",
        )
        schema = current_module.schemas[schema_name]
        if not ss.indexed_documents:
            st.info("Carica prima i documenti dalla pagina Document Hub.")
        else:
            doc_options = ["ALL ACTIVE DOCUMENTS"] + list(ss.indexed_documents)
            target = st.selectbox("Documenti sorgente", doc_options, key=f"doc_target_{mid}")
            if st.button("Avvia estrazione strutturata", icon=":material/bolt:", type="primary", use_container_width=True):
                chosen = ss.indexed_documents if target == "ALL ACTIVE DOCUMENTS" else {target: ss.indexed_documents[target]}
                pages_map = {name: meta["pages"] for name, meta in chosen.items()}
                with loader(f"Estrazione: {schema.label}", "Normalizzazione e calcoli deterministici…", "bar"):
                    result = extract_for_documents(pages_map, schema_name, module_id=mid)
                    done = [d for d in pages_map if d not in result.get("errors", {})]
                    existing = ss.extracted_data.get(mid, {}).get(schema_name)
                    ss.extracted_data.setdefault(mid, {})[schema_name] = merge_result(existing, {**result, "processed_documents": done})
                    ss.reviewed_data.setdefault(mid, {}).pop(schema_name, None)
                    vkey = (mid, schema_name)
                    ss.editor_version[vkey] = ss.editor_version.get(vkey, 0) + 1
                for name, error in result.get("errors", {}).items():
                    st.warning(f"{name}: {error}")
                if not result.get("errors"):
                    st.success(f"Record estratti: {result.get('total_records', 0)}")
        current = ss.extracted_data.get(mid, {}).get(schema_name)
        if current and current.get("records"):
            records = current["records"]
            reviewed = ss.reviewed_data.get(mid, {}).get(schema_name)
            source_records = reviewed if reviewed is not None else records
            st.metric("Record disponibili per revisione", len(source_records))
            df = records_to_dataframe(source_records, schema)
            version = ss.editor_version.get((mid, schema_name), 0)
            edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic", key=f"editor_{mid}_{schema_name}_{version}", column_config={"_rid": None}, disabled=["source_document", "source_page"])
            ss.reviewed_data.setdefault(mid, {})[schema_name] = dataframe_to_records(edited_df, source_records, schema)
            st.caption("Le modifiche manuali vengono normalizzate nuovamente e i campi derivati sono ricalcolati dal motore esistente.")
            fields = schema.ordered_field_names()
            labels = schema.all_labels()
            selected = st.multiselect("Campi inclusi nei report", fields, default=ss.export_fields.get(mid, {}).get(schema_name, fields), format_func=lambda f: labels.get(f, f), key=f"export_cols_{mid}_{schema_name}")
            ss.export_fields.setdefault(mid, {})[schema_name] = selected
            payload = build_export_payload(mid)
            prefix = current_module.report.get("filename_prefix", "REPORT")
            c_excel, c_word = st.columns(2, gap="large")
            excel_bytes = create_styled_excel_report(extracted_data_by_schema=payload, source_documents=list(ss.indexed_documents), company_profile=ss.company_profile, selected_fields_by_schema=ss.export_fields.get(mid, {}), module_id=mid)
            word_bytes = create_styled_word_report(extracted_data_by_schema=payload, source_documents=list(ss.indexed_documents), company_profile=ss.company_profile, selected_fields_by_schema=ss.export_fields.get(mid, {}), module_id=mid)
            with c_excel:
                st.download_button("Scarica Excel ufficiale", excel_bytes, file_name=f"Report_{prefix}_{schema_name}_{datetime.now():%Y%m%d}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_chart:", use_container_width=True)
            with c_word:
                st.download_button("Scarica report Word", word_bytes, file_name=f"Verbale_{prefix}_{datetime.now():%Y%m%d}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", icon=":material/description:", use_container_width=True)

    # PAGE 5 — deadlines and notifications
    elif page.startswith("⏰"):
        section_title("Monitoraggio Scadenze & Allerte", "Scadenze attive, stato di conformità e gestione dei canali di notifica.")
        active = get_active_deadlines()
        today = datetime.now().date()
        overdue = 0
        soon = 0
        for item in active:
            try:
                days = (datetime.fromisoformat(str(item["due_date"])).date() - today).days
                overdue += days < 0
                soon += 0 <= days <= 30
            except (ValueError, TypeError, KeyError):
                pass
        a, b, c = st.columns(3)
        a.metric("Scadenze attive", len(active))
        b.metric("Scadute", overdue)
        c.metric("Entro 30 giorni", soon)
        c_sync, c_sim = st.columns(2, gap="large")
        with c_sync:
            if st.button("Sincronizza scadenze dai record", icon=":material/sync:", use_container_width=True):
                count = sync_deadlines_to_db(collect_payload(ss.extracted_data, ss.reviewed_data), ss.indexed_documents.keys())
                st.success(f"Scadenze sincronizzate: {count}")
                st.rerun()
        with c_sim:
            if st.button("Simula invio (dry-run)", icon=":material/science:", use_container_width=True):
                ss.last_dispatch_result = ("dry_run", dispatch_alerts(dry_run=True))
        email_ok = SmtpEmailNotifier().configured
        sms_ok = TwilioSmsNotifier().configured
        st.markdown("#### Canali di notifica")
        e1, e2 = st.columns(2)
        e1.markdown(f"**Email** · {'Configurato' if email_ok else 'Non configurato'}")
        e2.markdown(f"**SMS** · {'Configurato' if sms_ok else 'Non configurato'}")
        if st.button("Invia allerte reali", icon=":material/send:", type="primary", use_container_width=True, disabled=not (email_ok or sms_ok)):
            with loader("Invio notifiche", "Invio email e SMS…", "bar"):
                ss.last_dispatch_result = ("live", dispatch_alerts(dry_run=False))
        last = ss.get("last_dispatch_result")
        if last:
            mode, result = last
            st.caption("Risultato simulazione" if mode == "dry_run" else "Risultato invio reale")
            render_stat_chips([
                ("Email inviate", result.get("sent_email", 0), "ok" if result.get("sent_email", 0) else "muted"),
                ("SMS inviati", result.get("sent_sms", 0), "ok" if result.get("sent_sms", 0) else "muted"),
                ("Già gestite", result.get("skipped", 0), "muted"),
                ("Simulate", result.get("simulated", 0), "warn" if result.get("simulated", 0) else "muted"),
                ("Fallite", result.get("failed", 0), "crit" if result.get("failed", 0) else "muted"),
            ])
        st.markdown("#### Registro scadenze attive")
        if active:
            df = pd.DataFrame(active)
            cols = [c for c in ["due_date", "description", "module_id", "source_document", "source_page"] if c in df.columns]
            df = df[cols].rename(columns={"due_date": "Data scadenza", "description": "Obbligo", "module_id": "Modulo", "source_document": "Documento", "source_page": "Pagina"})
            st.dataframe(df, use_container_width=True, hide_index=True)
            if st.button("Svuota registro scadenze", icon=":material/delete_forever:", use_container_width=True, key="btn_clear_deadlines"):
                n_removed = deactivate_all_deadlines()
                ss.last_dispatch_result = None
                ss.flash_msg = f"Registro scadenze svuotato · {n_removed} scadenze rimosse."
                st.rerun()
        else:
            st.info("Nessuna scadenza attiva nel database.")
        st.divider()
        st.markdown("#### Destinatari")
        r1, r2 = st.columns([2, 1])
        with r1:
            address = st.text_input("Email o numero di telefono", key="new_alert_addr")
        with r2:
            channel = st.selectbox("Canale", ["email", "sms"], key="new_alert_ch")
        if st.button("Aggiungi destinatario", icon=":material/person_add:", use_container_width=True):
            clean = address.strip()
            valid = ("@" in clean and "." in clean) if channel == "email" else len(clean) >= 8
            if not clean or not valid:
                st.warning("Inserisci un indirizzo email o un numero di telefono valido.")
            else:
                import uuid
                if add_recipient(str(uuid.uuid4()), channel, clean):
                    st.success("Destinatario aggiunto.")
                    st.rerun()
                else:
                    st.error("Impossibile salvare il destinatario.")
        recipients = get_active_recipients()
        if recipients:
            st.dataframe(pd.DataFrame([{"Canale": r["channel"].upper(), "Destinatario": r["address"]} for r in recipients]), use_container_width=True, hide_index=True)
            c_sel_rec, c_del_rec, c_clear_rec = st.columns([2.5, 1.2, 1.3], gap="small")
            with c_sel_rec:
                target_rec_id = st.selectbox(
                    "Seleziona destinatario da rimuovere",
                    options=[r["id"] for r in recipients],
                    format_func=lambda rid: next(f"[{r['channel'].upper()}] {r['address']}" for r in recipients if r["id"] == rid),
                    key="sel_remove_recipient",
                    label_visibility="collapsed",
                )
            with c_del_rec:
                if st.button("Rimuovi destinatario", icon=":material/delete:", use_container_width=True, key="btn_remove_recipient"):
                    if target_rec_id and deactivate_recipient_by_id(target_rec_id):
                        st.toast("Destinatario rimosso con successo.")
                        st.rerun()
            with c_clear_rec:
                if st.button("Svuota tutti i destinatari", icon=":material/delete_forever:", use_container_width=True, key="btn_clear_all_recipients"):
                    count = deactivate_all_recipients()
                    st.toast(f"Tutti i destinatari sono stati rimossi ({count}).")
                    st.rerun()
        else:
            st.info("Nessun destinatario configurato.")


if __name__ == "__main__":
    render_ui()
