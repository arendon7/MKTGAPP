from __future__ import annotations

from http import HTTPStatus

from .background_service import BackgroundServiceError


class BackgroundSchedulingHTTPMixin:
    def _background_error(self, exc: Exception) -> None:
        if isinstance(exc, BackgroundServiceError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._extension_error(exc)

    def _background_get(self, parts: list[str]) -> bool:
        if parts != ["api", "meta", "background"]:
            return False
        try:
            self._json(self.server.runtime.background_status())
        except Exception as exc:
            self._background_error(exc)
        return True

    def _background_post(self, parts: list[str]) -> bool:
        if parts == ["api", "meta", "background", "register"]:
            try:
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.background_register()
                self._json(result, HTTPStatus.CREATED)
            except Exception as exc:
                self._background_error(exc)
            return True
        if parts == ["api", "meta", "background", "open-settings"]:
            try:
                self._body()
                self._json(self.server.runtime.background_open_settings())
            except Exception as exc:
                self._background_error(exc)
            return True
        return False

    def _background_delete(self, parts: list[str]) -> bool:
        if parts != ["api", "meta", "background"]:
            return False
        try:
            with self.server.mutation_lock:
                result = self.server.runtime.background_unregister()
            self._json(result)
        except Exception as exc:
            self._background_error(exc)
        return True


__all__ = ["BackgroundSchedulingHTTPMixin"]
