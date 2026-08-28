"""Command-line entry point for candidate verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import run_verification


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m verify")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--json", type=Path, default=Path("out/verification.json"))
    parser.add_argument("--incident")
    args = parser.parse_args()
    result = run_verification(
        args.candidate,
        repo_root=Path.cwd(),
        output_path=args.json,
        incident_id=args.incident,
    )
    print(
        f"candidate={result['candidate']} verified={result['verified']} "
        f"failed_signals={result['failed_signals']}"
    )


if __name__ == "__main__":
    main()
