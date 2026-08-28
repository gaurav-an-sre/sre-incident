"""The only module that imports the Cursor SDK."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEMO_TAG, MODEL, REPO_URL


@dataclass
class CloudFleet:
    repo: Path
    api_key: str | None = None
    repo_url: str = REPO_URL
    model: str = MODEL
    client: Any = None

    def _sdk(self) -> Any:
        import cursor_sdk  # type: ignore[import-not-found]

        return cursor_sdk

    def _resolve_client(self) -> Any:
        if self.client is not None:
            return self.client
        sdk = self._sdk()
        kwargs = {"allow_api_key_env_fallback": True}
        try:
            self.client = sdk.Client(**kwargs)
        except (TypeError, AttributeError, ImportError):
            bridge = sdk.Bridge.launch(workspace=str(self.repo))
            self.client = sdk.Client(bridge.endpoint, **kwargs)
        return self.client

    def create_agent(
        self,
        role: str,
        incident_id: str,
        hypothesis_id: str = "",
        *,
        starting_ref: str | None = None,
        auto_create_pr: bool = False,
    ) -> Any:
        sdk = self._sdk()
        cloud = sdk.CloudAgentOptions(
            repos=[
                sdk.CloudRepository(
                    url=self.repo_url,
                    starting_ref=starting_ref,
                )
            ],
            auto_create_pr=auto_create_pr,
            metadata={
                "demo": DEMO_TAG,
                "incident": incident_id,
                "role": role,
                "hypothesis": hypothesis_id,
            },
        )
        kwargs = {
            "model": self.model,
            "api_key": self.api_key,
            "name": f"{role} investigation {incident_id}",
            "cloud": cloud,
        }
        try:
            return sdk.Agent.create(**kwargs)
        except (TypeError, AttributeError, ImportError):
            return self._resolve_client().create_agent(**kwargs)

    def resume_agent(self, agent_id: str) -> Any:
        sdk = self._sdk()
        try:
            return sdk.Agent.resume(agent_id)
        except (TypeError, AttributeError, ImportError):
            return self._resolve_client().resume_agent(agent_id)

    def list_agents(self) -> list[Any]:
        sdk = self._sdk()
        try:
            result = sdk.Agent.list()
        except (TypeError, AttributeError, ImportError):
            result = self._resolve_client().list_agents()
        items = list(getattr(result, "items", result) or [])
        return [
            item
            for item in items
            if dict(getattr(item, "metadata", {})).get("demo") == DEMO_TAG
        ]

    def is_agent_not_found(self, error: BaseException) -> bool:
        sdk = self._sdk()
        error_type = getattr(sdk, "AgentNotFoundError", None)
        if error_type is not None:
            return isinstance(error, error_type)
        return "agent_not_found" in str(error).lower()
