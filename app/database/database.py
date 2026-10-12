import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import get_db_path


def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            document_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        );
    """)

    try:
        cursor.execute("ALTER TABLE conversations ADD COLUMN document_id TEXT;")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            company_name TEXT NOT NULL,
            vat_number TEXT,
            address TEXT,
            rsga_name TEXT,
            technical_director TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # در صورت وجود رکوردهای هاردکد قدیمی EFFE.EMME، آن‌ها را پاک می‌کنیم
    cursor.execute("""
        UPDATE company_profile
        SET company_name = '', vat_number = '', address = '', rsga_name = '', technical_director = ''
        WHERE company_name LIKE '%EFFE.EMME%';
    """)

    # ایجاد یک ردیف پیش‌فرض خالی در صورت عدم وجود
    cursor.execute("SELECT COUNT(*) FROM company_profile WHERE id = 1;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO company_profile (id, company_name, vat_number, address, rsga_name, technical_director)
            VALUES (1, '', '', '', '', '');
        """)

    conn.commit()
    conn.close()


def get_company_profile() -> Dict[str, Any]:
    """دریافت آخرین اطلاعات پروفایل شرکت از دیتابیس (بدون مقادیر هاردکد پیش‌فرض)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT company_name, vat_number, address, rsga_name, technical_director, updated_at FROM company_profile WHERE id = 1;")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "company_name": "",
        "vat_number": "",
        "address": "",
        "rsga_name": "",
        "technical_director": "",
        "updated_at": datetime.now().isoformat()
    }


def update_company_profile(
    company_name: str,
    vat_number: str = "",
    address: str = "",
    rsga_name: str = "",
    technical_director: str = ""
) -> None:
    """به‌روزرسانی پایدار مشخصات شرکت در دیتابیس."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO company_profile (id, company_name, vat_number, address, rsga_name, technical_director, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            company_name = excluded.company_name,
            vat_number = excluded.vat_number,
            address = excluded.address,
            rsga_name = excluded.rsga_name,
            technical_director = excluded.technical_director,
            updated_at = CURRENT_TIMESTAMP;
    """, (company_name.strip(), vat_number.strip(), address.strip(), rsga_name.strip(), technical_director.strip()))
    conn.commit()
    conn.close()


def create_user() -> str:
    user_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (id) VALUES (?);", (user_id,))
    conn.commit()
    conn.close()
    return user_id


def create_document(user_id: str, filename: str) -> str:
    doc_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO documents (id, user_id, filename) VALUES (?, ?, ?);", (doc_id, user_id, filename))
    conn.commit()
    conn.close()
    return doc_id


def create_conversation(user_id: str, document_id: Optional[str] = None) -> str:
    conv_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (id, user_id, document_id) VALUES (?, ?, ?);",
        (conv_id, user_id, document_id)
    )
    conn.commit()
    conn.close()
    return conv_id


def save_message(conversation_id: str, role: str, content: str) -> str:
    msg_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?);",
        (msg_id, conversation_id, role, content)
    )
    conn.commit()
    conn.close()
    return msg_id


def get_conversation_history(conversation_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC;",
        (conversation_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]