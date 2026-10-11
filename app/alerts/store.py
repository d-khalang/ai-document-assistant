"""SQLite persistence layer for deadlines, recipients, and alert logs."""
import os
import sqlite3
import json
from app.config import get_db_path
from typing import Dict, List, Optional, Any

DB_PATH = os.getenv("ASSISTANT_DB_PATH", "assistant.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def ensure_alert_tables() -> None:
    """ایجاد جداول مورد نیاز برای سیستم هشدارها در صورت عدم وجود."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS deadlines (
          id TEXT PRIMARY KEY,
          module_id TEXT NOT NULL,
          schema_name TEXT NOT NULL,
          field_name TEXT NOT NULL,
          description TEXT NOT NULL,
          due_date TEXT NOT NULL,
          thresholds TEXT NOT NULL,
          source_document TEXT,
          source_page INTEGER,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alert_recipients (
          id TEXT PRIMARY KEY,
          channel TEXT NOT NULL CHECK (channel IN ('email', 'sms')),
          address TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1,
          UNIQUE(channel, address)
        );

        CREATE TABLE IF NOT EXISTS alert_log (
          id TEXT PRIMARY KEY,
          deadline_id TEXT NOT NULL,
          due_date TEXT NOT NULL,
          threshold_days INTEGER NOT NULL,
          channel TEXT NOT NULL,
          recipient TEXT NOT NULL,
          status TEXT NOT NULL,
          error TEXT,
          sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_sent
          ON alert_log(deadline_id, due_date, threshold_days, channel, recipient) WHERE status = 'sent';
        """)
        conn.commit()


def upsert_deadline(
    deadline_id: str,
    module_id: str,
    schema_name: str,
    field_name: str,
    description: str,
    due_date: str,
    thresholds: List[int],
    source_document: Optional[str] = None,
    source_page: Optional[int] = None
) -> None:
    """ثبت یا به‌روزرسانی سررسید با حفظ شناسه یکتا."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO deadlines (
            id, module_id, schema_name, field_name, description, due_date, thresholds, source_document, source_page, active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(id) DO UPDATE SET
            due_date = excluded.due_date,
            description = excluded.description,
            thresholds = excluded.thresholds,
            active = 1;
        """, (
            deadline_id, module_id, schema_name, field_name, description,
            due_date, json.dumps(thresholds), source_document, source_page
        ))
        conn.commit()


def get_active_deadlines() -> List[Dict[str, Any]]:
    """دریافت کلیه سررسیدهای فعال."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deadlines WHERE active = 1 ORDER BY due_date ASC")
        return [dict(row) for row in cursor.fetchall()]


def add_recipient(recipient_id: str, channel: str, address: str) -> bool:
    """ثبت گیرنده جدید هشدار (ایمیل یا پیامک)."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO alert_recipients (id, channel, address, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(channel, address) DO UPDATE SET active = 1;
            """, (recipient_id, channel, address))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding recipient: {e}")
        return False


def get_active_recipients(channel: Optional[str] = None) -> List[Dict[str, Any]]:
    """دریافت فهرست گیرندگان فعال."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if channel:
            cursor.execute("SELECT * FROM alert_recipients WHERE active = 1 AND channel = ?", (channel,))
        else:
            cursor.execute("SELECT * FROM alert_recipients WHERE active = 1")
        return [dict(row) for row in cursor.fetchall()]


def is_alert_already_sent(deadline_id: str, due_date: str, threshold_days: int, channel: str, recipient: str) -> bool:
    """بررسی ارسال قبلی هشدار جهت جلوگیری از تکرار."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 1 FROM alert_log
        WHERE deadline_id = ? AND due_date = ? AND threshold_days = ? AND channel = ? AND recipient = ? AND status = 'sent'
        """, (deadline_id, due_date, threshold_days, channel, recipient))
        return cursor.fetchone() is not None


def log_alert_result(
    log_id: str,
    deadline_id: str,
    due_date: str,
    threshold_days: int,
    channel: str,
    recipient: str,
    status: str,
    error: Optional[str] = None
) -> None:
    """ثبت نتیجه ارسال در لاگ."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO alert_log (id, deadline_id, due_date, threshold_days, channel, recipient, status, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, deadline_id, due_date, threshold_days, channel, recipient, status, error))
        conn.commit()

def deactivate_deadlines_for_document(source_document: str) -> int:
    """غیرفعال کردن تمام سررسیدهای سندی که حذف شده است."""
    with get_connection() as conn:
        cur = conn.execute("UPDATE deadlines SET active = 0 WHERE active = 1 AND source_document = ?", (source_document,))
        conn.commit()
        return cur.rowcount

def deactivate_missing_deadlines(keep_ids, source_documents) -> int:
    """غیرفعال کردن سررسیدهای تغییریافته یا حذف‌شده."""
    docs = list(source_documents)
    if not docs:
        return 0
    keep = list(keep_ids)
    q_docs = ",".join("?" * len(docs))
    sql = f"UPDATE deadlines SET active = 0 WHERE active = 1 AND source_document IN ({q_docs})"
    params = docs
    if keep:
        sql += f" AND id NOT IN ({','.join('?' * len(keep))})"
        params = docs + keep
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount