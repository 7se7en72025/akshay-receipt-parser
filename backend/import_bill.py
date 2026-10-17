"""Import real bills through the running local API, without committing source files."""

import argparse
from contextlib import ExitStack
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    with ExitStack() as stack:
        uploads = [
            ("files", (path.name, stack.enter_context(path.open("rb")), "application/octet-stream"))
            for path in args.files
        ]
        with httpx.Client(trust_env=False, timeout=60) as client:
            response = client.post("http://127.0.0.1:8001/api/documents", files=uploads)
            response.raise_for_status()
        print(response.text)


if __name__ == "__main__":
    main()
