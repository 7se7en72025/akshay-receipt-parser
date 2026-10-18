import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from freeze_qwen_validation import freeze  # noqa: E402


class ValidationFreezeTests(unittest.TestCase):
    def test_existing_protocol_is_never_replaced(self):
        with tempfile.TemporaryDirectory(prefix="qwen-freeze-test-") as directory:
            path = Path(directory) / "lock.json"
            first = freeze(path, {"prompt": "fixture"}, "fixture-selection", False, "fixture-runtime")
            original = path.read_bytes()
            self.assertEqual(freeze(path, {"prompt": "fixture"}, "fixture-selection", True, "fixture-runtime"), first)
            with self.assertRaises(RuntimeError):
                freeze(path, {"prompt": "changed"}, "fixture-selection", True, "fixture-runtime")
            self.assertEqual(path.read_bytes(), original)

    def test_cannot_retroactively_freeze_seen_validation_inputs(self):
        with tempfile.TemporaryDirectory(prefix="qwen-freeze-test-") as directory:
            path = Path(directory) / "lock.json"
            with self.assertRaisesRegex(RuntimeError, "already exist"):
                freeze(path, {"prompt": "fixture"}, "fixture-selection", True, "fixture-runtime")
            self.assertFalse(path.exists())
