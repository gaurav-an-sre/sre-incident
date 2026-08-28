"""Command-line interface for the incident agent fleet."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .orchestrate import InvestigatorOrchestrator
from .publish import PublishOrchestrator
from .remediate import RemediationOrchestrator
from .sdk import CloudFleet


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m incident_agents")
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate")
    investigate.add_argument("--incident", required=True)
    investigate.add_argument("--starting-ref")
    investigate.add_argument("--fresh", action="store_true")
    investigate.add_argument("--dry-run", action="store_true")
    remediate = subparsers.add_parser("remediate")
    remediate.add_argument("--incident", required=True)
    remediate.add_argument("--decision")
    remediate.add_argument("--starting-ref")
    remediate.add_argument("--fresh", action="store_true")
    remediate.add_argument("--dry-run", action="store_true")
    publish = subparsers.add_parser("publish")
    publish.add_argument("--incident", required=True)
    publish.add_argument("--parent-page")
    publish.add_argument("--dry-run", action="store_true")
    status = subparsers.add_parser("status")
    status.add_argument("--incident", required=True)
    subparsers.add_parser("agents")
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == "investigate":
        artifact = InvestigatorOrchestrator(
            root,
            args.incident,
            starting_ref=args.starting_ref,
            fresh=args.fresh,
            dry_run=args.dry_run,
        ).run()
        for role, report in artifact["reports"].items():
            validation = report.get("validation", {})
            print(
                f"{role}: verdict={report.get('verdict')} "
                f"valid_citations={validation.get('valid_citations', 0)} "
                f"bundle_citations={validation.get('bundle_citations', 0)}"
            )
            for failure in validation.get("failures", []):
                print(f"{role}: citation checker caught {failure}")
            for failure in validation.get("correction_attempt", {}).get("failures", []):
                print(f"{role}: citation checker caught {failure} (before correction)")
        print(json.dumps(artifact["adjudication"]["decision"], indent=2, sort_keys=True))
    elif args.command == "remediate":
        artifact = RemediationOrchestrator(
            root,
            args.incident,
            starting_ref=args.starting_ref,
            fresh=args.fresh,
            dry_run=args.dry_run,
        ).run(Path(args.decision) if args.decision else None)
        print(json.dumps(artifact, indent=2, sort_keys=True))
    elif args.command == "publish":
        artifact = PublishOrchestrator(root, args.incident).publish(
            parent_page_id=args.parent_page,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            print(json.dumps(artifact, indent=2, sort_keys=True))
    elif args.command == "status":
        state_path = root / "out" / args.incident / "state.json"
        if not state_path.exists():
            raise SystemExit(f"no state for incident {args.incident}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for role, value in state.get("roles", {}).items():
            report = value.get("report") or {}
            print(f"{role:12} {value.get('status', 'pending'):12} {report.get('verdict', '-')}")
    else:
        fleet = CloudFleet(root, api_key=os.getenv("CURSOR_API_KEY"))
        for agent in fleet.list_agents():
            print(
                json.dumps(
                    {
                        "id": getattr(agent, "id", None),
                        "metadata": dict(getattr(agent, "metadata", {})),
                    }
                )
            )


if __name__ == "__main__":
    main()
