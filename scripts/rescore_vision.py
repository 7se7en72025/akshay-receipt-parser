"""Regrade cached readings after an audited reference fix; never call a model."""
import argparse
import contextlib
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from benchmark_vision import CACHE, MODELS, ROOT, summarize


def rescore(manifest, version, model):
    directory = CACHE / "runs" / version / model.replace(":", "_")
    summary_path = directory / "summary.json"
    previous = json.loads(summary_path.read_text(encoding="utf-8"))
    if not previous["completed_100"] or previous["documents"] != 100:
        raise RuntimeError("Only complete archived runs may be regraded.")
    for row in manifest["documents"]:
        result = json.loads((directory / (Path(row["image_file"]).stem + ".json")).read_text())
        if result["sha256"] != row["sha256"] or result["prompt_version"] != version:
            raise RuntimeError("Archived input identity changed.")
    backup = directory / "summary.before-currency-audit.json"
    if not backup.exists():
        backup.write_bytes(summary_path.read_bytes())
    with contextlib.redirect_stdout(io.StringIO()):
        summarize(manifest, directory, model, 100, generation_protocol=previous["protocol"])
    current = json.loads(summary_path.read_text(encoding="utf-8"))
    current["rescored_at"] = datetime.now(timezone.utc).isoformat()
    current["rescoring_reason"] = "Qualified C$/A$ remain known currencies; monetary expectations follow printed two-decimal formatting. No model inference or source/metadata edits."
    summary_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    original = json.loads(backup.read_text(encoding="utf-8"))
    return {"version": version, "model": model,
            "original_metrics": {key: value for key, value in original.items() if key not in {"results", "protocol"}},
            "regraded": current}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-v5", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["documents"]:
        if hashlib.sha256((CACHE / row["image_file"]).read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("Original source checksum changed; refusing to regrade.")
    configurations = [("vision-read-v3", model) for model in ("ocr-baseline", *MODELS)]
    configurations.append(("vision-read-v4", MODELS[0]))
    if args.include_v5:
        configurations.append(("vision-read-v5", MODELS[0]))
    runs = [rescore(manifest, version, model) for version, model in configurations]
    report = {
        "rescored_at": datetime.now(timezone.utc).isoformat(),
        "source": manifest["source"], "revision": manifest["revision"],
        "reason": "The pinned renderer prints C$ for CAD and A$ for AUD; the old visibility mask incorrectly treated them as bare dollars.",
        "renderer_source": "https://github.com/alamgirqazi/synthetic-invoice-gen/blob/91082ede48d2c0b2e32d9c489ea35f34e9922a99/render_receipts.py",
        "model_calls_made": 0, "original_source_or_metadata_changed": False,
        "runs": runs,
    }
    (ROOT / "docs/testing/currency-scoring-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps([{
        "version": run["version"], "model": run["model"],
        "visible_correct": run["regraded"]["visible_correct_fields"],
        "visible_checked": run["regraded"]["visible_checked_fields"],
        "exact_bills": run["regraded"]["printed_exact_bills"],
    } for run in runs], indent=2))


if __name__ == "__main__":
    main()
