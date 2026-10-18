"""Test report publication using explicitly synthetic fixtures, never live model calls."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import report_vision_benchmark as publisher  # noqa: E402
from benchmark_vision import reference, score, summarize  # noqa: E402

from backend import vision  # noqa: E402


class VisionReportTests(unittest.TestCase):
    def test_regrading_keeps_generation_protocol_and_original_reading(self):
        row = {
            "file_name": "fixture.png", "image_file": "fixture.jpg", "sha256": "fixture-sha",
            "_template_used": "utility_bill", "invoice_number": "FIX-1",
            "document_number": None, "receipt_number": None, "supplier_name": "Fixture",
            "document_date": "2026-01-15", "document_currency": "GBP",
            "document_total_net": 10, "document_total_tax": 0,
            "document_total_amount": 10, "line_items": [],
        }
        manifest = {"source": "fixture", "revision": "fixture", "license": "fixture", "documents": [row]}
        with tempfile.TemporaryDirectory(prefix="rescore-test-") as directory:
            folder = Path(directory)
            cache = folder / "fixture.json"
            cache.write_text(json.dumps({"seconds": 1, "reading": reference(row, True)}))
            original = cache.read_bytes()
            frozen_protocol = {"prompt_version": "fixture-original", "image_edge": 999}
            with contextlib.redirect_stdout(io.StringIO()):
                summarize(manifest, folder, publisher.MODELS[0], 1, generation_protocol=frozen_protocol)
            summary = json.loads((folder / "summary.json").read_text())
            self.assertEqual(summary["protocol"], frozen_protocol)
            self.assertEqual(cache.read_bytes(), original)
            self.assertEqual(summary["printed_exact_bills"], 1)
            self.assertFalse(summary["completed_100"])

    def test_qualified_dollars_remain_known_but_bare_dollars_do_not(self):
        base = {
            "_template_used": "event_ticket", "invoice_number": None,
            "document_number": "FIX-1", "receipt_number": None,
            "supplier_name": "Fixture", "document_date": "2026-01-15",
            "document_total_net": 10, "document_total_tax": 0,
            "document_total_amount": 10, "line_items": [],
        }
        for code, wanted in (("USD", None), ("CAD", "CAD"), ("AUD", "AUD")):
            with self.subTest(code=code):
                self.assertEqual(reference({**base, "document_currency": code}, True)["currency"], wanted)

    def test_visible_rate_uses_template_format_without_editing_hidden_metadata(self):
        row = {
            "_template_used": "utility_bill", "invoice_number": "FIX-1",
            "document_number": None, "receipt_number": None,
            "supplier_name": "Fixture", "document_date": "2026-01-15",
            "document_currency": "GBP", "document_total_net": 10,
            "document_total_tax": 0, "document_total_amount": 10,
            "line_items": [{"description": "Fixture usage", "quantity": 5000,
                            "unit_price": 0.002, "amount": 10}],
        }
        visible = reference(row, visible=True)
        self.assertEqual(visible["items"][0]["unit_price"], "0.00")
        self.assertEqual(reference(row)["items"][0]["unit_price"], 0.002)
        self.assertEqual(row["line_items"][0]["unit_price"], 0.002)
        self.assertTrue(score(visible, visible)["exact"])
        self.assertFalse(score(visible, reference(row))["exact"])

    def test_a_currency_guess_does_not_count_as_correct_abstention(self):
        expected = {
            "supplier_name": None, "bill_number": None, "bill_date": None,
            "currency": None, "taxable_total": None, "tax_total": None,
            "grand_total": None, "items": [],
        }
        actual = {**expected, "currency": "USD"}
        result = score(actual, expected)
        self.assertEqual([entry["field"] for entry in result["mismatches"]], ["currency"])
        self.assertFalse(result["exact"])

    def test_money_symbols_score_by_value_without_hiding_invalid_abstentions(self):
        expected = {
            "supplier_name": "Seller",
            "bill_number": "B1",
            "bill_date": "2026-01-02",
            "currency": "USD",
            "taxable_total": None,
            "tax_total": None,
            "grand_total": 1200.5,
            "items": [],
        }
        actual = {**expected, "grand_total": "$1,200.50", "tax_total": "7%"}
        result = score(actual, expected)
        self.assertEqual([entry["field"] for entry in result["mismatches"]], ["tax_total"])

    def test_incomplete_run_is_not_published(self):
        with tempfile.TemporaryDirectory(prefix="akshay-report-test-") as directory:
            root = Path(directory).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            cache = root / "cache"
            cache.mkdir()
            (cache / "manifest.json").write_text(
                json.dumps({"documents": [{"image_file": f"bill-{i}.jpg"} for i in range(100)]})
            )
            with patch.object(publisher, "CACHE", cache), patch.object(publisher, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "Complete all 100"):
                    publisher.main()
            self.assertFalse((root / "docs/testing/200-bill-vision-results.json").exists())

    def test_complete_fixture_report_preserves_failures_and_model_budgets(self):
        with tempfile.TemporaryDirectory(prefix="akshay-report-test-") as directory:
            root = Path(directory).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            cache = root / "cache"
            cache.mkdir()
            documents = [
                {
                    "file_name": f"fixture-{i}.png",
                    "image_file": f"fixture-{i}.jpg",
                    "sha256": f"fixture-sha-{i}",
                    "_template_used": "modern_minimal",
                    "supplier_name": "Fixture Seller",
                    "invoice_number": "FIX-1",
                    "document_number": None,
                    "receipt_number": None,
                    "document_date": "2026-01-02",
                    "document_currency": "EUR",
                    "document_total_net": 100,
                    "document_total_tax": 0,
                    "document_total_amount": 100,
                    "taxes": [],
                    "line_items": [
                        {
                            "description": "Fixture item",
                            "quantity": 2,
                            "unit_price": 50,
                            "amount": 100,
                        }
                    ],
                }
                for i in range(100)
            ]
            (cache / "manifest.json").write_text(
                json.dumps(
                    {
                        "source": "fixture-only",
                        "revision": "fixture",
                        "license": "fixture",
                        "documents": documents,
                    }
                )
            )
            reading = {
                "supplier_name": "Fixture Seller",
                "bill_number": "FIX-1",
                "bill_date": "2026-01-02",
                "currency": "EUR",
                "taxable_total": "100",
                "tax_total": None,
                "grand_total": "100",
                "items": [
                    {
                        "description": "Fixture item",
                        "quantity": "2",
                        "unit_price": "50",
                        "amount": "100",
                    }
                ],
            }
            for model in ("ocr-baseline", *publisher.MODELS):
                folder = cache / "runs" / vision.PROMPT_VERSION / model.replace(":", "_")
                folder.mkdir(parents=True)
                for index, row in enumerate(documents):
                    result = {
                        "seconds": 1,
                        "reading": reading,
                        "model_digest": "fixture-digest" if model != "ocr-baseline" else None,
                        "sha256": row["sha256"],
                        "prompt_version": vision.PROMPT_VERSION,
                        "model": model,
                        "image_edge": vision.IMAGE_EDGE,
                        "preprocessing_version": vision.PREPROCESSING_VERSION,
                        "model_options": vision.model_options(model),
                    }
                    if model == publisher.MODELS[-1] and index == 0:
                        result = {
                            "seconds": 180,
                            "error": "fixture timeout",
                            "model_digest": "fixture-digest",
                            "sha256": row["sha256"],
                            "prompt_version": vision.PROMPT_VERSION,
                            "model": model,
                        }
                    (folder / (Path(row["image_file"]).stem + ".json")).write_text(
                        json.dumps(result)
                    )
            original = root / "data/benchmark"
            original.mkdir(parents=True)
            (original / "final-currency.json").write_text(
                json.dumps({"count": 100, "exact_bills": 99, "results": []})
            )
            (original / "api-final.json").write_text(
                json.dumps(
                    {
                        "count": 100,
                        "failures": [],
                        "round_trip_exact": 100,
                        "source_checksums_exact": 100,
                    }
                )
            )
            (cache.parent / "api-smoke-result.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "prompt_version": vision.PROMPT_VERSION,
                        "normalization_version": vision.NORMALIZATION_VERSION,
                        "raw_readings_preserved": True,
                        "draft_unchanged": True,
                        "source_unchanged": True,
                        "invalid_suggestion_rejected": True,
                        "stale_report_rejected": True,
                    }
                )
            )
            with (
                patch.object(publisher, "CACHE", cache),
                patch.object(publisher, "ROOT", root),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                publisher.main()
            report = json.loads((root / "docs/testing/200-bill-vision-results.json").read_text())
            self.assertEqual(report["unique_bills"], 200)
            self.assertEqual(report["original_regression"]["exact_bills"], 99)
            granite = report["models"][publisher.MODELS[-1]]
            self.assertEqual(granite["errors"], 1)
            self.assertEqual(granite["results"][0]["printed_score"]["correct"], 0)
            self.assertEqual(granite["protocol"]["model_options"]["num_ctx"], 12288)
            self.assertTrue((root / "docs/testing/200-bill-vision-comparison.md").is_file())

    def test_publication_rejects_mismatched_cached_identity_and_settings(self):
        with tempfile.TemporaryDirectory(prefix="akshay-report-test-") as directory:
            folder = Path(directory)
            manifest = {"documents": [{"image_file": "fixture.png", "sha256": "expected"}]}
            model = publisher.MODELS[0]
            valid = {
                "sha256": "expected",
                "prompt_version": vision.PROMPT_VERSION,
                "model": model,
                "image_edge": vision.IMAGE_EDGE,
                "preprocessing_version": vision.PREPROCESSING_VERSION,
                "model_options": vision.model_options(model),
            }
            for field, wrong in (
                ("sha256", "other-input"),
                ("prompt_version", "old-prompt"),
                ("model", "other-model"),
                ("image_edge", 999),
                ("preprocessing_version", "other-preparation"),
                ("model_options", {"num_ctx": 1}),
            ):
                with self.subTest(field=field):
                    (folder / "fixture.json").write_text(json.dumps({**valid, field: wrong}))
                    with self.assertRaisesRegex(RuntimeError, "mismatch"):
                        publisher.validate_attempts(manifest, folder, model)
            (folder / "fixture.json").write_text(json.dumps(valid))
            publisher.validate_attempts(manifest, folder, model)

    def test_publication_requires_a_current_complete_api_workflow(self):
        valid = {
            "status": "completed",
            "prompt_version": vision.PROMPT_VERSION,
            "normalization_version": vision.NORMALIZATION_VERSION,
            "raw_readings_preserved": True,
            "draft_unchanged": True,
            "source_unchanged": True,
            "invalid_suggestion_rejected": True,
            "stale_report_rejected": True,
        }
        publisher.validate_smoke(valid)
        for key in valid:
            with self.subTest(field=key), self.assertRaisesRegex(RuntimeError, "API workflow"):
                publisher.validate_smoke({**valid, key: None})
