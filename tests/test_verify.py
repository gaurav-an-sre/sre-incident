import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from incident_agents.prompts import render_prompt
from incident_agents.publish import PublishOrchestrator
from incident_agents.remediate import RemediationOrchestrator
from incident_agents.sdk import CloudFleet
from verify.engine import run_verification
from verify.reference import reference_quote


def test_reference_pricer_hand_computed_values() -> None:
    root = Path(__file__).resolve().parents[1]
    healthy = root / "config" / "pricing.healthy.yaml"
    promo = root / "config" / "pricing.promo.yaml"
    cart = [
        {"unit_price_cents": 6800, "quantity": 1},
        {"unit_price_cents": 1800, "quantity": 1},
        {"unit_price_cents": 1400, "quantity": 1},
    ]
    assert reference_quote(cart, healthy) == {
        "subtotal_cents": 10000,
        "discount_cents": 0,
        "tax_cents": 800,
        "shipping_cents": 999,
        "total_cents": 11799,
    }
    assert reference_quote(cart, promo) == {
        "subtotal_cents": 10000,
        "discount_cents": 0,
        "tax_cents": 800,
        "shipping_cents": 0,
        "total_cents": 10800,
    }


def test_wrong_fix_only_fails_charged_amount_signal(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    candidate = tmp_path / "candidate"
    archive = subprocess.run(
        ["git", "archive", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    archive_path = tmp_path / "candidate.tar"
    archive_path.write_bytes(archive)
    candidate.mkdir()
    subprocess.run(["tar", "-xf", str(archive_path), "-C", str(candidate)], check=True)
    shutil.copy(root / "tools" / "shopper.py", candidate / "tools" / "shopper.py")
    shutil.copy(root / "fixtures" / "wrong_fix.patch", tmp_path / "wrong_fix.patch")
    subprocess.run(["git", "apply", str(tmp_path / "wrong_fix.patch")], cwd=candidate, check=True)
    result = run_verification(
        str(candidate),
        repo_root=root,
        output_path=tmp_path / "verification.json",
    )
    assert result["verified"] is False
    assert result["failed_signals"] == ["S2b", "S3", "S5"]
    assert {signal["id"] for signal in result["signals"] if signal["passed"]} >= {
        "S1",
        "S2a",
        "S4",
        "S6",
    }
    discrepancy = next(
        item
        for signal in result["signals"]
        if signal["id"] == "S3"
        for item in signal["measured"]["discrepancies"]
    )
    assert discrepancy["classification"] == "overcharge"
    assert discrepancy["authorized_amount_cents"] == discrepancy["quoted_amount_cents"] + 999


def test_remediation_dry_run_claim_is_persisted(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    incident = "inc-20260828T054250Z-696028f6"
    destination = tmp_path / "out" / incident
    destination.mkdir(parents=True)
    (destination / "investigation.json").write_text(
        json.dumps(
            {
                "reports": {
                    "H-CHANGE": {
                        "hypothesis_id": "H-CHANGE",
                        "evidence": [],
                    }
                },
                "adjudication": {
                    "decision": {
                        "accepted_hypothesis": "H-CHANGE",
                        "root_cause": "duplicated shipping arithmetic",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = RemediationOrchestrator(
        tmp_path,
        incident,
        dry_run=True,
        fresh=True,
        replies_dir=root / "tests" / "fixtures" / "replies",
    ).run()
    assert result["claim"].startswith("The duplicated shipping arithmetic")
    assert result["branch"].startswith("cursor/remediation/")
    assert json.loads((destination / "remediation.json").read_text())["claim"] == result["claim"]


def test_remediation_refuses_inconclusive_adjudication(tmp_path: Path) -> None:
    incident = "inc-1"
    destination = tmp_path / "out" / incident
    destination.mkdir(parents=True)
    (destination / "investigation.json").write_text(
        json.dumps({"adjudication": {"decision": {"accepted_hypothesis": None}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="valid accepted hypothesis"):
        RemediationOrchestrator(tmp_path, incident, dry_run=True, fresh=True).run()


def test_publish_dry_run_is_reviewable_without_notion_credentials(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    incident = "inc-20260828T054250Z-696028f6"
    shutil.copytree(root / "incidents" / incident, tmp_path / "incidents" / incident)
    destination = tmp_path / "out" / incident
    destination.mkdir(parents=True)
    (destination / "investigation.json").write_text(
        json.dumps({"reports": {}, "adjudication": {"decision": None}}),
        encoding="utf-8",
    )
    result = PublishOrchestrator(tmp_path, incident).publish(dry_run=True)
    artifact = Path(result["path"])
    assert artifact.exists()
    assert f"Incident {incident}" in artifact.read_text(encoding="utf-8")


def test_postmortem_tokens_render_without_touching_json_braces(tmp_path: Path) -> None:
    (tmp_path / "postmortem.md").write_text(
        '{"incident": "{incident_id}", "parent": "{parent_page_id}"}',
        encoding="utf-8",
    )
    assert render_prompt(
        "postmortem.md",
        {"incident_id": "inc-1", "parent_page_id": "page-1"},
        tmp_path,
    ) == '{"incident": "inc-1", "parent": "page-1"}'


def test_remediator_cloud_agent_requests_pull_request(tmp_path: Path) -> None:
    class FakeAgent:
        created: list[dict] = []

        @classmethod
        def create(cls, **kwargs):
            cls.created.append(kwargs)
            return SimpleNamespace(agent_id="agent-1")

    class FakeSDK:
        class CloudRepository:
            def __init__(self, url: str, starting_ref: str | None = None) -> None:
                self.url = url
                self.starting_ref = starting_ref

        class CloudAgentOptions:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        Agent = FakeAgent

    fleet = CloudFleet(tmp_path)
    fleet._sdk = lambda: FakeSDK()  # type: ignore[method-assign]
    FakeAgent.created.clear()
    fleet.create_agent("remediator", "inc-1", auto_create_pr=True)
    assert FakeAgent.created[-1]["cloud"].auto_create_pr is True
