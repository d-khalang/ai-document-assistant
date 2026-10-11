"""Dispatcher: aggregates pending alerts per recipient into a single digest and logs results."""
import uuid
from typing import Dict, List, Optional
from datetime import date
from app.alerts.store import (
    get_active_deadlines,
    get_active_recipients,
    is_alert_already_sent,
    log_alert_result
)
from app.alerts.scanner import scan_deadlines, Alert
from app.alerts.notifiers import SmtpEmailNotifier, TwilioSmsNotifier


def build_email_digest(alerts: List[Alert]) -> str:
    lines = [
        "AVVISO SCADENZE E CONFORMITÀ NORMATIVA",
        "=====================================",
        f"Totale scadenze in evidenza: {len(alerts)}\n"
    ]
    for a in alerts:
        if a.days_left < 0:
            status_txt = f"SCADUTO DA {-a.days_left} GIORNI"
        elif a.days_left == 0:
            status_txt = "SCADE OGGI!"
        else:
            status_txt = f"Scade tra {a.days_left} giorni"

        lines.append(f"• [{status_txt}] {a.description}")
        lines.append(f"  Data Scadenza: {a.due_date} | Fonte: {a.source} | Modulo: {a.module_id}\n")

    lines.append("Verificare gli adempimenti sulla piattaforma Document Intelligence.")
    return "\n".join(lines)


def dispatch_alerts(
    today: Optional[date] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    اجرای کامل فرآیند اسکن و توزیع هشدارها.
    خروجی: دیکشنری تعداد هشدارهای ارسال‌شده، شبیه‌سازی‌شده و رد شده.
    """
    deadlines = get_active_deadlines()
    alerts = scan_deadlines(deadlines, today=today)

    recipients_email = get_active_recipients(channel="email")
    recipients_sms = get_active_recipients(channel="sms")

    email_client = SmtpEmailNotifier()
    sms_client = TwilioSmsNotifier()

    # اضافه شدن کلید simulated
    stats = {"sent_email": 0, "sent_sms": 0, "skipped": 0, "failed": 0, "simulated": 0}

    # ۱. پردازش ایمیل‌ها
    for rec in recipients_email:
        addr = rec["address"]
        pending_alerts = [
            a for a in alerts 
            if not is_alert_already_sent(a.deadline_id, a.due_date, a.threshold, "email", addr)
        ]

        if not pending_alerts:
            stats["skipped"] += len(alerts)
            continue

        subject = f"⚠️ Notifica Scadenze ({len(pending_alerts)} adempimenti in scadenza)"
        body = build_email_digest(pending_alerts)

        if dry_run:
            print(f"[DRY-RUN EMAIL to {addr}]\n{subject}\n{body}\n")
            stats["sent_email"] += len(pending_alerts)
            continue

        # اگر تنظیمات SMTP کانفیگ نشده باشد، فقط در آمار شبیه‌سازی حساب می‌شود و لاگ 'sent' ثبت نمی‌شود
        if not email_client.configured:
            stats["simulated"] += len(pending_alerts)
            continue

        try:
            email_client.send(addr, subject, body)
            for a in pending_alerts:
                log_alert_result(str(uuid.uuid4()), a.deadline_id, a.due_date, a.threshold, "email", addr, "sent")
            stats["sent_email"] += len(pending_alerts)
        except Exception as e:
            for a in pending_alerts:
                log_alert_result(str(uuid.uuid4()), a.deadline_id, a.due_date, a.threshold, "email", addr, "failed", str(e))
            stats["failed"] += len(pending_alerts)

    # ۲. پردازش پیامک‌ها
    for rec in recipients_sms:
        addr = rec["address"]
        for a in alerts:
            if is_alert_already_sent(a.deadline_id, a.due_date, a.threshold, "sms", addr):
                continue

            msg_txt = f"Avviso: {a.description} scade il {a.due_date} ({a.days_left} gg rimasti)."
            if dry_run:
                print(f"[DRY-RUN SMS to {addr}]: {msg_txt}")
                stats["sent_sms"] += 1
                continue

            # اگر تنظیمات توئیلیو کانفیگ نشده باشد، لاگ 'sent' ثبت نمی‌شود
            if not sms_client.configured:
                stats["simulated"] += 1
                continue

            try:
                sms_client.send(addr, "ALLERTA SCADENZA", msg_txt)
                log_alert_result(str(uuid.uuid4()), a.deadline_id, a.due_date, a.threshold, "sms", addr, "sent")
                stats["sent_sms"] += 1
            except Exception as e:
                log_alert_result(str(uuid.uuid4()), a.deadline_id, a.due_date, a.threshold, "sms", addr, "failed", str(e))
                stats["failed"] += 1

    return stats