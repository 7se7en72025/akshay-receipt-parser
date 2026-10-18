"""Lock the selected Qwen reader before the new validation set's first inference."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from benchmark_vision import MODELS, ROOT, evaluation_signature, reference

HOME = Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai"))


def freeze(path, signature, selection_sha, has_readings, runtime_version):
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["signature"] != signature or saved["selection_manifest_sha256"] != selection_sha:
            raise RuntimeError("A different validation protocol is already frozen; refusing to replace it.")
        return saved
    if has_readings:
        raise RuntimeError("Validation readings already exist; cannot claim a pre-inference freeze.")
    lock = {
        "frozen_at": datetime.now(timezone.utc).isoformat(), "signature": signature,
        "selection_manifest_sha256": selection_sha, "runtime_version": runtime_version,
    }
    # Exclusive creation prevents a simultaneous process replacing a frozen reader.
    with path.open("x", encoding="utf-8") as output:
        json.dump(lock, output, indent=2)
    return lock


def main():
    from report_qwen_validation import archived_development, choose_candidate

    from backend import vision
    first, _ = archived_development("vision-read-v4")
    candidate, _ = archived_development("vision-read-v5")
    adopt, _, _ = choose_candidate(first, candidate)
    selected = "vision-read-v5" if adopt else "vision-read-v4"
    if vision.PROMPT_VERSION != selected:
        raise RuntimeError("Active reader does not match the completed development acceptance gate.")
    cache = HOME / "benchmark-validation100"
    selection = json.loads((ROOT / "docs/testing/validation100-selection.json").read_text())
    selection_sha = hashlib.sha256((cache / "manifest.json").read_bytes()).hexdigest()
    if selection_sha != selection["manifest_sha256"]:
        raise RuntimeError("Validation selection changed.")
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["documents"]:
        reference(row, visible=True)  # Validate reference shapes before any model inference.
    with httpx.Client(trust_env=False, timeout=5) as client:
        tags = client.get(vision.OLLAMA_URL + "/api/tags")
        tags.raise_for_status()
        digest = next(row["digest"] for row in tags.json()["models"] if row["name"] == MODELS[0])
        version = client.get(vision.OLLAMA_URL + "/api/version")
        version.raise_for_status()
    lock = freeze(
        HOME / "validation100-protocol.json", evaluation_signature(MODELS[0], digest),
        selection_sha, any((cache / "runs").glob("**/synth*.json")), version.json()["version"],
    )
    print(json.dumps(lock, indent=2))


if __name__ == "__main__":
    main()
