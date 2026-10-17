import hashlib
import importlib.util
import io
import json
import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

import pypdfium2 as pdfium
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from . import ai, worker
from . import database as store
from .config import (
    EXPORTS,
    MAX_BATCH_BYTES,
    MAX_BATCH_FILES,
    MAX_FILE_BYTES,
    MAX_IMAGE_PIXELS,
    PREVIEWS,
    ROOT,
    TEMPLATES,
    UPLOADS,
)
from .models import ApproveRequest, ExportRequest, Invoice, SaveRequest, TemplateConfig
from .validation import validate_invoice
from .workbooks import FIELDS, create_export, inspect_template

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    thread = worker.start()
    yield
    worker.stop(thread)


app = FastAPI(title="Akshay invoice workspace", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = {
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
    }
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in allowed:
        return HTMLResponse("This workspace accepts local requests only.", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def document_or_404(document_id):
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(404, "Document not found.")
    return document


def financial_year(value):
    try:
        day = date.fromisoformat(str(value))
        return day.year - (day.month < 4)
    except ValueError:
        return None


def business_duplicates(invoice, document_id):
    if not invoice.bill_number or not invoice.supplier_name:
        return []
    with store.connection() as db:
        rows = db.execute(
            """SELECT id,invoice_json FROM documents WHERE id<>? AND
            lower(json_extract(invoice_json,'$.bill_number'))=lower(?)""",
            (document_id, invoice.bill_number.strip()),
        ).fetchall()
    matches = []
    for row in rows:
        other = json.loads(row["invoice_json"])
        same_supplier = (
            invoice.supplier_gstin.upper() == other.get("supplier_gstin", "").upper()
            if invoice.supplier_gstin and other.get("supplier_gstin")
            else invoice.supplier_name.casefold().strip()
            == other.get("supplier_name", "").casefold().strip()
        )
        same_year = financial_year(invoice.bill_date) == financial_year(other.get("bill_date"))
        if same_supplier and same_year:
            matches.append(row["id"])
    return matches


def present(document, include_raw=True):
    invoice = Invoice.model_validate(document["invoice"])
    document["invoice"] = invoice.model_dump(mode="json")
    document["validation"] = validate_invoice(
        invoice, business_duplicates(invoice, document["id"]) if include_raw else []
    )
    if not include_raw:
        document.pop("raw_text", None)
        document.pop("raw_tables", None)
    return document


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "workspace": "local",
        "ai": ai.capabilities(),
        "ocr_installed": importlib.util.find_spec("rapidocr") is not None,
        "limits": {"file_mb": 15, "batch_files": MAX_BATCH_FILES, "pages": 25},
        "export_fields": FIELDS,
    }


@app.get("/api/documents")
def documents():
    with store.connection() as db:
        rows = db.execute(
            """SELECT id,filename,status,invoice_json,extraction_notes,method,page_count,
            version,error,created_at,updated_at FROM documents ORDER BY created_at DESC LIMIT 500"""
        ).fetchall()
    return [present(store.decode(row), include_raw=False) for row in rows]


@app.get("/api/inbox")
def inbox(
    search: str = Query(default="", max_length=200),
    status: Literal["all", "review", "approved", "processing"] = "all",
    date_from: date | None = None,
    date_to: date | None = None,
    order: Literal["newest", "bill_date", "amount"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "The start date must be before the end date.")
    conditions, parameters = [], []
    if search.strip():
        # Treat %, _ and backslashes as literal search characters.
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("""(filename || ' ' ||
            coalesce(json_extract(invoice_json,'$.supplier_name'),'') || ' ' ||
            coalesce(json_extract(invoice_json,'$.bill_number'),'') || ' ' ||
            coalesce(json_extract(invoice_json,'$.supplier_gstin'),'') || ' ' ||
            coalesce(json_extract(invoice_json,'$.purchase_number'),'')) LIKE ? ESCAPE '\\'""")
        parameters.append(f"%{term}%")
    for value, operator in ((date_from, ">="), (date_to, "<=")):
        if value:
            conditions.append(f"json_extract(invoice_json,'$.bill_date') {operator} ?")
            parameters.append(value.isoformat())
    where = " AND ".join(conditions) or "1=1"
    status_conditions = {
        "all": "1=1",
        "review": "status IN ('needs_review','failed')",
        "approved": "status='approved'",
        "processing": "status IN ('queued','processing')",
    }
    ordering = {
        "newest": "created_at DESC,id DESC",
        "bill_date": "json_extract(invoice_json,'$.bill_date') DESC,created_at DESC,id DESC",
        "amount": "CAST(json_extract(invoice_json,'$.grand_total') AS REAL) DESC,created_at DESC,id DESC",
    }[order]
    with store.connection() as db:
        # Use one read snapshot for counts, totals and the current page.
        db.execute("BEGIN")
        total = db.execute("SELECT count(*) FROM documents").fetchone()[0]
        counts = {
            row[0]: row[1]
            for row in db.execute(
                f"SELECT status,count(*) FROM documents WHERE {where} GROUP BY status",
                parameters,
            )
        }
        approved_value = sum(
            (
                Decimal(str(row[0]))
                for row in db.execute(
                    f"SELECT json_extract(invoice_json,'$.grand_total') FROM documents WHERE {where} AND status='approved'",
                    parameters,
                )
                if row[0] is not None
            ),
            Decimal(0),
        )
        matched = db.execute(
            f"SELECT count(*) FROM documents WHERE {where} AND {status_conditions[status]}",
            parameters,
        ).fetchone()[0]
        # Clamp a page if filtering or changes in status made the last page empty.
        page = min(page, max(1, (matched + page_size - 1) // page_size))
        rows = db.execute(
            f"""SELECT id,filename,status,method,page_count,version,
            error,created_at,updated_at,json_object(
            'supplier_name',json_extract(invoice_json,'$.supplier_name'),
            'bill_number',json_extract(invoice_json,'$.bill_number'),
            'bill_date',json_extract(invoice_json,'$.bill_date'),
            'grand_total',json_extract(invoice_json,'$.grand_total')) AS invoice_json
            FROM documents WHERE {where} AND {status_conditions[status]}
            ORDER BY {ordering} LIMIT ? OFFSET ?""",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    return {
        "items": [store.decode(row) for row in rows],
        "total": total,
        "matched": matched,
        "page": page,
        "page_size": page_size,
        "counts": {
            "all": sum(counts.values()),
            "review": counts.get("needs_review", 0) + counts.get("failed", 0),
            "approved": counts.get("approved", 0),
            "processing": counts.get("queued", 0) + counts.get("processing", 0),
        },
        "approved_value": str(approved_value),
    }


def detect_type(content):
    if b"%PDF-" in content[:1024]:
        return "application/pdf", ".pdf"
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise ValueError("Choose a PDF, JPG or PNG file.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds 25 megapixels.")
            mime = "image/jpeg" if image.format == "JPEG" else "image/png"
            image.verify()
            return mime, ".jpg" if mime == "image/jpeg" else ".png"
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Choose a readable PDF, JPG or PNG file.") from error


@app.post("/api/documents", status_code=201)
def upload_documents(
    files: Annotated[list[UploadFile], File()],
    use_ai: Annotated[bool, Form()] = False,
):
    if not 1 <= len(files) <= MAX_BATCH_FILES:
        raise HTTPException(413, f"Upload 1 to {MAX_BATCH_FILES} files at a time.")
    if use_ai and not ai.capabilities()["available"]:
        raise HTTPException(422, "The configured local AI model is not available.")
    result = {"created": [], "duplicates": [], "errors": []}
    total = 0
    for upload in files:
        filename = re.sub(
            r"[\x00-\x1f]", "", (upload.filename or "bill").replace("\\", "/").split("/")[-1]
        )[:160]
        try:
            content = upload.file.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if not content or len(content) > MAX_FILE_BYTES:
                raise ValueError("File is empty or exceeds 15 MB.")
            if total > MAX_BATCH_BYTES:
                raise ValueError("Batch exceeds 60 MB. Upload the remaining files separately.")
            mime, extension = detect_type(content)
            digest = hashlib.sha256(content).hexdigest()
            with store.connection() as db:
                existing = db.execute(
                    "SELECT id FROM documents WHERE sha256=?", (digest,)
                ).fetchone()
            if existing:
                result["duplicates"].append({"filename": filename, "id": existing["id"]})
                continue
            document_id = uuid4().hex
            storage_name = document_id + extension
            path = UPLOADS / storage_name
            path.write_bytes(content)
            try:
                with store.connection() as db:
                    db.execute(
                        """INSERT INTO documents
                        (id,filename,storage_name,mime,sha256,invoice_json,use_ai,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            document_id,
                            filename,
                            storage_name,
                            mime,
                            digest,
                            Invoice().model_dump_json(),
                            int(use_ai),
                            store.now(),
                            store.now(),
                        ),
                    )
                    store.event(db, document_id, "uploaded", {"filename": filename})
            except sqlite3.IntegrityError:
                path.unlink(missing_ok=True)
                with store.connection() as db:
                    existing = db.execute(
                        "SELECT id FROM documents WHERE sha256=?", (digest,)
                    ).fetchone()
                if not existing:
                    raise
                result["duplicates"].append({"filename": filename, "id": existing["id"]})
                continue
            result["created"].append({"id": document_id, "filename": filename})
        except ValueError as error:
            result["errors"].append({"filename": filename, "message": str(error)})
        finally:
            upload.file.close()
    return result


@app.get("/api/documents/{document_id}")
def get_document(document_id: str):
    document = present(document_or_404(document_id))
    with store.connection() as db:
        document["history"] = [
            dict(row)
            for row in db.execute(
                """SELECT id,action,created_at FROM review_events WHERE document_id=?
                ORDER BY created_at DESC LIMIT 30""",
                (document_id,),
            ).fetchall()
        ]
    return document


def history_or_404(document_id, event_id):
    document_or_404(document_id)
    with store.connection() as db:
        row = db.execute(
            "SELECT * FROM review_events WHERE id=? AND document_id=?",
            (event_id, document_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "History entry not found.")
    detail = json.loads(row["detail"])
    snapshot = detail.get("invoice") or detail.get("previous")
    return {**dict(row), "detail": detail, "invoice": snapshot}


@app.get("/api/documents/{document_id}/history/{event_id}")
def history(document_id: str, event_id: str):
    return history_or_404(document_id, event_id)


class RestoreRequest(BaseModel):
    version: int


@app.post("/api/documents/{document_id}/history/{event_id}/restore")
def restore(document_id: str, event_id: str, payload: RestoreRequest):
    record = history_or_404(document_id, event_id)
    if not record["invoice"]:
        raise HTTPException(422, "This activity has no saved invoice snapshot.")
    invoice = Invoice.model_validate(record["invoice"])
    # Restoring creates a new unapproved draft; it never rewrites the audit trail.
    return save_document(
        document_id,
        SaveRequest(invoice=invoice, version=payload.version),
        action="restored",
        restore_event_id=event_id,
    )


def save_document(document_id, payload, approve=False, action=None, restore_event_id=None):
    document = document_or_404(document_id)
    if document["status"] in {"queued", "processing"}:
        raise HTTPException(409, "Wait for processing to finish before editing.")
    if any(item.source_page > document["page_count"] for item in payload.invoice.items):
        raise HTTPException(422, "An item refers to a page outside this document.")
    validation = validate_invoice(
        payload.invoice, business_duplicates(payload.invoice, document_id)
    )
    if approve:
        if validation["errors"]:
            raise HTTPException(422, "Resolve the validation errors before approval.")
        if validation["warnings"] and not payload.acknowledge_warnings:
            raise HTTPException(422, "Confirm that you have reviewed the warnings before approval.")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT version,invoice_json FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if current["version"] != payload.version:
            raise HTTPException(409, "This draft changed in another window. Reload before saving.")
        db.execute(
            """UPDATE documents SET invoice_json=?,status=?,error=NULL,version=version+1,
            updated_at=? WHERE id=?""",
            (
                payload.invoice.model_dump_json(),
                "approved" if approve else "needs_review",
                store.now(),
                document_id,
            ),
        )
        store.event(
            db,
            document_id,
            action or ("approved" if approve else "saved"),
            {
                "previous": json.loads(current["invoice_json"]),
                "invoice": payload.invoice.model_dump(mode="json"),
                "review_note": payload.review_note if approve else "",
                "restored_from": restore_event_id,
            },
        )
    return get_document(document_id)


@app.put("/api/documents/{document_id}")
def save(document_id: str, payload: SaveRequest):
    return save_document(document_id, payload)


@app.post("/api/documents/{document_id}/approve")
def approve(document_id: str, payload: ApproveRequest):
    return save_document(document_id, payload, approve=True)


class RetryRequest(BaseModel):
    version: int
    use_ai: bool = False


@app.post("/api/documents/{document_id}/retry")
def retry(document_id: str, payload: RetryRequest):
    document = document_or_404(document_id)
    if document["status"] not in {"failed", "needs_review"}:
        raise HTTPException(409, "Only failed or unapproved bills can be re-extracted.")
    if payload.use_ai and not ai.capabilities()["available"]:
        raise HTTPException(422, "The local AI model is not available.")
    with store.connection() as db:
        changed = db.execute(
            """UPDATE documents SET status='queued',use_ai=?,error=NULL,
            version=version+1,updated_at=? WHERE id=? AND version=?""",
            (int(payload.use_ai), store.now(), document_id, payload.version),
        ).rowcount
        if not changed:
            raise HTTPException(409, "Document changed. Reload before retrying.")
        store.event(db, document_id, "requeued", {"previous": document["invoice"]})
    return get_document(document_id)


@app.get("/api/documents/{document_id}/source")
def original(document_id: str):
    document = document_or_404(document_id)
    return FileResponse(
        UPLOADS / document["storage_name"],
        media_type=document["mime"],
        filename=document["filename"],
    )


@app.get("/api/documents/{document_id}/preview/{page_number}")
def preview(document_id: str, page_number: int):
    document = document_or_404(document_id)
    if not 1 <= page_number <= min(25, document["page_count"]):
        raise HTTPException(404, "Page not found.")
    source = UPLOADS / document["storage_name"]
    if document["mime"] != "application/pdf":
        return FileResponse(source, media_type=document["mime"])
    target = PREVIEWS / f"{document_id}-{page_number}.png"
    if not target.exists():
        try:
            pdf = pdfium.PdfDocument(source)
            try:
                page = pdf[page_number - 1]
                try:
                    width, height = page.get_size()
                    if width * height * 1.7**2 > MAX_IMAGE_PIXELS:
                        raise ValueError("PDF page exceeds the preview rendering limit.")
                    bitmap = page.render(scale=1.7)
                    try:
                        bitmap.to_pil().save(target)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                pdf.close()
        except Exception as error:
            raise HTTPException(
                422, "Preview is unavailable. Download the original to review it."
            ) from error
    return FileResponse(target, media_type="image/png")


@app.get("/api/templates")
def templates():
    with store.connection() as db:
        rows = db.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
    return [{**dict(row), "config": json.loads(row["config_json"])} for row in rows]


@app.post("/api/templates", status_code=201)
def upload_template(file: Annotated[UploadFile, File()]):
    content = file.file.read(MAX_FILE_BYTES + 1)
    file.file.close()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Template exceeds 15 MB.")
    template_id = uuid4().hex
    storage_name = template_id + ".xlsx"
    path = TEMPLATES / storage_name
    path.write_bytes(content)
    try:
        details = inspect_template(path, header_row=None)
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(error)[:250]) from error
    filename = (file.filename or "template.xlsx").replace("\\", "/").split("/")[-1][:160]
    with store.connection() as db:
        db.execute(
            "INSERT INTO templates VALUES(?,?,?,?,?)",
            (
                template_id,
                filename,
                storage_name,
                "{}",
                store.now(),
            ),
        )
    return {"id": template_id, "filename": filename, **details}


def template_or_404(template_id):
    with store.connection() as db:
        row = db.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Template not found.")
    return dict(row)


@app.get("/api/templates/{template_id}/inspect")
def inspect(
    template_id: str,
    sheet_name: str | None = None,
    header_row: int | None = Query(default=None, ge=1, le=200),
):
    template = template_or_404(template_id)
    try:
        return inspect_template(TEMPLATES / template["storage_name"], sheet_name, header_row)
    except (ValueError, KeyError) as error:
        raise HTTPException(422, str(error)) from error


@app.put("/api/templates/{template_id}")
def save_template(template_id: str, config: TemplateConfig):
    template = template_or_404(template_id)
    try:
        details = inspect_template(
            TEMPLATES / template["storage_name"], config.sheet_name, config.header_row
        )
        allowed = {column["index"] for column in details["columns"]}
        if not config.mapping or any(key not in FIELDS for key in config.mapping):
            raise ValueError("Map at least one supported field.")
        if len(set(config.mapping.values())) != len(config.mapping):
            raise ValueError("Each target column can be mapped only once.")
        if not set(config.mapping.values()).issubset(allowed):
            raise ValueError("Map only columns with a heading in the selected header row.")
        if config.start_row <= config.header_row:
            raise ValueError("Choose an insertion row after the header.")
    except (ValueError, KeyError) as error:
        raise HTTPException(422, str(error)) from error
    with store.connection() as db:
        db.execute(
            "UPDATE templates SET config_json=? WHERE id=?", (config.model_dump_json(), template_id)
        )
    return {"id": template_id, "config": config.model_dump()}


@app.post("/api/exports", status_code=201)
def export(payload: ExportRequest):
    ids = list(dict.fromkeys(payload.document_ids))
    documents = [document_or_404(document_id) for document_id in ids]
    if any(document["status"] != "approved" for document in documents):
        raise HTTPException(422, "Only approved bills can be exported.")
    template = template_or_404(payload.template_id) if payload.template_id else None
    try:
        return create_export(documents, template)
    except (ValueError, KeyError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/exports")
def exports():
    with store.connection() as db:
        rows = db.execute(
            "SELECT id,created_at,snapshot_json FROM exports ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            **json.loads(row["snapshot_json"]),
        }
        for row in rows
    ]


@app.get("/api/exports/{export_id}/download")
def download_export(export_id: str):
    with store.connection() as db:
        row = db.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Export not found.")
    return FileResponse(
        EXPORTS / row["storage_name"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"akshay-invoices-{export_id[:8]}.xlsx",
    )


dist = ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="workspace")
else:

    @app.get("/", response_class=HTMLResponse)
    def root():
        return "<h1>Akshay invoice workspace</h1><p>Build the frontend or open its dev server on port 5174.</p>"
