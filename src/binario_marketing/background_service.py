from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

from .config import default_paths


_COMMANDS = {"status", "register", "unregister", "open-settings"}


class BackgroundServiceError(RuntimeError):
    pass


class BackgroundServiceManager:
    """Use only the bundled SMAppService helper to manage the app LaunchAgent."""

    def __init__(self, helper: Path | None = None, data_root: Path | None = None):
        configured = os.environ.get("BINARIO_BACKGROUND_SERVICE_HELPER", "").strip()
        self.helper = Path(helper or configured).expanduser() if (helper or configured) else None
        self.data_root = (data_root or default_paths().home).expanduser().resolve()

    def _supported(self) -> bool:
        if platform.system() != "Darwin":
            return False
        try:
            return int((platform.mac_ver()[0] or "0").split(".", 1)[0]) >= 13
        except ValueError:
            return False

    def _helper_ready(self) -> bool:
        return bool(self.helper and self.helper.is_file() and os.access(self.helper, os.X_OK))

    def _run_helper(self, command: str) -> dict:
        if command not in _COMMANDS:
            raise ValueError("unsupported background service command")
        if not self._supported():
            raise BackgroundServiceError("background scheduling requires macOS 13 or newer")
        if not self._helper_ready():
            raise BackgroundServiceError("background scheduling helper is unavailable")
        try:
            result = subprocess.run(
                [str(self.helper), command],
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
                env={"PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackgroundServiceError(f"background service helper failed: {type(exc).__name__}") from None
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            raise BackgroundServiceError("background service helper returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise BackgroundServiceError("background service helper returned an invalid payload")
        if result.returncode != 0:
            raise BackgroundServiceError(str(payload.get("error") or "background service helper failed")[:1000])
        return payload

    def _latest_agent_status(self) -> dict | None:
        path = self.data_root / "State" / "background_social" / "status.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"error": "background agent status is unreadable"}
        return payload if isinstance(payload, dict) else {"error": "background agent status is invalid"}

    def status(self) -> dict:
        supported = self._supported()
        helper_available = self._helper_ready()
        registration = "unsupported" if not supported else "helper-unavailable"
        requires_approval = False
        error = None
        if supported and helper_available:
            try:
                payload = self._run_helper("status")
                registration = str(payload.get("status") or "unknown")
                requires_approval = bool(payload.get("requires_approval"))
            except BackgroundServiceError as exc:
                registration = "error"
                error = str(exc)
        return {
            "supported": supported,
            "minimum_macos": 13,
            "helper_available": helper_available,
            "registration": registration,
            "enabled": registration == "enabled",
            "requires_approval": requires_approval,
            "error": error,
            "last_agent_run": self._latest_agent_status(),
            "cadence_seconds": 60,
            "timing": "best-effort",
        }

    def register(self) -> dict:
        self._run_helper("register")
        return self.status()

    def unregister(self) -> dict:
        self._run_helper("unregister")
        return self.status()

    def open_settings(self) -> dict:
        self._run_helper("open-settings")
        return self.status()


__all__ = ["BackgroundServiceError", "BackgroundServiceManager"]
