import json
import logging
import multiprocessing
import sqlite3
import threading
import time

from . import database as store
from .config import UPLOADS

logger = logging.getLogger(__name__)
STOP = threading.Event()


def process_document(document_id):
    from .ai import assist, merge_proposal
    from .extraction import extract_document

    document = store.get_document(document_id)
    try:
        result = extract_document(UPLOADS / document["storage_name"], document["mime"])
        if document["use_ai"]:
            try:
                proposal = assist(result["raw_text"], result["page_count"])
                result["invoice"], merge_notes = merge_proposal(
                    result["invoice"], proposal, result["raw_text"]
                )
                result["notes"].extend(merge_notes)
                result["method"] += "+local-ai"
                result["notes"].append(
                    "Local AI filled source-backed missing fields. Existing extracted values were preserved. Verify the draft."
                )
            except Exception as error:
                logger.warning("AI assist failed for %s: %s", document_id, error)
                result["notes"].append(
                    "Local AI could not produce a valid result. The direct/OCR draft is retained."
                )
        with store.connection() as db:
            db.execute(
                """UPDATE documents SET status='needs_review', invoice_json=?,raw_text=?,
                raw_tables=?,extraction_notes=?,method=?,page_count=?,error=NULL,
                source_currency=?,version=version+1,updated_at=? WHERE id=? AND status='processing'""",
                (
                    result["invoice"].model_dump_json(),
                    result["raw_text"],
                    json.dumps(result["raw_tables"]),
                    json.dumps(result["notes"]),
                    result["method"],
                    result["page_count"],
                    result["invoice"].currency,
                    store.now(),
                    document_id,
                ),
            )
            store.event(
                db,
                document_id,
                "extracted",
                {
                    "method": result["method"],
                    "items": len(result["invoice"].items),
                    "invoice": result["invoice"].model_dump(mode="json"),
                    "previous": document["invoice"],
                },
            )
    except Exception as error:
        logger.exception("Document processing failed: %s", document_id)
        message = (
            str(error)[:350]
            if isinstance(error, ValueError)
            else ("Processing could not finish. Retry the document or enter the bill manually.")
        )
        with store.connection() as db:
            db.execute(
                """UPDATE documents SET status='failed',error=?,version=version+1,
                updated_at=? WHERE id=?""",
                (message, store.now(), document_id),
            )


def supervise():
    context = multiprocessing.get_context("spawn")
    while not STOP.is_set():
        try:
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT id FROM documents WHERE status='queued' ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row:
                    db.execute(
                        "UPDATE documents SET status='processing',attempts=attempts+1,updated_at=? WHERE id=?",
                        (store.now(), row["id"]),
                    )
        except sqlite3.Error:
            logger.exception("Could not read the processing queue; retrying shortly")
            STOP.wait(2)
            continue
        if row is None:
            STOP.wait(0.6)
            continue
        process = context.Process(target=process_document, args=(row["id"],))
        try:
            process.start()
            deadline = time.monotonic() + 240
            while process.is_alive() and not STOP.is_set() and time.monotonic() < deadline:
                process.join(0.5)
            if process.is_alive():
                process.terminate()
                process.join(5)
                reason = (
                    "Processing paused when the app stopped."
                    if STOP.is_set()
                    else (
                        "Processing exceeded four minutes. Split the document or review it manually."
                    )
                )
                with store.connection() as db:
                    db.execute(
                        "UPDATE documents SET status=?,error=?,version=version+1,updated_at=? WHERE id=?",
                        ("queued" if STOP.is_set() else "failed", reason, store.now(), row["id"]),
                    )
            elif process.exitcode != 0:
                with store.connection() as db:
                    db.execute(
                        "UPDATE documents SET status='failed',error=?,updated_at=? WHERE id=?",
                        (
                            "The processing worker stopped unexpectedly. Retry this bill.",
                            store.now(),
                            row["id"],
                        ),
                    )
        except Exception:
            logger.exception("Unable to start processing worker")
            with store.connection() as db:
                db.execute(
                    "UPDATE documents SET status='failed',error=?,updated_at=? WHERE id=?",
                    ("Could not start the processing worker.", store.now(), row["id"]),
                )
        finally:
            if not process.is_alive():
                process.close()


def start():
    STOP.clear()
    thread = threading.Thread(target=supervise, daemon=True, name="invoice-supervisor")
    thread.start()
    return thread


def stop(thread):
    STOP.set()
    thread.join(8)
