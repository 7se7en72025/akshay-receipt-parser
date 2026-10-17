# Akshay invoice workspace

A local web application for supplier bill extraction, human review and Excel export.

**Workflow:** upload PDF/JPG/PNG files → direct extraction or local OCR → editable draft → validation → staff approval → new Excel workbook.

## Run on Windows

Requirements: Python 3.11+ and Bun. No paid server or AI API key is required.

From the repository root:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Setup
~~~

Open **http://127.0.0.1:8001**. On later runs, omit -Setup. Keep the server process running while working.

The setup command creates a repository-local Python environment, installs the locked dependencies, installs frontend dependencies and builds the interface. It does not change the machine's persistent PowerShell execution policy.

Manual setup:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
cd frontend
bun install --frozen-lockfile
bun run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
~~~

For frontend development, run the backend as above and run bun run dev from frontend in a second terminal. The frontend on port 5174 proxies /api to port 8001.

## Features

- Batch upload: up to 12 PDF/JPG/PNG files, 15 MB per file and 60 MB per batch.
- Up to 25 pages per PDF; a single processing job has a four-minute deadline.
- Direct table extraction using pdfplumber, with header-based mapping and parent/child tax headings.
- Local RapidOCR for images and scans, using ONNX Runtime on CPU.
- Optional loopback Ollama assistance for proposing structured invoice data.
- Original document preview, source text, editable item rows, saved drafts and review history.
- Decimal arithmetic, missing-field checks and reconciliation of item amounts and bill totals.
- Duplicate file detection and same-supplier/bill/financial-year warnings.
- Approval requires resolving errors and explicitly acknowledging remaining warnings.
- Standard Excel export with Line Items and Bill Summary sheets.
- Upload .xlsx templates, choose worksheet/headings/insertion row and map output columns.
- Template exports refuse occupied or merged destination cells instead of overwriting them.
- Export history records document versions and the template configuration used.
- Search every saved bill by filename, bill number, supplier, GSTIN or purchase number.
- Filter by bill dates and status, sort by upload date, bill date or amount, and browse 25 bills per page.
- Lightweight inbox responses exclude product rows; full records load when you open a bill.
- Keep the last upload report available with per-file errors and links to duplicate bills.

## Using the workspace

1. Upload one bill or a small batch.
2. Open its review draft. Compare every entry with the original.
3. Correct supplier details, bill details, product rows and printed totals.
4. Save the draft to refresh validation.
5. Open Checks & history, resolve errors and review warnings.
6. Approve the bill. Approval here confirms the extracted invoice data; it does not confirm receipt of stock or initiate a payment.
7. Select approved bills and create a workbook. Choose the standard workbook or a saved template.

Editing an approved record reopens the draft. It must be approved again before another export.

Inbox counts and approved value cover the current search and bill-date range across all pages; status tabs then narrow the bill list. Bills without a date are excluded when a date filter is set. Clear filters to show them again. Search treats `%` and `_` as literal characters.

Previous bill and Next bill follow the inbox page you opened, even if an approved bill leaves the Needs review tab. Go back to the inbox to browse another page. Selection can span pages, up to 200 approved bills per export; Clear selection removes the complete selection. The server checks approval again before exporting.

Last upload keeps the most recent upload report available during the current browser session. The report is replaced by the next upload and cleared on page reload; uploaded originals and processing results remain in the database.

Use Ctrl+S (Cmd+S on macOS) to save an edited draft. Leaving through the sidebar or closing/reloading the tab warns about unsaved changes. Reload saved discards local edits only after confirmation and is useful after a version conflict.

Select an activity in Checks & history to inspect its saved values and review note. Restore as draft creates a new unapproved version and preserves the audit trail. Save or reload current edits before restoring. Older extraction activities created before snapshot support may have no restorable values.

## Existing Excel template

Use Excel templates → Attach .xlsx template. The app suggests a heading row based on recognised field names; confirm it.

Choose the worksheet and heading row, then select Read headings. Map the columns and confirm an empty insertion row. Save the mapping before exporting. The original workbook is preserved.

Only agreed .xlsx layouts are supported. Existing formulas are retained where possible but not calculated by openpyxl. Shapes, macros, advanced charts and every Excel feature are not guaranteed to round-trip. Formula cells and existing mapped data are not overwritten. Export is capped at 10,000 product rows.

## Optional local AI

The standard PDF/OCR path does not require a general AI model. To enable assisted extraction:

1. Install and run Ollama separately.
2. Install a model appropriate for the computer's available memory.
3. Copy .env.example to .env and set AKSHAY_OLLAMA_MODEL to its exact installed model name.
4. Restart the backend.

The model endpoint must be loopback-only. The app sends extracted text, not image files, to this optional text model. Scans go through OCR first. It requests an Invoice-shaped JSON response and validates it before replacing the draft. If assistance fails, the direct/OCR draft is retained.

A valid schema does not prove the values are correct. AI proposals require the same staff review. Models are not downloaded automatically by this application.

## Supported formats and limitations

The first parser targets clearly labelled purchase/invoice tables, including the supplied store-generated purchase-bill layout. Quantity, rate, taxable amounts and tax subcolumns are mapped by headings rather than a fixed column order.

A new supplier layout, unfamiliar labels, merged cells, damaged pages or a blurry photo can need correction. OCR column reconstruction is approximate. Unsupported documents remain review drafts; use manual rows or configured AI assistance.

Both printed discount columns are preserved without assuming whether each represents an amount or percentage. Staff must confirm their meaning.

Initial OCR models support their bundled languages; this is not a promise of reliable recognition for every language or handwritten bill. Initial model preparation may need network access depending on the selected RapidOCR configuration.

## Local data and access

This version is a **single-operator local workspace**, bound to 127.0.0.1. It has no staff accounts or shared authentication. Do not use it as a public or LAN deployment.

SQLite and uploaded/generated files live under data/ by default:

- workspace.sqlite3: document records, draft versions and review events.
- uploads/: immutable original bills.
- previews/: rendered page images.
- templates/: original uploaded workbooks.
- exports/: generated workbooks.

These folders, .env, the virtual environment and model files are excluded from Git. The supplied real bill is not committed. To change the data directory, set AKSHAY_DATA_DIR in .env.

Stop the backend before copying the complete data directory for a consistent local backup. Shared deployment, authentication, a production database migration plan, retention rules and managed backups are separate work.

### Create a backup while the app is running

~~~powershell
.\.venv\Scripts\python.exe -m backend.backup "C:\Users\RAIYYAN\Downloads\akshay-backup-2026-10-17.zip"
~~~

Choose a new filename in an existing folder outside the data directory. The command uses SQLite's backup API and includes the immutable invoice, template and export files referenced by that database snapshot. Generated previews, dependencies and `.env` are excluded. It refuses to overwrite an existing archive. The ZIP contains private bills and is not encrypted; keep it in a protected location.

To restore, stop the app, extract into a **new empty folder**, set `AKSHAY_DATA_DIR` in `.env` to the extracted `data` folder, then restart. Keep your previous data until the restored workspace is reviewed. Incomplete jobs are resumed on startup. Model configuration remains in your existing `.env`.

## Import from the command line

With the local backend running:

~~~powershell
.\.venv\Scripts\python.exe -m backend.import_bill "C:\bills\supplier.pdf"
~~~

This submits the document through the same upload API. It does not approve or export it.

## Code layout

- backend/extraction.py: direct extraction, OCR and column mapping.
- backend/validation.py: required fields and Decimal reconciliation.
- backend/ai.py: optional local-model adapter.
- backend/worker.py: queued processing and interruption recovery.
- backend/main.py: local API, review/approval and file routes.
- backend/workbooks.py: template inspection and safe Excel export.
- backend/database.py: local SQLite schema and audit events.
- frontend/src/: React/TypeScript inbox, review, templates and history.

## Development checks

~~~powershell
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\python.exe -m compileall -q backend
cd frontend
bun run build
~~~

No test suite has been added or run. Real invoice formats still require operator review. POS integration, live inventory, student shopping and historical POS database migration are not part of this invoice MVP.
