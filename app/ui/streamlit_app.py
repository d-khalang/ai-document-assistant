import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from app.ui.theme import inject_custom_css, render_kpi_row
from app.alerts.store import (
    ensure_alert_tables,
    upsert_deadline,
    get_active_deadlines,
    add_recipient,
    get_active_recipients
)
from app.alerts.scanner import scan_deadlines
from app.alerts.store import deactivate_deadlines_for_document
from app.extraction.pipeline import (
    apply_results, build_routing_plan, collect_errors, collect_payload, evict_document,
    merge_result, pending_tasks, run_batch_extraction, sync_deadlines_to_db,
)
from app.alerts.deadlines import extract_deadlines_from_records
from app.alerts.dispatcher import dispatch_alerts
from app.alerts.notifiers import SmtpEmailNotifier, TwilioSmsNotifier
from app.reporting.platform_excel_exporter import create_platform_excel_report

from app.ai.gemini import generate_answer
from app.ai.prompts import build_rag_prompt
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
    create_document,
    create_conversation,
    save_message,
    get_conversation_history,
    get_company_profile,
    update_company_profile,
)


def initialize_session():
    """مقداردهی اولیه با فیلدهای شرکتی کاملاً خالی در شروع هر نشست."""
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

    # در شروع هر بار باز شدن وب‌اپ، اطلاعات شرکت کاملاً خالی است تا کاربر خودش پر کند
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


def process_single_document(file) -> int:
    pages = load_document_content(file, file.name)
    if not pages:
        raise ValueError("No readable text could be extracted from document.")

    for p in pages:
        p["document_name"] = file.name

    chunks = split_text_into_chunks(pages, file.name)
    if not chunks:
        raise ValueError("Document did not produce any valid chunks.")

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
    """One-click flow: deterministic routing -> parallel extraction -> deadline sync -> executive report."""
    ss = st.session_state
    docs = ss.indexed_documents
    labels = _route_labels()
    by_label = {v: k for k, v in labels.items()}

    with st.expander("🚀 Analisi Automatica Piattaforma (Routing + Estrazione + Fascicolo)", expanded=True):
        st.caption("I documenti vengono assegnati in modo deterministico al modulo/schema più adatto "
                   "(regole in schemas/*.json). Puoi correggere l'instradamento prima di avviare.")

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
        run = c_run.button("▶️ Esegui analisi completa", type="primary", use_container_width=True,
                           help="Estrae solo i documenti non ancora analizzati, sincronizza le scadenze e genera il fascicolo.")
        rebuild = c_rebuild.button("📊 Rigenera solo il fascicolo", use_container_width=True,
                                   help="Ricostruisce l'Excel includendo le modifiche fatte nella griglia di revisione.")

        if run:
            # documents re-routed by the user: drop their records from the previous schema
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
                    bar = st.progress(0.0)

                    def on_progress(done, total, doc, sname, err):  # runs in the script thread
                        bar.progress(done / total)
                        st.write(f"{'✗' if err else '✓'} **{doc}** → `{sname}`" + (f" — {err}" if err else ""))
                        if err:
                            failures[doc] = err

                    results = run_batch_extraction(tasks, pages_by_doc, max_workers=3, on_progress=on_progress)
                    apply_results(ss.extracted_data, ss.reviewed_data, ss.editor_version, ss.routed_to, results)
                    status.update(label=f"Estrazione completata ({len(tasks) - len(failures)}/{len(tasks)} OK)",
                                  state="complete" if not failures else "error", expanded=bool(failures))
            else:
                st.info("Nessun documento nuovo da analizzare.")

            payload = collect_payload(ss.extracted_data, ss.reviewed_data)
            n_dl = sync_deadlines_to_db(payload, docs.keys())
            _build_platform_report(labels, effective)
            st.success(f"Fascicolo pronto · {n_dl} scadenze sincronizzate per il monitoraggio.")
        elif rebuild:
            sync_deadlines_to_db(collect_payload(ss.extracted_data, ss.reviewed_data), docs.keys())
            _build_platform_report(labels, effective)

        if ss.platform_xlsx:
            data, ts = ss.platform_xlsx
            st.download_button(
                label=f"📥 Scarica Fascicolo Gestionale Completo (.xlsx) — generato {ts:%H:%M:%S}",
                data=data,
                file_name=f"Report_Gestionale_Completo_{ts:%Y%m%d_%H%M}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


def render_ui():
    st.set_page_config(
        page_title="AI Document Intelligence Platform",
        page_icon="📋",
        layout="wide",
    )
    inject_custom_css()

    initialize_session()
    total_chunks = sum(doc["chunks"] for doc in st.session_state.indexed_documents.values())

    with st.sidebar:
        st.header("⚙️ Workspace & Standards")

        available_mods = {m.module_id: m for m in list_modules()}
        selected_mod_id = st.selectbox(
            "🧩 Modulo / Standard Operativo:",
            options=list(available_mods.keys()),
            format_func=lambda k: available_mods[k].label,
            key="active_module"
        )
        current_module = available_mods[selected_mod_id]

        st.caption(f"**Versione Standard:** `{current_module.version}`")
        if st.button("🔄 Ricarica Schemi (Hot Reload)", use_container_width=True, help="Ricarica i file JSON da schemas/ senza riavviare Streamlit"):
            reload_registry()
            st.success("Schemi e moduli aggiornati da disco!")
            st.rerun()

        st.divider()

        with st.expander("🏢 Profilo Aziendale / Tenant", expanded=False):
            prof = st.session_state.company_profile
            c_name = st.text_input("Ragione Sociale:", value=prof.get("company_name", ""), placeholder="es. Acme Solutions S.p.A.")
            c_vat = st.text_input("P.IVA / Codice Fiscale:", value=prof.get("vat_number", ""), placeholder="es. IT12345678901")
            c_addr = st.text_input("Sede Operativa:", value=prof.get("address", ""), placeholder="es. Via Roma 10, Torino (TO)")
            c_rsga = st.text_input("Responsabile SGA / Referente:", value=prof.get("rsga_name", ""), placeholder="es. Ing. Mario Rossi")
            c_dir = st.text_input("Direzione Tecnica / Firmatario:", value=prof.get("technical_director", ""), placeholder="es. Dott. Giuseppe Verdi")

            if st.button("💾 Salva Profilo Aziendale", use_container_width=True):
                update_company_profile(c_name, c_vat, c_addr, c_rsga, c_dir)
                st.session_state.company_profile = {
                    "company_name": c_name.strip(),
                    "vat_number": c_vat.strip(),
                    "address": c_addr.strip(),
                    "rsga_name": c_rsga.strip(),
                    "technical_director": c_dir.strip()
                }
                st.success("Profilo aziendale salvato!")
                st.rerun()

        st.divider()
        st.subheader("📚 Active Knowledge Base")
        st.write(f"**Documenti Caricati:** `{len(st.session_state.indexed_documents)}`")
        st.write(f"**Chunk Indicizzati:** `{total_chunks}`")

        if st.session_state.indexed_documents:
            for fname, meta in st.session_state.indexed_documents.items():
                st.caption(f"✓ **{fname}** ({meta['chunks']} chunks)")

        st.divider()
        if st.button("🔄 Nuova Sessione Chat", use_container_width=True):
            reset_conversation()
            st.rerun()

        with st.expander("🛠 Manutenzione Vettoriale", expanded=False):
            st.caption("Elimina l'intero indice ChromaDB persistente su disco.")
            if st.button("🗑️ Reset Totale Indice Vettoriale", use_container_width=True):
                clear_chroma_collection()
                st.session_state.indexed_documents.clear()
                reset_conversation()
                st.session_state.extracted_data.clear()
                st.session_state.reviewed_data.clear()
                st.success("Indice vettoriale azzerato!")
                st.rerun()

    active_comp = st.session_state.company_profile.get("company_name", "").strip()
    caption_tenant = f" | {active_comp}" if active_comp else ""
    st.title(f"📋 {current_module.label}")
    st.caption(f"Enterprise Document Intelligence — Multi-Tenant Platform{caption_tenant}")

    mid = current_module.module_id
    total_docs = len(st.session_state.indexed_documents)

    mod_records = sum(
        len(st.session_state.reviewed_data.get(mid, {}).get(s, res.get("records", [])))
        for s, res in st.session_state.extracted_data.get(mid, {}).items()
    )

    try:
        active_deadlines = get_active_deadlines()
        urgent_alerts = scan_deadlines(active_deadlines, max_overdue_days=30)
        urgent_count = len([a for a in urgent_alerts if a.days_left <= 30])
        urgent_level = "crit" if urgent_count > 0 else ""
    except Exception:
        urgent_count = 0
        urgent_level = ""

    kpi_items = [
        ("Documenti Attivi", total_docs, "Knowledge Base", ""),
        ("Chunk Vettoriali", total_chunks, "ChromaDB Indice", ""),
        ("Record Estratti", mod_records, f"Modulo: {current_module.module_id}", ""),
        ("Scadenze (≤ 30 gg)", urgent_count, "Attenzione richiesta", urgent_level)
    ]
    render_kpi_row(kpi_items)

    col_ingest, col_workspace = st.columns([1, 1.2], gap="large")

    with col_ingest:
        st.subheader("1. Ingestion Pipeline")
        uploaded_files = st.file_uploader(
            "Carica documenti aziendali (PDF, DOCX, XLSX, Immagini):",
            type=["pdf", "docx", "xlsx", "xls", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            help="Supporta PDF nativi o scansionati, Word (.docx), fogli Excel (.xlsx/.xls) e immagini."
        )

        current_filenames = [f.name for f in uploaded_files] if uploaded_files else []

        indexed_names = list(st.session_state.indexed_documents.keys())
        for existing_name in indexed_names:
            if existing_name not in current_filenames:
                remove_document_from_chromadb(existing_name)
                del st.session_state.indexed_documents[existing_name]
                st.session_state.processing_errors.pop(existing_name, None)
                evict_document(st.session_state.extracted_data, st.session_state.reviewed_data,
                               st.session_state.editor_version, existing_name)
                deactivate_deadlines_for_document(existing_name)
                for key in ("routing_plan", "routing_overrides", "routed_to"):
                    st.session_state[key].pop(existing_name, None)
                st.session_state.platform_xlsx = None

        if not current_filenames and indexed_names:
            reset_conversation()
            st.session_state.extracted_data.clear()
            st.session_state.reviewed_data.clear()
            st.rerun()

        if uploaded_files:
            files_to_process = [
                f for f in uploaded_files 
                if f.name not in st.session_state.indexed_documents 
                and f.name not in st.session_state.processing_errors
            ]

            if files_to_process:
                with st.status(f"Elaborazione in corso ({len(files_to_process)} file)...", expanded=True) as status:
                    for f in files_to_process:
                        try:
                            st.write(f"Analisi **{f.name}**...")
                            chunk_count = process_single_document(f)
                            st.write(f"✓ **{f.name}**: indicizzato ({chunk_count} chunk)")
                        except Exception as e:
                            st.session_state.processing_errors[f.name] = str(e)
                            st.write(f"✗ **{f.name}**: errore ({str(e)})")

                    status.update(label="Elaborazione batch completata!", state="complete", expanded=False)
        else:
            st.session_state.processing_errors = {}

        if st.session_state.indexed_documents:
            st.success(f"Archivio attivo: {len(st.session_state.indexed_documents)} documenti pronti per RAG ed estrazione.")

            render_platform_pipeline(current_module.module_id)

        if st.session_state.processing_errors:
            st.error("Errori di elaborazione:")
            for fname, err in st.session_state.processing_errors.items():
                st.markdown(f"- ⚠️ **{fname}**: {err}")

    with col_workspace:
        tab_chat, tab_extraction, tab_deadlines = st.tabs([
            "💬 Document Chat (RAG)", 
            "📊 Structured Extraction & Review", 
            "⏰ Scadenze & Monitoraggio"
        ])

        with tab_chat:
            st.caption("Interroga semanticamente tutti i documenti attivi.")
            history = get_conversation_history(st.session_state.conversation_id)

            chat_container = st.container(height=380)
            with chat_container:
                if not history:
                    st.info("La Knowledge Base è attiva. Poni una domanda sui documenti.")
                for msg in history:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            with st.expander("⚙️ Parametri Avanzati di Ricerca (Opzionale)", expanded=False):
                top_k = st.slider(
                    "Profondità di contesto (Top-K Chunks):",
                    min_value=1,
                    max_value=8,
                    value=RAG_TOP_K,
                    help="Numero di frammenti di testo più rilevanti inviati al modello per la risposta."
                )
            user_query = st.chat_input("Fai una domanda sui documenti...")

            if user_query:
                if not st.session_state.indexed_documents:
                    st.warning("Carica almeno un documento prima di avviare la chat.")
                else:
                    with st.spinner("Sintesi della risposta dai documenti verificati..."):
                        try:
                            active_doc_names = list(st.session_state.indexed_documents.keys())
                            retrieved_chunks = retrieve_relevant_chunks(
                                query=user_query,
                                collection_name="document_chunks",
                                top_k=top_k,
                                document_names=active_doc_names
                            )
                            rag_prompt = build_rag_prompt(user_query, retrieved_chunks)
                            assistant_answer = generate_answer(rag_prompt)
                            save_message(st.session_state.conversation_id, "user", user_query)
                            save_message(st.session_state.conversation_id, "assistant", assistant_answer)
                            st.rerun()
                        except Exception as e:
                            st.error(f"⚠️ {str(e)}")

        with tab_extraction:
            mid = current_module.module_id
            st.caption(f"Estrazione mirata per: **{current_module.label}**")

            schema_names = list(current_module.schemas.keys())
            if not schema_names:
                st.warning("Nessuno schema disponibile per questo modulo.")
            else:
                schema_name = st.selectbox(
                    "Schema di Estrazione:",
                    options=schema_names,
                    format_func=lambda s: f"{current_module.schemas[s].label} — {current_module.schemas[s].description}",
                    key=f"schema_select_{mid}"
                )
                schema_def = current_module.schemas[schema_name]

                if not st.session_state.indexed_documents:
                    st.info("📂 Carica almeno un documento nella colonna di sinistra per abilitare l'estrazione.")
                else:
                    docs_map = st.session_state.indexed_documents
                    target_doc = st.selectbox(
                        "Documento Sorgente:",
                        options=["ALL ACTIVE DOCUMENTS"] + list(docs_map.keys()),
                        key=f"doc_target_{mid}"
                    )

                    if st.button("🚀 Avvia Estrazione Strutturata", use_container_width=True):
                        chosen_docs = (
                            docs_map if target_doc == "ALL ACTIVE DOCUMENTS" else {target_doc: docs_map[target_doc]}
                        )
                        pages_by_doc = {name: meta["pages"] for name, meta in chosen_docs.items()}

                        with st.spinner(f"Estrazione schema '{schema_def.label}' in corso..."):
                            result = extract_for_documents(pages_by_doc, schema_name, module_id=mid)
                            done = [d for d in pages_by_doc if d not in result.get("errors", {})]
                            existing = st.session_state.extracted_data.get(mid, {}).get(schema_name)
                            st.session_state.extracted_data.setdefault(mid, {})[schema_name] = merge_result(
                                existing, {**result, "processed_documents": done}
                            )
                            st.session_state.reviewed_data.setdefault(mid, {}).pop(schema_name, None)
                            
                            ver_key = (mid, schema_name)
                            st.session_state.editor_version[ver_key] = st.session_state.editor_version.get(ver_key, 0) + 1

                            if result.get("errors"):
                                for err_doc, err_msg in result["errors"].items():
                                    st.warning(f"⚠️ Errore su {err_doc}: {err_msg}")
                            else:
                                st.success(f"Estratti {result['total_records']} record con successo!")

                current_res = st.session_state.extracted_data.get(mid, {}).get(schema_name)
                if current_res and current_res.get("records"):
                    st.markdown(f"### 📋 Revisione Record: `{schema_def.label}`")
                    st.info("💡 Modifica i dati direttamente nella griglia: i valori modificati saranno ricalcolati e inseriti nei report finali.")

                    ver = st.session_state.editor_version.get((mid, schema_name), 0)
                    initial_records = current_res["records"]
                    df_for_editor = records_to_dataframe(initial_records, schema_def)

                    edited_df = st.data_editor(
                        df_for_editor,
                        use_container_width=True,
                        num_rows="dynamic",
                        key=f"editor_{mid}_{schema_name}_{ver}",
                        column_config={"_rid": None},
                        disabled=["source_document", "source_page"]
                    )

                    reviewed_records = dataframe_to_records(edited_df, initial_records, schema_def)
                    st.session_state.reviewed_data.setdefault(mid, {})[schema_name] = reviewed_records

                    st.caption(f"✓ Record verificati: `{len(reviewed_records)}` | Modulo attivo: `{current_module.label}`")

                    st.divider()
                    st.subheader("📥 Genera Report Ufficiali")
                    
                    all_schema_fields = schema_def.ordered_field_names()
                    schema_labels = schema_def.all_labels()
                    
                    selected_cols = st.multiselect(
                        "Seleziona colonne per l'esportazione:",
                        options=all_schema_fields,
                        default=all_schema_fields,
                        format_func=lambda f: schema_labels.get(f, f),
                        key=f"export_cols_{mid}_{schema_name}"
                    )
                    st.session_state.export_fields.setdefault(mid, {})[schema_name] = selected_cols

                    col_dl_excel, col_dl_word = st.columns(2)
                    payload = build_export_payload(mid)
                    prefix = current_module.report.get("filename_prefix", "REPORT")

                    with col_dl_excel:
                        excel_bytes = create_styled_excel_report(
                            extracted_data_by_schema=payload,
                            source_documents=list(st.session_state.indexed_documents.keys()),
                            company_profile=st.session_state.company_profile,
                            selected_fields_by_schema=st.session_state.export_fields.get(mid, {}),
                            module_id=mid
                        )
                        st.download_button(
                            label=f"📊 Scarica Excel Ufficiale ({prefix})",
                            data=excel_bytes,
                            file_name=f"Report_{prefix}_{schema_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )

                    with col_dl_word:
                        word_bytes = create_styled_word_report(
                            extracted_data_by_schema=payload,
                            source_documents=list(st.session_state.indexed_documents.keys()),
                            company_profile=st.session_state.company_profile,
                            selected_fields_by_schema=st.session_state.export_fields.get(mid, {}),
                            module_id=mid
                        )
                        st.download_button(
                            label="📄 Scarica Verbale Word Ufficiale (.docx)",
                            data=word_bytes,
                            file_name=f"Verbale_{prefix}_{datetime.now().strftime('%Y%m%d')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )

        with tab_deadlines:
            st.subheader("⏰ Monitoraggio Scadenze e Allerte Automatiche")
            st.caption("Pianificazione automatica scadenze normative e invio notifiche Email/SMS.")

            c_btn, c_sim = st.columns([1, 1])
            with c_btn:
                if st.button("🔔 Attiva Monitoraggio sui Record Verificati", use_container_width=True):
                    n_sync = sync_deadlines_to_db(
                        collect_payload(st.session_state.extracted_data, st.session_state.reviewed_data),
                        st.session_state.indexed_documents.keys())
                    if n_sync:
                        st.success(f"✓ {n_sync} scadenze sincronizzate (tutti i moduli) e attive per il monitoraggio!")
                    else:
                        st.info("Nessuna scadenza trovata nei record. Esegui prima l'analisi.")

            with c_sim:
                if st.button("🚀 Simula Scansione Notifiche (Dry-run)", use_container_width=True):
                    res_sim = dispatch_alerts(dry_run=True)
                    st.info(f"Simulazione completata: Email={res_sim['sent_email']} | SMS={res_sim['sent_sms']} | Saltate={res_sim['skipped']}")

            smtp_ok = SmtpEmailNotifier().configured
            sms_ok = TwilioSmsNotifier().configured
            st.caption(f"Email: {'✅ Configurato' if smtp_ok else '⚠️ Non configurato (SMTP_HOST nel .env)'} · "
                       f"SMS: {'✅ Configurato' if sms_ok else '⚠️ Non configurato'}")

            if st.button("📨 Invia Allerte Reali", type="primary", use_container_width=True,
                         disabled=not (smtp_ok or sms_ok)):
                with st.spinner("Invio notifiche in corso..."):
                    res = dispatch_alerts(dry_run=False)
                msg = (f"Email inviate: {res['sent_email']} · SMS inviati: {res['sent_sms']} · "
                       f"Saltate (già inviate): {res['skipped']} · Simulate: {res['simulated']} · Fallite: {res['failed']}")
                if res["failed"] > 0:
                    st.error(msg)
                else:
                    st.success(msg)

            active_dls = get_active_deadlines()
            if active_dls:
                st.markdown("### 📋 Elenco Scadenze Attive nel Database")
                df_dl = pd.DataFrame(active_dls)[["due_date", "description", "module_id", "source_document", "source_page"]]
                df_dl.columns = ["Data Scadenza", "Descrizione Obbligo", "Modulo", "Documento", "Pagina"]
                st.dataframe(df_dl, use_container_width=True)
            else:
                st.caption("Nessuna scadenza attualmente monitorata nel database.")

            st.divider()
            st.markdown("### 📬 Configurazione Destinatari Allerte")
            c_rec_addr, c_rec_type, c_rec_add = st.columns([2, 1, 1])
            with c_rec_addr:
                new_addr = st.text_input("Indirizzo Email o Telefono (+39...):", key="new_alert_addr")
            with c_rec_type:
                new_ch = st.selectbox("Canale:", ["email", "sms"], key="new_alert_ch")
            with c_rec_add:
                st.write("")
                st.write("")
                if st.button("Aggiungi Destinatario", use_container_width=True):
                    addr_clean = new_addr.strip()
                    is_valid = ("@" in addr_clean and "." in addr_clean) if new_ch == "email" else (len(addr_clean) >= 8)
                    
                    if not addr_clean or not is_valid:
                        st.warning("Inserisci un indirizzo email o un numero di telefono valido.")
                    else:
                        import uuid
                        ok = add_recipient(str(uuid.uuid4()), new_ch, addr_clean)
                        if ok:
                            st.success("Destinatario aggiunto con successo!")
                            st.rerun()
                        else:
                            st.error("Errore durante il salvataggio del destinatario.")

            curr_recs = get_active_recipients()
            if curr_recs:
                st.write("**Destinatari Attivi:** " + ", ".join([f"`{r['channel'].upper()}: {r['address']}`" for r in curr_recs]))


if __name__ == "__main__":
    render_ui()