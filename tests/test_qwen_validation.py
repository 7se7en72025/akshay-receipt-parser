import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from report_qwen_validation import (  # noqa: E402
    choose_candidate,
    collect,
    protocol_signature,
    validate_protocol_lock,
)


class FrozenValidationTests(unittest.TestCase):
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
