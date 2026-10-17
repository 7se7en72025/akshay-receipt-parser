"""Download 100 new, distinct, externally authored bills; never feed labels to AI.

InvoiceOCR-Synth by Alamgir Qazi, CC BY 4.0. See the pinned source below.
Only clean images are selected, in dataset order, before evaluating any model.
"""

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

DATASET = "alamgirqazi/invoice-ocr-synthetic"
REVISION = "673ff85be462eb7f3715ec188a295dd17ca11115"
SOURCE = f"https://huggingface.co/datasets/{DATASET}"
CACHE = (
    Path(os.environ.get("AKSHAY_AI_HOME", "D:/KyvernoBuild/akshay-local-ai")) / "benchmark-new100"
)
ROOT = Path(__file__).resolve().parent.parent


def fetch(url, **kwargs):
    with httpx.Client(follow_redirects=True, trust_env=False, timeout=120) as client:
        response = client.get(url, **kwargs)
        response.raise_for_status()
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", type=int, default=0,
                        help="Skip this many distinct clean documents before selecting 100.")
    parser.add_argument("--output-dir", type=Path, default=CACHE)
    args = parser.parse_args()
    if args.skip < 0:
        parser.error("--skip must be non-negative")
    cache = args.output_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    manifest = cache / "manifest.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if saved["revision"] != REVISION:
            raise ValueError("Unexpected benchmark revision.")
        if saved.get("selection_skip", 0) != args.skip or len(saved["documents"]) != 100:
            raise ValueError("Existing manifest uses a different selection; choose a new output directory.")
        for row in saved["documents"]:
            if (
                hashlib.sha256((cache / row["image_file"]).read_bytes()).hexdigest()
                != row["sha256"]
            ):
                raise ValueError("Cached source checksum mismatch.")
        print("100 cached source images verified.", flush=True)
        return
    metadata = fetch(f"https://huggingface.co/api/datasets/{DATASET}").json()
    if metadata["sha"] != REVISION or metadata["cardData"]["license"] != "cc-by-4.0":
        raise ValueError("Dataset changed; review its revision and license before downloading.")
    selected, seen = [], set()
    for offset in range(0, 2814, 100):
        page = fetch(
            "https://datasets-server.huggingface.co/rows",
            params={
                "dataset": DATASET,
                "config": "default",
                "split": "train",
                "offset": offset,
                "length": 100,
            },
        ).json()
        for entry in page["rows"]:
            row = entry["row"]
            if row["quality"] != "clean" or row["file_name"] in seen:
                continue
            if f"/{REVISION}/" not in row["image"]["src"]:
                raise ValueError("Image URL does not match the pinned revision.")
            seen.add(row["file_name"])
            if len(seen) <= args.skip:
                continue
            selected.append({**row, "dataset_row": entry["row_idx"]})
            if len(selected) == 100:
                break
        if len(selected) == 100:
            break
    if len(selected) != 100:
        raise ValueError("Expected 100 unique base documents.")

    def download(row):
        image = row.pop("image")
        content = fetch(image["src"]).content
        name = Path(row["file_name"]).stem + ".jpg"
        (cache / name).write_bytes(content)
        return {**row, "image_file": name, "sha256": hashlib.sha256(content).hexdigest()}

    with ThreadPoolExecutor(max_workers=6) as pool:
        documents = list(pool.map(download, selected))
    hashes = {row["sha256"] for row in documents}
    old_manifest = ROOT / "data/benchmark/manifest.json"
    if old_manifest.exists():
        old = json.loads(old_manifest.read_text(encoding="utf-8"))
        if hashes & {row["sha256"] for row in old["documents"]}:
            raise ValueError("New set overlaps the previous 100 bills.")
    if len(hashes) != 100:
        raise ValueError("Duplicate images in new set.")
    development_manifest = CACHE / "manifest.json"
    if args.skip and development_manifest.exists():
        development = json.loads(development_manifest.read_text(encoding="utf-8"))["documents"]
        if hashes & {row["sha256"] for row in development} or (
            {row["file_name"] for row in documents} & {row["file_name"] for row in development}
        ):
            raise ValueError("Validation set overlaps the development set.")
    manifest.write_text(
        json.dumps(
            {
                "source": SOURCE,
                "revision": REVISION,
                "license": "CC-BY-4.0",
                "selection": f"100 distinct clean base documents in dataset order after skipping {args.skip} distinct clean documents.",
                "selection_skip": args.skip,
                "documents": documents,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Downloaded 100 unique new bills to {cache}.", flush=True)


if __name__ == "__main__":
    main()
