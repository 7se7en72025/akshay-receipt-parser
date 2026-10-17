import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKSHAY_DATA_DIR", ROOT / "data")).resolve()
UPLOADS = DATA / "uploads"
EXPORTS = DATA / "exports"
TEMPLATES = DATA / "templates"
PREVIEWS = DATA / "previews"
for directory in (DATA, UPLOADS, EXPORTS, TEMPLATES, PREVIEWS):
    directory.mkdir(parents=True, exist_ok=True)

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_BATCH_FILES = 12
MAX_BATCH_BYTES = 60 * 1024 * 1024
MAX_PAGES = 25
MAX_IMAGE_PIXELS = 25_000_000
OLLAMA_URL = os.environ.get("AKSHAY_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("AKSHAY_OLLAMA_MODEL", "")
if urlparse(OLLAMA_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
    raise RuntimeError("This local workspace accepts only a loopback Ollama endpoint.")
