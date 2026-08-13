from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


SERVICE = "com.sistemabinario.marketing.meta"


class MetaCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialStatus:
    configured: bool
    source: str
    writable: bool


class MetaCredentialStore:
    """Resolve Meta credentials without ever persisting them in project/application JSON."""

    def __init__(self, helper: Path | None = None):
        configured = os.environ.get("BINARIO_META_KEYCHAIN_HELPER", "").strip()
        self.helper = Path(helper or configured).expanduser() if (helper or configured) else None

    def _helper_ready(self) -> bool:
        return bool(self.helper and self.helper.is_file() and os.access(self.helper, os.X_OK))

    def _run_helper(self, command: str, *, secret: str | None = None) -> subprocess.CompletedProcess[str]:
        if not self._helper_ready():
            raise MetaCredentialError("native Meta Keychain helper is unavailable")
        try:
            return subprocess.run(
                [str(self.helper), command],
                input=secret,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
                env={"PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MetaCredentialError(f"native Meta Keychain helper failed: {type(exc).__name__}") from None

    def read(self) -> str | None:
        env_token = os.environ.get("META_ACCESS_TOKEN", "").strip()
        if env_token:
            return env_token
        if not self._helper_ready():
            return None
        result = self._run_helper("get")
        if result.returncode == 3:
            return None
        if result.returncode != 0:
            raise MetaCredentialError("unable to read Meta token from macOS Keychain")
        token = result.stdout.strip()
        return token or None

    def status(self) -> CredentialStatus:
        if os.environ.get("META_ACCESS_TOKEN", "").strip():
            return CredentialStatus(True, "environment", self._helper_ready())
        if not self._helper_ready():
            return CredentialStatus(False, "none", False)
        result = self._run_helper("status")
        if result.returncode != 0:
            raise MetaCredentialError("unable to inspect macOS Keychain")
        configured = result.stdout.strip() == "configured"
        return CredentialStatus(configured, "keychain" if configured else "none", True)

    def write(self, token: str) -> CredentialStatus:
        clean = str(token or "").strip()
        if not clean:
            raise ValueError("Meta access token is required")
        if len(clean) > 8192:
            raise ValueError("Meta access token is unexpectedly large")
        result = self._run_helper("set", secret=clean)
        if result.returncode != 0:
            raise MetaCredentialError("unable to save Meta token in macOS Keychain")
        return CredentialStatus(True, "keychain", True)

    def delete(self) -> CredentialStatus:
        if not self._helper_ready():
            if os.environ.get("META_ACCESS_TOKEN", "").strip():
                raise MetaCredentialError("Meta token is supplied by environment and cannot be removed by the app")
            return CredentialStatus(False, "none", False)
        result = self._run_helper("delete")
        if result.returncode != 0:
            raise MetaCredentialError("unable to remove Meta token from macOS Keychain")
        configured = bool(os.environ.get("META_ACCESS_TOKEN", "").strip())
        return CredentialStatus(configured, "environment" if configured else "none", True)
