"""Report the completed development rerun and a separately frozen new 100-bill set."""
import contextlib
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from benchmark_vision import MODELS, ROOT, evaluation_signature, reference, score, summarize
from report_qwen_improvement import paired_changes
from report_vision_benchmark import validate_attempts, validate_smoke

HOME = Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai"))
MODEL = MODELS[0]


def choose_candidate(first, candidate):
    changes = paired_changes(first, candidate)
    numeric = {"quantity", "unit_price", "amount", "taxable_total", "tax_total", "grand_total"}
    regressions = [
        {"id": row["id"], "field": field}
        for row in changes for field in row["regressed_fields"]
        if field.split(".")[-1] in numeric
    ]
    adopt = (
        not regressions
        and candidate["visible_correct_fields"] >= first["visible_correct_fields"]
        and candidate["printed_correct_fields"] >= first["printed_correct_fields"]
    )
    return adopt, regressions, changes


def validate_protocol_lock(lock, expected):
    if lock.get("signature") != expected:
        raise RuntimeError("Validation protocol differs from the frozen pre-inference protocol.")


def protocol_signature(model_digest):
    return evaluation_signature(MODEL, model_digest)


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


def archived_development(version):
    cache = HOME / "benchmark-new100"
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    directory = cache / "runs" / version / MODEL.replace(":", "_")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if not summary["completed_100"] or summary["protocol"]["prompt_version"] != version:
        raise RuntimeError("Complete both development attempts before reporting.")
    scores = {row["id"]: row for row in summary["results"]}
    if len(scores) != 100:
        raise RuntimeError("Development snapshot contains duplicate or missing inputs.")
    readings = {}
    for row in manifest["documents"]:
        attempt = json.loads((directory / (Path(row["image_file"]).stem + ".json")).read_text())
        if (
            hashlib.sha256((cache / row["image_file"]).read_bytes()).hexdigest() != row["sha256"]
            or attempt["sha256"] != row["sha256"] or attempt["prompt_version"] != version
            or attempt["model"] != MODEL
        ):
            raise RuntimeError("Archived source or reader identity changed.")
        if not attempt.get("error") and (
            attempt.get("image_edge") != summary["protocol"]["image_edge"]
            or attempt.get("model_options") != summary["protocol"]["model_options"]
            or attempt.get("base_prompt_sha256", summary["protocol"]["prompt_sha256"])
            != summary["protocol"]["prompt_sha256"]
        ):
            raise RuntimeError("Archived image, prompt or generation settings changed.")
        raw = dict(attempt.get("raw_reading") or attempt.get("reading") or {})
        raw["bill_date"] = (attempt.get("reading") or {}).get("bill_date")
        actual = score(raw, reference(row, visible=True))
        if attempt.get("error"):
            actual.update(correct=0, visible_correct=0, abstention_correct=0, exact=False)
        saved = scores[row["file_name"]]["printed_score"]
        if any(actual[key] != saved[key] for key in ("correct", "visible_correct", "checked", "exact")):
            raise RuntimeError("Archived scoring changed; do not silently rewrite the baseline.")
        readings[row["file_name"]] = attempt
    for summary_key, score_key in (
        ("visible_correct_fields", "visible_correct"), ("visible_checked_fields", "visible_checked"),
        ("printed_correct_fields", "correct"), ("printed_checked_fields", "checked"),
        ("abstention_correct_fields", "abstention_correct"),
        ("abstention_checked_fields", "abstention_checked"),
    ):
        if summary[summary_key] != sum(row["printed_score"][score_key] for row in scores.values()):
            raise RuntimeError("Archived summary does not match its per-bill scores.")
    return summary, readings


def main():
    from backend import vision
    first, first_readings = archived_development("vision-read-v4")
    candidate, candidate_readings = archived_development("vision-read-v5")
    adopt, numeric_regressions, changes = choose_candidate(first, candidate)
    selected_version = "vision-read-v5" if adopt else "vision-read-v4"
    if vision.PROMPT_VERSION != selected_version:
        raise RuntimeError("Active reader does not match the development acceptance gate.")
    development_manifest = json.loads((HOME / "benchmark-new100/manifest.json").read_text())
    development = candidate if adopt else first
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
    digests = {row["model_digest"] for result in (first, candidate, validation) for row in result["results"]}
    if len(digests) != 1 or None in digests:
        raise RuntimeError("Missing or mixed model revisions.")
    lock = json.loads((HOME / "validation100-protocol.json").read_text())
    validate_protocol_lock(lock, protocol_signature(next(iter(digests))))
    smoke = json.loads((HOME / "api-smoke-result.json").read_text())
    validate_smoke(smoke)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "distinct_documents": 200, "model": MODEL,
        "first_development_attempt": first, "candidate_development": candidate,
        "selected_development": development, "candidate_adopted": adopt,
        "candidate_numeric_regressions": numeric_regressions,
        "acceptance_gate": "No new quantity, rate, amount or total errors; no decline in visible or overall field agreement.",
        "new_validation": validation, "development_changes": changes,
        "protocol_lock": lock, "validation_selection": selection,
        "first_development_readings": first_readings,
        "candidate_development_readings": candidate_readings, "validation_readings": validation_readings,
        "real_api_workflow": smoke,
        "limits": [
            "Development images were used to find defects; their rerun is not held-out accuracy.",
            "Validation inputs and protocol were frozen before their first inference.",
            "Both sets share a synthetic source and template families, not independent layout coverage.",
            "Clean images are not representative of arbitrary phone photos, languages or Indian GST layouts.",
            "Template visibility rules exclude intentionally absent fields, but do not certify every glyph is visible; some source images clip edge text.",
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
    for label, result in (("Development: first attempt (v4)", first),
                          ("Development: candidate (v5)", candidate),
                          (f"100 new bills: selected {selected_version}", validation)):
        c, n = result["visible_correct_fields"], result["visible_checked_fields"]
        table.append(f"| {label} | {c}/{n} ({c/n:.2%}) | {result['printed_exact_bills']}/100 | "
                     f"{result['abstention_correct_fields']}/{result['abstention_checked_fields']} | {result['errors']} |")
    fixed = sum(len(row["fixed_fields"]) for row in changes)
    regressed = sum(len(row["regressed_fields"]) for row in changes)
    text = "\n".join([
        "# Qwen: development and 100 new validation bills", "",
        f"Generated: {report['generated_at']}", "",
        "200 distinct source bills; the development 100 were evaluated with the initial and candidate readers.",
        "The second 100 were selected before tuning and evaluated with the frozen selected reader.", "",
        "| Run | Expected printed fields correct | Entire printed contract exact | Correct absent-field abstentions | Failures |",
        "| --- | --- | --- | --- | --- |", *table, "",
        f"Development changes: {fixed} previously wrong fields fixed; {regressed} previously correct fields regressed.",
        f"Candidate adopted: **{adopt}**. Selected reader: `{selected_version}`.",
        "The gate rejects a candidate introducing any new quantity, rate, amount or total mistakes.",
        "No decimal tolerance, row-order relaxation or reference metadata edits were used.",
        "The pinned templates print money with %.2f. One new-set metadata rate has hidden precision;",
        "printed scoring uses its displayed value while full-label scoring retains the original metadata.",
        "Display-precision formatting alone leaves the first 100 scores unchanged. The separate C$/A$ audit",
        "corrects currency visibility and regrades all compared runs uniformly; earlier headline scores are superseded.",
        "See [currency scoring audit](currency-scoring-audit.json), [precision audit](visible-precision-audit.json)",
        "and [pilot experiments](qwen-pilot-experiments.json).", "",
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
