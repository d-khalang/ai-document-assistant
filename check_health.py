"""
Platform Healthcheck & Sanity Suite.
Verifies schema registry validity, routing rules consistency, and runs all pytests.

Usage:
    python check_health.py
"""
import sys
import subprocess
from pathlib import Path

# Safe terminal encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def check_schemas() -> bool:
    print("[1/3] Validating Schema Registry & Declarative Routing Rules...")
    try:
        from app.extraction.registry import reload_registry
        from app.extraction.pipeline import classify_document

        modules = reload_registry()
        total_schemas = 0
        routable_count = 0
        fallback_count = 0

        for m in modules.values():
            for sname, sdef in m.schemas.items():
                total_schemas += 1
                r = getattr(sdef, "routing", None) or {}
                if r.get("keywords") or r.get("strong_keywords"):
                    routable_count += 1
                if r.get("fallback"):
                    fallback_count += 1

        print(f"   [OK] Loaded {len(modules)} operational modules across {total_schemas} schemas.")
        print(f"   [OK] {routable_count} schemas equipped with routing keywords, {fallback_count} designated as fallback.")

        # اعتبارسنجی دقیق اسکیمای فال‌بک
        if fallback_count != 1:
            print(f"   [ERROR] Expected exactly 1 fallback schema, found {fallback_count}!")
            return False

        # Smoke test classification with exact assertion
        test_doc = "bolletta_test.pdf"
        test_pages = [{"page_number": 1, "text": "Fattura energia elettrica fornitore eVISO consumo kwh codice pod"}]
        decision = classify_document(test_doc, test_pages)
        expected_route = ("energy_utility", "energy_bill")

        if decision.route == expected_route:
            print(f"   [OK] Deterministic routing test passed: '{test_doc}' -> {decision.route[0]}::{decision.route[1]} (score: {decision.score})")
        else:
            print(f"   [ERROR] Deterministic routing failed: expected {expected_route}, got {decision.route}")
            return False

        return True
    except Exception as e:
        print(f"   [ERROR] Schema Registry Error: {e}")
        return False


def check_database_initialization() -> bool:
    print("[2/3] Validating SQLite Database & Alert Tables Schema...")
    try:
        from app.database.database import init_db
        from app.alerts.store import ensure_alert_tables

        init_db()
        ensure_alert_tables()
        print("   [OK] Database connection and table schemas verified.")
        return True
    except Exception as e:
        print(f"   [ERROR] Database Initialization Error: {e}")
        return False


def run_test_suite() -> bool:
    print("[3/3] Executing Complete Pytest Test Suite...")
    # اجرای تمام تست‌ها بدون فیلتر کردن کاذب
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=str(ROOT_DIR)
    )
    if res.returncode == 0:
        print("   [OK] All 18 automated tests passed successfully.")
        return True
    else:
        print(f"   [FAIL] Pytest suite failed with exit code {res.returncode}.")
        return False


def main():
    print("==================================================")
    print("   AI DOCUMENT INTELLIGENCE - HEALTHCHECK SUITE   ")
    print("==================================================")
    ok_schemas = check_schemas()
    ok_db = check_database_initialization()
    ok_tests = run_test_suite()

    print("--------------------------------------------------")
    if ok_schemas and ok_db and ok_tests:
        print("STATUS: ALL SYSTEMS HEALTHY & COMPLIANT (100% OPERATIONAL)")
        print("==================================================")
        sys.exit(0)
    else:
        print("STATUS: HEALTHCHECK FAILED! PLEASE RESOLVE ISSUES ABOVE.")
        print("==================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()