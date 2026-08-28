"""Evidence citation validation and verdict enforcement."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_WHITESPACE = re.compile(r"\s+")
MIN_EXCERPT_LENGTH = 12


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _allowed_path(path_value: str, repo_root: Path, incident_id: str) -> tuple[str, Path | None]:
    candidate = (repo_root / path_value).resolve()
    bundle_root = (repo_root / "incidents" / incident_id).resolve()
    allowed_roots = [bundle_root] + [
        (repo_root / name).resolve()
        for name in ("checkout_svc", "payments", "config", "tools")
    ]
    if not any(_inside(candidate, root) for root in allowed_roots):
        return "disallowed_path", None
    return "ok", candidate


def validate_report(report: dict[str, Any], repo_root: Path, incident_id: str) -> dict[str, Any]:
    evidence = report.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
        report["evidence"] = evidence
    valid_count = 0
    bundle_valid = 0
    failures: list[str] = []
    bundle_root = (repo_root / "incidents" / incident_id).resolve()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            item = {"file": "", "excerpt": "", "why": ""}
            evidence[index] = item
        excerpt = str(item.get("excerpt", ""))
        path_value = str(item.get("file", ""))
        classification, path = _allowed_path(path_value, repo_root, incident_id)
        if len(excerpt) < MIN_EXCERPT_LENGTH:
            classification = "too_short"
        elif classification == "ok":
            if path is None or not path.is_file():
                classification = "not_found"
            else:
                content = path.read_text(encoding="utf-8")
                if excerpt not in content and _normalise(excerpt) not in _normalise(content):
                    classification = "not_found"
                else:
                    classification = "valid"
        item["validation"] = classification
        if classification == "valid":
            valid_count += 1
            if path is not None and _inside(path, bundle_root):
                bundle_valid += 1
        else:
            failures.append(f"{path_value}: {classification}")
    verdict = report.get("verdict")
    downgraded = verdict in {"supported", "rejected"} and (valid_count < 2 or bundle_valid < 1)
    if downgraded:
        report["verdict"] = "inconclusive"
    report["validation"] = {
        "valid_citations": valid_count,
        "bundle_citations": bundle_valid,
        "downgraded": downgraded,
        "reason": (
            "verdict requires at least two valid citations including one bundle citation"
            if downgraded
            else None
        ),
        "failures": failures,
    }
    return report


def citation_failures(report: dict[str, Any]) -> str:
    validation = report.get("validation", {})
    return json.dumps(
        {
            "failures": validation.get("failures", []),
            "valid_citations": validation.get("valid_citations", 0),
            "bundle_citations": validation.get("bundle_citations", 0),
        },
        indent=2,
        sort_keys=True,
    )
