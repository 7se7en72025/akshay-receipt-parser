# 200-bill regression and local vision comparison

> Historical scoring snapshot: the old C$/A$ visibility mask was incorrect. See [the scoring audit](currency-scoring-audit.json) for uniformly regraded results; original scores below are retained for traceability.

Generated: 2026-10-17T19:25:40.038535+00:00

## What was evaluated

The original 100 bills remain a regression set. Another 100 distinct bills from
[Alamgir Qazi's InvoiceOCR-Synth](https://huggingface.co/datasets/alamgirqazi/invoice-ocr-synthetic) were added, pinned to
`673ff85be462eb7f3715ec188a295dd17ca11115` under CC BY 4.0. Selection was the first 100 distinct
base documents in dataset order with `quality=clean`, before model evaluation.
Image checksums are recorded; none overlap the original manifest.

The new set has 416 line items across six templates:
event_ticket: 17, freelancer_invoice: 11, formal_corporate: 15, modern_minimal: 16, utility_bill: 19, pos_thermal: 22.
Reference currencies: USD: 15, GBP: 31, CAD: 5, EUR: 44, AUD: 5.
It contains foreign currency documents; the INR workspace does not approve them.

Both installed models attempted the same 100 original images. No OCR text,
draft, filename or reference answer was sent to either model. Readings are cached
with the source SHA-256, exact installed model digest and prompt version.

## New 100-bill results

| Reader | Visible values correct | Entire printed-field contract exact | Failed responses | Median per bill |
| --- | --- | --- | --- | --- |
| ocr-baseline | 1775/2262 (78.5%) | 25/100 | 0 | 2.88 s |
| qwen3-vl:2b-instruct-q4_K_M | 2196/2262 (97.1%) | 38/100 | 0 | 15.13 s |
| granite3.2-vision:2b | 924/2262 (40.8%) | 0/100 | 16 | 86.09 s |

Visible-value accuracy excludes reference fields which the template does not
print. The whole-bill contract includes header values, row count, every item
description/quantity/rate/amount in source order, and correct abstention when a
field is not printed. It is deliberately stricter than adding totals. A failed
response scores zero correct fields. Known currency prefixes, suffixes and
number separators are parsed using the application's numeric reader; raw model
strings are preserved. Exact decimals are compared without
balancing, rounding tolerances or changing reference answers.

Full-label agreement is also retained in the JSON report. It is not the primary
accuracy measure because some metadata, including event-ticket subtotals and
unit rates, is absent from the rendered image. A model must not guess it.
Date mismatches include deliberate abstention for ambiguous numerical dates;
the raw model date reading remains available in the read-only page reading for review.

## Original regression and workflow integrity

- Original extractor: 99/100 exact, plus the
  existing explicitly flagged one-cent printed FX discrepancy. The source
  entries are retained; that discrepancy is not counted as exact.
- Original real API workflow: 100/100 stored drafts match
  their extraction snapshots and 100/100 source hashes
  match. Foreign-currency approvals, relabelling and unapproved exports are blocked.
- Real PDF upload → extraction → vision subprocess → report: completed. The
  source and draft were unchanged; invalid selections and stale report application
  were rejected. This checks integration, not the correctness of model readings.

## Fixes made during evaluation

- Copy the printed date as text, then normalize it in code only when its order
  is unambiguous. Schema-constrained ISO conversion had corrupted date digits.
- Normalize correctly read money such as `$60.00` into a decimal value instead
  of rejecting it solely because the model retained a currency symbol. Never
  calculate a new amount or reinterpret percentages as money.
- Keep a separate printed unit rate and line amount. Handle explicit thermal
  receipt `@ rate each` continuation lines without adding them to item names.
- Keep `Qty / Value` as one heading and `Unit Price` / `Value` as separate columns.
- Read printed quantity-times-description rows in order summaries and Hours/Rate
  tables. Missing rates stay blank; a separate invoice heading cannot swallow
  the neighboring supplier name as an invoice number.
- Read explicit C$/A$/CAD/AUD amount prefixes without converting their values,
  and avoid counting a tax summary again when GST components are already printed.
- Retain the known source currency when a payable line only has a dollar sign;
  ambiguous dollars never become INR by default.
- Bound image resolution, context and evaluation batches after Windows memory
  pressure during an earlier larger run. Run OCR and model benchmarks sequentially.
- Close rendered PDF page resources explicitly; test the real subprocess path.

## Protocol and limits

Hardware: 16 GB RAM, NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM, NVIDIA driver
566.07 during evaluation. Official portable Ollama v0.40.5. Models are local
Apache-2.0 releases; one model is loaded at a time.
Final prompt: `vision-read-v3`; image longest edge 1280px;
shared generation options: `{"num_batch": 128, "num_ctx": 4096, "num_predict": 2048, "seed": 0, "temperature": 0}`.
Granite uses a 12288-token context because its image encoder needs about 8k input
tokens for these A4 pages; Qwen uses 4096. Both get the same image, prompt and
2048-token output limit. Exact per-model options are recorded in the JSON report.
Reported latency excludes downloads and idle pauses. Low GPU clocks and
temperatures around 87-88 degrees C were observed, but sampled NVIDIA status did
not flag thermal slowdown; heat alone is not a confirmed explanation. Ollama also
reported partial CPU offloading for Granite (1.41 GB of a 2.52 GB loaded model on
GPU in one snapshot). Later requests used idle pauses. These timings are
indicative observations, not a controlled hardware speed comparison.

The new set was used for debugging. These results are a regression/evaluation
measure, not unseen production accuracy. Blurry photos, handwriting, unusual
languages, other layouts and multi-page bills need separate evaluation. Small
models can still read the same wrong value as OCR or invent absent fields.

Source-visibility rules were audited against the six generator templates at
[revision 91082ede48d2c0b2e32d9c489ea35f34e9922a99](https://github.com/alamgirqazi/synthetic-invoice-gen/tree/91082ede48d2c0b2e32d9c489ea35f34e9922a99/templates)
and sample images before the final comparison. Row descriptions are compared
with normalized whitespace and case, not fuzzy matching. A rendered truncation
in the thermal template is reflected in its printed-field reference.

Verification remains optional human review. Matching fields do not prove the
bill is correct. Currency, aggregate tax, ambiguous rows and conflicting pages
are read-only comparisons; applying a selected suggestion creates an audited,
unapproved draft guarded by its saved version.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\setup_local_vision.py
.\.venv\Scripts\python.exe scripts\prepare_vision_benchmark.py
.\.venv\Scripts\python.exe scripts\benchmark_vision.py --baseline --refresh
.\.venv\Scripts\python.exe scripts\benchmark_vision.py
.\.venv\Scripts\python.exe scripts\benchmark_invoices.py --label final-currency --strict
.\.venv\Scripts\python.exe scripts\benchmark_api.py
.\.venv\Scripts\python.exe scripts\smoke_vision_api.py
.\.venv\Scripts\python.exe scripts\report_vision_benchmark.py
```

Run these commands sequentially. Cached model runs resume without repeating
completed requests. `--retry-errors` retries failed responses; `--refresh` reruns
all selected inputs while retaining prior local attempts. Model installation
and initial dataset preparation require internet. Inference is loopback-only.
Downloads, original images, runtime files and caches stay outside Git.

See [the machine-readable per-bill results](200-bill-vision-results.json) for every
source checksum, mismatch and failure, and [the review workflow](../local-vision.md).
