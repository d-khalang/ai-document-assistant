# AGENTS.md — AI Engineering & Architectural Guidelines

This document defines the non-negotiable architectural invariants, development workflows, and coding standards for all AI agents (Gemini, Claude, GPT, Antigravity) and human engineers working on the **Enterprise Document Intelligence & Compliance Platform**.

---

## 1. Core Architecture & Tech Stack

- **Runtime & Language:** Python 3.12 (Strict type hints, clean modular layout, PEP 8)
- **UI & Presentation:** Streamlit (Single-page enterprise dashboard layout in `app/ui/`)
- **AI Core:** Google Gemini API via official `google-genai` SDK (`gemini-3.6-flash` default)
- **Vector Database:** ChromaDB (Isolated persistent collections in `chroma_data/`, per-document filtering)
- **Relational Storage:** SQLite (WAL mode, parameterized queries, dynamic path via `app.config.get_db_path()`)
- **Document Ingestion:** PyMuPDF (`pymupdf`/fitz), `python-docx`, `openpyxl`, `Pillow`
- **Charts:** `matplotlib` (Agg, `app/reporting/charts.py` only) — PNG bytes embedded in Excel/Word
- **Testing:** Pytest with clean temporary database isolation (`tests/conftest.py`)

---

## 2. Inviolable Architectural Principles (Non-Negotiable)

### 🔴 Principle 1: Zero-Hallucination & 100% Deterministic Calculations
- LLMs are strictly bounded to text extraction and field normalization.
- **NEVER** ask the LLM to calculate prices, percentages, unit ratios (e.g., €/kWh, km/l), compliance scores, deadline days left, or statistical aggregations.
- All domain calculations must be executed via pure, deterministic Python code in `app/extraction/calculators.py` or `app/extraction/pipeline.py`.

### 🔴 Principle 2: Strict Separation of Concerns (UI vs. Domain Core)
- Streamlit modules in `app/ui/` (`streamlit_app.py`, `theme.py`) are **strictly presentation layers**.
- **NEVER** write core business logic, document extraction, vector retrieval, database queries, or file exporters directly inside Streamlit render loops.
- Heavy/batch operations must run via dedicated pure functions (`run_batch_extraction` with `ThreadPoolExecutor`) without touching `st.session_state` or `st.*` from worker threads. Only the main script thread handles UI progress and updates session state.

### 🔴 Principle 3: Declarative, Schema-Driven Extensibility
- Domain logic and schemas live exclusively in `schemas/*.json` (`energy_utility`, `hr_training`, `machinery_maintenance`, `iso_14001`, `general_documents`, `fleet_fuel_expenses`).
- Routing rules, keyword scoring (`strong_keywords`, `keywords`), field types, computed operators, derived dates (`derived_dates`), report layouts (`layout`), alert thresholds, and domain-specific chat wording (`chat.guidelines`) **must be declared in JSON**.
- **NEVER** hardcode schema names, field names, or classification keywords in Python code.

### 🔴 Principle 4: Concurrency & Database Safety
- SQLite must always be accessed with dynamic path resolution via `app.config.get_db_path()`.
- Use context managers with scoped connections to prevent database lockups (`sqlite3.OperationalError: database is locked`).
- Never touch `assistant.db` during automated testing; tests must strictly use the `isolated_database` fixture in `tests/conftest.py`.

### 🔴 Principle 5: Alerts & Notification Safeguards
- Unconfigured notification clients (`notifiers.configured == False`) must count under `stats["simulated"]` and **MUST NOT** log `status = 'sent'` in `alert_logs`.
- Document removal must evict records and deactivate deadlines (`deactivate_deadlines_for_document`, `deactivate_missing_deadlines`).

### 🔴 Principle 6: Test-Driven Stability & Zero Regressions
- The entire offline test suite (`pytest -q -p no:cacheprovider`) must remain 100% green before concluding any task (v2.6 baseline: 97/97 tests passing). The authoritative gate is `python check_health.py` (exit code 0); never lower the count by deleting or skipping tests.
- Any new architectural feature or bug fix must be accompanied by offline unit/integration tests in `tests/`.

---

## 3. Directory Structure & Module Responsibilities

```
ai-document-assistant/
├── AGENTS.md                   # This file (AI engineering constitution)
├── PROJECT_STATE.md            # Living memory of milestones, architecture & next steps
├── schemas/                    # Declarative JSON schemas (fields, computed, alerts, routing)
├── app/
│   ├── ai/                     # Gemini client, retry logic & prompt templates
│   ├── alerts/                 # Deadlines extraction, scanner, dispatcher, store & sync
│   ├── database/               # SQLite initialization, tenant profiles & RAG history
│   ├── extraction/             # Registry, calculators, normalizer, extractor, pipeline.py
│   ├── rag/                    # Multi-format loaders, chunker, embeddings, vectorstore
│   ├── reporting/              # Scoped Excel/Word exporters & Platform 4-sheet Excel engine
│   └── ui/                     # Streamlit frontend & custom enterprise theme
├── assistant.db                # Local SQLite database (WAL mode)
├── chroma_data/                # Local ChromaDB persistent vector storage
└── tests/                      # Automated Pytest suite (offline & isolated fixtures)
```

---

## 4. Operational Guidelines for AI Pair-Programming

When modifying or expanding this codebase, always follow this workflow:

1. **Understand Before Modifying:**
   - Review relevant schema definitions in `schemas/*.json` and existing pure functions before changing logic.
   - Do not break backward compatibility with legacy exporters or existing unit tests.

2. **Develop in Isolated Steps:**
   - **Step A:** Write or update pure Python logic and unit tests in `tests/`.
   - **Step B:** Run the test suite: `python -m pytest -q -p no:cacheprovider`.
   - **Step C:** Wire up the UI in `app/ui/` only after the core logic is 100% verified.

3. **Keep the Living Memory Updated:**
   - After completing any significant milestone, record the completed items and future tasks in `PROJECT_STATE.md`.

