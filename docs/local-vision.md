# Local image verification

The **Verify with AI** panel in **Checks & history** reads the original PDF page
or uploaded photo with a locally installed vision model. Unlike text-assisted
re-extraction, it does not receive the extracted text or saved invoice draft.

## Setup

Use an existing local Ollama installation, or on this Windows workstation run:

```powershell
.\.venv\Scripts\python.exe scripts\setup_local_vision.py
```

The helper downloads the official portable Windows runtime, verifies the
release SHA-256 checksum, and installs two Apache-2.0 vision models:

- `qwen3-vl:2b-instruct-q4_K_M`
- `granite3.2-vision:2b`

Runtime, model storage and setup logs are under
`D:\KyvernoBuild\akshay-local-ai`; allow at least 12 GB free. The helper starts
Ollama hidden on `127.0.0.1:11435`, with one loaded model and one inference at a
time. Re-run it after a computer restart to start the portable service again.
Installed models are reused without contacting the model registry. To use a
different drive, set `$env:AKSHAY_AI_HOME = 'E:\AkshayLocalAI'` before running
the setup or benchmark commands. Keep this folder outside the repository.
Downloads require internet; invoice verification uses only the local endpoint.
There is no paid API key or per-page service fee.

Set these values in the application's ignored `.env`, preserving other settings:

```dotenv
AKSHAY_OLLAMA_URL=http://127.0.0.1:11435
AKSHAY_VISION_MODEL=qwen3-vl:2b-instruct-q4_K_M
AKSHAY_VISION_MODELS=qwen3-vl:2b-instruct-q4_K_M,granite3.2-vision:2b
```

Restart the backend. Keep `AKSHAY_OLLAMA_MODEL` empty unless you separately want
text-assisted re-extraction. Both features share the configured local endpoint.
An existing Ollama installation on port 11434 can also be used by changing the URL.

## Review workflow

1. Save the invoice draft, then open **Checks & history → Verify with AI**.
2. Select an installed model and choose **Verify original**. Checks run in a
   separate persisted queue; leaving the review panel does not cancel a job.
3. Inspect differences against the original page. Agreements are also available
   using **Show agreeing fields**. Model agreement does not establish correctness.
   **Independent AI page readings** shows all read rows, including unmatched ones,
   and the verbatim printed date. It is read-only; no rows are inserted silently.
4. Select individual editable suggestions and choose **Apply … suggestions to
   draft**. The app asks for confirmation, saves a new unapproved version and
   records the model, report ID and selected fields in history.
5. Review ordinary validation checks and approve separately.

Nothing is automatically overwritten. Applying suggestions requires the exact
saved version used by the report. Any saved edit, restore, approval or
re-extraction makes the old report stale. Previous draft values remain in history.

## Scope and failure handling

- Headers checked: supplier name/GSTIN, bill number/date, currency, printed net
  subtotal, total tax and payable. Item checks cover quantity, unit price and
  printed line amount. Other tax components, rates, discounts and charges still
  need normal validation and source review.
- The currency and aggregate tax comparisons are read-only. An aggregate tax
  cannot safely be assigned to an individual CGST, SGST or IGST field.
- Item proposals require a unique matching description on the same page in both
  readings. Duplicate, missing or different descriptions are flagged for manual
  review; rows are never inserted, removed or matched by their position alone.
- Conflicting header values across pages require manual review. Known currency
  disagreements disable monetary proposals. Dual-currency item suggestions are
  also read-only.
- Each page is rendered independently, preserving the immutable source. Images
  are oriented and bounded to 1280 pixels on the longest edge, with a 4096-token
  context and 128-token evaluation batches to limit memory use. This can lose tiny
  print; open the original when the model cannot read it.
- A model request has a 180-second read timeout. A separate process has a
  15-minute overall job deadline. At most 25 pages and 12 queued/running jobs are
  accepted. Failed pages and incomplete coverage are shown explicitly.
- A stopped/crashed job becomes failed or partial; an app restart marks an
  interrupted running job failed. It never approves a document or changes its
  draft. Queued jobs can run after restart.

This is a second reading for human review, not an authenticity check or an
accuracy guarantee. Small local models can confidently misread a bill.

## Sources

- [Ollama structured image output documentation](https://docs.ollama.com/capabilities/structured-outputs)
- [Qwen model and license](https://ollama.com/library/qwen3-vl:2b-instruct-q4_K_M)
- [Granite model and license](https://ollama.com/library/granite3.2-vision:2b)
