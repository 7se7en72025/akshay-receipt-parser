"""Create a consistent private workspace archive without stopping the local app."""

import argparse
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from . import database as store
from .config import DATA


def create_backup(destination: Path):
    destination = destination.expanduser().resolve()
    if destination == DATA or DATA in destination.parents:
        raise ValueError("Save the backup outside the workspace data directory.")
    if destination.suffix.lower() != ".zip":
        raise ValueError("Choose a destination ending in .zip.")
    if not destination.parent.is_dir():
        raise ValueError("The destination folder does not exist.")
    database = DATA / "workspace.sqlite3"
    if not database.is_file():
        raise ValueError("Start the workspace once before creating a backup.")
    with tempfile.TemporaryDirectory(prefix="akshay-backup-") as temporary:
        snapshot = Path(temporary) / "workspace.sqlite3"
        with (
            closing(sqlite3.connect(database)) as source,
            closing(sqlite3.connect(snapshot)) as target,
        ):
            source.backup(target)
        references = []
        with closing(sqlite3.connect(snapshot)) as db:
            for table, folder in (
                ("documents", "uploads"),
                ("templates", "templates"),
                ("exports", "exports"),
            ):
                references.extend(
                    (folder, row[0]) for row in db.execute(f"SELECT storage_name FROM {table}")
                )
        # Original and exported files are immutable. Copy only files referenced
        # by the database snapshot, excluding later uploads and unfinished writes.
        for folder, filename in references:
            if Path(filename).name != filename or not (DATA / folder / filename).is_file():
                raise ValueError("A referenced workspace file is missing. Backup was not created.")
        try:
            # Exclusive creation never overwrites an existing backup.
            with destination.open("xb") as output:
                try:
                    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                        archive.write(snapshot, "data/workspace.sqlite3")
                        for folder, filename in references:
                            archive.write(DATA / folder / filename, f"data/{folder}/{filename}")
                        archive.writestr(
                            "manifest.json",
                            json.dumps(
                                {
                                    "application": "akshay-receipt-parser",
                                    "format_version": 1,
                                    "created_at": store.now(),
                                    "files": len(references),
                                    "restore": "Stop the app. Extract into a new empty folder. Set AKSHAY_DATA_DIR to its data folder, then restart. Retain your current data until the restored workspace is reviewed.",
                                },
                                indent=2,
                            ),
                        )
                except BaseException:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise
        except FileExistsError as error:
            raise ValueError("That backup already exists. Choose a new filename.") from error
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New .zip file outside the data directory")
    args = parser.parse_args()
    try:
        print(f"Backup created: {create_backup(args.destination)}")
        print("This archive contains private invoices. Store it securely.")
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Backup failed: {error}\n")


if __name__ == "__main__":
    main()
