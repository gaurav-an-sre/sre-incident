"""Concurrent investigation and adjudication orchestration."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

from .config import DEFAULT_STARTING_REF, HYPOTHESIS_ROLES
from .prompts import render_prompt
from .sdk import CloudFleet
from .state import StateStore
from .streaming import stream_run
from .validate import citation_failures, validate_report

_JSON_FENCE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_report(text: str) -> dict[str, Any]:
    fenced = _JSON_FENCE.search(text)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text.strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("agent reply did not contain a JSON object")


class DryRunAgent:
    def __init__(self, role: str, replies_dir: Path) -> None:
        self.role = role
        self.replies_dir = replies_dir
        self.agent_id = f"dry-{role}"
        self.runs = 0

    def send(self, _prompt: str) -> Any:
        self.runs += 1
        suffix = "_correction" if self.runs > 1 else ""
        if self.role == "adjudicator":
            name = f"adjudicate{suffix}.json"
        elif self.runs > 1:
            name = f"{self.role.removeprefix('H-').lower()}_correction.json"
        else:
            name = f"{self.role.removeprefix('H-').lower()}.json"
        reply = (self.replies_dir / name).read_text(encoding="utf-8")
        return DryRunRun(reply, self.agent_id, f"dry-run-{self.role}-{self.runs}")


class DryRunRun:
    def __init__(self, reply: str, agent_id: str, run_id: str) -> None:
        self.reply = reply
        self.agent_id = agent_id
        self.run_id = run_id

    def stream(self) -> list[dict[str, str]]:
        return [{"type": "assistant", "message": self.reply}]

    def wait(self) -> Any:
        return type("Result", (), {"result": self.reply, "run_id": self.run_id})()


class DryRunFleet:
    def __init__(self, replies_dir: Path) -> None:
        self.replies_dir = replies_dir
        self.agents: dict[str, DryRunAgent] = {}

    def create_agent(
        self, role: str, _incident_id: str, _hypothesis_id: str = "", **_kwargs: Any
    ) -> DryRunAgent:
        agent = DryRunAgent(role, self.replies_dir)
        self.agents[role] = agent
        return agent

    def resume_agent(self, agent_id: str) -> DryRunAgent:
        role = agent_id.removeprefix("dry-")
        return self.agents.setdefault(role, DryRunAgent(role, self.replies_dir))

    def is_agent_not_found(self, _error: BaseException) -> bool:
        return False


class InvestigatorOrchestrator:
    def __init__(
        self,
        repo_root: Path,
        incident_id: str,
        *,
        starting_ref: str | None = None,
        fresh: bool = False,
        fleet: Any | None = None,
        dry_run: bool = False,
        replies_dir: Path | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.incident_id = incident_id
        self.starting_ref = starting_ref or DEFAULT_STARTING_REF
        self.store = StateStore(repo_root, incident_id, fresh=fresh)
        self.out_dir = repo_root / "out" / incident_id
        self.fleet: Any
        if dry_run:
            fixture_dir = replies_dir or repo_root / "tests" / "fixtures" / "replies"
            self.fleet = DryRunFleet(fixture_dir)
        else:
            self.fleet = fleet or CloudFleet(
                repo=repo_root,
                api_key=os.getenv("CURSOR_API_KEY"),
            )
        self.dry_run = dry_run

    def _agent_for(self, role: str, hypothesis_id: str) -> Any:
        state = self.store.role(role)
        if state["agent_id"]:
            try:
                return self.fleet.resume_agent(state["agent_id"])
            except Exception as error:
                if not self.fleet.is_agent_not_found(error):
                    raise
        agent = self.fleet.create_agent(
            role,
            self.incident_id,
            hypothesis_id,
            starting_ref=self.starting_ref,
        )
        state["agent_id"] = getattr(agent, "agent_id", getattr(agent, "id", None))
        if state["agent_id"] is None:
            raise RuntimeError(f"{role} agent has no id")
        self.store.save()
        return agent

    def _send(self, role: str, agent: Any, prompt: str) -> str:
        state = self.store.role(role)
        try:
            run = agent.send(prompt)
        except Exception as error:
            if not self.fleet.is_agent_not_found(error):
                raise
            hypothesis = HYPOTHESIS_ROLES.get(role)
            replacement = self.fleet.create_agent(
                role,
                self.incident_id,
                hypothesis.hypothesis_id if hypothesis else "",
                starting_ref=self.starting_ref,
            )
            state["agent_id"] = getattr(replacement, "agent_id", getattr(replacement, "id", None))
            self.store.save()
            run = replacement.send(prompt)
        run_result = stream_run(run, self.out_dir / f"{role}.jsonl")
        state.setdefault("run_ids", []).append(
            getattr(run_result, "run_id", getattr(run_result, "id", None))
        )
        self.store.save()
        return str(getattr(run_result, "result", ""))

    def _investigate_role(self, role: str, details: Any) -> None:
        state = self.store.role(role)
        if state.get("status") == "validated" and state.get("report"):
            return
        agent = self._agent_for(role, details.hypothesis_id)
        preamble = render_prompt("_preamble.md", {"bundle_dir": f"incidents/{self.incident_id}"})
        prompt = render_prompt(
            details.prompt_file,
            {"preamble": preamble, "bundle_dir": f"incidents/{self.incident_id}"},
        )
        state["status"] = "investigating"
        self.store.save()
        text = self._send(role, agent, prompt)
        try:
            report = parse_report(text)
        except ValueError as error:
            repair = render_prompt("repair_json.md", {"error": str(error)})
            report = parse_report(self._send(role, agent, repair))
        report = validate_report(report, self.repo_root, self.incident_id)
        if report.get("validation", {}).get("downgraded"):
            first_validation = dict(report["validation"])
            correction = render_prompt(
                "citation_correction.md",
                {"failures": citation_failures(report)},
            )
            try:
                corrected = parse_report(self._send(role, agent, correction))
                report = validate_report(corrected, self.repo_root, self.incident_id)
                report["validation"]["correction_attempt"] = {
                    "failures": first_validation.get("failures", []),
                    "valid_citations": first_validation.get("valid_citations", 0),
                    "bundle_citations": first_validation.get("bundle_citations", 0),
                }
            except (ValueError, OSError):
                report["validation"]["downgraded"] = True
                report["validation"]["reason"] = "citation correction reply was invalid"
                report["verdict"] = "inconclusive"
                report["validation"]["correction_attempt"] = first_validation
        state["report"] = report
        state["validation"] = report.get("validation")
        state["status"] = "validated"
        self.store.save()

    def _adjudicate(self, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
        state = self.store.data.get("adjudication")
        if state:
            return cast(dict[str, Any], state)
        agent = self._agent_for("adjudicator", "")
        rendered = render_prompt(
            "adjudicate.md",
            {"reports": json.dumps(reports, indent=2, sort_keys=True)},
        )
        text = self._send("adjudicator", agent, rendered)
        decision = parse_report(text)
        eligible: set[str] = set()
        for report in reports.values():
            hypothesis_id = report.get("hypothesis_id")
            if report.get("verdict") == "supported" and isinstance(hypothesis_id, str):
                eligible.add(hypothesis_id)
        if decision.get("accepted_hypothesis") not in eligible:
            eligibility = ", ".join(
                f"{hypothesis}: post-validation verdict supported"
                for hypothesis in sorted(eligible)
            ) or "none"
            correction = (
                "Your accepted_hypothesis is ineligible. Reply with the full JSON decision again. "
                f"Eligible hypotheses are {eligibility}. Every other hypothesis is ineligible "
                "because its post-validation verdict is not supported."
            )
            corrected = parse_report(self._send("adjudicator", agent, correction))
            if corrected.get("accepted_hypothesis") not in eligible:
                corrected["accepted_hypothesis"] = None
                corrected["adjudication_invalid"] = True
            decision = corrected
        state = {
            "agent_id": self.store.role("adjudicator").get("agent_id"),
            "run_ids": self.store.role("adjudicator").get("run_ids", []),
            "decision": decision,
        }
        self.store.data["adjudication"] = state
        self.store.save()
        return dict(state)

    def run(self) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self._investigate_role, role, details)
                for role, details in HYPOTHESIS_ROLES.items()
            ]
            for future in futures:
                future.result()
        reports = {
            role: self.store.role(role).get("report") or {}
            for role in HYPOTHESIS_ROLES
        }
        adjudication = self._adjudicate(reports)
        artifact = {
            "incident_id": self.incident_id,
            "reports": reports,
            "adjudication": adjudication,
            "agents": {
                role: {
                    "agent_id": self.store.role(role).get("agent_id"),
                    "run_ids": self.store.role(role).get("run_ids", []),
                    "stream_path": self.store.role(role).get("stream_path"),
                }
                for role in (*HYPOTHESIS_ROLES, "adjudicator")
            },
        }
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "investigation.json").write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return artifact
