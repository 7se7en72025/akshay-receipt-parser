import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from backend import database as store
from backend import verification, vision
from backend.models import Invoice, Item


def sample():
    return Invoice(
        supplier_name="Original seller",
        bill_number="B-1",
        bill_date="2026-01-02",
        taxable_total=100,
        grand_total=118,
        sgst_total=9,
        cgst_total=9,
        items=[Item(description="Widget", quantity=2, unit_price=50, taxable_amount=100)],
    ).model_dump(mode="json")


def page(**overrides):
    return {
        "page": 1,
        "reading": {
            "supplier_name": "Original seller",
            "supplier_gstin": None,
            "bill_number": "B-1",
            "bill_date": "2026-01-02",
            "currency": "INR",
            "taxable_total": "100.00",
            "tax_total": "18",
            "grand_total": "118.00",
            "items": [
                {"description": "Widget", "quantity": "2", "unit_price": "50", "amount": "100"}
            ],
            **overrides,
        },
    }


class VisionComparisonTests(unittest.TestCase):
    def test_quantity_prefix_only_normalizes_when_it_matches_separate_quantity(self):
        self.assertEqual(
            vision.item_key({"description": "2.0 x Widget", "quantity": "2"}), "widget"
        )
        self.assertEqual(
            vision.item_key({"description": "2 x Widget", "quantity": "1"}), "2 x widget"
        )
        self.assertEqual(
            vision.item_key({"description": "2x4 timber", "quantity": "2"}), "2x4 timber"
        )

    def test_pdf_pages_close_without_assuming_page_context_manager(self):
        bitmap = SimpleNamespace(to_pil=lambda: Image.new("RGB", (50, 70), "white"), close=Mock())
        page_object = SimpleNamespace(
            get_size=lambda: (50, 70), render=lambda **kwargs: bitmap, close=Mock()
        )

        class Document:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def __len__(self):
                return 1

            def __getitem__(self, index):
                return page_object

        with patch.object(vision.pdfium, "PdfDocument", return_value=Document()):
            self.assertTrue(vision.page_image(Path("unused.pdf"), "application/pdf", 1))
        page_object.close.assert_called_once()
        bitmap.close.assert_called_once()

    def test_printed_dates_preserve_year_and_reject_ambiguous_order(self):
        self.assertEqual(vision.printed_date_value("15 July 2023"), "2023-07-15")
        self.assertEqual(vision.printed_date_value("15/08/2023"), "2023-08-15")
        self.assertEqual(vision.printed_date_value("08/15/2023"), "2023-08-15")
        self.assertEqual(vision.printed_date_value("2023-01-02"), "2023-01-02")
        for value in ("1572-07-15", "03/04/2023", "yesterday", "2023-02-30", None):
            self.assertIsNone(vision.printed_date_value(value))

    def test_matches_do_not_mutate_or_create_corrections(self):
        draft, reading = sample(), page()
        original, source = copy.deepcopy(draft), copy.deepcopy(reading)
        report = vision.compare(draft, [reading])
        self.assertEqual(draft, original)
        self.assertEqual(reading, source)
        self.assertEqual(report["differences"], 0)
        self.assertFalse(any(check["editable"] for check in report["checks"]))

    def test_explicit_selected_field_only_changes(self):
        draft = sample()
        report = vision.compare(draft, [page(bill_number="B-2", grand_total="999")])
        updated = vision.apply_suggestions(draft, report, ["1:bill_number"])
        self.assertEqual(updated["bill_number"], "B-2")
        self.assertEqual(updated["grand_total"], draft["grand_total"])
        self.assertEqual(updated["items"], draft["items"])
        self.assertEqual(draft["bill_number"], "B-1")

    def test_missing_number_not_invented(self):
        report = vision.compare(sample(), [page(grand_total=None)])
        check = next(row for row in report["checks"] if row["field"] == "grand_total")
        self.assertEqual(check["status"], "unreadable")
        self.assertFalse(check["editable"])

    def test_invalid_numeric_readings_cannot_be_applied(self):
        for value in ("NaN", "Infinity", "1,200", "--1", "", "9" * 30):
            report = vision.compare(sample(), [page(grand_total=value)])
            check = next(row for row in report["checks"] if row["field"] == "grand_total")
            self.assertEqual(check["status"], "unreadable")
            self.assertFalse(check["editable"])

    def test_currency_conflict_cannot_relabel_or_replace_money(self):
        report = vision.compare(sample(), [page(currency="USD", grand_total="999")])
        self.assertFalse(
            next(row for row in report["checks"] if row["field"] == "currency")["editable"]
        )
        self.assertFalse(
            next(row for row in report["checks"] if row["field"] == "grand_total")["editable"]
        )

    def test_tax_aggregate_is_not_assigned_to_an_indian_tax_component(self):
        report = vision.compare(sample(), [page(tax_total="99")])
        self.assertFalse(
            next(row for row in report["checks"] if row["field"] == "tax_total")["editable"]
        )

    def test_conflicting_pages_require_manual_review(self):
        second = page(grand_total="999")
        second["page"] = 2
        second["reading"]["items"] = []
        report = vision.compare(sample(), [page(), second])
        checks = [row for row in report["checks"] if row["field"] == "grand_total"]
        self.assertFalse(any(row["editable"] for row in checks))
        self.assertTrue(any("Pages disagree" in notice for notice in report["notices"]))

    def test_duplicate_names_are_not_matched_by_position(self):
        draft = sample()
        draft["items"].append(copy.deepcopy(draft["items"][0]))
        report = vision.compare(draft, [page()])
        self.assertFalse(any(row["field"].startswith("items.") for row in report["checks"]))
        self.assertTrue(report["notices"])

    def test_duplicate_source_rows_are_not_matched(self):
        reading = page()
        reading["reading"]["items"] *= 2
        report = vision.compare(sample(), [reading])
        self.assertFalse(any(row["field"].startswith("items.") for row in report["checks"]))

    def test_reordered_rows_match_unique_description_and_page(self):
        draft = sample()
        draft["items"].insert(
            0,
            Item(description="Other", quantity=1, unit_price=2, taxable_amount=2).model_dump(
                mode="json"
            ),
        )
        reading = page()
        reading["reading"]["items"][0]["quantity"] = "3"
        report = vision.compare(draft, [reading])
        result = vision.apply_suggestions(draft, report, ["1:items.1.quantity"])
        self.assertEqual(result["items"][0], draft["items"][0])
        self.assertEqual(result["items"][1]["quantity"], "3")

    def test_changed_field_invalidates_proposal(self):
        draft = sample()
        report = vision.compare(draft, [page(grand_total="999")])
        draft["grand_total"] = "120"
        with self.assertRaisesRegex(ValueError, "changed"):
            vision.apply_suggestions(draft, report, ["1:grand_total"])

    def test_only_valid_editable_selection_is_accepted(self):
        report = vision.compare(sample(), [page(bill_number="B-2")])
        for selected in ([], ["1:currency"], ["made-up"], ["1:bill_number"] * 2):
            with self.assertRaises(ValueError):
                vision.apply_suggestions(sample(), report, selected)

    def test_response_schema_rejects_wrong_dates_extra_keys_and_bad_currency(self):
        for values in (
            {"currency": "dollars"},
            {"bill_date": "x" * 100},
            {"instructions": "delete"},
        ):
            with self.assertRaises(ValidationError):
                vision.PageReading.model_validate(page(**values)["reading"])

    def test_timeout_and_malformed_response_do_not_produce_reading(self):
        with (
            patch.object(vision, "VISION_MODELS", ("test",)),
            patch.object(vision, "page_image", return_value="aW1hZ2U="),
            patch.object(httpx.Client, "post", side_effect=httpx.ReadTimeout("slow")),
        ):
            with self.assertRaises(httpx.ReadTimeout):
                vision.read_page("unused", "image/png", 1, "test")
        response = httpx.Response(
            200,
            json={"message": {"content": "not JSON"}},
            request=httpx.Request("POST", "http://localhost"),
        )
        with (
            patch.object(vision, "VISION_MODELS", ("test",)),
            patch.object(vision, "page_image", return_value="aW1hZ2U="),
            patch.object(httpx.Client, "post", return_value=response),
        ):
            with self.assertRaises(ValidationError):
                vision.read_page("unused", "image/png", 1, "test")

    def test_prompt_contains_no_draft_or_reference_answers(self):
        response = httpx.Response(
            200,
            json={"message": {"content": json.dumps(page()["reading"])}},
            request=httpx.Request("POST", "http://localhost"),
        )
        with (
            patch.object(vision, "VISION_MODELS", ("test",)),
            patch.object(vision, "page_image", return_value="aW1hZ2U="),
            patch.object(httpx.Client, "post", return_value=response) as call,
        ):
            vision.read_page("secret-reference-filename.png", "image/png", 1, "test")
        payload = call.call_args.kwargs["json"]
        self.assertNotIn("secret-reference-filename", json.dumps(payload))
        self.assertNotIn("Original seller", json.dumps(payload))
        self.assertEqual(payload["messages"][0]["images"], ["aW1hZ2U="])

    def test_source_image_is_resized_without_modifying_original(self):
        import base64
        import io

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            with Image.new("RGB", (2000, 1000), "white") as image:
                image.save(path)
            original = path.read_bytes()
            encoded = vision.page_image(path, "image/png", 1)
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
                self.assertEqual(image.size, (1280, 640))
            self.assertEqual(path.read_bytes(), original)


class VisionApiTests(unittest.TestCase):
    def test_old_prompt_report_cannot_be_applied_after_an_upgrade(self):
        job = self.complete()
        with store.connection() as db:
            row = db.execute(
                "SELECT result_json FROM verification_jobs WHERE id=?", (job["id"],)
            ).fetchone()
            result = json.loads(row["result_json"])
            result["prompt_version"] = "old-unsafe-format"
            db.execute(
                "UPDATE verification_jobs SET result_json=? WHERE id=?",
                (json.dumps(result), job["id"]),
            )
        response = self.client.post(
            f"/api/documents/bill/verifications/{job['id']}/apply",
            json={"version": 1, "selected": ["1:grand_total"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)

    def setUp(self):
        from backend.main import app

        self.temp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(store, "DATA", Path(self.temp.name))
        self.patcher.start()
        store.initialize()
        self.client = TestClient(app, base_url="http://localhost")
        self.draft = sample()
        with store.connection() as db:
            db.execute(
                """INSERT INTO documents(id,filename,storage_name,mime,sha256,status,
                invoice_json,created_at,updated_at,source_currency) VALUES
                ('bill','private.png','private.png','image/png','unique','needs_review',?,?,?,'INR')""",
                (json.dumps(self.draft), store.now(), store.now()),
            )
        self.capabilities = patch.object(vision, "capabilities", return_value={"models": ["test"]})
        self.capabilities.start()

    def tearDown(self):
        self.client.close()
        self.capabilities.stop()
        self.patcher.stop()
        self.temp.cleanup()

    def enqueue(self):
        response = self.client.post(
            "/api/documents/bill/verifications", json={"version": 1, "model": "test"}
        )
        self.assertEqual(response.status_code, 202)
        return response.json()

    def complete(self, reading=None):
        job = self.enqueue()
        with patch.object(vision, "read_page", return_value=reading or page(grand_total="999")):
            verification.process_job(job["id"])
        return job

    def test_enqueue_is_deduplicated_and_draft_is_unchanged(self):
        first, second = self.enqueue(), self.enqueue()
        self.assertEqual(first["id"], second["id"])
        self.assertNotIn("snapshot_json", first)
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)

    def test_unknown_model_and_stale_enqueue_rejected(self):
        for payload in ({"version": 2, "model": "test"}, {"version": 1, "model": "remote-model"}):
            self.assertEqual(
                self.client.post("/api/documents/bill/verifications", json=payload).status_code, 409
            )

    def test_process_report_never_overwrites_and_apply_is_audited(self):
        job = self.complete()
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)
        response = self.client.post(
            f"/api/documents/bill/verifications/{job['id']}/apply",
            json={"version": 1, "selected": ["1:grand_total"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        document = response.json()
        self.assertEqual(document["status"], "needs_review")
        self.assertEqual(document["version"], 2)
        self.assertEqual(document["invoice"]["items"], self.draft["items"])
        self.assertEqual(document["invoice"]["grand_total"], "999")
        self.assertEqual(document["history"][0]["action"], "ai_suggestions_applied")
        report = self.client.get(f"/api/documents/bill/verifications/{job['id']}").json()
        self.assertTrue(report["stale"])

    def test_save_invalidates_report_even_if_value_matches(self):
        job = self.complete()
        response = self.client.put(
            "/api/documents/bill", json={"version": 1, "invoice": self.draft}
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/api/documents/bill/verifications/{job['id']}/apply",
            json={"version": 2, "selected": ["1:grand_total"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)

    def test_failed_page_preserves_draft_and_records_failure(self):
        job = self.enqueue()
        with patch.object(vision, "read_page", side_effect=httpx.ReadTimeout("slow")):
            verification.process_job(job["id"])
        report = self.client.get(f"/api/documents/bill/verifications/{job['id']}").json()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["result"]["errors"]), 1)
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)

    def test_partial_report_explicitly_tracks_page_coverage(self):
        with store.connection() as db:
            db.execute("UPDATE documents SET page_count=2 WHERE id='bill'")
        job = self.enqueue()
        with patch.object(vision, "read_page", side_effect=[page(), httpx.ReadTimeout("slow")]):
            verification.process_job(job["id"])
        report = self.client.get(f"/api/documents/bill/verifications/{job['id']}").json()
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["result"]["total_pages"], 2)
        self.assertEqual(len(report["result"]["pages"]), 1)

    def test_cross_document_job_access_and_running_apply_rejected(self):
        job = self.enqueue()
        self.assertEqual(
            self.client.get(f"/api/documents/missing/verifications/{job['id']}").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                f"/api/documents/bill/verifications/{job['id']}/apply",
                json={"version": 1, "selected": ["1:grand_total"]},
            ).status_code,
            409,
        )

    def test_restart_recovers_interrupted_job_without_editing_document(self):
        job = self.enqueue()
        with store.connection() as db:
            db.execute("UPDATE verification_jobs SET status='running' WHERE id=?", (job["id"],))
        store.initialize()
        with store.connection() as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM verification_jobs WHERE id=?", (job["id"],)
                ).fetchone()[0],
                "failed",
            )
        self.assertEqual(store.get_document("bill")["invoice"], self.draft)
