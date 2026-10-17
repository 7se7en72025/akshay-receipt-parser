# 100-bill evaluation

Date: 17 October 2026. This is a development regression corpus, not an unseen accuracy benchmark or a promise of perfect extraction.

## Source and reproducibility

Data attribution: Drew IPP, [invoice-extraction-benchmark](https://huggingface.co/datasets/drew-ipp/invoice-extraction-benchmark), revision `446bab08662790cb39457792243bff5704373b95`, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Reference labels are authored by the dataset publisher, independently of this parser. No publisher extraction code is used.

The deterministic selection includes all 99 text-PDF documents labelled `invoice`, plus the first scan-category image in document-ID order. These are 100 distinct synthetic bills, with SHA-256 verification, across 955 labelled line items. Credit notes, statements and multiple-invoice documents are excluded. This is mostly digital-document coverage with only one scan; it does not establish reliable performance on phone photos, handwriting or every language. Source files and cached labels are excluded from Git.

Run from the repository root:

~~~powershell
.\.venv\Scripts\python.exe scripts\benchmark_invoices.py --download --label final-currency --strict
.\.venv\Scripts\python.exe scripts\benchmark_api.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

The application does not read reference labels. Only the separate evaluation script reads them. The reference outputs were not changed to make failures pass.

## Results

| Check | Result |
| --- | --- |
| Public bills downloaded and verified | 100/100 |
| Final bills matching every assessed field | 99/100 |
| Source rounding discrepancy retained and flagged | 1/100 |
| Unexpected extraction mismatches | 0 |
| Real upload/worker pipeline completed | 100/100 |
| Saved drafts identical to direct extractor output | 100/100 |
| Downloaded originals retain source checksum | 100/100 |
| Incorrect foreign-currency approvals rejected | 100/100 |
| Foreign source relabelling as INR rejected | 100/100 |
| Rejected requests preserve invoice entries and version | 100/100 |
| Unapproved bulk export rejected | Yes |
| Unit/API regression methods | 29 passed |
| Column-order combinations within regression tests | 120 passed |
| Original supplied Akshay bill regression | 8 items, quantity 223, total INR 56,334; no validation errors |

The initial parser matched zero bills on every assessed field. Corrections cover borderless tables, repeated multi-page headings, date formats, locale separators, tax labels and registration-number separation, VAT-inclusive totals, dual-currency columns, and preservation of valid fields when one field is invalid.

Assessed fields: supplier, bill number, invoice date, currency, taxable/net subtotal, tax aggregate, grand total, item count, every labelled item description and item amount. Whitespace and case are normalized for text. Financial values are compared at currency-cent precision. Explicit alternate item amounts provided by the publisher are accepted for dual-currency lines. Tax aggregate sums recorded components; absent components contribute zero only to that comparison and remain null in the actual draft. The corpus does not independently label every quantity, unit, rate, GSTIN or HSN, so those fields are not certified by this score. Separate column-order, number parsing and supplied-bill checks cover examples of those fields.

All 100 external bills are foreign-currency documents. Their rejection is intentional in this INR purchase workspace; it is not evidence that all 100 can be approved and exported. The successful INR save/approve/export/reopen/restore workflow is covered separately by the API regression suite.

## The remaining source discrepancy

Document: `currency-dual-eur-nad-2`.

- Printed original subtotal: EUR 162.48.
- Printed exchange rate: 1 EUR = 19.9871 NAD.
- Conversion rounded to cents: NAD 3,247.50.
- Printed payable box and publisher normalized reference subtotal: NAD 3,247.51.
- No separate local-currency subtotal or local-currency item amounts are printed.

The parser preserves the original EUR item entries and the NAD payable total. It records the computed conversion and flags the one-cent discrepancy. It does not change correct product entries or fabricate a balancing amount. `--strict` accepts only this named, exact discrepancy and requires its exchange-rate warning; the score remains 99 exact bills, not 100. Any additional mismatch fails the run.

## Preventing incorrect corrections

Validation is read-only: it identifies inconsistent fields without changing entries. Failed approval requests leave saved data and versions intact. Optional AI assistance can fill missing source-backed values; it cannot overwrite existing extracted fields, remove existing rows or change the source currency. Conflicts remain visible in extraction notes. A real local AI model was not configured for this evaluation; the merge behaviour was tested directly with conflicting and fabricated proposals.

The real API evaluation uses an isolated temporary workspace on loopback port 18091, and removes it afterwards. Test invoices are not added to the operator's actual workspace.

See [the per-document results](100-bill-results.json) for document identifiers, source hashes and mismatches. Full local reports remain in `data/benchmark/`.
