"""Persisted verification queue with one bounded local model job at a time."""

import json
import logging
import multiprocessing
import sqlite3
import threading
import time
from uuid import uuid4

from . import database as store
from . import vision
from .config import MAX_PAGES, UPLOADS

logger = logging.getLogger(__name__)
STOP = threading.Event()


def present(row, current_version):
    if not row:
        return None
    job = dict(row)
    job["result"] = json.loads(job.pop("result_json"))
    job.pop("snapshot_json", None)
    job["stale"] = job["document_version"] != current_version
    return job


def enqueue(document, model, version):
    if document["version"] != version or document["status"] in {"queued", "processing", "failed"}:
        raise ValueError("Save and reload the extracted draft before verifying it.")
    if model not in vision.capabilities()["models"]:
        raise ValueError("The selected local vision model is not installed or available.")
    if not 1 <= document["page_count"] <= MAX_PAGES:
        raise ValueError("Document exceeds the supported page limit.")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT version,status FROM documents WHERE id=?", (document["id"],)
        ).fetchone()
        if current["version"] != version or current["status"] in {"queued", "processing", "failed"}:
            raise ValueError("Draft changed. Reload before verifying.")
        existing = db.execute(
            """SELECT * FROM verification_jobs WHERE document_id=?
            AND document_version=? AND model=? AND status IN ('queued','running')""",
            (document["id"], version, model),
        ).fetchone()
        if existing:
            return present(existing, version)
        queued = db.execute(
            "SELECT count(*) FROM verification_jobs WHERE status IN ('queued','running')"
        ).fetchone()[0]
        if queued >= 12:
            raise ValueError("Verification queue is full. Wait for a running check to finish.")
        job_id = uuid4().hex
        db.execute(
            """INSERT INTO verification_jobs
            (id,document_id,document_version,model,status,snapshot_json,created_at,updated_at)
            VALUES(?,?,?,?,'queued',?,?,?)""",
            (
                job_id,
                document["id"],
                version,
                model,
                json.dumps(document["invoice"]),
                store.now(),
                store.now(),
            ),
        )
        store.event(
            db,
            document["id"],
            "ai_verification_requested",
            {"job_id": job_id, "model": model, "version": version},
        )
        return present(
            db.execute("SELECT * FROM verification_jobs WHERE id=?", (job_id,)).fetchone(), version
        )


def process_job(job_id):
    with store.connection() as db:
        row = dict(db.execute("SELECT * FROM verification_jobs WHERE id=?", (job_id,)).fetchone())
    document = store.get_document(row["document_id"])
    snapshot = json.loads(row["snapshot_json"])
    pages, errors = [], []
    for page in range(1, document["page_count"] + 1):
        try:
            pages.append(
                vision.read_page(
                    UPLOADS / document["storage_name"], document["mime"], page, row["model"]
                )
            )
        except Exception as error:
            logger.warning("Vision page %s failed: %s", page, type(error).__name__)
            errors.append(
                {
                    "page": page,
                    "error": "The local model could not read this page. Inspect it manually or retry.",
                }
            )
        result = {
            "pages": pages,
            "errors": errors,
            "report": vision.compare(snapshot, pages),
            "total_pages": document["page_count"],
            "prompt_version": vision.PROMPT_VERSION,
        }
        with store.connection() as db:
            db.execute(
                "UPDATE verification_jobs SET result_json=?,completed_pages=?,updated_at=? WHERE id=?",
                (json.dumps(result), page, store.now(), job_id),
            )
    status = "completed" if not errors else ("partial" if pages else "failed")
    with store.connection() as db:
        db.execute(
            "UPDATE verification_jobs SET status=?,error=?,updated_at=? WHERE id=?",
            (
                status,
                "Some source pages could not be read." if errors else None,
                store.now(),
                job_id,
            ),
        )
        store.event(
            db,
            document["id"],
            "ai_verification_finished",
            {
                "job_id": job_id,
                "model": row["model"],
                "version": row["document_version"],
                "status": status,
                "read_pages": len(pages),
                "failed_pages": len(errors),
            },
        )


def finish_interrupted(job_id, reason):
    with store.connection() as db:
        row = db.execute(
            "SELECT result_json FROM verification_jobs WHERE id=?", (job_id,)
        ).fetchone()
        result = json.loads(row["result_json"])
        db.execute(
            "UPDATE verification_jobs SET status=?,error=?,updated_at=? WHERE id=? AND status='running'",
            ("partial" if result.get("pages") else "failed", reason, store.now(), job_id),
        )


def supervise():
    context = multiprocessing.get_context("spawn")
    while not STOP.is_set():
        try:
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT id FROM verification_jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row:
                    db.execute(
                        "UPDATE verification_jobs SET status='running',updated_at=? WHERE id=?",
                        (store.now(), row["id"]),
                    )
        except sqlite3.Error:
            logger.exception("Unable to read the vision queue")
            STOP.wait(2)
            continue
        if not row:
            STOP.wait(0.6)
            continue
        process = context.Process(target=process_job, args=(row["id"],))
        try:
            process.start()
            deadline = time.monotonic() + 900
            while process.is_alive() and not STOP.is_set() and time.monotonic() < deadline:
                process.join(0.5)
            if process.is_alive():
                process.terminate()
                process.join(5)
                finish_interrupted(
                    row["id"],
                    "Verification stopped before all pages were read. Review the incomplete coverage and retry.",
                )
            elif process.exitcode != 0:
                finish_interrupted(
                    row["id"], "Vision worker stopped unexpectedly. Retry verification."
                )
        except Exception:
            logger.exception("Unable to start vision worker")
            finish_interrupted(row["id"], "Could not start local verification. Retry it.")
        finally:
            if not process.is_alive():
                process.close()


def start():
    STOP.clear()
    thread = threading.Thread(target=supervise, daemon=True, name="vision-supervisor")
    thread.start()
    return thread


def stop(thread):
    STOP.set()
    thread.join(8)
