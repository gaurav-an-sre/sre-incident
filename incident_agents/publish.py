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


def _verification_path(repo_root: Path, incident_id: str) -> Path:
    incident_path = repo_root / "out" / incident_id / "verification.json"
    return incident_path if incident_path.exists() else repo_root / "out" / "verification.json"


def _first_valid_excerpt(report: dict[str, Any]) -> str:
    for evidence in report.get("evidence", []):
        if evidence.get("validation") == "valid":
            return str(evidence.get("excerpt", ""))
    return "No valid citation recorded."


def _verification_measurement(signal: dict[str, Any]) -> str:
    measured = signal.get("measured", {})
    signal_id = signal.get("id")
    if signal_id == "S1":
        return (
            f"{measured.get('succeeded', 0)} succeeded and "
            f"{measured.get('declined', 0)} declined out of "
            f"{measured.get('attempts', 0)} attempts "
            f"({float(measured.get('success_rate', 0)):.1%})."
        )
    if signal_id == "S2a":
        carts = measured.get("carts", [])
        subtotals = ", ".join(str(cart.get("subtotal_cents")) for cart in carts)
        return (
            f"Threshold {measured.get('threshold_cents')} cents; real API carts "
            f"at subtotals {subtotals}."
        )
    if signal_id == "S2b":
        discrepancies = measured.get("discrepancies", [])
        return (
            f"Direct pricing sweep at {', '.join(map(str, measured.get('subtotals', [])))} "
            f"cents; {len(discrepancies)} discrepancies."
        )
    if signal_id == "S3":
        discrepancies = measured.get("discrepancies", [])
        if not discrepancies:
            return "Every quoted, authorized, and reference amount matched."
        first = discrepancies[0]
        return (
            f"{len(discrepancies)} discrepancies; order {first.get('order_id')} "
            f"quoted {first.get('quoted_amount_cents')} cents, authorized "
            f"{first.get('authorized_amount_cents')} cents, reference "
            f"{first.get('reference_amount_cents')} cents "
            f"({first.get('classification')})."
        )
    if signal_id == "S4":
        return (
            f"{len(measured.get('failures', []))} qualifying carts failed the "
            "free-shipping check."
        )
    if signal_id == "S5":
        return (
            f"Undercharge: {measured.get('undercharge', {}).get('decision')}; "
            f"overcharge: {measured.get('overcharge', {}).get('decision')}; "
            f"matching: {measured.get('match', {}).get('decision')}."
        )
    if signal_id == "S6":
        return (
            f"{measured.get('attempts', 0)} attempts, {measured.get('declined', 0)} "
            f"declines, and {measured.get('new_alerts', 0)} new alerts."
        )
    return "Measurement not recorded."


def _render_prompt(
    repo_root: Path,
    incident_id: str,
    *,
    parent_page_id: str,
    alert: dict[str, Any],
    investigation: dict[str, Any],
    remediation: dict[str, Any],
    verification: dict[str, Any],
) -> str:
    bundle = repo_root / "incidents" / incident_id
    return render_prompt(
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
            "incident_id": incident_id,
        },
    )


def render_postmortem(repo_root: Path, incident_id: str) -> str:
    bundle = repo_root / "incidents" / incident_id
    alert = _read_json(bundle / "alert.json")
    investigation = _read_json(repo_root / "out" / incident_id / "investigation.json")
    remediation_path = repo_root / "out" / incident_id / "remediation.json"
    verification_path = _verification_path(repo_root, incident_id)
    remediation = _read_json(remediation_path) if remediation_path.exists() else None
    verification = _read_json(verification_path) if verification_path.exists() else None
    decision = investigation.get("adjudication", {}).get("decision")
    deploys = _read_jsonl(bundle / "deploys.jsonl")
    change_description = (
        deploys[0].get("change_description", "the recorded deployment")
        if deploys
        else "the recorded deployment"
    )
    reports = investigation.get("reports", {})
    accepted = decision.get("accepted_hypothesis") if isinstance(decision, dict) else None
    accepted_report = reports.get(accepted, {}) if accepted else {}
    declined = alert.get("declined", 0)
    attempts = alert.get("attempts", 0)
    window = f"{alert.get('window_start', 'unknown')} to {alert.get('window_end', 'unknown')}"
    verification_signals = (verification or {}).get("signals", [])
    remediation_report = (remediation or {}).get("report", {})
    remediation_branch = (remediation or {}).get("branch", remediation_report.get("branch"))
    remediation_pr = (remediation or {}).get("pr_url", remediation_report.get("pr_url"))
    lines = [
        f"# Incident {incident_id} — checkout failures after promotion deploy",
        "",
        "## Summary",
        "",
        (
            f"Between {window}, {declined} of {attempts} checkout attempts were declined "
            f"after `{change_description}`. "
            "The accepted investigation attributes the incident to "
            f"{accepted or 'no accepted hypothesis'}."
        ),
        (
            "The independent verifier "
            f"{'accepted' if verification and verification.get('verified') else 'did not accept'} "
            "the candidate result."
        ),
        "",
        "## Customer impact",
        "",
        (
            f"Customers made {attempts} recorded checkout attempts during {window}; "
            f"{declined} received a checkout decline. The accepted investigation describes "
            "the affected population as qualifying carts, while smaller carts continued to "
            "succeed. "
            "The frozen record contains no operator-facing process error or health-check failure; "
            "the recorded payment outcome was a structured business decline."
        ),
        "",
        "## Detection",
        "",
        (
            "The watchdog fired because "
            f"{alert.get('reason', 'the recorded threshold was crossed')}. "
            f"The alert window was {window}. Payment evidence records `amount_mismatch` business "
            "decisions, and the metrics evidence records low latency rather than a provider outage."
        ),
        "",
        "## Timeline",
        "",
        _timeline(bundle),
        "",
        "## Root cause",
        "",
        str(
            (decision or {}).get("root_cause")
            or accepted_report.get("root_cause")
            or "No root cause was recorded."
        ),
        "",
        "## Hypotheses considered",
        "",
        "| Hypothesis | Verdict | Citations valid | Deciding excerpt |",
        "| --- | --- | ---: | --- |",
        *[
            (
                f"| {name} | {report.get('verdict', 'unknown')} | "
                f"{report.get('validation', {}).get('valid_citations', 0)} | "
                f"{_first_valid_excerpt(report)} |"
            )
            for name, report in sorted(reports.items())
        ],
        "",
        "## What went wrong beyond the bug",
        "",
        (
            "The incident exposed duplicated pricing arithmetic and the absence of a check that "
            "the customer quote and authorization amount agree. The recorded evidence also shows "
            "that a pricing configuration could change the quote path without exercising the "
            "payment path, while business declines remained distinct from process failures."
        ),
        "",
        "## Mitigation and remediation",
        "",
        (
            f"The remediation record reports branch `{remediation_branch or 'not recorded'}`"
            + (
                f" and pull request [{remediation_pr}]({remediation_pr})."
                if remediation_pr
                else " and no pull request URL."
            )
            + " Its claim was: "
            + str(
                remediation_report.get(
                    "claim", (remediation or {}).get("claim", "not recorded")
                )
            )
            .rstrip(".")
            + "."
        ),
        "",
        "## Verification",
        "",
        (
            "Independent verifier verdict: "
            f"**{str((verification or {}).get('verified', 'not run')).lower()}**."
        ),
        "",
        "| Signal | Passed | What was measured |",
        "| --- | --- | --- |",
        *[
            f"| {signal.get('id')} | {'yes' if signal.get('passed') else 'no'} | "
            f"{_verification_measurement(signal)} |"
            for signal in verification_signals
        ],
        "",
        "## Action items",
        "",
        (
            "- [ ] Add a pre-deploy assertion that quote, authorization, and reference "
            "totals agree; this would catch duplicated arithmetic before promotion changes ship."
        ),
        (
            "- [ ] Alert on `amount_mismatch` business declines and quote/authorization "
            "divergence; this would detect the failure faster than the aggregate watchdog."
        ),
        (
            "- [ ] Keep the independent seven-signal verification gate mandatory for "
            "remediation promotion."
        ),
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
        prompt_destination = destination.with_name("postmortem_prompt.md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown, encoding="utf-8")
        investigation = _read_json(
            self.repo_root / "out" / self.incident_id / "investigation.json"
        )
        bundle = self.repo_root / "incidents" / self.incident_id
        alert = _read_json(bundle / "alert.json")
        remediation_path = self.repo_root / "out" / self.incident_id / "remediation.json"
        verification_path = _verification_path(self.repo_root, self.incident_id)
        remediation = _read_json(remediation_path) if remediation_path.exists() else {}
        verification = _read_json(verification_path) if verification_path.exists() else {}
        prompt = _render_prompt(
            self.repo_root,
            self.incident_id,
            parent_page_id=parent_page_id or "(dry-run: no parent page)",
            alert=alert,
            investigation=investigation,
            remediation=remediation,
            verification=verification,
        )
        prompt_destination.write_text(prompt, encoding="utf-8")
        if dry_run:
            print(markdown)
            return {
                "incident_id": self.incident_id,
                "dry_run": True,
                "path": str(destination),
                "prompt_path": str(prompt_destination),
            }
        token = os.getenv("NOTION_TOKEN")
        if not parent_page_id or not token:
            raise ValueError("live publishing requires --parent-page and NOTION_TOKEN")
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
