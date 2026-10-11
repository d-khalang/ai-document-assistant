"""
Platform pipeline: deterministic document routing + batch extraction across modules.

- Routing is 100% deterministic (keyword scoring declared in schemas/*.json under "routing"),
  no LLM involved. The UI lets the user override every decision.
- Extraction reuses `extract_structured_data` unchanged; only orchestration lives here.
- Worker threads call ONLY pure functions (no Streamlit / session_state access);
  progress callbacks are invoked from the calling thread.
"""
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from app.extraction.registry import SchemaDef, list_modules

Route = Tuple[str, str]          # (module_id, schema_name)
Task = Tuple[str, str, str]      # (document, module_id, schema_name)

SAMPLE_CHARS = 8000
MIN_SCORE = 2.0
STRONG_WEIGHT = 3.0
FILENAME_BONUS = 2.0


# ----------------------------------------------------------------------------- routing
def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[\s_\-\.]+", " ", s)


@lru_cache(maxsize=2048)
def _compile(term: str) -> "re.Pattern[str]":
    """'pod' -> whole word; 'attest*' -> prefix match."""
    t = _norm(term).strip()
    prefix = t.endswith("*")
    body = re.escape(t.rstrip("*").strip()).replace("\\ ", " ")
    return re.compile(r"(?<![a-z0-9])" + body + ("" if prefix else r"(?![a-z0-9])"))


@dataclass(frozen=True)
class RouteDecision:
    document: str
    route: Optional[Route]
    score: float
    runner_up: Optional[Route]
    reason: str      # matched | tie-resolved | fallback | unrouted


def _iter_schemas() -> Iterator[Tuple[str, str, SchemaDef]]:
    for m in list_modules():
        for sname, s in m.schemas.items():
            yield m.module_id, sname, s


def _score(schema: SchemaDef, text: str, fname: str) -> float:
    r = schema.routing or {}
    total = 0.0
    for terms, weight in ((r.get("keywords") or [], 1.0), (r.get("strong_keywords") or [], STRONG_WEIGHT)):
        for term in terms:
            p = _compile(term)
            if p.search(text):
                total += weight
            if p.search(fname):
                total += FILENAME_BONUS
    return total


def classify_document(name: str, pages: List[Dict[str, Any]],
                      preferred_module: Optional[str] = None) -> RouteDecision:
    """Score every routable schema. Exact ties go to `preferred_module`, then registry order."""
    text = _norm(" ".join((p.get("text") or "") for p in pages)[:SAMPLE_CHARS])
    fname = _norm(name)

    cands = []
    for order, (mid, sname, schema) in enumerate(_iter_schemas()):
        r = schema.routing or {}
        if r.get("keywords") or r.get("strong_keywords"):
            cands.append((_score(schema, text, fname), mid, sname, order))
    cands.sort(key=lambda c: (-c[0], 0 if c[1] == preferred_module else 1, c[3]))

    if cands and cands[0][0] >= MIN_SCORE:
        best = cands[0]
        runner = cands[1] if len(cands) > 1 and cands[1][0] > 0 else None
        tie = runner is not None and runner[0] == best[0]
        return RouteDecision(name, (best[1], best[2]), best[0],
                             (runner[1], runner[2]) if runner else None,
                             "tie-resolved" if tie else "matched")

    for mid, sname, schema in _iter_schemas():
        if (schema.routing or {}).get("fallback"):
            return RouteDecision(name, (mid, sname), cands[0][0] if cands else 0.0, None, "fallback")
    return RouteDecision(name, None, cands[0][0] if cands else 0.0, None, "unrouted")


def build_routing_plan(pages_by_doc: Dict[str, List[Dict[str, Any]]],
                       preferred_module: Optional[str] = None) -> Dict[str, RouteDecision]:
    return {n: classify_document(n, p, preferred_module) for n, p in pages_by_doc.items()}


# ----------------------------------------------------------------------------- execution
def _processed(res: Dict[str, Any]) -> set:
    """Documents already handled for a schema (also understands results from the manual tab)."""
    return set(res.get("processed_documents") or []) | {r.get("source_document") for r in res.get("records", [])}


def pending_tasks(routes: Dict[str, Optional[Route]], extracted: Dict[str, Any], force: bool = False) -> List[Task]:
    tasks: List[Task] = []
    for doc, route in routes.items():
        if not route:
            continue
        mid, sname = route
        res = (extracted.get(mid) or {}).get(sname)
        if force or res is None or doc not in _processed(res):
            tasks.append((doc, mid, sname))
    return tasks


def run_batch_extraction(
    tasks: List[Task],
    pages_by_doc: Dict[str, List[Dict[str, Any]]],
    max_workers: int = 3,
    on_progress: Optional[Callable[[int, int, str, str, Optional[str]], None]] = None,
    extract_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[Route, Dict[str, Any]]:
    """
    One extraction per (document, schema), run in a thread pool (Gemini calls are I/O bound).
    A failing document never stops the batch. Returns {(module_id, schema): result}.
    """
    if extract_fn is None:
        from app.extraction.extractor import extract_structured_data as extract_fn  # lazy: needs SDK

    results: Dict[Route, Dict[str, Any]] = {}
    if not tasks:
        return results

    def _one(task: Task) -> Dict[str, Any]:
        doc, mid, sname = task
        return extract_fn(pages_by_doc[doc], sname, module_id=mid, source_document=doc)

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks)))) as pool:
        futures = {pool.submit(_one, t): t for t in tasks}
        for done, fut in enumerate(as_completed(futures), start=1):
            doc, mid, sname = futures[fut]
            res = results.setdefault((mid, sname), {
                "schema": sname, "module_id": mid, "records": [], "errors": {}, "processed_documents": []})
            err = None
            try:
                res["records"].extend(fut.result().get("records", []))
                res["processed_documents"].append(doc)
            except Exception as e:  # noqa: BLE001
                err = str(e)
                res["errors"][doc] = err
            res["total_records"] = len(res["records"])
            if on_progress:
                on_progress(done, len(tasks), doc, sname, err)
    return results


def merge_result(existing: Optional[Dict[str, Any]], new: Dict[str, Any]) -> Dict[str, Any]:
    """Replace records of re-processed documents, keep everything else."""
    redone = set(new.get("processed_documents") or []) | set((new.get("errors") or {}))
    base = existing or {}
    records = [r for r in base.get("records", []) if r.get("source_document") not in redone] + list(new["records"])
    records.sort(key=lambda r: (r.get("source_document") or "", r.get("source_page") or 0))
    errors = {d: e for d, e in (base.get("errors") or {}).items() if d not in redone}
    errors.update(new.get("errors") or {})
    processed = sorted((_processed(base) - {None}) | set(new.get("processed_documents") or []))
    return {**base, "schema": new["schema"], "module_id": new["module_id"], "records": records,
            "total_records": len(records), "errors": errors, "processed_documents": processed}


def apply_results(extracted: Dict[str, Any], reviewed: Dict[str, Any], versions: Dict[Any, int],
                  routed_to: Dict[str, Route], results: Dict[Route, Dict[str, Any]]) -> None:
    """Merge batch results into session dicts. Schemas that change get a new editor version
    (their manual edits in the review grid restart from the fresh extraction)."""
    for (mid, sname), res in results.items():
        extracted.setdefault(mid, {})[sname] = merge_result(extracted.get(mid, {}).get(sname), res)
        (reviewed.get(mid) or {}).pop(sname, None)
        versions[(mid, sname)] = versions.get((mid, sname), 0) + 1
        for doc in res.get("processed_documents", []):
            routed_to[doc] = (mid, sname)


def evict_document(extracted: Dict[str, Any], reviewed: Dict[str, Any], versions: Dict[Any, int],
                   doc: str, only_route: Optional[Route] = None) -> None:
    """Remove a document's records (everywhere, or only from the schema it was previously routed to)."""
    for mid, schemas in extracted.items():
        for sname, res in schemas.items():
            if only_route and (mid, sname) != tuple(only_route):
                continue
            recs = res.get("records", [])
            keep = [r for r in recs if r.get("source_document") != doc]
            errs = res.setdefault("errors", {})
            proc = res.get("processed_documents") or []
            if len(keep) != len(recs) or doc in proc or doc in errs:
                res["records"], res["total_records"] = keep, len(keep)
                res["processed_documents"] = [d for d in proc if d != doc]
                errs.pop(doc, None)
                (reviewed.get(mid) or {}).pop(sname, None)
                versions[(mid, sname)] = versions.get((mid, sname), 0) + 1


# ----------------------------------------------------------------------------- payload / sync
def collect_payload(extracted: Dict[str, Any], reviewed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """All modules, human-reviewed records taking precedence over raw extraction."""
    out: Dict[str, Dict[str, Any]] = {}
    for mid, schemas in extracted.items():
        for sname, res in schemas.items():
            rev = (reviewed.get(mid) or {}).get(sname)
            recs = rev if rev is not None else res.get("records", [])
            out.setdefault(mid, {})[sname] = {**res, "records": recs, "total_records": len(recs)}
    return out


def collect_errors(extracted: Dict[str, Any]) -> Dict[str, str]:
    errs: Dict[str, str] = {}
    for schemas in extracted.values():
        for res in schemas.values():
            errs.update(res.get("errors") or {})
    return errs


def sync_deadlines_to_db(payload: Dict[str, Any], active_docs: Iterable[str]) -> int:
    """Make the alerts DB mirror the current records: upsert live deadlines, deactivate stale ones."""
    from app.alerts.store import deactivate_missing_deadlines, upsert_deadline
    from app.reporting.platform_excel_exporter import build_deadlines_from_payload

    docs = list(active_docs)
    deadlines = build_deadlines_from_payload(payload, set(docs))
    for d in deadlines:
        upsert_deadline(d["id"], d["module_id"], d["schema_name"], d["field_name"], d["description"],
                        d["due_date"], d["thresholds"], d["source_document"], d["source_page"])
    deactivate_missing_deadlines({d["id"] for d in deadlines}, docs)
    return len(deadlines)