# Qwen v4 trial: incomplete

19 of the requested 100 bills were read before the run stopped for low available
system RAM. The Android emulator remains open at the user's request. Qwen was
unloaded to release memory. The benchmark now checks memory before each new
request and saves a partial summary when it cannot safely continue.

| Same 19 bills | Visible values correct | Entire printed contract exact |
| --- | --- | --- |
| Previous v3 | 399/407 | 6/19 |
| Candidate v4 | 401/407 | 7/19 |

Including absent-field checks, 25 previously wrong fields were fixed and no
previously correct fields regressed in these 19 bills. There were no failed
responses. Missing-field abstentions improved; currency guesses and some
description, supplier, tax, unit-price and ambiguous-date mismatches remain.

These results **do not establish accuracy over all 100 bills**. Sources, reference
answers and strict scoring were unchanged. This is the same synthetic debugging
set, not a held-out evaluation. Driver 617.42 was active, but the prompt also
changed, so this does not measure driver speed improvement.

[Partial evidence](qwen-v4-partial-results.json) preserves per-bill scores,
mismatches, source hashes, model digests and the protocol. The historical
[complete two-model evaluation](200-bill-vision-comparison.md) is retained.

Resume when sufficient RAM is available:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_vision.py --model qwen3-vl:2b-instruct-q4_K_M --limit 100 --pause-seconds 10
```

The same command reuses completed readings. A cold model requires 4.5 GB
available RAM; between requests, the loaded model requires 1.5 GB headroom.
These are conservative local benchmark limits, not universal model requirements.
The complete report publisher refuses partial runs; after 100 attempts, run the
real API smoke check before publishing the Qwen comparison.
