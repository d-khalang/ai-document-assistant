import pytest
from datetime import date
from app.alerts.scanner import scan_deadlines, classify, OVERDUE
from app.alerts.deadlines import extract_deadlines_from_records
from app.alerts.store import (
    upsert_deadline,
    add_recipient,
    get_active_deadlines,
    is_alert_already_sent,
    log_alert_result
)
from app.alerts.dispatcher import dispatch_alerts


@pytest.mark.offline
def test_alert_engine_full():
    assert classify(25, [30, 15, 7]) == 30
    assert classify(10, [30, 15, 7]) == 15
    assert classify(-2, [30, 15, 7]) == OVERDUE

    records = [{
        "source_document": "cert.pdf",
        "source_page": 1,
        "fields": {
            "nominativo_dipendente": {"normalized_value": "Mario Rossi", "status": "EXTRACTED"},
            "corso_descrizione": {"normalized_value": "Forklift", "status": "EXTRACTED"},
            "data_scadenza_rinnovo": {"normalized_value": "2026-10-15", "status": "EXTRACTED"}
        }
    }]
    dls = extract_deadlines_from_records("iso_14001", "personnel_training", records)
    assert len(dls) == 1
    d = dls[0]

    upsert_deadline(d["id"], d["module_id"], d["schema_name"], d["field_name"], d["description"], d["due_date"], d["thresholds"], d["source_document"], d["source_page"])
    add_recipient("r1", "email", "auditor@effeemme.it")
    add_recipient("r2", "sms", "+393331234567")

    res = dispatch_alerts(today=date(2026, 10, 1), dry_run=True)
    assert res["sent_email"] >= 1
    assert res["sent_sms"] >= 1

    log_alert_result("log1", d["id"], d["due_date"], 15, "email", "auditor@effeemme.it", "sent")
    assert is_alert_already_sent(d["id"], d["due_date"], 15, "email", "auditor@effeemme.it") is True


@pytest.mark.offline
def test_scan_deadlines_max_overdue_days():
    sample_deadlines = [
        {"id": "d1", "description": "Overdue recently", "due_date": "2026-10-05", "thresholds": [30, 15, 7], "module_id": "m1"},
        {"id": "d2", "description": "Overdue too old", "due_date": "2026-08-01", "thresholds": [30, 15, 7], "module_id": "m1"},
    ]
    # today is 2026-10-12:
    # d1 is 7 days overdue (days_left = -7) -> within max_overdue_days=30
    # d2 is 72 days overdue (days_left = -72) -> exceeds max_overdue_days=30
    alerts = scan_deadlines(sample_deadlines, today=date(2026, 10, 12), max_overdue_days=30)
    assert len(alerts) == 1
    assert alerts[0].deadline_id == "d1"


@pytest.mark.offline
def test_dispatch_alerts_configured_mock(monkeypatch):
    from app.alerts.notifiers import SmtpEmailNotifier
    monkeypatch.setattr(SmtpEmailNotifier, "configured", True)
    monkeypatch.setattr(SmtpEmailNotifier, "send", lambda self, to, sub, body: None)

    upsert_deadline("d_mock", "m1", "s1", "f1", "Test Mock", "2026-10-15", [30, 15, 7], "doc.pdf", 1)
    add_recipient("r_mock", "email", "audit_test@company.it")

    stats = dispatch_alerts(today=date(2026, 10, 10), dry_run=False)
    assert stats["sent_email"] >= 1
    assert stats["failed"] == 0



@pytest.mark.offline
def test_deactivate_all_deadlines_clears_registry():
    from app.alerts.store import deactivate_all_deadlines

    upsert_deadline("d_clear_1", "m1", "s1", "f1", "Clear A", "2026-11-01", [30, 15, 7], "a.pdf", 1)
    upsert_deadline("d_clear_2", "m1", "s1", "f1", "Clear B", "2026-12-01", [30, 15, 7], "b.pdf", 1)
    assert len(get_active_deadlines()) >= 2

    removed = deactivate_all_deadlines()
    assert removed >= 2
    assert get_active_deadlines() == []
    assert deactivate_all_deadlines() == 0


@pytest.mark.offline
def test_recipient_deactivation_and_reactivation():
    from app.alerts.store import (
        get_active_recipients,
        deactivate_recipient_by_id,
        deactivate_recipient,
        deactivate_all_recipients,
    )

    assert add_recipient("rx1", "email", "remove_me@company.it")
    assert add_recipient("rx2", "sms", "+393330000001")
    assert add_recipient("rx3", "email", "user3@company.it")
    ids = {r["id"] for r in get_active_recipients()}
    assert {"rx1", "rx2", "rx3"} <= ids

    # Deactivate by ID
    assert deactivate_recipient_by_id("rx1") is True
    assert deactivate_recipient_by_id("rx1") is False
    assert deactivate_recipient_by_id("does_not_exist") is False
    ids = {r["id"] for r in get_active_recipients()}
    assert "rx1" not in ids and "rx2" in ids

    # Deactivate by address
    assert deactivate_recipient("user3@company.it", "email") is True
    assert deactivate_recipient("user3@company.it", "email") is False
    assert "user3@company.it" not in {r["address"] for r in get_active_recipients()}

    # Re-adding reactivates the row
    assert add_recipient("rx1_new", "email", "remove_me@company.it")
    assert "remove_me@company.it" in {r["address"] for r in get_active_recipients("email")}

    # Bulk clear
    assert deactivate_all_recipients() >= 2
    assert get_active_recipients() == []
    assert deactivate_all_recipients() == 0