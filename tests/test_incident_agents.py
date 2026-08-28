import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from incident_agents.orchestrate import InvestigatorOrchestrator
from incident_agents.prompts import render_prompt
from incident_agents.sdk import CloudFleet
from incident_agents.streaming import stream_run
from incident_agents.validate import validate_report


class FakeCloudRepository:
    def __init__(self, url: str, starting_ref: str | None = None) -> None:
        self.url = url
        self.starting_ref = starting_ref


class FakeCloudOptions:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeAgent:
    created: list[dict] = []

    @classmethod
    def create(cls, **kwargs):
        cls.created.append(kwargs)
        return SimpleNamespace(agent_id=f"agent-{len(cls.created)}")

    @classmethod
    def resume(cls, agent_id):
        return SimpleNamespace(agent_id=agent_id)

    @classmethod
    def list(cls):
        return SimpleNamespace(items=[SimpleNamespace(metadata={"demo": "sre-incident"})])


class FakeSDK:
    CloudRepository = FakeCloudRepository
    CloudAgentOptions = FakeCloudOptions
    Agent = FakeAgent

    class AgentNotFoundError(Exception):
        pass


def test_cloud_fleet_metadata_starting_ref_and_listing(monkeypatch, tmp_path: Path) -> None:
    fleet = CloudFleet(tmp_path)
    fleet._sdk = lambda: FakeSDK()  # type: ignore[method-assign]
    FakeAgent.created.clear()
    agent = fleet.create_agent(
        "change", "inc-1", "H-CHANGE", starting_ref="cursor/investigation"
    )
    options = FakeAgent.created[0]["cloud"]
    assert agent.agent_id == "agent-1"
    assert options.repos[0].starting_ref == "cursor/investigation"
    assert options.auto_create_pr is False
    assert options.metadata == {
        "demo": "sre-incident",
        "incident": "inc-1",
        "role": "change",
        "hypothesis": "H-CHANGE",
    }
    assert len(fleet.list_agents()) == 1
    assert fleet.is_agent_not_found(FakeSDK.AgentNotFoundError("gone"))
    assert not fleet.is_agent_not_found(RuntimeError("agent_not_found"))


def test_three_agent_creation_can_run_concurrently(tmp_path: Path) -> None:
    fleet = CloudFleet(tmp_path)
    fleet._sdk = lambda: FakeSDK()  # type: ignore[method-assign]
    FakeAgent.created.clear()
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(
            executor.map(
                lambda role: fleet.create_agent(
                    role, "inc-1", f"H-{role.upper()}", starting_ref="main"
                ),
                ("change", "dependency", "capacity"),
            )
        )
    assert len(FakeAgent.created) == 3
    assert {item["cloud"].metadata["role"] for item in FakeAgent.created} == {
        "change",
        "dependency",
        "capacity",
    }


def test_streaming_preserves_typed_event_and_waits(tmp_path: Path) -> None:
    class Run:
        def __init__(self):
            self.waited = False

        def stream(self):
            return iter(
                [{"type": "tool_call", "timestamp": "2025-01-01T00:00:00Z", "args": {"path": "x"}}]
            )

        def wait(self):
            self.waited = True
            return SimpleNamespace(result='{"ok": true}', run_id="run-1")

    run = Run()
    result = stream_run(run, tmp_path / "role.jsonl")
    record = json.loads((tmp_path / "role.jsonl").read_text())
    assert record["event_type"] == "tool_call"
    assert record["timestamp"] == "2025-01-01T00:00:00Z"
    assert record["payload"]["args"]["path"] == "x"
    assert run.waited is True
    assert result.run_id == "run-1"


def test_validate_all_citation_classifications_and_whitespace(tmp_path: Path) -> None:
    bundle = tmp_path / "incidents" / "inc-1"
    bundle.mkdir(parents=True)
    (bundle / "alert.json").write_text("success rate below 90 percent\n", encoding="utf-8")
    source = tmp_path / "tools"
    source.mkdir()
    (source / "x.py").write_text("first   line\nsecond line\n", encoding="utf-8")
    report = {
        "hypothesis_id": "H-CHANGE",
        "verdict": "supported",
        "evidence": [
            {
                "file": "incidents/inc-1/alert.json",
                "excerpt": "success rate below 90 percent",
                "why": "",
            },
            {"file": "tools/x.py", "excerpt": "first line second line", "why": ""},
            {"file": "tools/missing.py", "excerpt": "missing citation here", "why": ""},
            {"file": "missing.py", "excerpt": "outside path citation", "why": ""},
            {"file": "../secret", "excerpt": "outside repository", "why": ""},
            {"file": "tools/x.py", "excerpt": "short", "why": ""},
        ],
    }
    result = validate_report(report, tmp_path, "inc-1")
    assert [item["validation"] for item in result["evidence"]] == [
        "valid",
        "valid",
        "not_found",
        "disallowed_path",
        "disallowed_path",
        "too_short",
    ]
    assert result["validation"]["downgraded"] is False


def test_supported_report_without_bundle_evidence_is_downgraded(tmp_path: Path) -> None:
    source = tmp_path / "tools"
    source.mkdir()
    (source / "x.py").write_text("a sufficiently long citation\n", encoding="utf-8")
    report = {
        "hypothesis_id": "H-CHANGE",
        "verdict": "supported",
        "evidence": [
            {"file": "tools/x.py", "excerpt": "a sufficiently long citation", "why": ""},
            {"file": "tools/x.py", "excerpt": "a sufficiently long citation", "why": ""},
        ],
    }
    result = validate_report(report, tmp_path, "inc-1")
    assert result["verdict"] == "inconclusive"
    assert result["validation"]["downgraded"] is True


def test_prompt_rendering_preserves_literal_json_braces(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text(
        'Schema: {"verdict": "supported"}\\nBundle: {bundle_dir}\\n',
        encoding="utf-8",
    )
    assert render_prompt("prompt.md", {"bundle_dir": "incidents/inc-1"}, tmp_path) == (
        'Schema: {"verdict": "supported"}\\nBundle: incidents/inc-1\\n'
    )


def test_dry_run_catches_fabricated_citation_and_adjudicates(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    incident = "inc-20260828T054250Z-696028f6"
    artifact = InvestigatorOrchestrator(
        root,
        incident,
        fresh=True,
        dry_run=True,
    ).run()
    dependency = artifact["reports"]["H-DEPENDENCY"]
    assert dependency["verdict"] == "rejected"
    assert all(item["validation"] == "valid" for item in dependency["evidence"])
    assert dependency["validation"]["correction_attempt"]["failures"]
    assert artifact["adjudication"]["decision"]["accepted_hypothesis"] == "H-CHANGE"


def test_failed_citation_correction_downgrades_report(tmp_path: Path) -> None:
    import shutil

    root = Path(__file__).resolve().parents[1]
    replies = tmp_path / "replies"
    shutil.copytree(root / "tests/fixtures/replies", replies)
    bad = json.loads((replies / "change.json").read_text())
    bad["evidence"] = [
        {
            "file": "tools/does-not-exist.py",
            "excerpt": "fabricated evidence citation",
            "why": "intentionally invalid",
        }
    ]
    (replies / "change.json").write_text(json.dumps(bad))
    (replies / "change_correction.json").write_text(json.dumps(bad))
    artifact = InvestigatorOrchestrator(
        root,
        "inc-20260828T054250Z-696028f6",
        fresh=True,
        dry_run=True,
        replies_dir=replies,
    ).run()
    report = artifact["reports"]["H-CHANGE"]
    assert report["verdict"] == "inconclusive"
    assert report["validation"]["downgraded"] is True


def test_malformed_json_gets_one_repair_run(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    incident = "inc-20260828T054250Z-696028f6"

    class RepairAgent:
        def __init__(self, role):
            self.role = role
            self.agent_id = f"fake-{role}"
            self.calls = 0

        def send(self, _prompt):
            self.calls += 1
            if self.role == "H-CHANGE" and self.calls == 1:
                reply = "not json"
            else:
                filename = {
                    "H-CHANGE": "change.json",
                    "H-DEPENDENCY": "dependency_correction.json",
                    "H-CAPACITY": "capacity.json",
                    "adjudicator": "adjudicate_correction.json",
                }[self.role]
                reply = (root / "tests/fixtures/replies" / filename).read_text()
            return SimpleNamespace(
                stream=lambda: iter([{"type": "assistant", "message": reply}]),
                wait=lambda: SimpleNamespace(result=reply, run_id=f"{self.role}-{self.calls}"),
            )

    class Fleet:
        def __init__(self):
            self.agents = {}

        def create_agent(self, role, *_args, **_kwargs):
            self.agents[role] = RepairAgent(role)
            return self.agents[role]

        def resume_agent(self, agent_id):
            return self.agents[agent_id.removeprefix("fake-")]

        def is_agent_not_found(self, _error):
            return False

    fleet = Fleet()
    artifact = InvestigatorOrchestrator(root, incident, fresh=True, fleet=fleet).run()
    assert fleet.agents["H-CHANGE"].calls == 2
    assert artifact["reports"]["H-CHANGE"]["hypothesis_id"] == "H-CHANGE"


def test_agent_recreation_after_typed_not_found(tmp_path: Path) -> None:
    class Missing(Exception):
        pass

    class Fleet:
        def __init__(self):
            self.created = []

        def resume_agent(self, _agent_id):
            raise Missing("not found")

        def is_agent_not_found(self, error):
            return isinstance(error, Missing)

        def create_agent(self, role, incident, hypothesis, **kwargs):
            self.created.append((role, incident, hypothesis, kwargs))
            return SimpleNamespace(agent_id="new-agent")

    fleet = Fleet()
    orchestrator = InvestigatorOrchestrator(
        tmp_path, "inc-1", starting_ref="branch", fleet=fleet, fresh=True
    )
    with orchestrator.store.update_role("H-CHANGE") as role:
        role["agent_id"] = "old-agent"
    agent = orchestrator._agent_for("H-CHANGE", "H-CHANGE")
    assert agent.agent_id == "new-agent"
    assert fleet.created[0][3]["starting_ref"] == "branch"
    assert orchestrator.store.role("H-CHANGE")["agent_id"] == "new-agent"


def test_existing_agent_is_resumed_without_recreation(tmp_path: Path) -> None:
    class Fleet:
        def __init__(self):
            self.created = 0
            self.resumed = []

        def resume_agent(self, agent_id):
            self.resumed.append(agent_id)
            return SimpleNamespace(agent_id=agent_id)

        def create_agent(self, *_args, **_kwargs):
            self.created += 1
            return SimpleNamespace(agent_id="new-agent")

        def is_agent_not_found(self, _error):
            return False

    fleet = Fleet()
    orchestrator = InvestigatorOrchestrator(
        tmp_path, "inc-1", fleet=fleet, fresh=True
    )
    with orchestrator.store.update_role("H-CHANGE") as role:
        role["agent_id"] = "existing-agent"
    assert orchestrator._agent_for("H-CHANGE", "H-CHANGE").agent_id == "existing-agent"
    assert fleet.resumed == ["existing-agent"]
    assert fleet.created == 0


def test_state_updates_are_atomic_and_none_are_lost(tmp_path: Path) -> None:
    from incident_agents.state import StateStore

    store = StateStore(tmp_path, "inc-1", fresh=True)
    failures: list[Exception] = []
    start = threading.Barrier(8)

    def worker(index: int) -> None:
        try:
            start.wait()
            for update in range(20):
                with store.update_role("shared") as role:
                    role.setdefault("updates", {})[f"{index}-{update}"] = True
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    while any(thread.is_alive() for thread in threads):
        if store.path.exists():
            json.loads(store.path.read_text(encoding="utf-8"))
    for thread in threads:
        thread.join()
    assert failures == []
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert len(saved["roles"]["shared"]["updates"]) == 160


@pytest.mark.parametrize("has_eligible_hypothesis", [False, True])
def test_explicit_null_adjudication_is_terminal(
    tmp_path: Path, has_eligible_hypothesis: bool
) -> None:
    class Agent:
        agent_id = "adj-agent"

        def __init__(self):
            self.calls = 0

        def send(self, _prompt):
            self.calls += 1
            reply = json.dumps({"accepted_hypothesis": None, "unresolved_questions": []})
            return SimpleNamespace(
                stream=lambda: iter([{"type": "assistant", "message": reply}]),
                wait=lambda: SimpleNamespace(result=reply, run_id=f"adj-{self.calls}"),
            )

    class Fleet:
        def __init__(self):
            self.agent = Agent()

        def create_agent(self, *_args, **_kwargs):
            return self.agent

        def resume_agent(self, _agent_id):
            return self.agent

        def is_agent_not_found(self, _error):
            return False

    fleet = Fleet()
    orchestrator = InvestigatorOrchestrator(tmp_path, "inc-1", fresh=True, fleet=fleet)
    reports = {
        "H-CHANGE": {
            "hypothesis_id": "H-CHANGE",
            "verdict": "supported" if has_eligible_hypothesis else "rejected",
        },
        "H-DEPENDENCY": {"hypothesis_id": "H-DEPENDENCY", "verdict": "inconclusive"},
        "H-CAPACITY": {"hypothesis_id": "H-CAPACITY", "verdict": "rejected"},
    }
    result = orchestrator._adjudicate(reports)
    assert result["decision"]["accepted_hypothesis"] is None
    assert "adjudication_invalid" not in result["decision"]
    assert fleet.agent.calls == 1


def test_adjudicator_cannot_retain_ineligible_choice(tmp_path: Path) -> None:
    class Agent:
        agent_id = "adj-agent"

        def send(self, _prompt):
            reply = json.dumps({"accepted_hypothesis": "H-DEPENDENCY"})
            return SimpleNamespace(
                stream=lambda: iter([{"type": "assistant", "message": reply}]),
                wait=lambda: SimpleNamespace(result=reply, run_id="adj-run"),
            )

    class Fleet:
        def create_agent(self, *_args, **_kwargs):
            return Agent()

        def resume_agent(self, _agent_id):
            return Agent()

        def is_agent_not_found(self, _error):
            return False

    orchestrator = InvestigatorOrchestrator(
        tmp_path, "inc-1", fresh=True, fleet=Fleet()
    )
    reports = {
        "H-CHANGE": {"hypothesis_id": "H-CHANGE", "verdict": "supported"},
        "H-DEPENDENCY": {"hypothesis_id": "H-DEPENDENCY", "verdict": "rejected"},
        "H-CAPACITY": {"hypothesis_id": "H-CAPACITY", "verdict": "inconclusive"},
    }
    result = orchestrator._adjudicate(reports)
    assert result["decision"]["accepted_hypothesis"] is None
    assert result["decision"]["adjudication_invalid"] is True


def test_adjudication_correction_uses_owned_prompt_file(tmp_path: Path) -> None:
    class Agent:
        agent_id = "adj-agent"

        def __init__(self):
            self.prompts: list[str] = []

        def send(self, prompt):
            self.prompts.append(prompt)
            accepted = "H-DEPENDENCY" if len(self.prompts) == 1 else "H-CHANGE"
            reply = json.dumps({"accepted_hypothesis": accepted})
            return SimpleNamespace(
                stream=lambda: iter([{"type": "assistant", "message": reply}]),
                wait=lambda: SimpleNamespace(
                    result=reply, run_id=f"adj-run-{len(self.prompts)}"
                ),
            )

    class Fleet:
        def __init__(self):
            self.agent = Agent()

        def create_agent(self, *_args, **_kwargs):
            return self.agent

        def resume_agent(self, _agent_id):
            return self.agent

        def is_agent_not_found(self, _error):
            return False

    fleet = Fleet()
    orchestrator = InvestigatorOrchestrator(tmp_path, "inc-1", fresh=True, fleet=fleet)
    reports = {
        "H-CHANGE": {"hypothesis_id": "H-CHANGE", "verdict": "supported"},
        "H-DEPENDENCY": {"hypothesis_id": "H-DEPENDENCY", "verdict": "rejected"},
        "H-CAPACITY": {"hypothesis_id": "H-CAPACITY", "verdict": "rejected"},
    }
    result = orchestrator._adjudicate(reports)
    assert result["decision"]["accepted_hypothesis"] == "H-CHANGE"
    assert "Your decision was rejected." in fleet.agent.prompts[1]
    assert 'You accepted `"H-DEPENDENCY"`' in fleet.agent.prompts[1]
    assert "Eligible now: H-CHANGE: post-validation verdict supported" in fleet.agent.prompts[1]
    assert "{accepted}" not in fleet.agent.prompts[1]
    assert "{eligible}" not in fleet.agent.prompts[1]
