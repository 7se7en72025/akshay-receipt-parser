# Qwen: development and 100 new validation bills

Generated: 2026-10-18T00:56:45.347972+00:00

200 distinct bill images from one synthetic dataset; the development 100 were evaluated with the initial and candidate readers.
The second 100 were selected before tuning and evaluated with the frozen selected reader.

Checks cover supplier, bill number/date, currency, net/tax/payable totals, row count and
item descriptions, quantities, unit rates and amounts. Addresses, bank details and GST splits are not scored.

| Run | Expected printed fields correct | Entire printed contract exact | Correct absent-field abstentions | Failures |
| --- | --- | --- | --- | --- |
| Development: first attempt (v4) | 2207/2271 (97.18%) | 52/100 | 168/193 | 0 |
| Development: candidate (v5) | 2188/2271 (96.35%) | 50/100 | 165/193 | 0 |
| 100 new bills: selected vision-read-v4 | 2104/2157 (97.54%) | 53/100 | 91/115 | 0 |

Development changes: 28 previously wrong fields fixed; 50 previously correct fields regressed.
Candidate adopted: **No**. Selected reader: `vision-read-v4`.
The gate rejects a candidate introducing any new quantity, rate, amount or total mistakes.
No decimal tolerance, row-order relaxation or reference metadata edits were used.
The pinned templates print money with %.2f. One new-set metadata rate has hidden precision;
printed scoring uses its displayed value while full-label scoring retains the original metadata.
Display-precision formatting alone leaves the first 100 scores unchanged. The separate C$/A$ audit
corrects currency visibility and regrades all compared runs uniformly; earlier headline scores are superseded.
See [currency scoring audit](currency-scoring-audit.json), [precision audit](visible-precision-audit.json)
and [pilot experiments](qwen-pilot-experiments.json).

## Remaining mismatches on the new 100

| Field | Mismatches |
| --- | --- |
| amount | 1 |
| bill_date | 8 |
| bill_number | 8 |
| currency | 25 |
| description | 17 |
| supplier_name | 1 |
| tax_total | 5 |
| taxable_total | 6 |
| unit_price | 6 |

These include misreads, unsupported guesses and deliberate abstention for ambiguous dates.
An amount mismatch remains; matching totals or a valid response do not establish correct transcription.

## Limits

- Development images were used to find defects; their rerun is not held-out accuracy.
- Validation inputs and protocol were frozen before their first inference.
- Both sets share a synthetic source and template families, not independent layout coverage.
- Clean images are not representative of arbitrary phone photos, languages or Indian GST layouts.
- Template visibility rules exclude intentionally absent fields, but do not certify every glyph is visible; some source images clip edge text.
- No reference labels, draft or OCR answers are model inputs. No balancing or source-metadata edits.
- Ambiguous printed dates remain unresolved; correct abstention can still differ from hidden metadata.
- Failures remain in denominators. Exact bill agreement is stricter than visible-field accuracy.
- Model unloading and varying system load make timing an uncontrolled performance comparison.
- Human review remains required. Model agreement is not proof of correctness.

## Evidence

[Full results](qwen-two-set-results.json) preserve every per-bill mismatch, raw reading, source hash,
model digest, frozen schema/prompt/image protocol and the real API smoke check.
Prepared-input hashes and raw-to-normalized reconstruction were verified for 100/100 new responses.
The real API check preserved the source and draft and rejected invalid/stale suggestion application.
Source: [Alamgir Qazi's InvoiceOCR-Synth](https://huggingface.co/datasets/alamgirqazi/invoice-ocr-synthetic), CC BY 4.0,
revision `673ff85be462eb7f3715ec188a295dd17ca11115`. The validation set skips the first 100 distinct clean documents.
The reference visibility rules were audited on the development templates before validation inference.
