from __future__ import annotations

import json
import os
import platform
import plistlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .atomic import write_json_atomic
from .config import default_paths
from .meta_graph import MetaGraphClient
from .social_process_lock import SocialProcessLock
from .social_service import MetaSocialPublisher
from .social_store import SocialStore
from .workspace import Workspace


LAUNCH_AGENT_LABEL = "com.sistemabinario.marketing.social-scheduler"
LAUNCH_AGENT_INTERVAL_SECONDS = 60
APP_SUPPORT_DIR = "Binario Marketing IA"


@dataclass(frozen=True)
class BackgroundRunResult:
    status: str
    ran_at: str
    processed: int
    published: int
    failed: int
    recovered: int
    busy: bool
    error: str | None = None


@dataclass(frozen=True)
class BackgroundAgentStatus:
    platform_supported: bool
    installed: bool
    loaded: bool
    stale: bool
    plist_path: str
    app_bundle: str | None
    interval_seconds: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path() -> Path:
    return default_paths().state / "social-background" / "status.json"


def _save_run_status(result: BackgroundRunResult) -> None:
    write_json_atomic(_status_path(), asdict(result))


def social_background_last_run() -> dict | None:
    path = _status_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    allowed = {"status", "ran_at", "processed", "published", "failed", "recovered", "busy", "error"}
    return {key: payload.get(key) for key in allowed if key in payload}


def _record_results(workspace: Workspace, rows: list[dict]) -> None:
    for row in rows:
        status = str(row.get("status") or "").lower()
        if status not in {"published", "failed"}:
            continue
        workspace.registries.timeline.append(f"publication.{status}", {
            "project_id": row.get("project_id"),
            "publication_id": row.get("id"),
            "channel": row.get("channel"),
            "remote_id": row.get("remote_id"),
            "attempts": row.get("attempts"),
            "error": row.get("error"),
            "source": "background-worker",
        })


def run_social_background_once(*, limit: int = 20) -> BackgroundRunResult:
    if limit < 1 or limit > 100:
        raise ValueError("background social limit must be between 1 and 100")
    paths = default_paths()
    social = SocialStore(paths.state / "social")
    workspace = Workspace(paths.state / "workspace")
    try:
        connection = MetaGraphClient.diagnose_env()
    except Exception as exc:
        result = BackgroundRunResult(
            "ERROR", _now(), 0, 0, 0, 0, False,
            f"{type(exc).__name__}: credential diagnostics failed",
        )
        _save_run_status(result)
        return result
    if not connection.configured:
        result = BackgroundRunResult("NO_CREDENTIALS", _now(), 0, 0, 0, 0, False)
        _save_run_status(result)
        return result

    recovered = 0
    recovery_lock = SocialProcessLock(social.root)
    if recovery_lock.acquire():
        try:
            recovered_rows = social.recover_interrupted()
            recovered = len(recovered_rows)
            for row in recovered_rows:
                workspace.registries.timeline.append("publication.failed", {
                    "project_id": row.project_id,
                    "publication_id": row.id,
                    "channel": row.channel,
                    "remote_id": row.remote_id,
                    "attempts": row.attempts,
                    "error": row.error,
                    "source": "background-recovery",
                })
        finally:
            recovery_lock.release()
    else:
        result = BackgroundRunResult("BUSY", _now(), 0, 0, 0, 0, True)
        _save_run_status(result)
        return result

    try:
        rows = MetaSocialPublisher(social, MetaGraphClient.from_env()).run_due(limit=limit)
        _record_results(workspace, rows)
        published = sum(str(row.get("status")) == "PUBLISHED" for row in rows)
        failed = sum(str(row.get("status")) == "FAILED" for row in rows)
        result = BackgroundRunResult(
            "OK",
            _now(),
            len(rows),
            published,
            failed,
            recovered,
            False,
        )
    except Exception as exc:
        result = BackgroundRunResult(
            "ERROR",
            _now(),
            0,
            0,
            0,
            recovered,
            False,
            f"{type(exc).__name__}: publication cycle failed",
        )
    _save_run_status(result)
    return result


def worker_main() -> int:
    result = run_social_background_once()
    print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")))
    return 0 if result.status in {"OK", "BUSY", "NO_CREDENTIALS"} else 1


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_SUPPORT_DIR


def launch_agent_plist_path() -> Path:
    return _launch_agents_dir() / f"{LAUNCH_AGENT_LABEL}.plist"


def _infer_app_bundle() -> Path | None:
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.name.endswith(".app"):
            return parent
    return None


def _bundle_paths(app_bundle: Path) -> dict[str, Path]:
    app = app_bundle.expanduser().resolve()
    resources = app / "Contents" / "Resources"
    return {
        "app": app,
        "python": resources / "runtime" / "python" / "bin" / "python3",
        "source": resources / "source" / "src",
        "helper": app / "Contents" / "MacOS" / "binario-meta-keychain",
    }


def _validate_bundle(app_bundle: Path) -> dict[str, Path]:
    paths = _bundle_paths(app_bundle)
    if not paths["app"].is_dir():
        raise ValueError("Binario Marketing app bundle is unavailable")
    if not paths["python"].is_file() or not os.access(paths["python"], os.X_OK):
        raise ValueError("embedded Python runtime is unavailable")
    if not (paths["source"] / "binario_marketing" / "social_background.py").is_file():
        raise ValueError("background worker source is unavailable in the app bundle")
    if not paths["helper"].is_file() or not os.access(paths["helper"], os.X_OK):
        raise ValueError("Meta Keychain helper is unavailable")
    return paths


def _launchctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env={"PATH": "/usr/bin:/bin"},
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _write_worker_wrapper(source_root: Path) -> Path:
    support = _support_dir()
    support.mkdir(parents=True, exist_ok=True)
    wrapper = support / "social-worker.py"
    body = (
        "from __future__ import annotations\n"
        "import sys\n"
        f"sys.path.insert(0, {str(source_root)!r})\n"
        "from binario_marketing.social_background import worker_main\n"
        "raise SystemExit(worker_main())\n"
    )
    wrapper.write_text(body, encoding="utf-8")
    os.chmod(wrapper, 0o600)
    return wrapper


def _read_plist() -> dict | None:
    path = launch_agent_plist_path()
    if not path.is_file():
        return None
    try:
        payload = plistlib.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def social_background_status(*, runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _launchctl) -> BackgroundAgentStatus:
    plist_path = launch_agent_plist_path()
    supported = platform.system() == "Darwin"
    payload = _read_plist()
    installed = payload is not None
    app_bundle = None
    stale = False
    if payload:
        args = payload.get("ProgramArguments") or []
        python_path = Path(args[0]).expanduser() if isinstance(args, list) and args else None
        wrapper_path = Path(args[-1]).expanduser() if isinstance(args, list) and len(args) >= 2 else None
        helper_value = str((payload.get("EnvironmentVariables") or {}).get("BINARIO_META_KEYCHAIN_HELPER") or "").strip()
        helper_path = Path(helper_value).expanduser() if helper_value else None
        if python_path:
            for parent in python_path.parents:
                if parent.name.endswith(".app"):
                    app_bundle = str(parent)
                    break
        stale = not bool(
            python_path
            and python_path.is_file()
            and wrapper_path
            and wrapper_path.is_file()
            and helper_path
            and helper_path.is_file()
            and app_bundle
        )
    loaded = False
    if supported:
        result = runner(["print", f"{_domain()}/{LAUNCH_AGENT_LABEL}"])
        loaded = result.returncode == 0
    return BackgroundAgentStatus(
        supported,
        installed,
        loaded,
        stale,
        str(plist_path),
        app_bundle,
        LAUNCH_AGENT_INTERVAL_SECONDS,
    )


def social_background_overview(*, runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _launchctl) -> dict:
    return {
        "agent": asdict(social_background_status(runner=runner)),
        "last_run": social_background_last_run(),
    }


def install_social_background(
    app_bundle: Path | None = None,
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _launchctl,
) -> BackgroundAgentStatus:
    if platform.system() != "Darwin":
        raise ValueError("background social scheduling is only available on macOS")
    app = app_bundle or _infer_app_bundle()
    if app is None:
        raise ValueError("app bundle path is required outside the packaged macOS app")
    paths = _validate_bundle(app)
    wrapper = _write_worker_wrapper(paths["source"])
    support = _support_dir()
    logs = support / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin",
        "BINARIO_META_KEYCHAIN_HELPER": str(paths["helper"]),
    }
    configured_home = os.environ.get("BINARIO_IA_HOME", "").strip()
    if configured_home:
        env["BINARIO_IA_HOME"] = str(Path(configured_home).expanduser().resolve())
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(paths["python"]), "-I", "-B", str(wrapper)],
        "EnvironmentVariables": env,
        "StartInterval": LAUNCH_AGENT_INTERVAL_SECONDS,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "social-worker.log"),
        "StandardErrorPath": str(logs / "social-worker-error.log"),
    }
    launch_dir = _launch_agents_dir()
    launch_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agent_plist_path()
    temp = plist_path.with_suffix(".plist.tmp")
    temp.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))
    os.chmod(temp, 0o600)
    os.replace(temp, plist_path)

    runner(["bootout", f"{_domain()}/{LAUNCH_AGENT_LABEL}"])
    result = runner(["bootstrap", _domain(), str(plist_path)])
    if result.returncode != 0:
        try:
            plist_path.unlink()
        except FileNotFoundError:
            pass
        try:
            wrapper.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError((result.stderr or result.stdout or "launchctl bootstrap failed").strip())
    runner(["kickstart", f"{_domain()}/{LAUNCH_AGENT_LABEL}"])
    return social_background_status(runner=runner)


def uninstall_social_background(
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _launchctl,
) -> BackgroundAgentStatus:
    plist_path = launch_agent_plist_path()
    if platform.system() == "Darwin":
        runner(["bootout", f"{_domain()}/{LAUNCH_AGENT_LABEL}"])
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass
    wrapper = _support_dir() / "social-worker.py"
    try:
        wrapper.unlink()
    except FileNotFoundError:
        pass
    return social_background_status(runner=runner)


if __name__ == "__main__":
    raise SystemExit(worker_main())
