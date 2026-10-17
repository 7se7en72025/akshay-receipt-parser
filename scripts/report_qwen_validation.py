"""Report the completed development rerun and a separately frozen new 100-bill set."""
import contextlib
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from benchmark_vision import MODELS, ROOT, summarize
from report_qwen_improvement import paired_changes
from report_vision_benchmark import validate_attempts, validate_smoke

HOME = Path("D:/KyvernoBuild/akshay-local-ai")
MODEL = MODELS[0]


def validate_protocol_lock(lock, expected):
    if lock.get("signature") != expected:
        raise RuntimeError("Validation protocol differs from the frozen pre-inference protocol.")


def protocol_signature(model_digest):
    from backend import vision
    return vision.reader_signature(MODEL, model_digest)


def collect(cache):
    from backend import vision
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    rows = manifest["documents"]
    directory = cache / "runs" / vision.PROMPT_VERSION / MODEL.replace(":", "_")
    if len(rows) != 100 or len({row["sha256"] for row in rows}) != 100:
        raise RuntimeError("Expected 100 distinct source documents.")
    if any(not (directory / (Path(row["image_file"]).stem + ".json")).exists() for row in rows):
        raise RuntimeError("Both sets require all 100 attempts before publication.")
    for row in rows:
        if hashlib.sha256((cache / row["image_file"]).read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("Source image changed.")
    validate_attempts(manifest, directory, MODEL)
    with contextlib.redirect_stdout(io.StringIO()):
        summarize(manifest, directory, MODEL, 100)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    readings = {row["file_name"]: json.loads(
        (directory / (Path(row["image_file"]).stem + ".json")).read_text(encoding="utf-8")
    ) for row in rows}
    return manifest, summary, readings


def main():
    development_manifest, development, development_readings = collect(HOME / "benchmark-new100")
    validation_manifest, validation, validation_readings = collect(HOME / "benchmark-validation100")
    if {row["sha256"] for row in development_manifest["documents"]} & {
        row["sha256"] for row in validation_manifest["documents"]
    }:
        raise RuntimeError("Development and validation sets overlap.")
    selection = json.loads((ROOT / "docs/testing/validation100-selection.json").read_text())
    actual_manifest_sha = hashlib.sha256(
        (HOME / "benchmark-validation100/manifest.json").read_bytes()
    ).hexdigest()
    if actual_manifest_sha != selection["manifest_sha256"]:
        raise RuntimeError("Validation selection changed after freezing.")
    digests = {row["model_digest"] for result in (development, validation) for row in result["results"]}
    if len(digests) != 1 or None in digests:
        raise RuntimeError("Missing or mixed model revisions.")
    lock = json.loads((HOME / "validation100-protocol.json").read_text())
    validate_protocol_lock(lock, protocol_signature(next(iter(digests))))
    first = json.loads((HOME / "benchmark-new100/runs/vision-read-v4" /
                        MODEL.replace(":", "_") / "summary.json").read_text())
    if not first["completed_100"] or first["protocol"]["prompt_version"] != "vision-read-v4":
        raise RuntimeError("First development attempt must be complete and preserved.")
    changes = paired_changes(first, development)
    smoke = json.loads((HOME / "api-smoke-result.json").read_text())
    validate_smoke(smoke)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "distinct_documents": 200, "model": MODEL,
        "first_development_attempt": first, "improved_development": development,
        "new_validation": validation, "development_changes": changes,
        "protocol_lock": lock, "validation_selection": selection,
        "development_readings": development_readings, "validation_readings": validation_readings,
        "real_api_workflow": smoke,
        "limits": [
            "Development images were used to find defects; their rerun is not held-out accuracy.",
            "Validation inputs and protocol were frozen before their first inference.",
            "Both sets share a synthetic source and template families, not independent layout coverage.",
            "Clean images are not representative of arbitrary phone photos, languages or Indian GST layouts.",
            "No reference labels, draft or OCR answers are model inputs. No balancing or reference edits.",
            "Ambiguous printed dates remain unresolved; correct abstention can still differ from hidden metadata.",
            "Failures remain in denominators. Exact bill agreement is stricter than visible-field accuracy.",
            "Model unloading and varying system load make timing an uncontrolled performance comparison.",
            "Human review remains required. Model agreement is not proof of correctness.",
        ],
    }
    target = ROOT / "docs/testing"
    (target / "qwen-two-set-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    table = []
    for label, result in (("Development: first attempt", first),
                          ("Development: improved reader", development),
                          ("100 new bills: first attempt", validation)):
        c, n = result["visible_correct_fields"], result["visible_checked_fields"]
        table.append(f"| {label} | {c}/{n} ({c/n:.2%}) | {result['printed_exact_bills']}/100 | "
                     f"{result['abstention_correct_fields']}/{result['abstention_checked_fields']} | {result['errors']} |")
    fixed = sum(len(row["fixed_fields"]) for row in changes)
    regressed = sum(len(row["regressed_fields"]) for row in changes)
    text = "\n".join([
        "# Qwen: development and 100 new validation bills", "",
        f"Generated: {report['generated_at']}", "",
        "200 distinct source bills; the development 100 were evaluated before and after improvements.",
        "The second 100 were selected before tuning and evaluated with a frozen reader.", "",
        "| Run | Visible values correct | Entire printed contract exact | Correct absent-field abstentions | Failures |",
        "| --- | --- | --- | --- | --- |", *table, "",
        f"Development changes: {fixed} previously wrong fields fixed; {regressed} previously correct fields regressed.",
        "Strict decimal, row-order and description scoring stayed unchanged; no reference answers were edited.", "",
        "## Limits", "", *["- " + value for value in report["limits"]], "",
        "## Evidence", "",
        "[Full results](qwen-two-set-results.json) preserve every per-bill mismatch, raw reading, source hash,",
        "model digest, frozen schema/prompt/image protocol and the real API smoke check.",
        "Source: [InvoiceOCR-Synth](https://huggingface.co/datasets/alamgirqazi/invoice-ocr-synthetic), CC BY 4.0,",
        f"revision `{validation_manifest['revision']}`. The validation set skips the first 100 distinct clean documents.",
        "The reference visibility rules were audited on the development templates before validation inference.", "",
    ])
    (target / "qwen-two-set-evaluation.md").write_text(text, encoding="utf-8")
    print(json.dumps({"development_exact": development["printed_exact_bills"],
                      "validation_exact": validation["printed_exact_bills"],
                      "fixed": fixed, "regressed": regressed}))


if __name__ == "__main__":
    main()
