# Qwen: repeated 100-bill evaluation

> Historical scoring snapshot: the old C$/A$ visibility mask was incorrect. See [the scoring audit](currency-scoring-audit.json) for uniformly regraded results; original scores below are retained for traceability.

Generated: 2026-10-17T23:26:29.341389+00:00

Same model weights and original 100 images as the [historical comparison](200-bill-vision-comparison.md).
The prompt now distinguishes labelled aggregate totals, separate rates, customer names and missing placeholders.
The duplicated JSON schema was removed from the prose; the API still constrains the output schema.

| Run | Visible fields | Whole printed contract exact | Correct missing-field abstentions | Failures |
| --- | --- | --- | --- | --- |
| Before (v3) | 2196/2262 (97.08%) | 38/100 | 110/202 | 0 |
| After (v4) | 2205/2262 (97.48%) | 51/100 | 168/202 | 0 |

Field-level changes: 69 previously wrong fields fixed; 2 previously correct fields regressed.
No scoring tolerances, description matching or reference values were changed.

## Remaining mismatches

- bill_date: 5
- bill_number: 4
- currency: 20
- description: 39
- supplier_name: 2
- tax_total: 10
- taxable_total: 1
- unit_price: 10

## Evidence and limits

[Full results](qwen-improvement-results.json) include both scores, each changed field, all new raw readings,
source hashes, model digest, generation settings, prompt hash and the real API workflow check.
A failed response counts as a failure. Ambiguous dates and absent values require review rather than guessing.
These are clean synthetic debugging bills used during improvement, not a production or held-out accuracy estimate.
The GPU driver also changed between runs (566.07 to 617.42), so timing differences cannot be attributed to the prompt alone.
Human review is still required. Nothing is silently corrected, approved or exported.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_vision.py
.\.venv\Scripts\python.exe scripts/benchmark_vision.py --model qwen3-vl:2b-instruct-q4_K_M --limit 100 --pause-seconds 10
.\.venv\Scripts\python.exe scripts/smoke_vision_api.py
.\.venv\Scripts\python.exe scripts/report_qwen_improvement.py
```
