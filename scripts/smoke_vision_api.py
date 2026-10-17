"""Exercise the real upload, extraction, vision subprocess and report APIs.

Uses one public benchmark PDF and an isolated workspace, never staff bills.
This checks workflow/integrity, not whether the model's reading is correct.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
AI_HOME = Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai")).resolve()
URL = "http://127.0.0.1:18092"


def wait_for(client, path, predicate, seconds=600):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            response = client.get(path)
            response.raise_for_status()
            value = response.json()
            if predicate(value):
                return value
        except httpx.ConnectError:
            pass
        time.sleep(1)
    raise RuntimeError("Real vision API check timed out.")


def main():
    source_manifest = json.loads(
        (ROOT / "data/benchmark/manifest.json").read_text(encoding="utf-8")
    )
    row = source_manifest["documents"][0]
    source = ROOT / "data/benchmark" / row["file_name"]
    original = source.read_bytes()
    assert hashlib.sha256(original).hexdigest() == row["sha256"]
    model = "qwen3-vl:2b-instruct-q4_K_M"
    temporary = tempfile.TemporaryDirectory(prefix="api-smoke-", dir=AI_HOME)
    workspace = Path(temporary.name).resolve()
    assert workspace.parent == AI_HOME
    environment = {
        **os.environ,
        "AKSHAY_DATA_DIR": str(workspace),
        "AKSHAY_OLLAMA_URL": "http://127.0.0.1:11435",
        "AKSHAY_OLLAMA_MODEL": "",
        "AKSHAY_VISION_MODEL": model,
        "AKSHAY_VISION_MODELS": model,
    }
    with (AI_HOME / "api-smoke.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18092",
                "--no-access-log",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(base_url=URL, trust_env=False, timeout=30) as client:
                wait_for(
                    client, "/api/health", lambda value: value["vision"]["available"], seconds=60
                )
                response = client.post(
                    "/api/documents", files={"files": (source.name, original, "application/pdf")}
                )
                response.raise_for_status()
                document_id = response.json()["created"][0]["id"]
                path = f"/api/documents/{document_id}"
                document = wait_for(
                    client, path, lambda value: value["status"] == "needs_review", seconds=120
                )
                snapshot, version = document["invoice"], document["version"]
                response = client.post(
                    path + "/verifications", json={"version": version, "model": model}
                )
                assert response.status_code == 202, response.text
                job_id = response.json()["id"]
                job_path = path + "/verifications/" + job_id
                print(
                    "Real vision subprocess queued; waiting for original page reading.", flush=True
                )
                job = wait_for(
                    client, job_path, lambda value: value["status"] not in {"queued", "running"}
                )
                assert job["status"] == "completed", job
                assert len(job["result"]["pages"]) == document["page_count"]
                assert not job["stale"]
                saved = client.get(path).json()
                assert saved["invoice"] == snapshot and saved["version"] == version
                assert (
                    hashlib.sha256(client.get(path + "/source").content).hexdigest()
                    == row["sha256"]
                )
                assert client.get(path + "/preview/1").status_code == 200
                invalid = client.post(
                    job_path + "/apply", json={"version": version, "selected": ["invalid"]}
                )
                assert invalid.status_code == 422
                response = client.put(path, json={"invoice": snapshot, "version": version})
                assert response.status_code == 200
                stale = client.post(
                    job_path + "/apply", json={"version": version + 1, "selected": ["invalid"]}
                )
                assert stale.status_code == 409
                assert client.get(path).json()["invoice"] == snapshot
                report = {
                    "workflow": "real upload + extraction + vision subprocess",
                    "source_id": row["doc_id"],
                    "source_sha256": row["sha256"],
                    "model": model,
                    "prompt_version": job["result"]["prompt_version"],
                    "status": job["status"],
                    "pages_read": len(job["result"]["pages"]),
                    "draft_unchanged": True,
                    "source_unchanged": True,
                    "invalid_suggestion_rejected": True,
                    "stale_report_rejected": True,
                }
                (AI_HOME / "api-smoke-result.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
                print(json.dumps(report, indent=2), flush=True)
        finally:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            process.wait(timeout=15)
            # The resolved deletion target is checked against the task directory.
            if workspace.parent != AI_HOME:
                raise RuntimeError("Refusing cleanup outside the isolated task directory.")
            temporary.cleanup()


if __name__ == "__main__":
    main()
