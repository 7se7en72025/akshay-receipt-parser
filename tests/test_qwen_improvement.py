"""Paired reporting must preserve regressions and reject mismatched inputs."""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from benchmark_vision import cool_gpu, require_memory, unload_model  # noqa: E402
from report_qwen_improvement import paired_changes  # noqa: E402


def fixture():
    return {"results": [{
        "id": f"bill-{index}", "sha256": f"sha-{index}",
        "printed_score": {"checked": 12, "visible_checked": 10,
                          "abstention_checked": 2, "exact": False,
                          "mismatches": [{"field": "tax_total"}]},
    } for index in range(100)]}


class PairedQwenTests(unittest.TestCase):
    def test_hot_gpu_is_unloaded_and_cooled_before_another_request(self):
        with (
            patch("benchmark_vision.gpu_temperature", side_effect=[89, 85, 82]),
            patch("benchmark_vision.unload_model") as unload,
            patch("benchmark_vision.time.sleep") as sleep,
        ):
            cool_gpu("test-model", "http://localhost")
        unload.assert_called_once_with("test-model", "http://localhost")
        self.assertEqual(sleep.call_count, 2)

    def test_batch_cleanup_only_requests_model_unloading(self):
        response = httpx.Response(
            200, json={"done_reason": "unload"},
            request=httpx.Request("POST", "http://localhost/api/generate"),
        )
        with patch.object(httpx.Client, "post", return_value=response) as post:
            unload_model("test-model", "http://localhost")
        self.assertEqual(post.call_args.args, ("http://localhost/api/generate",))
        self.assertEqual(post.call_args.kwargs["json"], {"model": "test-model", "keep_alive": 0})

    def test_memory_guard_leaves_headroom_before_loading_and_between_bills(self):
        for available, loaded in ((0.5, True), (3.58, False)):
            with self.assertRaisesRegex(RuntimeError, "not a model failure"):
                require_memory(available, loaded)
        require_memory(1.6, True)
        require_memory(4.6, False)
        require_memory(None, False)

    def test_qwen_cold_start_can_use_available_gpu_memory(self):
        model = "qwen3-vl:2b-instruct-q4_K_M"
        require_memory(2.6, False, gpu_free=3.1, model=model)
        for available, gpu_free, selected in (
            (2.4, 3.1, model), (2.6, 2.9, model),
            (2.6, None, model), (2.6, 3.1, "granite3.2-vision:2b"),
        ):
            with self.assertRaises(RuntimeError):
                require_memory(available, False, gpu_free=gpu_free, model=selected)

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
