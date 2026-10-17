import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from report_qwen_validation import collect, protocol_signature, validate_protocol_lock  # noqa: E402


class FrozenValidationTests(unittest.TestCase):
    def test_any_reader_change_rejects_the_frozen_protocol(self):
        expected = protocol_signature("fixture-model-digest")
        lock = {"frozen_at": "fixture-before-inference", "signature": copy.deepcopy(expected)}
        validate_protocol_lock(lock, expected)
        for field in ("model_digest", "prompt_sha256", "schema_sha256", "reader_source_sha256",
                      "image_helper_sha256", "model_options", "image_edge"):
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
