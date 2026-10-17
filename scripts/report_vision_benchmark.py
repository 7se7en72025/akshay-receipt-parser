"""Publish an auditable report only after both models attempted all 100 bills."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from benchmark_vision import CACHE, MODELS, ROOT, summarize


def main():
    from backend import vision

    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    runs = CACHE / "runs" / vision.PROMPT_VERSION
    models = {}
    for model in ("ocr-baseline", *MODELS):
        directory = runs / model.replace(":", "_")
        if (
            sum(
                (directory / (Path(row["image_file"]).stem + ".json")).exists()
                for row in manifest["documents"]
            )
            != 100
        ):
            raise RuntimeError(f"Complete all 100 input attempts for {model} before publishing.")
        summarize(manifest, directory, model, 100)
        result = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        if model != "ocr-baseline":
            digests = {row["model_digest"] for row in result["results"]}
            if len(digests) != 1 or None in digests:
                raise RuntimeError(
                    "Mixed or missing model digests; re-run with one installed model revision."
                )
        models[model] = result
    original = json.loads((ROOT / "data/benchmark/final-currency.json").read_text(encoding="utf-8"))
    original_summary = {key: value for key, value in original.items() if key != "results"}
    api = json.loads((ROOT / "data/benchmark/api-final.json").read_text(encoding="utf-8"))
    smoke = json.loads((CACHE.parent / "api-smoke-result.json").read_text(encoding="utf-8"))
    if original["count"] != 100 or api["count"] != 100 or api["failures"]:
        raise RuntimeError("Re-run the original 100-bill regression and API workflow first.")
    templates = dict(Counter(row["_template_used"] for row in manifest["documents"]))
    currencies = dict(Counter(row["document_currency"] for row in manifest["documents"]))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unique_bills": 200,
        "new_source": {key: value for key, value in manifest.items() if key != "documents"},
        "new_set_templates": templates,
        "new_set_currencies": currencies,
        "new_line_items": sum(len(row["line_items"]) for row in manifest["documents"]),
        "original_regression": original_summary,
        "original_api_workflow": api,
        "real_vision_api_workflow": smoke,
        "models": models,
        "limits": [
            "Synthetic clean images only in the new set; not production accuracy or a held-out evaluation.",
            "This set was used to find and fix parsing and prompting defects.",
            "Some labels are absent from the image. Printed-field scoring requires abstention for these fields.",
            "Full-label scoring also includes hidden metadata; hidden values must not be invented to improve it.",
            "Each failed response counts as zero correct fields, not a skipped document.",
            "Ambiguous numerical dates are deliberately left unnormalized for manual review; their verbatim readings are retained.",
            "AI suggestions never automatically alter, approve or export a bill.",
        ],
    }
    target = ROOT / "docs/testing"
    target.mkdir(parents=True, exist_ok=True)
    (target / "200-bill-vision-results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    table = []
    for model, result in models.items():
        correct, checked = result["visible_correct_fields"], result["visible_checked_fields"]
        table.append(
            f"| {model} | {correct}/{checked} ({correct / checked:.1%}) | {result['printed_exact_bills']}/100 | {result['errors']} | {result['median_seconds']:.2f} s |"
        )
    text = f"""# 200-bill regression and local vision comparison

Generated: {report["generated_at"]}

## What was evaluated

The original 100 bills remain a regression set. Another 100 distinct bills from
[Alamgir Qazi's InvoiceOCR-Synth]({manifest["source"]}) were added, pinned to
`{manifest["revision"]}` under CC BY 4.0. Selection was the first 100 distinct
base documents in dataset order with `quality=clean`, before model evaluation.
Image checksums are recorded; none overlap the original manifest.

The new set has {report["new_line_items"]} line items across six templates:
{", ".join(f"{name}: {count}" for name, count in templates.items())}.
Reference currencies: {", ".join(f"{name}: {count}" for name, count in currencies.items())}.
It contains foreign currency documents; the INR workspace does not approve them.

Both installed models attempted the same 100 original images. No OCR text,
draft, filename or reference answer was sent to either model. Readings are cached
with the source SHA-256, exact installed model digest and prompt version.

## New 100-bill results

| Reader | Visible values correct | Entire printed-field contract exact | Failed responses | Median per bill |
| --- | --- | --- | --- | --- |
{chr(10).join(table)}

Visible-value accuracy excludes reference fields which the template does not
print. The whole-bill contract includes header values, row count, every item
description/quantity/rate/amount in source order, and correct abstention when a
field is not printed. It is deliberately stricter than adding totals. A failed
response scores zero correct fields. Exact decimals are compared without
balancing, rounding tolerances or changing reference answers.

Full-label agreement is also retained in the JSON report. It is not the primary
accuracy measure because some metadata, including event-ticket subtotals and
unit rates, is absent from the rendered image. A model must not guess it.
Date mismatches include deliberate abstention for ambiguous numerical dates;
the verbatim date remains available in the read-only page reading for review.

## Original regression and workflow integrity

- Original extractor: {original["exact_bills"]}/100 exact, plus the
  existing explicitly flagged one-cent printed FX discrepancy. The source
  entries are retained; that discrepancy is not counted as exact.
- Original real API workflow: {api["round_trip_exact"]}/100 stored drafts match
  their extraction snapshots and {api["source_checksums_exact"]}/100 source hashes
  match. Foreign-currency approvals, relabelling and unapproved exports are blocked.
- Real PDF upload → extraction → vision subprocess → report: completed. The
  source and draft were unchanged; invalid selections and stale report application
  were rejected. This checks integration, not the correctness of model readings.

## Fixes made during evaluation

- Copy the printed date as text, then normalize it in code only when its order
  is unambiguous. Schema-constrained ISO conversion had corrupted date digits.
- Keep a separate printed unit rate and line amount. Handle explicit thermal
  receipt `@ rate each` continuation lines without adding them to item names.
- Keep `Qty / Value` as one heading and `Unit Price` / `Value` as separate columns.
- Retain the known source currency when a payable line only has a dollar sign;
  ambiguous dollars never become INR by default.
- Bound image resolution, context and evaluation batches after Windows memory
  pressure during an earlier larger run. Run OCR and model benchmarks sequentially.
- Close rendered PDF page resources explicitly; test the real subprocess path.

## Protocol and limits

Hardware: 16 GB RAM, NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM. Official portable
Ollama v0.40.5. Models are local Apache-2.0 releases; one model is loaded at a time.
Final prompt: `{vision.PROMPT_VERSION}`; image longest edge {vision.IMAGE_EDGE}px;
options: `{json.dumps(vision.MODEL_OPTIONS, sort_keys=True)}`.
Reported latency excludes downloads and idle pauses. Sustained laptop GPU heat
reduced clock speeds during testing; later requests used cooldown pauses. These
timings are indicative observations, not a controlled hardware speed comparison.

The new set was used for debugging. These results are a regression/evaluation
measure, not unseen production accuracy. Blurry photos, handwriting, unusual
languages, other layouts and multi-page bills need separate evaluation. Small
models can still read the same wrong value as OCR or invent absent fields.

Source-visibility rules were audited against the six generator templates at
[revision 91082ede48d2c0b2e32d9c489ea35f34e9922a99](https://github.com/alamgirqazi/synthetic-invoice-gen/tree/91082ede48d2c0b2e32d9c489ea35f34e9922a99/templates)
and sample images before the final comparison. Row descriptions are compared
with normalized whitespace and case, not fuzzy matching. A rendered truncation
in the thermal template is reflected in its printed-field reference.

Verification remains optional human review. Matching fields do not prove the
bill is correct. Currency, aggregate tax, ambiguous rows and conflicting pages
are read-only comparisons; applying a selected suggestion creates an audited,
unapproved draft guarded by its saved version.

## Reproduce

```powershell
.\\.venv\\Scripts\\python.exe scripts\\setup_local_vision.py
.\\.venv\\Scripts\\python.exe scripts\\prepare_vision_benchmark.py
.\\.venv\\Scripts\\python.exe scripts\\benchmark_vision.py --baseline --refresh
.\\.venv\\Scripts\\python.exe scripts\\benchmark_vision.py
.\\.venv\\Scripts\\python.exe scripts\\benchmark_invoices.py --label final-currency --strict
.\\.venv\\Scripts\\python.exe scripts\\benchmark_api.py
.\\.venv\\Scripts\\python.exe scripts\\smoke_vision_api.py
.\\.venv\\Scripts\\python.exe scripts\\report_vision_benchmark.py
```

Run these commands sequentially. Cached model runs resume without repeating
completed requests. `--retry-errors` retries failed responses; `--refresh` reruns
all selected inputs while retaining prior local attempts. Model installation
and initial dataset preparation require internet. Inference is loopback-only.
Downloads, original images, runtime files and caches stay outside Git.

See [the machine-readable per-bill results](200-bill-vision-results.json) for every
source checksum, mismatch and failure, and [the review workflow](../local-vision.md).
"""
    (target / "200-bill-vision-comparison.md").write_text(text, encoding="utf-8")
    print("Published the completed comparison and per-bill results.", flush=True)


if __name__ == "__main__":
    main()
