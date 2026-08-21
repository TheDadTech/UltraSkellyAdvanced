from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class OnboardingState(BaseModel):
    network_choice_made: bool = False
    network_mode: Literal["hotspot", "home"] = "hotspot"
    disclaimer_accepted: bool = False


class OnboardingStore:
    """Persist the intentionally small, non-secret first-boot state."""

    def __init__(self, data_dir: Path, helper: Path, *, enabled: bool) -> None:
        self.path = data_dir / "onboarding.json"
        self.helper = helper
        self.enabled = enabled

    def load(self) -> OnboardingState:
        if not self.path.exists():
            return OnboardingState()
        try:
            return OnboardingState.model_validate_json(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return OnboardingState()

    def save(self, state: OnboardingState) -> OnboardingState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return state

    def public_status(self, *, prop_configured: bool) -> dict[str, object]:
        state = self.load()
        if not self.enabled:
            phase = "complete"
        elif not state.network_choice_made:
            phase = "network"
        elif not state.disclaimer_accepted:
            phase = "disclaimer"
        elif not prop_configured:
            phase = "pairing"
        else:
            phase = "complete"
        return {
            "enabled": self.enabled,
            "phase": phase,
            "network_mode": state.network_mode,
            "network_choice_made": state.network_choice_made,
            "disclaimer_accepted": state.disclaimer_accepted,
            "hotspot": {"ssid": "UltraSkellyAdvanced-Setup", "password": "dadtech1"},
        }

    def choose_offline(self) -> OnboardingState:
        state = self.load().model_copy(
            update={"network_choice_made": True, "network_mode": "hotspot"}
        )
        return self.save(state)

    def connect_wifi(self, ssid: str, password: str) -> OnboardingState:
        self._run("wifi-connect", ssid, input_text=password)
        state = self.load().model_copy(
            update={"network_choice_made": True, "network_mode": "home"}
        )
        return self.save(state)

    def scan_wifi(self) -> list[dict[str, object]]:
        output = self._run("wifi-list")
        networks: list[dict[str, object]] = []
        for line in output.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("ssid"):
                networks.append(item)
        return networks

    def refresh_wifi(self) -> None:
        self._run("wifi-refresh")

    def wifi_status(self) -> dict[str, object]:
        try:
            payload = json.loads(self._run("wifi-status"))
        except (RuntimeError, ValueError):
            payload = {"mode": self.load().network_mode, "last_result": None}
        return payload if isinstance(payload, dict) else {}

    def use_hotspot(self) -> OnboardingState:
        self._run("wifi-hotspot")
        return self.save(
            self.load().model_copy(
                update={"network_choice_made": True, "network_mode": "hotspot"}
            )
        )

    def prepare_bluetooth(self) -> None:
        self._run("bluetooth-prepare")

    def accept_disclaimer(self) -> OnboardingState:
        return self.save(
            self.load().model_copy(update={"disclaimer_accepted": True})
        )

    def ssh_status(self) -> dict[str, object]:
        try:
            output = self._run("ssh-status").strip()
        except RuntimeError:
            output = "disabled"
        return {
            "enabled": output == "enabled",
            "username": "dadtech",
            "hostname": "usa-controller",
        }

    def enable_ssh(self, password: str, *, persistent: bool) -> dict[str, object]:
        self._run("ssh-enable", "persistent" if persistent else "temporary", input_text=password)
        return self.ssh_status()

    def disable_ssh(self) -> dict[str, object]:
        self._run("ssh-disable")
        return self.ssh_status()

    def system_action(self, action: Literal["service-restart", "reboot", "shutdown"]) -> None:
        self._run(action)

    def _run(self, action: str, *arguments: str, input_text: str | None = None) -> str:
        if not self.helper.exists():
            raise RuntimeError("This system control is only available on a USA image")
        result = subprocess.run(
            ["sudo", "-n", str(self.helper), action, *arguments],
            input=(f"{input_text}\n" if input_text is not None else None),
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "The system request failed")
        return result.stdout
