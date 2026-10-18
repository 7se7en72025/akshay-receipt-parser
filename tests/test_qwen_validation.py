import base64
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from report_qwen_validation import (  # noqa: E402
    choose_candidate,
    collect,
    protocol_signature,
    validate_protocol_lock,
    validate_request_artifact,
)

from backend import vision  # noqa: E402


class FrozenValidationTests(unittest.TestCase):
    def test_raw_response_and_prepared_image_cannot_be_silently_replaced(self):
        with tempfile.TemporaryDirectory(prefix="qwen-provenance-test-") as directory:
            cache = Path(directory)
            with Image.new("RGB", (100, 100), "white") as image:
                image.save(cache / "fixture.jpg")
            raw = {key: None for key in vision.PageReading.model_fields}
            raw["items"] = []
            prepared = vision.page_image(cache / "fixture.jpg", "image/jpeg", 1)
            attempt = {
                "raw_response": json.dumps(raw), "raw_reading": raw,
                "reading": vision.normalize_reading(raw),
                "base_prompt_sha256": hashlib.sha256(vision.PROMPT.encode()).hexdigest(),
                "input_image_sha256": hashlib.sha256(base64.b64decode(prepared)).hexdigest(),
            }
            row = {"image_file": "fixture.jpg"}
            self.assertTrue(validate_request_artifact(cache, row, attempt))
            for field, value in (("input_image_sha256", "wrong"),
                                 ("raw_reading", {**raw, "grand_total": "999"}),
                                 ("reading", {**raw, "grand_total": "999"})):
                with self.subTest(field=field), self.assertRaises(RuntimeError):
                    validate_request_artifact(cache, row, {**attempt, field: value})

    def test_more_matches_cannot_hide_new_quantity_or_money_errors(self):
        first = {
            "visible_correct_fields": 900, "printed_correct_fields": 1000,
            "results": [{
                "id": f"fixture-{i}", "sha256": f"fixture-sha-{i}",
                "printed_score": {"checked": 12, "visible_checked": 10,
                                  "abstention_checked": 2, "exact": False,
                                  "mismatches": [{"field": "tax_total"}]},
            } for i in range(100)],
        }
        candidate = copy.deepcopy(first)
        candidate["visible_correct_fields"] += 1
        candidate["printed_correct_fields"] += 1
        candidate["results"][0]["printed_score"]["mismatches"] = [{"field": "items.0.quantity"}]
        adopt, regressions, _ = choose_candidate(first, candidate)
        self.assertFalse(adopt)
        self.assertEqual(regressions[0]["field"], "items.0.quantity")
        candidate["results"][0]["printed_score"]["mismatches"] = []
        self.assertTrue(choose_candidate(first, candidate)[0])

    def test_any_reader_change_rejects_the_frozen_protocol(self):
        expected = protocol_signature("fixture-model-digest")
        lock = {"frozen_at": "fixture-before-inference", "signature": copy.deepcopy(expected)}
        validate_protocol_lock(lock, expected)
        for field in ("model_digest", "prompt_sha256", "schema_sha256", "reader_source_sha256",
                      "image_helper_sha256", "model_options", "image_edge", "scoring_sha256"):
            changed = copy.deepcopy(lock)
            changed["signature"][field] = "changed"
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                validate_protocol_lock(changed, expected)

    def test_incomplete_validation_cannot_be_published(self):
        with tempfile.TemporaryDirectory(prefix="qwen-validation-test-") as directory:
            cache = Path(directory)
            (cache / "manifest.json").write_text(json.dumps({"documents": [
                {"file_name": f"fixture-{i}.png", "image_file": f"fixture-{i}.jpg",
                 "sha256": f"fixture-{i}"} for i in range(100)
            ]}))
            with self.assertRaisesRegex(RuntimeError, "all 100 attempts"):
                collect(cache)
