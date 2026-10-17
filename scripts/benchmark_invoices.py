"""Reproducible evaluation against 100 externally authored public invoices.

Dataset: Drew IPP invoice-extraction-benchmark, CC BY 4.0.
Reference labels are used only here, never by the application's extractor.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REVISION = "446bab08662790cb39457792243bff5704373b95"
SOURCE = "https://huggingface.co/datasets/drew-ipp/invoice-extraction-benchmark"
BASE = f"{SOURCE}/resolve/{REVISION}"
CACHE = ROOT / "data" / "benchmark"


def fetch(url):
    for attempt in range(4):
        try:
            with httpx.Client(trust_env=False, follow_redirects=True, timeout=60) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def prepare():
    CACHE.mkdir(parents=True, exist_ok=True)
    metadata = CACHE / "metadata.jsonl"
    metadata.write_bytes(fetch(BASE + "/corpus/v1/metadata.jsonl"))
    rows = [json.loads(line) for line in metadata.read_text(encoding="utf-8").splitlines()]
    selected = sorted(
        (row for row in rows if row["kind"] == "invoice" and row["render"] == "pdf"),
        key=lambda row: row["doc_id"],
    )
    scans = sorted(
        (row for row in rows if row["kind"] == "invoice" and row["category"] == "scan"),
        key=lambda row: row["doc_id"],
    )
    selected += scans[: 100 - len(selected)]
    if len(selected) != 100 or len({row["sha256"] for row in selected}) != 100:
        raise ValueError("The pinned evaluation set must contain 100 distinct bills.")

    def download(row):
        path = CACHE / row["file_name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            path.write_bytes(fetch(BASE + "/corpus/v1/" + row["file_name"]))
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Source checksum mismatch: {row['doc_id']}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(download, selected))
    (CACHE / "manifest.json").write_text(
        json.dumps(
            {"source": SOURCE, "revision": REVISION, "license": "CC-BY-4.0", "documents": selected},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Downloaded and checksum-verified {len(selected)} distinct public bills.", flush=True)
    return selected


def text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def amount(value):
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


def evaluate(rows, label):
    from backend.extraction import extract_document
    from backend.validation import validate_invoice

    results = []
    for index, row in enumerate(rows, 1):
        started = time.monotonic()
        mismatches = []
        try:
            path = CACHE / row["file_name"]
            result = extract_document(
                path, "application/pdf" if path.suffix == ".pdf" else "image/png"
            )
            invoice = result["invoice"]
            expected = row["expected"]
            checks = {
                "supplier_name": (text(invoice.supplier_name), text(expected["vendor_name"])),
                "bill_number": (text(invoice.bill_number), text(expected["invoice_number"])),
                "currency": (invoice.currency, expected["currency"]),
                "tax_total": (
                    amount(
                        sum(
                            (
                                getattr(invoice, field) or Decimal(0)
                                for field in (
                                    "sgst_total",
                                    "cgst_total",
                                    "igst_total",
                                    "cess_total",
                                    "other_tax_total",
                                )
                            ),
                            Decimal(0),
                        )
                    ),
                    amount(expected["tax"]),
                ),
                "bill_date": (
                    str(invoice.bill_date) if invoice.bill_date else None,
                    expected["invoice_date"],
                ),
                "taxable_total": (amount(invoice.taxable_total), amount(expected["subtotal"])),
                "grand_total": (amount(invoice.grand_total), amount(expected["total"])),
                "item_count": (len(invoice.items), len(expected["lines"])),
            }
            for key, (actual, wanted) in checks.items():
                if actual != wanted:
                    mismatches.append({"field": key, "actual": actual, "expected": wanted})
            for position, (item, wanted) in enumerate(zip(invoice.items, expected["lines"])):
                if text(item.description) != text(wanted["description"]):
                    mismatches.append(
                        {
                            "field": f"items[{position}].description",
                            "actual": item.description,
                            "expected": wanted["description"],
                        }
                    )
                accepted = [
                    amount(wanted["amount"]),
                    *[amount(value) for value in wanted.get("alt_amounts", [])],
                ]
                if amount(item.taxable_amount) not in accepted:
                    mismatches.append(
                        {
                            "field": f"items[{position}].taxable_amount",
                            "actual": item.taxable_amount,
                            "expected": wanted["amount"],
                        }
                    )
            validation = validate_invoice(invoice)
            entry = {
                "id": row["doc_id"],
                "category": row["category"],
                "file_name": row["file_name"],
                "mismatches": mismatches,
                "invoice": invoice.model_dump(mode="json"),
                "validation": validation,
                "expected_flag": expected["should_flag"],
                "extraction_notes": result["notes"],
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        except Exception as error:
            entry = {
                "id": row["doc_id"],
                "category": row["category"],
                "mismatches": [
                    {
                        "field": "exception",
                        "actual": f"{type(error).__name__}: {error}",
                        "expected": "no exception",
                    }
                ],
            }
        results.append(entry)
        if index % 5 == 0 or index == 100:
            print(
                f"{label}: {index}/100; exact bills {sum(not entry['mismatches'] for entry in results)}",
                flush=True,
            )
    report = {
        "source": SOURCE,
        "revision": REVISION,
        "label": label,
        "count": len(results),
        "exact_bills": sum(not entry["mismatches"] for entry in results),
        "mismatch_fields": dict(
            Counter(
                re.sub(r"items\[\d+\]", "items[]", item["field"])
                for entry in results
                for item in entry["mismatches"]
            )
        ),
        "results": results,
    }
    destination = CACHE / f"{label}.json"
    destination.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--label", default="evaluation")
    parser.add_argument("--strict", action="store_true", help="Fail on any mismatch except the documented source FX-rounding discrepancy")
    args = parser.parse_args()
    rows = (
        prepare()
        if args.download
        else json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))["documents"]
    )
    report = evaluate(rows, args.label)
    if args.strict:
        for record in report["results"]:
            if not record["mismatches"]:
                continue
            known = (record["id"] == "currency-dual-eur-nad-2" and len(record["mismatches"]) == 1
                     and record["mismatches"][0]["field"] == "taxable_total"
                     and amount(record["mismatches"][0]["actual"]) == Decimal("3247.50")
                     and amount(record["mismatches"][0]["expected"]) == Decimal("3247.51")
                     and any(issue["field"] == "exchange_rate" for issue in record["validation"]["issues"]))
            if not known:
                raise SystemExit("Unexpected mismatch: " + record["id"])
