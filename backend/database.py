import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from .config import DATA


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    db = sqlite3.connect(DATA / "workspace.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, storage_name TEXT NOT NULL,
          mime TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'queued', invoice_json TEXT NOT NULL DEFAULT '{}',
          raw_text TEXT NOT NULL DEFAULT '', raw_tables TEXT NOT NULL DEFAULT '[]',
          extraction_notes TEXT NOT NULL DEFAULT '[]', method TEXT NOT NULL DEFAULT '',
          page_count INTEGER NOT NULL DEFAULT 1, error TEXT,
          version INTEGER NOT NULL DEFAULT 1, attempts INTEGER NOT NULL DEFAULT 0,
          use_ai INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS review_events (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
          action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS templates (
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, storage_name TEXT NOT NULL,
          config_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exports (
          id TEXT PRIMARY KEY, storage_name TEXT NOT NULL,
          snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS documents_queue ON documents(status, created_at);
        CREATE INDEX IF NOT EXISTS documents_created ON documents(created_at DESC);
        CREATE INDEX IF NOT EXISTS documents_bill_number
          ON documents(lower(json_extract(invoice_json,'$.bill_number')));
        CREATE INDEX IF NOT EXISTS events_document ON review_events(document_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS verification_jobs (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
          document_version INTEGER NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
          snapshot_json TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
          completed_pages INTEGER NOT NULL DEFAULT 0, error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS verification_document
          ON verification_jobs(document_id,created_at DESC);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
        if "source_currency" not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN source_currency TEXT")
        db.execute("""UPDATE documents SET source_currency=coalesce(
            json_extract(invoice_json,'$.currency'),'INR') WHERE source_currency IS NULL
            AND status NOT IN ('queued','processing')""")
        db.execute("PRAGMA user_version=3")
        db.execute("""UPDATE verification_jobs SET status='failed',
            error='Verification interrupted when the app stopped. Run it again.'
            WHERE status='running'""")
        # This is a single-process local workspace. Recover interrupted jobs on startup.
        db.execute("UPDATE documents SET status='queued', error=NULL WHERE status='processing'")


def decode(row):
    if row is None:
        return None
    data = dict(row)
    for key, target in [
        ("invoice_json", "invoice"),
        ("raw_tables", "raw_tables"),
        ("extraction_notes", "extraction_notes"),
    ]:
        if key in data:
            data[target] = json.loads(data.pop(key))
    return data


def get_document(document_id):
    with connection() as db:
        return decode(db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone())


def event(db, document_id, action, detail):
    db.execute(
        "INSERT INTO review_events VALUES(?,?,?,?,?)",
        (uuid4().hex, document_id, action, json.dumps(detail), now()),
    )
