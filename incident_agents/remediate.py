"""Cloud remediation orchestration driven by an adjudicated incident."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .orchestrate import InvestigatorOrchestrator, parse_report
from .prompts import render_prompt


class RemediationOrchestrator(InvestigatorOrchestrator):
    def run(self, decision_path: Path | None = None) -> dict[str, Any]:
        source = decision_path or self.repo_root / "out" / self.incident_id / "investigation.json"
        investigation = json.loads(source.read_text(encoding="utf-8"))
        adjudication = investigation.get("adjudication", {})
        decision = adjudication.get("decision", {})
        accepted = decision.get("accepted_hypothesis")
        if accepted is None or decision.get("adjudication_invalid"):
            raise ValueError("cannot remediate without a valid accepted hypothesis")
        report: dict[str, Any] = next(
            (
                value
                for value in investigation.get("reports", {}).values()
                if value.get("hypothesis_id") == accepted
            ),
            {},
        )
        decision_for_agent = {
            "accepted_hypothesis": accepted,
            "root_cause": decision.get("root_cause"),
            "recommended_fix": decision.get("recommended_fix"),
            "must_not_do": decision.get("must_not_do", []),
            "evidence": report.get("evidence", []),
        }
        agent = self._agent_for("remediator", "", auto_create_pr=True)
        prompt = render_prompt(
            "remediate.md",
            {
                "decision": json.dumps(decision_for_agent, indent=2, sort_keys=True),
                "bundle_dir": f"incidents/{self.incident_id}",
            },
        )
        with self.store.update_role("remediator") as state:
            state["status"] = "remediating"
        text = self._send("remediator", agent, prompt, auto_create_pr=True)
        try:
            report = parse_report(text)
        except ValueError as error:
            repair = render_prompt("repair_json.md", {"error": str(error)})
            report = parse_report(self._send("remediator", agent, repair, auto_create_pr=True))
        branch = report.get("branch")
        pr_url = report.get("pr_url") or report.get("pull_request_url")
        claim = report.get("claim") or report.get("root_cause_addressed")
        with self.store.update_role("remediator") as state:
            state.update(
                {
                    "status": "complete",
                    "report": report,
                    "branch": branch,
                    "pr_url": pr_url,
                    "claim": claim,
                }
            )
        artifact = {
            "incident_id": self.incident_id,
            "agent_id": self.store.role("remediator").get("agent_id"),
            "run_ids": self.store.role("remediator").get("run_ids", []),
            "stream_path": self.store.role("remediator").get("stream_path"),
            "branch": branch,
            "pr_url": pr_url,
            "claim": claim,
            "report": report,
        }
        destination = self.repo_root / "out" / self.incident_id / "remediation.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return artifact
