import sqlite3
import json
import hashlib
import hmac
import os
from datetime import datetime

DB_PATH = "src/data/scans.db"


def init_db():
    """Initialize all database tables with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH)

    # Tier 2 Fix — WAL (Write-Ahead Logging) mode
    # Without WAL: concurrent background scan threads cause
    # "database is locked" errors when writing simultaneously.
    # WAL allows multiple readers + one writer at the same time.
    conn.execute("PRAGMA journal_mode=WAL;")

    # 5 second timeout before giving up on locked write
    # Prevents "database is locked" crashes under load
    conn.execute("PRAGMA busy_timeout=5000;")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY,
            file_name TEXT,
            file_size_mb REAL,
            verdict TEXT,
            risk_score INTEGER,
            safe_to_deploy INTEGER,
            status TEXT,
            report_text TEXT,
            scan_results TEXT,
            metadata TEXT,
            processing_time REAL,
            analyst_id INTEGER,
            created_at TEXT,
            completed_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            first_name TEXT,
            last_name TEXT,
            hashed_password TEXT NOT NULL,
            role TEXT DEFAULT 'readonly',
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


def save_scan(scan_result: dict, analyst_id: int = None,
              file_name: str = "unknown"):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO scans
            (id, file_name, file_size_mb, verdict, risk_score,
             safe_to_deploy, status, report_text, scan_results,
             metadata, processing_time, analyst_id,
             created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_result.get("scan_id"),
            file_name,
            scan_result.get("metadata", {}).get("file_size_mb", 0),
            scan_result.get("verdict"),
            scan_result.get("risk_score"),
            1 if scan_result.get("safe_to_deploy") else 0,
            scan_result.get("status"),
            scan_result.get("report", {}).get("report_text", ""),
            json.dumps(scan_result.get("scan_results", {})),
            json.dumps(scan_result.get("metadata", {})),
            scan_result.get("processing_time_seconds"),
            analyst_id,
            scan_result.get("started_at"),
            scan_result.get("completed_at")
        ))
        conn.commit()
    finally:
        conn.close()


def get_all_scans(limit: int = 50) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, file_name, verdict, risk_score,
               safe_to_deploy, status, processing_time, created_at
        FROM scans ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "scan_id": r[0], "file_name": r[1],
            "verdict": r[2], "risk_score": r[3],
            "safe_to_deploy": bool(r[4]), "status": r[5],
            "processing_time": r[6], "created_at": r[7]
        }
        for r in rows
    ]


def get_scan_by_id(scan_id: str) -> dict:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    cols = ["id", "file_name", "file_size_mb", "verdict", "risk_score",
            "safe_to_deploy", "status", "report_text", "scan_results",
            "metadata", "processing_time", "analyst_id",
            "created_at", "completed_at"]
    return dict(zip(cols, row))


def hash_password(password: str) -> str:
    salt = os.urandom(32).hex()
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(":")
        check = hashlib.sha256((plain + salt).encode()).hexdigest()
        return hmac.compare_digest(check, hashed)
    except Exception:
        return False


def create_user(username: str, email: str, password: str,
                role: str, first_name: str = "",
                last_name: str = "") -> dict:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        hashed = hash_password(password)
        cursor.execute("""
            INSERT INTO users
            (username, email, first_name, last_name,
             hashed_password, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, email, first_name, last_name,
              hashed, role, datetime.now().isoformat()))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return {"id": user_id, "username": username, "role": role}
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "Username or email already exists"}


def get_user_by_username(username: str) -> dict:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, hashed_password,
               role, is_active
        FROM users WHERE username = ?
    """, (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "email": row[2],
        "hashed_password": row[3], "role": row[4],
        "is_active": row[5]
    }