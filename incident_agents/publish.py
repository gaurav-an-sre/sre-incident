"""Notion postmortem publication orchestration and offline rendering."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from .orchestrate import InvestigatorOrchestrator, parse_report
from .prompts import render_prompt


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _timeline(bundle: Path) -> str:
    records = [
        _read_json(bundle / "alert.json"),
        *_read_jsonl(bundle / "deploys.jsonl"),
    ]
    lines = ["| Time | Event | Source |", "| --- | --- | --- |"]
    for record in records:
        timestamp = record.get("timestamp", "unknown")
        event = record.get("change_description") or record.get("reason", "alert")
        lines.append(f"| {timestamp} | {event} | frozen incident bundle |")
    return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def render_postmortem(repo_root: Path, incident_id: str) -> str:
    bundle = repo_root / "incidents" / incident_id
    alert = _read_json(bundle / "alert.json")
    investigation = _read_json(repo_root / "out" / incident_id / "investigation.json")
    remediation_path = repo_root / "out" / incident_id / "remediation.json"
    verification_path = repo_root / "out" / incident_id / "verification.json"
    remediation = _read_json(remediation_path) if remediation_path.exists() else None
    verification = _read_json(verification_path) if verification_path.exists() else None
    decision = investigation.get("adjudication", {}).get("decision")
    lines = [
        f"# Incident {incident_id} — checkout failures after promotion deploy",
        "",
        "## Summary",
        "",
        "This document is rendered from frozen incident and phase artifacts.",
        f"Alert record: `{alert.get('reason', 'not recorded')}`.",
        (
            "Independent verification: "
            f"`{verification.get('verified') if verification else 'not run'}`."
        ),
        "",
        "## Alert and impact",
        "",
        "```json",
        json.dumps(alert, indent=2, sort_keys=True),
        "```",
        "",
        "## Timeline",
        "",
        _timeline(bundle),
        "",
        "## Investigation",
        "",
        "```json",
        json.dumps(investigation.get("reports", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Incident commander's decision",
        "",
        "```json",
        json.dumps(decision, indent=2, sort_keys=True),
        "```",
        "",
        "## Remediation",
        "",
        "```json",
        json.dumps(remediation, indent=2, sort_keys=True),
        "```",
        "",
        "## Independent verification",
        "",
        "```json",
        json.dumps(verification, indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


class PublishOrchestrator(InvestigatorOrchestrator):
    def publish(
        self,
        *,
        parent_page_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        markdown = render_postmortem(self.repo_root, self.incident_id)
        destination = self.repo_root / "out" / self.incident_id / "postmortem.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")
        if dry_run:
            print(markdown)
            return {"incident_id": self.incident_id, "dry_run": True, "path": str(destination)}
        token = os.getenv("NOTION_TOKEN")
        if not parent_page_id or not token:
            raise ValueError("live publishing requires --parent-page and NOTION_TOKEN")
        investigation = _read_json(
            self.repo_root / "out" / self.incident_id / "investigation.json"
        )
        bundle = self.repo_root / "incidents" / self.incident_id
        alert = _read_json(bundle / "alert.json")
        remediation_path = self.repo_root / "out" / self.incident_id / "remediation.json"
        verification_path = self.repo_root / "out" / self.incident_id / "verification.json"
        remediation = _read_json(remediation_path) if remediation_path.exists() else {}
        verification = _read_json(verification_path) if verification_path.exists() else {}
        prompt = render_prompt(
            "postmortem.md",
            {
                "alert": json.dumps(alert, indent=2, sort_keys=True),
                "timeline": _timeline(bundle),
                "hypotheses": json.dumps(
                    investigation.get("reports", {}), indent=2, sort_keys=True
                ),
                "decision": json.dumps(
                    investigation.get("adjudication", {}).get("decision"),
                    indent=2,
                    sort_keys=True,
                ),
                "remediation": json.dumps(remediation, indent=2, sort_keys=True),
                "verification": json.dumps(verification, indent=2, sort_keys=True),
                "parent_page_id": parent_page_id,
                "incident_id": self.incident_id,
            },
        )
        agent = self._agent_for("scribe", "")
        with self.store.update_role("scribe") as state:
            state["status"] = "publishing"
        report = parse_report(self._send("scribe", agent, prompt))
        with self.store.update_role("scribe") as state:
            state["status"] = "published" if report.get("published") else "failed"
            state["report"] = report
        artifact = {
            "incident_id": self.incident_id,
            "agent_id": self.store.role("scribe").get("agent_id"),
            "run_ids": self.store.role("scribe").get("run_ids", []),
            "stream_path": self.store.role("scribe").get("stream_path"),
            "report": report,
            "markdown_path": str(destination),
        }
        (destination.parent / "publication.json").write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return artifact
