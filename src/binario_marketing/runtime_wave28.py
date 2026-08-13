from __future__ import annotations

from pathlib import Path

from . import service_wave27 as base
from .background_service import BackgroundServiceManager
from .social_process_lock import social_queue_lock
from .wave28_background import install_wave28_scheduler


class AppRuntime(base.AppRuntime):
    """Wave 27 runtime with coordinated desktop and periodic social execution."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        install_wave28_scheduler(runtime)
        runtime.background_service = BackgroundServiceManager(data_root=runtime.data_root)
        return runtime

    def publish_publication_now(self, project_id: str, publication_id: str) -> dict:
        with social_queue_lock(self.social.root, timeout=2.0) as acquired:
            if not acquired:
                raise ValueError("social queue is busy; retry publication in a moment")
            return super().publish_publication_now(project_id, publication_id)

    def background_status(self) -> dict:
        return self.background_service.status()

    def background_register(self) -> dict:
        return self.background_service.register()

    def background_unregister(self) -> dict:
        return self.background_service.unregister()

    def background_open_settings(self) -> dict:
        return self.background_service.open_settings()


__all__ = ["AppRuntime"]
