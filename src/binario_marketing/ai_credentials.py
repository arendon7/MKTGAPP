from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


CLOUD_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
AI_PROVIDERS = ("openai", "anthropic", "gemini", "ollama")


class AICredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class AICredentialStatus:
    provider: str
    configured: bool
    source: str
    writable: bool
    local: bool


class AICredentialStore:
    """Read cloud AI keys from env or the native Keychain helper.

    Secrets never enter project/application JSON. Ollama is local and needs no API key.
    """

    def __init__(self, helper: Path | None = None):
        configured = os.environ.get("BINARIO_KEYCHAIN_HELPER", "").strip()
        meta_helper = os.environ.get("BINARIO_META_KEYCHAIN_HELPER", "").strip()
        selected = helper or (Path(configured).expanduser() if configured else None) or (Path(meta_helper).expanduser() if meta_helper else None)
        self.helper = Path(selected).expanduser() if selected else None

    @staticmethod
    def _provider(provider: str) -> str:
        value = str(provider or "").strip().lower()
        if value not in AI_PROVIDERS:
            raise ValueError("unsupported AI provider")
        return value

    def _helper_ready(self) -> bool:
        return bool(self.helper and self.helper.is_file() and os.access(self.helper, os.X_OK))

    def _run_helper(self, command: str, provider: str, *, secret: str | None = None) -> subprocess.CompletedProcess[str]:
        provider = self._provider(provider)
        if provider == "ollama":
            raise AICredentialError("Ollama does not use a cloud API key")
        if not self._helper_ready():
            raise AICredentialError("native AI Keychain helper is unavailable")
        try:
            return subprocess.run(
                [str(self.helper), command, provider],
                input=secret,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
                env={"PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AICredentialError(f"native AI Keychain helper failed: {type(exc).__name__}") from None

    def read(self, provider: str) -> str | None:
        provider = self._provider(provider)
        if provider == "ollama":
            return None
        env_name = CLOUD_PROVIDER_ENV[provider]
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value
        if not self._helper_ready():
            return None
        result = self._run_helper("get", provider)
        if result.returncode == 3:
            return None
        if result.returncode != 0:
            raise AICredentialError(f"unable to read {provider} API key from macOS Keychain")
        return result.stdout.strip() or None

    def status(self, provider: str) -> AICredentialStatus:
        provider = self._provider(provider)
        if provider == "ollama":
            return AICredentialStatus(provider, True, "local", False, True)
        env_name = CLOUD_PROVIDER_ENV[provider]
        if os.environ.get(env_name, "").strip():
            return AICredentialStatus(provider, True, "environment", self._helper_ready(), False)
        if not self._helper_ready():
            return AICredentialStatus(provider, False, "none", False, False)
        result = self._run_helper("status", provider)
        if result.returncode != 0:
            raise AICredentialError("unable to inspect macOS Keychain")
        configured = result.stdout.strip() == "configured"
        return AICredentialStatus(provider, configured, "keychain" if configured else "none", True, False)

    def write(self, provider: str, api_key: str) -> AICredentialStatus:
        provider = self._provider(provider)
        if provider == "ollama":
            raise AICredentialError("Ollama local mode does not need an API key")
        clean = str(api_key or "").strip()
        if not clean:
            raise ValueError("API key is required")
        if len(clean) > 8192:
            raise ValueError("API key is unexpectedly large")
        env_name = CLOUD_PROVIDER_ENV[provider]
        if os.environ.get(env_name, "").strip():
            raise AICredentialError(f"{provider} connection is controlled by {env_name}")
        result = self._run_helper("set", provider, secret=clean)
        if result.returncode != 0:
            raise AICredentialError(f"unable to save {provider} API key in macOS Keychain")
        return AICredentialStatus(provider, True, "keychain", True, False)

    def delete(self, provider: str) -> AICredentialStatus:
        provider = self._provider(provider)
        if provider == "ollama":
            return AICredentialStatus(provider, True, "local", False, True)
        env_name = CLOUD_PROVIDER_ENV[provider]
        if os.environ.get(env_name, "").strip():
            raise AICredentialError(f"{provider} API key is supplied by environment and cannot be removed by the app")
        if not self._helper_ready():
            return AICredentialStatus(provider, False, "none", False, False)
        result = self._run_helper("delete", provider)
        if result.returncode != 0:
            raise AICredentialError(f"unable to remove {provider} API key from macOS Keychain")
        return AICredentialStatus(provider, False, "none", True, False)


__all__ = [
    "AI_PROVIDERS",
    "AICredentialError",
    "AICredentialStatus",
    "AICredentialStore",
    "CLOUD_PROVIDER_ENV",
]
