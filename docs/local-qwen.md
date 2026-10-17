# Local Qwen verification

The current prompt changes have a [19-bill partial trial](testing/qwen-v4-partial.md).
The full 100-bill rerun remains incomplete because of memory pressure.

The selected model is `qwen3-vl:2b-instruct-q4_K_M`. It reads the source image
independently, then the application compares that reading with the draft.
A suggestion does not change, approve or export an invoice automatically.

## Setup

From the repository root, with the Python environment installed:

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_vision.py
```

The script retains existing model weights and installs Qwen by default.
The optional `--include-granite` flag installs the historical comparison model;
it is not needed for Qwen. Existing Granite weights are retained.
Runtime/model files live under `D:/KyvernoBuild/akshay-local-ai` by default;
set `AKSHAY_AI_HOME` before setup to choose another directory.

Set these entries in the local, ignored `.env` file:

```dotenv
AKSHAY_OLLAMA_URL=http://127.0.0.1:11435
AKSHAY_VISION_MODEL=qwen3-vl:2b-instruct-q4_K_M
AKSHAY_VISION_MODELS=qwen3-vl:2b-instruct-q4_K_M
```

Start the application:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Open `http://127.0.0.1:8001`. Upload a bill, extract it, save the draft and run
image verification. Review the original beside the independent raw readings.
Apply only the suggestions you have checked; approval is a separate action.
After a restart, rerun setup to start the runtime, then start the app.

## Limits

The model sees original page images, never the draft, reference labels or OCR
text. Raw strings are preserved alongside normalized decimals and printed dates.
Ambiguous numeric dates remain unresolved. Item matching requires a unique
description on the same page; stale reports and unsupported suggestions are blocked.

Qwen can misread digits, choose the wrong printed total, infer an absent value
or agree with an OCR mistake. Agreement and arithmetic consistency are checks,
not proof of correct transcription. Review each bill against its original before
approval. The synthetic benchmark is a debugging set, not a guarantee for arbitrary
invoices or phone photos. Discrepancies are never balanced by changing entries.
