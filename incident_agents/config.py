"""Static configuration for the incident investigation fleet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_URL = "https://github.com/gaurav-an-sre/sre-incident"
MODEL = "composer-2.5"
DEMO_TAG = "sre-incident"
DEFAULT_STARTING_REF = "main"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@dataclass(frozen=True)
class HypothesisRole:
    prompt_file: str
    hypothesis_id: str


HYPOTHESIS_ROLES = {
    "H-CHANGE": HypothesisRole("hypothesis_change.md", "H-CHANGE"),
    "H-DEPENDENCY": HypothesisRole("hypothesis_dependency.md", "H-DEPENDENCY"),
    "H-CAPACITY": HypothesisRole("hypothesis_capacity.md", "H-CAPACITY"),
}
