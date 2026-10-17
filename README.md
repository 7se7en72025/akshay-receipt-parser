# Akshay invoice workspace

Local-first supplier invoice extraction, staff review and Excel export.

## Scope

PDF/JPG/PNG upload → text extraction or local OCR → column mapping → validation → editable review → approval → Excel export. Optional local Ollama assistance can propose structured data for unfamiliar layouts. Financial approval always remains a human action.

This repository is independent of SSMS. The first release is a single-operator local workspace; POS integration, stock updates, shared authentication and production hosting are later work.

## Development

Python 3.11+ and Bun/Node are required. Setup and feature instructions are added with their implementation commits. Uploaded bills, local databases, model files and generated workbooks are excluded from Git.

## Data

The supplied Akshay purchase bill informs the first parser profile. It is not committed. Other layouts can require corrected mappings or manual review; extraction is not guaranteed to be perfect.
