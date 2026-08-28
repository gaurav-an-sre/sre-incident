"""Prompt loading with narrow token substitution."""

from __future__ import annotations

from pathlib import Path

from .config import PROMPTS_DIR

TOKENS = (
    "preamble",
    "bundle_dir",
    "reports",
    "decision",
    "error",
    "failures",
    "accepted",
    "eligible",
    "alert",
    "timeline",
    "hypotheses",
    "remediation",
    "verification",
    "parent_page_id",
    "incident_id",
)


def load_prompt(name: str, prompts_dir: Path | None = None) -> str:
    directory = prompts_dir or PROMPTS_DIR
    return (directory / name).read_text(encoding="utf-8")


def render_prompt(
    name: str,
    values: dict[str, str],
    prompts_dir: Path | None = None,
) -> str:
    rendered = load_prompt(name, prompts_dir)
    for token in TOKENS:
        rendered = rendered.replace("{" + token + "}", values.get(token, "{" + token + "}"))
    return rendered
