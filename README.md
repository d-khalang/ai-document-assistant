# AI Document Intelligence & Enterprise Reporting Platform
### Production-Grade Multimodal RAG & ISO 14001 Compliance Audit System

An enterprise-ready Document Intelligence platform built with Python, Google Gemini, ChromaDB, and SQLite. The system processes complex heterogeneous corporate documentation (spreadsheets, digital PDFs, scanned files, Word documents, and images), provides grounded cross-document Q&A with page provenance, executes schema-driven compliance extraction with zero hallucination, and generates scoped audit-ready Excel and Word deliverables.

---

## Executive Summary & Architecture Highlights

Traditional LLM document pipelines suffer from unverified hallucinations, lost page citations, and brittle document ingestion. This platform resolves these issues through a deterministic, framework-free architecture:

* **Zero-Hallucination Principle:** The LLM is restricted strictly to text extraction and field normalization. All mathematical calculations (ratios, sums, differences, products), expiries, and aggregations are computed deterministically in pure Python. Unfound data points explicitly evaluate to `null` (`MISSING`).
* **Framework-Free Core:** Direct integration with official SDKs (`google-genai`, `chromadb`, `sqlite3`), avoiding heavy abstraction overheads from LangChain or LlamaIndex.
* **Guaranteed Provenance:** Source documents and page numbers are preserved through chunking, vector indexing, retrieval, UI review, and final report generation.
* **Strict Module Scoping:** Generated deliverables (Excel workbooks and Word reports) isolate data to the selected standard/module, eliminating cross-domain schema contamination.

---

## System Architecture

```text
                               +-----------------------------+
                               |     Streamlit Web UI        |
                               |  (Multi-Tenant Workspace)   |
                               +--------------+--------------+
                                              |
                   +--------------------------+--------------------------+
                   |                                                     |
                   v                                                     v
       [ Ingestion Pipeline ]                                [ Workspace Tabs ]
                   |                                                     |
  +--------------------------------+                  +------------------+------------------+
  |  Multi-Format Document Loaders |                  |                  |                  |
  |  - PDF (pypdf + PyMuPDF Vision)|                  v                  v                  v
  |  - Excel (Smart Header Parsing)|             [ RAG Chat ]      [ Extraction ]    [ Alerts Engine ]
  |  - Word (.docx) & Images (OCR) |                  |                  |                  |
  +----------------+---------------+                  |                  |                  |
                   |                                  v                  |                  v
                   v                           [ Semantic Search ]       |          [ SQLite DB Store ]
         [ Recursive Chunker ]                        |                  |          - Deadlines (UUID5)
                   |                                  v                  |          - Alert Dispatcher
                   v                          (ChromaDB Vectors)         |          - Smtp/Twilio Client
        (Gemini Embeddings API)                       |                  |
                   |                                  v                  v
                   v                           +--------------+  +------------------+
         (ChromaDB Persistent)                 | Gemini Flash |  | Human-in-the-Loop|
                   |                           | (Grounding)  |  | Review Grid (UI) |
                   +-------------------------->+--------------+  +--------+---------+
                                                                          |
                                                                          v
                                                                 [ Scoped Exporters ]
                                                                 - Excel (.xlsx)
                                                                 - Word (.docx)
```

---

## Key Enterprise Capabilities

### 1. Robust Multimodal & Spreadsheet Ingestion
* **Hybrid PDF Parsing:** Direct text extraction via `pypdf`, falling back automatically to PyMuPDF rendering (150 DPI) and Gemini Vision for scanned documentation.
* **Spreadsheet Preservation:** Excel sheets are parsed via intelligent header detection (`_parse_excel_sheet`), mapping rows with `.iloc` to unique key-value pairs to prevent ambiguous pandas Series errors and preserving sheet-page indexes.
* **Word & Image OCR:** Extraction of `.docx` paragraphs/tables and verbatim Vision transcription for PNG/JPG/WEBP.

### 2. Specialized Operational Standards & Schemas
Domain logic resides entirely in external JSON files (`schemas/*.json`):
* **ISO 14001 SGA (`iso_14001.json`):** Compliance schedules (`scadenziario`), fleet and fuel consumption (`vehicle_fuel`), utility metrics (`utility_consumption`), worker safety certifications (`personnel_training`), and environmental permits (`regulatory_authorization`).
* **Energy Utilities (`energy_utility.json`):** Electricity bills, consumption metrics, POD codes, and power ratings.
* **HR & Safety Training (`hr_training.json`):** Employee certifications, validity periods, and mandatory refresher courses.
* **Machinery Maintenance (`machinery_maintenance.json`):** Asset servicing records, maintenance intervals, and technician sign-offs.
* **Fleet Management (`fleet_fuel_expenses.json`):** Operational mileage, fuel volume, cost per liter, and deterministic $L/100\text{km}$ consumption ratios.
* **General Documents (`general_documents.json`):** Protocol numbers, issuing bodies, and statutory contractual expiry tracking.

### 3. Human-in-the-Loop Review Roundtrip
* Extracted entities feed directly into an interactive grid (`st.data_editor`).
* Manual corrections elevate field statuses to `EDITED`, instantly triggering deterministic recalculations in Python before exporting.

### 4. Scoped Multi-Tenant Reporting
* **Platform Multi-Sheet Excel Deliverables:** Color-coded KPI dashboard, master document register, prioritized deadline radar, and schema analytical sheets with Excel conditional formatting.
* **Formal Word Reports:** Styled `.docx` reports containing audit methodology statements, structured tables, and dynamic sign-off blocks populated from the company profile.

### 5. Automated Deadline Alerts Engine
* Extracts compliance deadlines into deterministic UUID5 identifiers.
* Pure-logic threshold classification (e.g., 30, 15, 7 days remaining or overdue).
* Deduplicated alert logging in SQLite and notification dispatching via SMTP Email (SSL/TLS) and Twilio SMS.

---

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Runtime & Language** | Python 3.12 | Core execution environment |
| **Frontend UI** | Streamlit | Responsive multi-tenant workspace with CSS theme injections |
| **LLM & Vision** | Google Gemini 3.6 Flash | Multimodal text generation, Vision OCR, and JSON schema extraction |
| **Vector Embeddings** | Gemini Embedding 001 | 768-dimensional semantic embeddings |
| **Vector Store** | ChromaDB | Persistent local vector store configured with Cosine similarity |
| **Relational Database** | SQLite (`sqlite3`) | Users, conversations, company tenant profiles, deadlines, and alert logs (WAL mode) |
| **Document Parsers** | `pypdf`, `pymupdf`, `python-docx`, `pandas`, `openpyxl`, `Pillow` | Robust multimodal and spreadsheet ingestors |
| **Test Framework** | Pytest | Automated test suite with dynamic temp-database isolation (65/65 passing) |

---

## Project Structure

```text
ai-document-assistant/
├── .streamlit/
│   └── config.toml             # Custom dark glassmorphism theme settings
├── app/
│   ├── ai/
│   │   ├── gemini.py           # Google GenAI SDK client, key rotation & retry backoff
│   │   └── prompts.py          # Grounded RAG prompts with page citation instructions
│   ├── alerts/
│   │   ├── deadlines.py        # Deterministic UUID5 deadline extractor
│   │   ├── dispatcher.py       # Notification aggregator (Email digest & SMS)
│   │   ├── notifiers.py        # Standard SMTP (SSL/TLS) and Twilio clients
│   │   ├── run.py              # CLI entrypoint for daily scheduled scanning
│   │   ├── scanner.py          # Pure-logic threshold classification & overdue detection
│   │   └── store.py            # SQLite persistence for alerts and deduplication logs
│   ├── database/
│   │   └── database.py         # Relational store (conversations, messages, tenant profiles)
│   ├── extraction/
│   │   ├── calculators.py      # Whitelist deterministic calculations (ratio, sum, diff, product)
│   │   ├── extractor.py        # Batch JSON extraction engine with provenance tracking
│   │   ├── normalizer.py       # Multilingual date (IT/EN), number, and plate normalizers
│   │   ├── pipeline.py         # Batch routing, non-blocking extraction & result merging
│   │   ├── registry.py         # Schema registry loader with hot-reload and cache invalidation
│   │   ├── review.py           # DataFrame <-> Record bidirectional roundtrip engine
│   │   └── schemas.py          # Backward-compatible shim for legacy imports
│   ├── rag/
│   │   ├── chunker.py          # Sliding-window text chunker preserving page numbers
│   │   ├── embeddings.py       # Batch vector generation with key rotation
│   │   ├── loader.py           # Unified document parser (PDF, Word, Excel, Images)
│   │   ├── retriever.py        # Semantic search filtered by active session documents
│   │   └── vectorstore.py      # Persistent ChromaDB client and document lifecycle handlers
│   ├── reporting/
│   │   ├── common.py           # Scope resolvers, column planners, and legacy mappings
│   │   ├── excel_exporter.py   # Multi-sheet audit Excel generator (openpyxl)
│   │   ├── platform_excel_exporter.py # 4-sheet universal executive platform workbook
│   │   └── word_exporter.py    # Formal signed Word report generator (python-docx)
│   ├── ui/
│   │   ├── streamlit_app.py    # Main UI application layout, tabs, and event handlers
│   │   └── theme.py            # Glassmorphism styling and KPI metric renderers
│   ├── config.py               # Centralized configuration with dynamic env fallbacks
│   └── main.py                 # Application root entrypoint
├── schemas/                    # Externalized schema definitions (JSON)
│   ├── energy_utility.json
│   ├── fleet_fuel_expenses.json
│   ├── general_documents.json
│   ├── hr_training.json
│   ├── iso_14001.json
│   └── machinery_maintenance.json
├── tests/                      # Automated Pytest suite
│   ├── conftest.py             # Database isolation fixtures
│   ├── test_alerts.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_pipeline.py
│   ├── test_platform_excel.py
│   ├── test_registry.py
│   ├── test_reports.py
│   └── test_review.py
├── .env.example                # Example environment variables
├── AGENTS.md                   # AI engineering constitution & architectural invariants
├── check_health.py             # Health check & compliance validation suite
├── pytest.ini                  # Pytest configuration settings
├── requirements.txt            # Project dependencies
└── PROJECT_STATE.md            # Living architectural milestone tracking
```

---

## Getting Started

### Prerequisites
* Python 3.12+
* Google Gemini API Key (obtainable via Google AI Studio)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/ai-document-assistant.git
   cd ai-document-assistant
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Copy `.env.example` to `.env` and supply your Gemini API key:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```ini
   GEMINI_API_KEY=AIzaSy...your_actual_key_here
   GEMINI_MODEL=gemini-3.6-flash
   GEMINI_EMBEDDING_MODEL=gemini-embedding-001
   ```

---

## Running the Application

### 1. Launch the Streamlit Web Workspace
Execute using either command:
```bash
python -m streamlit run app/ui/streamlit_app.py
```
or:
```bash
python -m streamlit run app/main.py
```
Open your browser at `http://localhost:8501`.

### 2. Run Daily Scheduled Deadline Scanner (CLI)
To run the automated alert scanner directly from the command line:
```bash
# Dry-run simulation (prints digest without sending):
python -m app.alerts.run --dry-run

# Run against a specific target date:
python -m app.alerts.run --today 2026-10-15
```

### 3. Run System Healthcheck
Verify registry schemas, SQLite tables, and the complete test suite:
```bash
python check_health.py
```

---

## Running Automated Tests

All core logic, schema registries, deterministic calculators, database models, scoped exporters, batch pipelines, and alert systems are verified offline via Pytest:

```bash
pytest -v -p no:cacheprovider
```

Sample output:
```text
============================= test session starts =============================
platform win32
rootdir: D:\ai-document-assistant
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 45 items

tests/test_alerts.py::test_alert_engine_full PASSED                      [  2%]
tests/test_alerts.py::test_scan_deadlines_max_overdue_days PASSED        [  4%]
tests/test_alerts.py::test_dispatch_alerts_configured_mock PASSED        [  6%]
tests/test_alerts.py::test_deactivate_all_deadlines_clears_registry PASSED [  8%]
tests/test_alerts.py::test_recipient_deactivation_and_reactivation PASSED [ 11%]
tests/test_config.py::test_default_config_values PASSED                  [ 13%]
tests/test_config.py::test_dynamic_db_path PASSED                        [ 15%]
tests/test_config.py::test_chunker_uses_config PASSED                    [ 17%]
tests/test_database.py::test_database_lifecycle PASSED                   [ 20%]
tests/test_database.py::test_company_profile PASSED                      [ 22%]
tests/test_document_chat_context.py::test_build_document_structured_context_extracted_and_calculated PASSED [ 24%]
tests/test_document_chat_context.py::test_build_document_structured_context_with_live_calculation PASSED [ 26%]
tests/test_document_chat_context.py::test_build_document_structured_context_empty_and_edge_cases PASSED [ 28%]
tests/test_document_chat_context.py::test_build_document_structured_context_multiple_records PASSED [ 31%]
tests/test_document_chat_context.py::test_build_rag_prompt_with_structured_context_and_provenance_rules PASSED [ 33%]
tests/test_document_chat_context.py::test_build_chat_structured_context_filters_active_documents_and_collects_guidelines PASSED [ 35%]
tests/test_document_chat_context.py::test_build_chat_structured_context_edge_cases PASSED [ 37%]
tests/test_pipeline.py::test_routing_is_deterministic_and_overridable_by_tiebreak PASSED [ 40%]
tests/test_pipeline.py::test_batch_run_merge_idempotence_and_eviction PASSED [ 42%]
tests/test_pipeline.py::test_stale_deadline_deactivated_when_record_changes PASSED [ 44%]
tests/test_pipeline.py::test_unconfigured_notifier_is_not_logged_as_sent PASSED [ 46%]
tests/test_pipeline.py::test_exporter_explains_unanalyzed_documents PASSED [ 48%]
tests/test_platform_excel.py::test_platform_excel_4_sheets_structure PASSED [ 51%]
tests/test_platform_excel.py::test_platform_excel_regulatory_authorization_sheet_title_and_columns PASSED [ 53%]
tests/test_registry.py::test_schema_registry_loading PASSED              [ 55%]
tests/test_registry.py::test_legacy_shim PASSED                          [ 57%]
tests/test_registry.py::test_deterministic_calculators PASSED            [ 60%]
tests/test_registry.py::test_compute_expiry_date_and_leap_year PASSED    [ 62%]
tests/test_registry.py::test_date_and_field_normalizers PASSED           [ 64%]
tests/test_registry.py::test_regulatory_authorization_layout_and_fields PASSED [ 66%]
tests/test_registry.py::test_derived_dates_schema_validation PASSED      [ 68%]
tests/test_registry.py::test_personnel_training_derived_dates_integration PASSED [ 71%]
tests/test_registry.py::test_chat_guidelines_schema_validation PASSED    [ 73%]
tests/test_reports.py::test_scoped_reporting_isolation PASSED            [ 75%]
tests/test_reports.py::test_word_report_regulatory_authorization_sections_and_empty_safety PASSED [ 77%]
tests/test_review.py::test_review_roundtrip PASSED                       [ 80%]
tests/test_training_expiry.py::test_training_expiry_rules_and_leap_year PASSED [ 82%]
tests/test_training_expiry.py::test_training_expiry_preserves_extracted_and_edited PASSED [ 84%]
tests/test_training_expiry.py::test_training_expiry_integration_with_deadline_alerts PASSED [ 86%]
tests/test_training_expiry.py::test_training_expiry_edge_cases_and_warnings PASSED [ 88%]
tests/test_training_expiry.py::test_hr_training_certificate_schema_derived_dates PASSED [ 91%]
tests/test_ui_theme.py::test_metric_cards_render_values_tone_and_escape_html PASSED [ 93%]
tests/test_ui_theme.py::test_metric_delta_is_rendered_only_when_a_real_figure_is_supplied PASSED [ 95%]
tests/test_ui_theme.py::test_injected_css_has_no_unresolved_placeholders PASSED [ 97%]
tests/test_ui_theme.py::test_page_header_shows_official_slogan_and_escapes_tenant PASSED [100%]

============================= 45 passed in 3.40s ==============================
```

---

## Known Limitations & Future Roadmap (V2)

### Current Architecture Limitations (MVP Scope)
* **Single Shared Chroma Collection:** Vector chunks reside in a shared persistent Chroma collection filtered at query-time by session document names.
* **Single Tenant Profile per Session:** The corporate tenant profile is stored in a single-row SQLite table intended for single-tenant or demo operation.
* **Embedding Batch Size:** Large documents (>100 pages) require external chunk batching during embedding to avoid single-call payload limits.

### Planned V2 Enhancements
* **FastAPI Backend Migration:** Decouple Streamlit to consume an asynchronous FastAPI REST/WebSocket backend.
* **Multi-User Role-Based Access (RBAC):** Integrate OAuth2/JWT authentication with dedicated schema permissions.
* **Chunk Batching & Context Pagination:** Implement adaptive sub-batching during embedding and multi-page chunk merging for documents exceeding 300 pages.