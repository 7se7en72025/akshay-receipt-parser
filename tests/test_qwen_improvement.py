"""Paired reporting must preserve regressions and reject mismatched inputs."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from benchmark_vision import require_memory  # noqa: E402
from report_qwen_improvement import paired_changes  # noqa: E402


def fixture():
    return {"results": [{
        "id": f"bill-{index}", "sha256": f"sha-{index}",
        "printed_score": {"checked": 12, "visible_checked": 10,
                          "abstention_checked": 2, "exact": False,
                          "mismatches": [{"field": "tax_total"}]},
    } for index in range(100)]}


class PairedQwenTests(unittest.TestCase):
    def test_memory_guard_leaves_headroom_before_loading_and_between_bills(self):
        for available, loaded in ((0.5, True), (3.58, False)):
            with self.assertRaisesRegex(RuntimeError, "not a model failure"):
                require_memory(available, loaded)
        require_memory(1.6, True)
        require_memory(4.6, False)
        require_memory(None, False)

    def test_fixed_and_regressed_fields_are_both_reported(self):
        before = fixture()
        after = copy.deepcopy(before)
        after["results"][0]["printed_score"]["mismatches"] = [{"field": "currency"}]
        change = paired_changes(before, after)[0]
        self.assertEqual(change["fixed_fields"], ["tax_total"])
        self.assertEqual(change["regressed_fields"], ["currency"])
        self.assertEqual(before, fixture())

    def test_incomplete_duplicate_or_changed_inputs_are_rejected(self):
        for kind in ("incomplete", "duplicate", "hash", "scoring"):
            with self.subTest(kind=kind):
                before = fixture()
                after = copy.deepcopy(before)
                if kind == "incomplete":
                    after["results"].pop()
                elif kind == "duplicate":
                    after["results"][0]["id"] = after["results"][1]["id"]
                elif kind == "hash":
                    after["results"][0]["sha256"] = "changed"
                else:
                    after["results"][0]["printed_score"]["checked"] = 11
                with self.assertRaises(RuntimeError):
                    paired_changes(before, after)
