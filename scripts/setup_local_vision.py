"""Install a checksum-verified portable Ollama runtime and free vision models on D:."""

import hashlib
import json
import os
import shutil
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai"))
VERSION = "v0.40.5"
BASE = f"https://github.com/ollama/ollama/releases/download/{VERSION}"
MODELS = ["qwen3-vl:2b-instruct-q4_K_M", "granite3.2-vision:2b"]
URL = "http://127.0.0.1:11435"


def file_digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download_runtime(archive, url, client):
    """Resume the complete prefix and fetch bounded ranges concurrently on D:."""
    with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as response:
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError("Runtime server does not support resumable downloads.")
        total = int(response.headers["content-range"].split("/")[-1])
    prefix = archive.stat().st_size if archive.exists() else 0
    if prefix >= total:
        raise RuntimeError(
            "Existing runtime archive failed its checksum. Rename it before retrying."
        )
    step = 16 * 1024**2
    ranges = [(start, min(start + step, total) - 1) for start in range(prefix, total, step)]

    def part(bounds):
        start, end = bounds
        path = archive.with_name(f"{archive.name}.part-{start}")
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(4):
            try:
                with client.stream(
                    "GET", url, headers={"Range": f"bytes={start}-{end}"}
                ) as response:
                    response.raise_for_status()
                    if (
                        response.status_code != 206
                        or response.headers.get("content-range") != f"bytes {start}-{end}/{total}"
                    ):
                        raise RuntimeError(
                            "Unexpected download range; refusing to corrupt the archive."
                        )
                    with path.open("wb") as output:
                        for chunk in response.iter_bytes(256 * 1024):
                            output.write(chunk)
                if path.stat().st_size != end - start + 1:
                    raise RuntimeError("Truncated download range.")
                return path
            except httpx.HTTPError:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)

    paths = {}
    completed = prefix
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(part, bounds): bounds for bounds in ranges}
        for future in as_completed(futures):
            bounds = futures[future]
            paths[bounds[0]] = future.result()
            completed += bounds[1] - bounds[0] + 1
            print(f"Runtime downloaded: {completed // 1024**2}/{total // 1024**2} MB", flush=True)
    # Append only after all parts succeeded. Failed downloads preserve the prefix.
    with archive.open("ab") as output:
        for start, _ in ranges:
            with paths[start].open("rb") as source:
                shutil.copyfileobj(source, output)


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    executable = RUNTIME / "runtime" / "ollama.exe"
    with httpx.Client(follow_redirects=True, trust_env=False, timeout=120) as client:
        if not executable.exists():
            checksums = client.get(BASE + "/sha256sum.txt")
            checksums.raise_for_status()
            name = "ollama-windows-amd64.zip"
            expected = next(
                line.split()[0]
                for line in checksums.text.splitlines()
                if line.split()[-1].lstrip("*").removeprefix("./") == name
            )
            archive = RUNTIME / name
            if not archive.exists() or file_digest(archive) != expected:
                if shutil.disk_usage(RUNTIME).free < 12 * 1024**3:
                    raise RuntimeError(
                        "At least 12 GB free space is required on the runtime drive."
                    )
                print("Downloading official Ollama portable runtime to D: ...", flush=True)
                download_runtime(archive, BASE + "/" + name, client)
                if file_digest(archive) != expected:
                    raise RuntimeError("Official runtime checksum verification failed.")
            destination = RUNTIME / "runtime"
            destination.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    resolved = (destination / entry.filename).resolve()
                    if (
                        destination.resolve() not in resolved.parents
                        and resolved != destination.resolve()
                    ):
                        raise RuntimeError("Unsafe runtime archive path.")
                bundle.extractall(destination)
            print("Official runtime SHA-256 verified and extracted.", flush=True)
        try:
            active = client.get(URL + "/api/version", timeout=2).is_success
        except httpx.HTTPError:
            active = False
        if not active:
            environment = {
                **os.environ,
                "OLLAMA_HOST": "127.0.0.1:11435",
                "OLLAMA_MODELS": str(RUNTIME / "models"),
                "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_FLASH_ATTENTION": "1",
                "OLLAMA_NO_CLOUD": "1",
            }
            with (RUNTIME / "server.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [str(executable), "serve"],
                    cwd=executable.parent,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            (RUNTIME / "server.json").write_text(
                json.dumps(
                    {"pid": process.pid, "url": URL, "models_path": str(RUNTIME / "models")}
                ),
                encoding="utf-8",
            )
            for _ in range(60):
                try:
                    if client.get(URL + "/api/version", timeout=2).is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Portable Ollama did not start; inspect its server.log.")
        elif not (RUNTIME / "server.json").exists():
            raise RuntimeError(
                "Port 11435 is already used by another runtime. Refusing to change its model storage."
            )
        tags = client.get(URL + "/api/tags")
        tags.raise_for_status()
        installed = {entry["name"] for entry in tags.json()["models"]}
        for model in MODELS:
            if model in installed:
                print(model + " already installed; retaining its current weights.", flush=True)
                continue
            print("Preparing " + model, flush=True)
            last = -1
            with client.stream(
                "POST", URL + "/api/pull", json={"model": model, "stream": True}, timeout=None
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise RuntimeError(event["error"])
                    percent = int(event.get("completed", 0) * 100 / max(event.get("total", 1), 1))
                    if percent // 10 > last // 10:
                        print(f"{model}: {event.get('status')} {percent}%", flush=True)
                        last = percent
                    if event.get("status") == "success":
                        print(model + " installed.", flush=True)
        print("Local vision runtime ready at " + URL, flush=True)


if __name__ == "__main__":
    main()
