"""Apply and verify the deliberately plausible rejected fix in a scratch copy."""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .engine import run_verification


def main() -> None:
    root = Path.cwd()
    output = root / "out" / "verification-wrong-fix.json"
    with tempfile.TemporaryDirectory(prefix="sre-wrong-fix-") as directory:
        candidate = Path(directory) / "candidate"
        candidate.mkdir()
        archive = subprocess.run(
            ["git", "archive", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            bundle.extractall(candidate)
        subprocess.run(
            ["git", "apply", str(root / "fixtures" / "wrong_fix.patch")],
            cwd=candidate,
            check=True,
        )
        result = run_verification(
            str(candidate),
            repo_root=root,
            output_path=output,
            agent_claim="The remediation fixed the checkout and verification is successful.",
        )
    print(
        f"candidate=wrong-fix verified={result['verified']} "
        f"failed_signals={result['failed_signals']}"
    )


if __name__ == "__main__":
    main()
