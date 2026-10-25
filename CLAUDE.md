# CLAUDE.md — Working Memory for Claude Code

> Read together with `AGENTS.md` (non-negotiable invariants — auto-loaded) and `PROJECT_STATE.md`
> (milestone log + official roadmap). If docs disagree with the code or with `check_health.py`
> output, the code and the health check win — point out the conflict instead of guessing.

## 1. Where we are (update this block at every milestone)
- **Version:** v2.6 — **Phase 1 of 3**, ~95% complete.
- **Last shipped:** deterministic `derived_dates` (training-certificate expiry); structured
  extracted-metadata context + provenance rules in Document Chat, now built by the pure function
  `build_chat_structured_context` with domain wording declared in `schemas/*.json → chat.guidelines`.
- **Baseline health:** `python check_health.py` → 6 modules / 10 schemas / 1 fallback / 65 tests green.
- **UI/UX alignment (inambiente design system) — done:** SVG hero banner + slogan + glass pills, card-style
  sidebar nav with chevrons and module selector, metric cards, styled dropzone (`app/ui/theme.py`).
  Metric cards support an optional `delta` (month-over-month) but it is only shown with a real
  computed figure — never hardcode trend numbers (no history exists yet; needs persisted counters).
- **Remaining in Phase 1:** operational checklist in `PROJECT_STATE.md` (SMTP/Twilio creds, daily
  scheduler) + Phase-1 debt in §6.

### Official roadmap — "From MVP to fully on-prem"
| Phase | Horizon | Stack / scope |
|---|---|---|
| **1 — Enterprise MVP** (current) | now | Streamlit + Gemini Flash/Vision + local ChromaDB + SQLite (WAL) |
| **2 — Scale & Internal Legal KB** | 3–9 months | FastAPI backend, Celery/Redis background jobs, PostgreSQL, Pydantic models, Hybrid Search (BM25 + dense), RBAC (RSGA / Technical Director / Auditor), child schemas (`prescrizioni_con_scadenza`), **local knowledge base of statutes (D.Lgs. 81/08, D.Lgs. 152/06, DM 02/09/2021…) and company documents** used as ground truth — no internet lookups |
| **3 — Sovereign, fully on-prem** | ~12 months | Single 24 GB GPU (RTX 4090 / A5000), vLLM or Ollama; Qwen 2.5 14B (4-bit) for extraction/reasoning, Qwen2-VL for scanned-document OCR, BGE-M3 for embeddings; **zero external tokens, zero document egress** |

Preparing for Phases 2–3 (pure functions, FastAPI-ready boundaries, local KB, on-prem readiness) is
**approved**. Actually introducing a new runtime dependency or service (FastAPI, Celery, Redis,
Postgres, vLLM…) is still a step the user starts explicitly — propose it, don't slip it in.

## 2. Health & test tools
- `python check_health.py` — full gate: schema registry load + exactly-one-fallback + routing smoke
  test, DB/alert-table init, then the whole pytest suite. **Must exit 0 before a task is done.**
- `python -m pytest -q -p no:cacheprovider` — offline suite (`tests/`, configured in `pytest.ini`).
- Single file: `python -m pytest tests/test_pipeline.py -q -p no:cacheprovider`.
- Root-level `test_*.py` are legacy manual scripts that hit the live Gemini API; not part of the
  suite. Never add tests there.
- New tests are offline and deterministic: inject fakes (`extract_fn=` in `run_batch_extraction`,
  monkeypatched notifiers/LLM calls). Anything needing the network gets `@pytest.mark.live_api`.
- The autouse `isolated_database` fixture (`tests/conftest.py`) redirects `ASSISTANT_DB_PATH`;
  never bypass it and never open `assistant.db` from a test.
- Run the app: `streamlit run app/ui/streamlit_app.py`.
- After changing test counts, keep `AGENTS.md`, `README.md`, `PROJECT_STATE.md` and §1 in sync.

## 3. Where things go
| Need | Put it in |
|---|---|
| New domain, document type, field, alert, routing keyword, expiry rule, report layout, domain chat wording | `schemas/*.json` only; add validation in `registry._parse_schema` for any new key |
| Numeric/date derivation | `app/extraction/calculators.py` (+ whitelist op in `registry.COMPUTE_OPS`) |
| Orchestration (routing, batch, merge, evict, deadline sync) | `app/extraction/pipeline.py` — pure functions over plain dicts |
| Prompt assembly / chat context | `app/ai/prompts.py` — generic wording only |
| LLM / vision / embedding calls | the AI adapter seam (§4.1) |
| Vector ops | `app/rag/*` |
| SQLite | `app/database/database.py`, `app/alerts/store.py` — `get_db_path()`, scoped connections, `?` params |
| Exports | `app/reporting/*` — scope via `resolve_scope`; layout from `SchemaDef.layout` |
| UI | `app/ui/streamlit_app.py`, `theme.py` — call the above and render; nothing else |

## 4. Future-proofing rules (today's code must not block Phases 2–3)

### 4.1 Keep the AI layer swappable (Phase 3 = Gemini → local Qwen/BGE-M3)
- All model access goes through four functions: `generate_answer`, `generate_structured_json`,
  `transcribe_image_with_vision` (`app/ai/gemini.py`) and `get_batch_embeddings`
  (`app/rag/embeddings.py`). Never import `google.genai` anywhere else; never call a model from
  extraction, RAG, alerts, reporting or UI code directly.
- Prompts must work for a 14B local model: explicit JSON structure, no reliance on Gemini-only
  features (grounding, tool use, huge context). Keep per-call context bounded.
- Never send document content to any service other than through that seam (zero-egress target).
- Embedding dimension is model-specific (gemini-embedding-001 = 3072, BGE-M3 = 1024): never
  hardcode it; a model change implies a re-index into a new collection, not a mixed one.

### 4.2 Keep the core FastAPI/Celery-ready (Phase 2)
- Every UI feature = pure domain function + offline test first. A loop over records, a date
  diff, or a DB/vector call inside `streamlit_app.py` is a bug — move it down.
- Domain functions take/return plain dicts, dataclasses and primitives — never
  `st.session_state`, `UploadedFile` or Streamlit objects. Prefer frozen dataclasses with simple
  typed fields (easy to mirror as Pydantic models later).
- Long-running work must stay callable without a UI thread (it will run in Celery workers).
- SQL stays portable: parameterized, no SQLite-only tricks beyond the WAL pragma, IDs are UUID
  strings, dates are ISO strings.

### 4.3 Data & retrieval
- Identify documents by `document_id`, not filename, in any new code path (filename keys are
  debt and break multi-tenancy).
- Chunks keep full text + metadata (document, page, source type) so BM25/hybrid search and
  citations can be added without re-ingesting.
- The future legal/regulatory KB must be a separate namespace from user documents, and its
  provenance must be distinguishable in prompts (statute vs. company document vs. extracted vs.
  calculated) — extend the existing `Stato:` provenance contract rather than inventing a parallel one.
- Don't assume "one document → one schema" beyond existing code; child schemas make it one-to-many.

### 4.4 Contracts that never change silently
- Field status: `EXTRACTED | EDITED | CALCULATED | UNCERTAIN | MISSING`. Derivations never
  overwrite `EXTRACTED`/`EDITED`. Adding a status is an architecture change — ask first.
- Backward compatibility: `app/extraction/schemas.py` shim, `get_chroma_collection` alias, and the
  public signatures of `extract_structured_data`, `merge_result`, `run_batch_extraction`,
  `build_rag_prompt` (new params only as optional keywords).
- Config over constants: model names, collection names, thresholds and limits come from
  `app/config.py` / `.env`. Never hardcode secrets.
- No LangChain / LlamaIndex: the RAG pipeline stays framework-free.
- Smallest change that works; no drive-by refactors of unrelated code.

## 5. Workflow
1. Read the relevant `schemas/*.json` and existing pure functions before changing logic.
2. Step A: domain logic + offline tests → Step B: `python check_health.py` → Step C: wire the UI.
3. After a significant milestone: update §1 here and append to `PROJECT_STATE.md`.
4. Commit only when asked; conventional messages (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).

## 6. Known debt (verified 2026-10-22 — re-check before relying on it)
- Chat structured context injects all records of all active documents with no size budget.
- Ingestion orchestration (`process_single_document`) and deadline KPI day-diffs still live in the UI.
- Chroma: one shared collection keyed by `document_name`; UI hardcodes `"document_chunks"` while
  `config.CHROMA_COLLECTION_NAME` is unused.
- `app/rag/embeddings.py` imports `google.genai` directly (outside the AI layer).
- `database.get_db_connection()` has no timeout / context manager (unlike `alerts/store.py`).
- Extraction/review state lives only in `st.session_state` (lost on browser close; blocks FastAPI).
- Hardcoded defaults: `extract_structured_data(schema_name="scadenziario")`, UI fallback `"iso_14001"`.
- `requirements.txt` has duplicates and unpinned versions (blocks reproducible Docker/CI).
- `README.md` "Future Roadmap (V2)" section predates the official 3-phase roadmap.
