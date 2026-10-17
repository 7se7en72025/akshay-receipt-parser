"""Run the 100 public bills through an isolated real upload/worker/review API."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
from benchmark_invoices import CACHE, ROOT


def main():
    rows = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))["documents"]
    references = {
        row["id"]: row["invoice"]
        for row in json.loads((CACHE / "final-currency.json").read_text())["results"]
    }
    report = {
        "count": len(rows),
        "failures": [],
        "round_trip_exact": 0,
        "source_checksums_exact": 0,
        "foreign_approval_blocked": 0,
        "currency_relabelling_blocked": 0,
    }
    temporary_root = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(
        prefix="akshay-api-evaluation-", dir=temporary_root
    ) as temporary:
        if Path(temporary).resolve().parent != temporary_root:
            raise RuntimeError(
                "Refusing evaluation cleanup outside the expected temporary directory."
            )
        environment = {**os.environ, "AKSHAY_DATA_DIR": temporary, "AKSHAY_OLLAMA_MODEL": ""}
        with (CACHE / "api-server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18091",
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                with httpx.Client(
                    base_url="http://127.0.0.1:18091", trust_env=False, timeout=60
                ) as client:
                    for _ in range(60):
                        if process.poll() is not None:
                            raise RuntimeError("Isolated test server stopped. See api-server.log.")
                        try:
                            if client.get("/api/health").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.5)
                    else:
                        raise RuntimeError("Test server did not start.")
                    ids = {}
                    for start in range(0, len(rows), 12):
                        with ExitStack() as stack:
                            batch = rows[start : start + 12]
                            files = [
                                (
                                    "files",
                                    (
                                        row["doc_id"] + (CACHE / row["file_name"]).suffix,
                                        stack.enter_context((CACHE / row["file_name"]).open("rb")),
                                        "application/octet-stream",
                                    ),
                                )
                                for row in batch
                            ]
                            response = client.post("/api/documents", files=files)
                            response.raise_for_status()
                            result = response.json()
                            if result["errors"] or len(result["created"]) != len(batch):
                                raise RuntimeError(f"Batch upload failed: {result}")
                            for row, record in zip(batch, result["created"], strict=True):
                                ids[row["doc_id"]] = record["id"]
                    deadline = time.monotonic() + 600
                    last = -1
                    while time.monotonic() < deadline:
                        documents = client.get("/api/documents").json()
                        completed = sum(
                            doc["status"] not in {"queued", "processing"} for doc in documents
                        )
                        if completed != last:
                            print(f"Real API worker: {completed}/100 processed", flush=True)
                            last = completed
                        if completed == len(rows):
                            break
                        time.sleep(2)
                    else:
                        raise RuntimeError("The 100-bill API run exceeded ten minutes.")
                    for index, row in enumerate(rows, 1):
                        document_id = ids[row["doc_id"]]
                        document = client.get(f"/api/documents/{document_id}").json()
                        if document["status"] != "needs_review":
                            report["failures"].append(
                                {"id": row["doc_id"], "error": document.get("error")}
                            )
                            continue
                        invoice = document["invoice"]
                        if invoice == references[row["doc_id"]]:
                            report["round_trip_exact"] += 1
                        else:
                            report["failures"].append(
                                {
                                    "id": row["doc_id"],
                                    "error": "stored draft differs from direct extractor",
                                }
                            )
                        source = client.get(f"/api/documents/{document_id}/source")
                        if hashlib.sha256(source.content).hexdigest() == row["sha256"]:
                            report["source_checksums_exact"] += 1
                        corrupted = copy.deepcopy(invoice)
                        corrupted["grand_total"] = "9999999.99"
                        response = client.post(
                            f"/api/documents/{document_id}/approve",
                            json={
                                "version": document["version"],
                                "invoice": corrupted,
                                "acknowledge_warnings": True,
                            },
                        )
                        if response.status_code == 422:
                            report["foreign_approval_blocked"] += 1
                        relabelled = {**invoice, "currency": "INR"}
                        response = client.put(
                            f"/api/documents/{document_id}",
                            json={"version": document["version"], "invoice": relabelled},
                        )
                        if response.status_code == 422:
                            report["currency_relabelling_blocked"] += 1
                        after = client.get(f"/api/documents/{document_id}").json()
                        if after["invoice"] != invoice or after["version"] != document["version"]:
                            report["failures"].append(
                                {
                                    "id": row["doc_id"],
                                    "error": "rejected request changed correct entries",
                                }
                            )
                        if index % 20 == 0:
                            print(
                                f"Stored draft, source and rejection checks: {index}/100",
                                flush=True,
                            )
                    report["unapproved_export_blocked"] = (
                        client.post(
                            "/api/exports", json={"document_ids": list(ids.values())}
                        ).status_code
                        == 422
                    )
                    print(json.dumps(report, indent=2), flush=True)
                    (CACHE / "api-final.json").write_text(
                        json.dumps(report, indent=2), encoding="utf-8"
                    )
                    if (
                        report["failures"]
                        or any(
                            report[key] != 100
                            for key in (
                                "round_trip_exact",
                                "source_checksums_exact",
                                "foreign_approval_blocked",
                                "currency_relabelling_blocked",
                            )
                        )
                        or not report["unapproved_export_blocked"]
                    ):
                        raise RuntimeError("API evaluation failed; inspect api-final.json.")
            finally:
                # This process and its descendants belong only to this isolated evaluation.
                if process.poll() is None:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                    process.wait(timeout=15)


if __name__ == "__main__":
    main()
