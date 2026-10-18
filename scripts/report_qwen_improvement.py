"""Publish a Qwen-only rerun without replacing the historical two-model report."""

import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from benchmark_vision import CACHE, MODELS, ROOT, summarize
from report_vision_benchmark import validate_attempts, validate_smoke


def paired_changes(before, after):
    old = {row["id"]: row for row in before["results"]}
    new = {row["id"]: row for row in after["results"]}
    if len(old) != 100 or old.keys() != new.keys():
        raise RuntimeError("Both runs must contain the same 100 distinct inputs.")
    changes = []
    for key, row in new.items():
        previous = old[key]
        if row["sha256"] != previous["sha256"]:
            raise RuntimeError("Input hash changed between runs.")
        a, b = previous["printed_score"], row["printed_score"]
        if (a["checked"], a["visible_checked"], a["abstention_checked"]) != (
            b["checked"], b["visible_checked"], b["abstention_checked"]
        ):
            raise RuntimeError("Scoring contract changed between runs.")
        old_errors = {m["field"] for m in a["mismatches"]}
        new_errors = {m["field"] for m in b["mismatches"]}
        changes.append({
            "id": key,
            "fixed_fields": sorted(old_errors - new_errors),
            "regressed_fields": sorted(new_errors - old_errors),
            "before_exact": a["exact"], "after_exact": b["exact"],
        })
    return changes


def main():
    from backend import vision

    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    model = MODELS[0]
    directory = CACHE / "runs" / vision.PROMPT_VERSION / model.replace(":", "_")
    documents = manifest["documents"]
    if len(documents) != 100 or any(
        not (directory / (Path(row["image_file"]).stem + ".json")).exists()
        for row in documents
    ):
        raise RuntimeError("Complete all 100 Qwen attempts before publishing.")
    validate_attempts(manifest, directory, model)
    for row in documents:
        import hashlib
        if hashlib.sha256((CACHE / row["image_file"]).read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("Original source checksum mismatch.")
    with contextlib.redirect_stdout(io.StringIO()):
        summarize(manifest, directory, model, 100)
    current = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    historical = json.loads(
        (ROOT / "docs/testing/200-bill-vision-results.json").read_text(encoding="utf-8")
    )
    before = historical["models"][model]
    old_digests = {row["model_digest"] for row in before["results"]}
    new_digests = {row["model_digest"] for row in current["results"]}
    if len(new_digests) != 1 or None in new_digests or old_digests != new_digests:
        raise RuntimeError("Different or missing model weights; not a paired prompt comparison.")
    smoke = json.loads((CACHE.parent / "api-smoke-result.json").read_text(encoding="utf-8"))
    validate_smoke(smoke)
    changes = paired_changes(before, current)
    readings = {
        row["file_name"]: json.loads(
            (directory / (Path(row["image_file"]).stem + ".json")).read_text(encoding="utf-8")
        ) for row in documents
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model, "before": before, "after": current,
        "changes": changes, "readings": readings, "real_api_workflow": smoke,
        "limits": [
            "Same clean synthetic debugging set, not held-out production accuracy.",
            "No labels, draft or OCR text supplied to the model; original images only.",
            "Strict scoring unchanged, including missing-field abstention and ambiguous dates.",
            "Reference values, original sources and drafts are not rewritten to improve scores.",
            "Driver changed from 566.07 to 617.42; latency is not a controlled prompt speed comparison.",
            "Human review remains required; matching totals do not prove correct entries.",
        ],
    }
    target = ROOT / "docs/testing"
    (target / "qwen-improvement-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = []
    for label, value in (("Before (v3)", before), (f"After ({vision.PROMPT_VERSION})", current)):
        c, n = value["visible_correct_fields"], value["visible_checked_fields"]
        rows.append(f"| {label} | {c}/{n} ({c/n:.2%}) | {value['printed_exact_bills']}/100 | "
                    f"{value['abstention_correct_fields']}/{value['abstention_checked_fields']} | {value['errors']} |")
    fixed = sum(len(row["fixed_fields"]) for row in changes)
    regressed = sum(len(row["regressed_fields"]) for row in changes)
    text = "\n".join([
        "# Qwen: repeated 100-bill evaluation", "", f"Generated: {report['generated_at']}", "",
        "Same model weights and original 100 images as the [historical comparison](200-bill-vision-comparison.md).",
        "The prompt now distinguishes labelled aggregate totals, separate rates, customer names and missing placeholders.",
        "The duplicated JSON schema was removed from the prose; the API still constrains the output schema.", "",
        "| Run | Visible fields | Whole printed contract exact | Correct missing-field abstentions | Failures |",
        "| --- | --- | --- | --- | --- |", *rows, "",
        f"Field-level changes: {fixed} previously wrong fields fixed; {regressed} previously correct fields regressed.",
        "No scoring tolerances, description matching or reference values were changed.", "",
        "## Remaining mismatches", "",
        *[f"- {key}: {count}" for key, count in sorted(current["mismatches_by_field"].items())], "",
        "## Evidence and limits", "",
        "[Full results](qwen-improvement-results.json) include both scores, each changed field, all new raw readings,",
        "source hashes, model digest, generation settings, prompt hash and the real API workflow check.",
        "A failed response counts as a failure. Ambiguous dates and absent values require review rather than guessing.",
        "These are clean synthetic debugging bills used during improvement, not a production or held-out accuracy estimate.",
        "The GPU driver also changed between runs (566.07 to 617.42), so timing differences cannot be attributed to the prompt alone.",
        "Human review is still required. Nothing is silently corrected, approved or exported.", "",
        "## Reproduce", "", "```powershell",
        r".\.venv\Scripts\python.exe scripts/setup_local_vision.py",
        r".\.venv\Scripts\python.exe scripts/benchmark_vision.py --model qwen3-vl:2b-instruct-q4_K_M --limit 100 --pause-seconds 10",
        r".\.venv\Scripts\python.exe scripts/smoke_vision_api.py",
        r".\.venv\Scripts\python.exe scripts/report_qwen_improvement.py", "```", "",
    ])
    (target / "qwen-improvement.md").write_text(text, encoding="utf-8")
    print(json.dumps({"fixed": fixed, "regressed": regressed,
                      "exact_bills": current["printed_exact_bills"]}))


if __name__ == "__main__":
    main()
