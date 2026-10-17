"""Selection fixtures are synthetic bytes, never model evaluation inputs."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import prepare_vision_benchmark as prepare  # noqa: E402


class VisionSelectionTests(unittest.TestCase):
    def test_second_set_skips_distinct_clean_documents_and_rejects_changed_selection(self):
        with tempfile.TemporaryDirectory(prefix="qwen-selection-test-") as directory:
            root = Path(directory)
            output = root / "validation"
            entries = [
                {"row_idx": index, "row": {
                    "quality": "clean", "file_name": f"fixture-{index}.png",
                    "image": {"src": f"https://fixture.invalid/{prepare.REVISION}/{index}.jpg"},
                }} for index in range(205)
            ]
            entries[3]["row"]["quality"] = "blurred"
            entries[8]["row"]["file_name"] = entries[7]["row"]["file_name"]

            def fetch(url, **kwargs):
                if "/api/datasets/" in url:
                    return SimpleNamespace(json=lambda: {
                        "sha": prepare.REVISION, "cardData": {"license": "cc-by-4.0"},
                    })
                if "datasets-server" in url:
                    offset = kwargs["params"]["offset"]
                    return SimpleNamespace(json=lambda: {"rows": entries[offset:offset + 100]})
                return SimpleNamespace(content=("fixture-only:" + url).encode())

            args = ["prepare", "--skip", "100", "--output-dir", str(output)]
            with (
                patch.object(sys, "argv", args), patch.object(prepare, "fetch", side_effect=fetch),
                patch.object(prepare, "ROOT", root), patch.object(prepare, "CACHE", root / "development"),
            ):
                prepare.main()
                saved = json.loads((output / "manifest.json").read_text())
                self.assertEqual(saved["selection_skip"], 100)
                self.assertEqual(len(saved["documents"]), 100)
                self.assertEqual(saved["documents"][0]["file_name"], "fixture-102.png")
                self.assertEqual(len({row["sha256"] for row in saved["documents"]}), 100)
                # A repeat verifies existing source bytes without downloading again.
                with patch.object(prepare, "fetch", side_effect=AssertionError("unexpected network")):
                    prepare.main()
                with patch.object(sys, "argv", ["prepare", "--output-dir", str(output)]):
                    with self.assertRaisesRegex(ValueError, "different selection"):
                        prepare.main()
