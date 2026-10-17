"""Resumable comparison of two local vision models on the SAME 100 new bills.

Ground truth is loaded only after inference and is never supplied to a model.
Report both full label agreement and printed-field agreement: some templates
deliberately do not print labels such as net subtotal, tax or unit price.
"""

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MODELS = ("qwen3-vl:2b-instruct-q4_K_M", "granite3.2-vision:2b")
os.environ.setdefault("AKSHAY_OLLAMA_URL", "http://127.0.0.1:11435")
os.environ.setdefault("AKSHAY_VISION_MODELS", ",".join(MODELS))
CACHE = (
    Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai")) / "benchmark-new100"
)


def reference(row, visible=False):
    template = row["_template_used"]
    number = row["invoice_number"] or row["document_number"] or row["receipt_number"]
    if template == "event_ticket":
        number = row["document_number"] or row["receipt_number"]
    elif template == "pos_thermal":
        number = row["receipt_number"] or row["document_number"]
    elif template == "formal_corporate":
        number = row["invoice_number"]
    expected = {
        "supplier_name": row["supplier_name"],
        "bill_number": number,
        "bill_date": row["document_date"],
        "currency": row["document_currency"],
        "taxable_total": row["document_total_net"],
        "tax_total": row["document_total_tax"],
        "grand_total": row["document_total_amount"],
        "items": [
            {
                "description": item["description"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "amount": item["amount"],
            }
            for item in row["line_items"]
        ],
    }
    if not visible:
        return expected
    # Audited against source templates and sample images, BEFORE model evaluation.
    # Bare dollar signs do not distinguish USD, CAD and AUD.
    if template not in {"formal_corporate", "utility_bill"} and expected["currency"] in {
        "USD",
        "CAD",
        "AUD",
    }:
        expected["currency"] = None
    if template == "event_ticket":
        expected["taxable_total"] = expected["tax_total"] = None
        for item in expected["items"]:
            item["unit_price"] = None
    elif template == "pos_thermal":
        for item in expected["items"]:
            item["description"] = item["description"][:28]
            if item["unit_price"] == item["amount"]:
                item["unit_price"] = None
    elif template in {"modern_minimal", "freelancer_invoice"}:
        if len(row["taxes"]) > 1 or (
            template == "modern_minimal" and not row["taxes"] and not row["document_total_tax"]
        ):
            expected["tax_total"] = None
    return expected


def score(reading, expected):
    from backend.vision import decimal, normalize_reading, normalized

    raw_reading = reading
    reading = normalize_reading(reading)

    checks, mismatches = [], []
    visible_checks, abstention_checks = [], []

    def check(path, actual, wanted, numeric=False):
        original = raw_reading
        try:
            for part in path.split("."):
                original = original[int(part)] if isinstance(original, list) else original.get(part)
        except (AttributeError, IndexError, TypeError, ValueError):
            original = None
        if path == "item_count":
            original = actual
        equal = (
            decimal(str(actual)) == decimal(str(wanted))
            if numeric
            else normalized(actual) == normalized(wanted)
        )
        if wanted is None:
            equal = original is None or original == ""
        checks.append(equal)
        (abstention_checks if wanted is None else visible_checks).append(equal)
        if not equal:
            mismatches.append(
                {
                    "field": path,
                    "actual": actual,
                    "raw_actual": original,
                    "expected": wanted,
                    "kind": "unsupported_format"
                    if actual is None and original not in (None, "")
                    else ("missing" if actual is None else "wrong"),
                }
            )

    for field in (
        "supplier_name",
        "bill_number",
        "bill_date",
        "currency",
        "taxable_total",
        "tax_total",
        "grand_total",
    ):
        check(field, reading.get(field), expected[field], numeric=field.endswith("total"))
    actual_items = reading.get("items", [])
    check("item_count", len(actual_items), len(expected["items"]), numeric=True)
    # Strict row order and all four row fields: no permissive row matching or rounding tolerance.
    for index, item in enumerate(expected["items"]):
        actual = actual_items[index] if index < len(actual_items) else {}
        for field in ("description", "quantity", "unit_price", "amount"):
            check(
                f"items.{index}.{field}",
                actual.get(field),
                item[field],
                numeric=field != "description",
            )
    # Extra hallucinated rows always cause item-count failure.
    return {
        "correct": sum(checks),
        "checked": len(checks),
        "exact": all(checks),
        "mismatches": mismatches,
        "visible_correct": sum(visible_checks),
        "visible_checked": len(visible_checks),
        "abstention_correct": sum(abstention_checks),
        "abstention_checked": len(abstention_checks),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--start-at",
        type=int,
        default=1,
        help="Resume at this 1-based input; earlier inputs must already have valid cached attempts.",
    )
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=5,
        help="Idle time between model requests to limit sustained laptop heat; excluded from inference latency.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run cached inputs, retaining prior attempts in their local result files.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Evaluate the deterministic OCR extractor instead of vision models.",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    if not 1 <= args.start_at <= args.limit:
        parser.error("--start-at must be between 1 and --limit")
    if not 0 <= args.pause_seconds <= 60:
        parser.error("--pause-seconds must be between 0 and 60")
    from backend import vision

    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    rows = manifest["documents"][: args.limit]
    output = CACHE / "runs" / vision.PROMPT_VERSION
    output.mkdir(parents=True, exist_ok=True)
    models = ["ocr-baseline"] if args.baseline else ([args.model] if args.model else MODELS)
    for model in models:
        model_digest = None
        if model != "ocr-baseline":
            with httpx.Client(trust_env=False, timeout=5) as client:
                response = client.get(vision.OLLAMA_URL + "/api/tags")
                response.raise_for_status()
                installed = {entry["name"]: entry["digest"] for entry in response.json()["models"]}
            if model not in installed:
                raise RuntimeError(
                    f"{model} is not installed. Complete model setup before benchmarking; no bill inference was attempted."
                )
            model_digest = installed[model]
        model_dir = output / model.replace(":", "_")
        model_dir.mkdir(exist_ok=True)
        for index, row in enumerate(rows, 1):
            source = CACHE / row["image_file"]
            if hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("Source image checksum mismatch.")
            result_file = model_dir / (source.stem + ".json")
            if index < args.start_at and not result_file.exists():
                raise RuntimeError("Cannot skip an input without a recorded attempt.")
            previous_attempts = []
            if result_file.exists():
                result = json.loads(result_file.read_text(encoding="utf-8"))
                if (
                    result["sha256"] != row["sha256"]
                    or result["prompt_version"] != vision.PROMPT_VERSION
                    or (model_digest and result.get("model_digest") != model_digest)
                ):
                    raise ValueError("Cached run does not match the evaluation input.")
                if index < args.start_at or (
                    not args.refresh and not (args.retry_errors and result.get("error"))
                ):
                    print(f"{model} {index}/{len(rows)} cached", flush=True)
                    continue
                previous_attempts = result.get("previous_attempts", []) + [
                    {key: value for key, value in result.items() if key != "previous_attempts"}
                ]
            if model != "ocr-baseline":
                time.sleep(args.pause_seconds)
            started = time.monotonic()
            try:
                # The source image and shared prompt are the only inputs.
                if model == "ocr-baseline":
                    result = baseline(source)
                else:
                    result = {**vision.read_page(source, "image/jpeg", 1, model), "model": model}
            except Exception as error:
                result = {
                    "model": model,
                    "error": type(error).__name__ + ": " + str(error)[:400],
                    "seconds": round(time.monotonic() - started, 3),
                }
            result.update({"sha256": row["sha256"], "prompt_version": vision.PROMPT_VERSION})
            result["model_digest"] = model_digest
            result["idle_pause_seconds"] = args.pause_seconds if model != "ocr-baseline" else 0
            if previous_attempts:
                result["previous_attempts"] = previous_attempts
            result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(
                f"{model} {index}/{len(rows)} {result['seconds']}s {'ERROR' if result.get('error') else 'read'}",
                flush=True,
            )
        summarize(manifest, model_dir, model, len(rows))


def baseline(source):
    from backend.extraction import extract_document
    from backend.vision import decimal

    started = time.monotonic()
    extracted = extract_document(source, "image/jpeg")
    invoice = extracted["invoice"].model_dump(mode="json")
    reading = {
        key: invoice[key]
        for key in (
            "supplier_name",
            "bill_number",
            "bill_date",
            "currency",
            "taxable_total",
            "grand_total",
        )
    }
    if reading["currency"] == "UNK":
        reading["currency"] = None
    parts = [
        invoice.get(key)
        for key in ("sgst_total", "cgst_total", "igst_total", "cess_total", "other_tax_total")
    ]
    reading["tax_total"] = (
        str(sum((decimal(value) or 0 for value in parts)))
        if any(value is not None for value in parts)
        else None
    )
    reading["items"] = [
        {
            "description": item["description"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "amount": item["taxable_amount"],
        }
        for item in invoice["items"]
    ]
    return {
        "reading": reading,
        "invoice": invoice,
        "method": extracted["method"],
        "seconds": round(time.monotonic() - started, 3),
    }


def summarize(manifest, model_dir, model, count):
    from backend import vision

    results = []
    for row in manifest["documents"][:count]:
        path = model_dir / (Path(row["image_file"]).stem + ".json")
        if not path.exists():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        record = {
            "id": row["file_name"],
            "sha256": row["sha256"],
            "template": row["_template_used"],
            "seconds": result["seconds"],
            "error": result.get("error"),
            "model_digest": result.get("model_digest"),
            "previous_attempts": len(result.get("previous_attempts", [])),
            "idle_pause_seconds": result.get("idle_pause_seconds", 0),
            "raw_date_reading": result.get("printed_date"),
        }
        # Failed/malformed/timed-out responses count as failures, never omitted.
        reading = dict(result.get("raw_reading") or result.get("reading") or {})
        if "bill_date" in reading:
            reading["bill_date"] = (result.get("reading") or {}).get("bill_date")
        record["label_score"] = score(reading, reference(row))
        record["printed_score"] = score(reading, reference(row, visible=True))
        if result.get("error"):
            for kind in ("label_score", "printed_score"):
                record[kind]["correct"] = 0
                record[kind]["exact"] = False
                record[kind]["visible_correct"] = 0
                record[kind]["abstention_correct"] = 0
        results.append(record)
    printed = [result["printed_score"] for result in results]
    summary = {
        "protocol": {
            "normalization_version": vision.NORMALIZATION_VERSION,
            "prompt_version": vision.PROMPT_VERSION,
            "prompt_sha256": hashlib.sha256(vision.PROMPT.encode()).hexdigest(),
            "image_edge": vision.IMAGE_EDGE,
            "model_options": vision.model_options(model),
            "description": "Strict row order, exact decimal values and normalized whitespace/case; no balancing or reference-fed inference.",
        },
        "source": manifest["source"],
        "revision": manifest["revision"],
        "license": manifest["license"],
        "model": model,
        "documents": len(results),
        "requested_documents": count,
        "completed_100": len(results) == count == 100,
        "errors": sum(bool(result["error"]) for result in results),
        "printed_exact_bills": sum(
            result["printed_score"]["exact"] and not result["error"] for result in results
        ),
        "label_exact_bills": sum(
            result["label_score"]["exact"] and not result["error"] for result in results
        ),
        "printed_correct_fields": sum(result["correct"] for result in printed),
        "printed_checked_fields": sum(result["checked"] for result in printed),
        "visible_correct_fields": sum(result["visible_correct"] for result in printed),
        "visible_checked_fields": sum(result["visible_checked"] for result in printed),
        "abstention_correct_fields": sum(result["abstention_correct"] for result in printed),
        "abstention_checked_fields": sum(result["abstention_checked"] for result in printed),
        "median_seconds": statistics.median(result["seconds"] for result in results)
        if results
        else None,
        "total_seconds": round(sum(result["seconds"] for result in results), 3),
        "mismatches_by_field": dict(
            Counter(
                mismatch["field"].split(".")[-1]
                for result in printed
                for mismatch in result["mismatches"]
            )
        ),
        "results": results,
    }
    if model == "ocr-baseline":
        summary["protocol"] = {
            "reader": "backend.extraction OCR path",
            "ocr_image_bounds": [2400, 3200],
            "description": "Application OCR preprocessing on original images; no vision model or vision context is used.",
        }
    (model_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2),
        flush=True,
    )


if __name__ == "__main__":
    main()
