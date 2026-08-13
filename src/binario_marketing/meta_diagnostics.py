from __future__ import annotations

from typing import Any

from .meta_credentials import MetaCredentialStore
from .meta_graph import MetaGraphClient, MetaGraphError


_EXPECTED_PERMISSIONS = {
    "instagram_publish": (
        "pages_show_list",
        "instagram_basic",
        "instagram_content_publish",
        "pages_read_engagement",
    ),
    "instagram_insights": (
        "instagram_basic",
        "instagram_manage_insights",
        "pages_read_engagement",
    ),
    "ads_read": ("ads_read",),
    "ads_create": ("ads_management",),
}

_PAGE_SUPER_TASKS = {"PROFILE_PLUS_FULL_CONTROL", "PROFILE_PLUS_MANAGE", "MANAGE"}
_CREATE_TASKS = {"PROFILE_PLUS_CREATE_CONTENT", "CREATE_CONTENT"} | _PAGE_SUPER_TASKS
_ANALYZE_TASKS = {"PROFILE_PLUS_ANALYZE", "ANALYZE"} | _PAGE_SUPER_TASKS
_ADVERTISE_TASKS = {"PROFILE_PLUS_ADVERTISE", "ADVERTISE"} | _PAGE_SUPER_TASKS


def _permission_inventory(client: MetaGraphClient) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "granted": [],
        "declined": [],
        "expired": [],
        "unknown": [],
        "error": None,
    }
    try:
        payload = client._request("GET", "me/permissions")
    except MetaGraphError as exc:
        result["error"] = str(exc)
        return result
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        result["error"] = "Meta returned an invalid permissions inventory"
        return result
    buckets = {"granted": [], "declined": [], "expired": [], "unknown": []}
    for row in rows:
        if not isinstance(row, dict):
            continue
        permission = str(row.get("permission") or "").strip()
        if not permission:
            continue
        status = str(row.get("status") or "unknown").strip().lower()
        bucket = status if status in buckets else "unknown"
        buckets[bucket].append(permission)
    result.update({key: sorted(set(value)) for key, value in buckets.items()})
    result["available"] = True
    return result


def _missing(expected: tuple[str, ...], granted: set[str], inventory_available: bool) -> list[str]:
    if not inventory_available:
        return []
    return [name for name in expected if name not in granted]


def _page_capabilities(tasks: list[str]) -> dict[str, bool]:
    values = {str(item).strip().upper() for item in tasks if str(item).strip()}
    return {
        "create_content": bool(values & _CREATE_TASKS),
        "analyze": bool(values & _ANALYZE_TASKS),
        "advertise": bool(values & _ADVERTISE_TASKS),
    }


def _check(check_id: str, state: str, title: str, detail: str, action: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"id": check_id, "state": state, "title": title, "detail": detail}
    if action:
        row["action"] = action
    return row


class MetaDiagnostics:
    """Capability-first, read-only Meta UAT diagnostics with no credential echo."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    @classmethod
    def from_env(cls) -> "MetaDiagnostics":
        return cls(MetaGraphClient.from_env())

    def report(self) -> dict[str, Any]:
        credential = MetaCredentialStore().status()
        permissions = _permission_inventory(self.client)
        granted = set(permissions["granted"])
        expected = {key: list(value) for key, value in _EXPECTED_PERMISSIONS.items()}
        missing = {
            key: _missing(value, granted, permissions["available"])
            for key, value in _EXPECTED_PERMISSIONS.items()
        }
        checks: list[dict[str, Any]] = []

        identity: dict[str, str] | None = None
        try:
            identity = self.client.identity()
            checks.append(_check("identity", "PASS", "Token reconocido", f"Meta respondió como {identity.get('name') or identity.get('id')}."))
        except MetaGraphError as exc:
            checks.append(_check("identity", "FAIL", "Token no utilizable", str(exc), "Reconecta Meta con un token vigente para la app correcta."))
            return {
                "status": "ACTION_REQUIRED",
                "graph_version": self.client.graph_version,
                "credential_source": credential.source,
                "identity": None,
                "permissions": {**permissions, "expected": expected, "missing": missing},
                "pages": [],
                "ad_accounts": [],
                "ready": {
                    "facebook_publish": False,
                    "instagram_publish": False,
                    "instagram_insights": False,
                    "ads_read": False,
                    "ads_create": False,
                },
                "checks": checks,
                "security": {"token_included": False, "mutation_performed": False},
            }

        pages: list[dict[str, Any]] = []
        page_error: str | None = None
        try:
            payload = self.client._request(
                "GET",
                "me/accounts",
                {"fields": "id,name,tasks,instagram_business_account{id,username}"},
            )
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                raise MetaGraphError("Meta returned an invalid Pages list")
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                tasks = [str(item) for item in (row.get("tasks") or []) if isinstance(item, str)]
                instagram = row.get("instagram_business_account")
                pages.append({
                    "id": str(row["id"]),
                    "name": str(row.get("name") or ""),
                    "tasks": sorted(set(tasks)),
                    "capabilities": _page_capabilities(tasks),
                    "instagram": {
                        "id": str(instagram.get("id")),
                        "username": str(instagram.get("username") or ""),
                    } if isinstance(instagram, dict) and instagram.get("id") else None,
                })
        except MetaGraphError as exc:
            page_error = str(exc)

        if page_error:
            checks.append(_check("pages", "FAIL", "Páginas no disponibles", page_error, "Revisa acceso a Páginas y el permiso pages_show_list."))
        elif not pages:
            checks.append(_check("pages", "FAIL", "Sin Páginas administrables", "El token funciona, pero Meta no devolvió Páginas administrables.", "Asigna acceso a una Página y vuelve a conectar."))
        else:
            checks.append(_check("pages", "PASS", "Páginas detectadas", f"{len(pages)} Página(s) disponibles con tareas de acceso visibles."))

        ig_pages = [page for page in pages if page["instagram"]]
        if ig_pages:
            checks.append(_check("instagram_link", "PASS", "Instagram profesional vinculado", f"{len(ig_pages)} Página(s) tienen una cuenta profesional de Instagram vinculada."))
        else:
            checks.append(_check("instagram_link", "WARN", "Instagram no vinculado", "No se encontró una cuenta profesional de Instagram vinculada a las Páginas disponibles.", "Vincula una cuenta Business/Creator a una Página de Facebook."))

        ad_accounts: list[dict[str, Any]] = []
        ad_error: str | None = None
        try:
            ad_accounts = self.client.ad_accounts()
        except MetaGraphError as exc:
            ad_error = str(exc)
        if ad_error:
            checks.append(_check("ads", "WARN", "Cuentas Ads no disponibles", ad_error, "Revisa acceso a la cuenta publicitaria y permisos ads_read / ads_management."))
        elif ad_accounts:
            checks.append(_check("ads", "PASS", "Cuentas Ads detectadas", f"{len(ad_accounts)} cuenta(s) publicitaria(s) disponibles."))
        else:
            checks.append(_check("ads", "WARN", "Sin cuentas Ads", "Meta respondió sin cuentas publicitarias disponibles para esta credencial.", "Asigna acceso a una cuenta publicitaria si vas a completar el UAT de pauta."))

        if permissions["available"]:
            missing_any = sorted({name for values in missing.values() for name in values})
            if missing_any:
                checks.append(_check("permissions", "WARN", "Permisos incompletos", ", ".join(missing_any), "Regenera el token incluyendo sólo los permisos necesarios para el flujo que vas a usar."))
            else:
                checks.append(_check("permissions", "PASS", "Permisos esperados presentes", "El inventario del token incluye los permisos esperados por los flujos habilitados."))
        else:
            checks.append(_check("permissions", "WARN", "Inventario de permisos no disponible", permissions.get("error") or "Meta no devolvió el inventario de permisos.", "Usa los checks funcionales de activos como fuente principal y revisa el token en las herramientas de Meta si persiste un bloqueo."))

        content_pages = [page for page in pages if page["capabilities"]["create_content"]]
        analyze_ig = [page for page in ig_pages if page["capabilities"]["analyze"]]
        advertise_pages = [page for page in pages if page["capabilities"]["advertise"]]
        inventory_available = bool(permissions["available"])
        permission_ok = lambda key: (not inventory_available) or not missing[key]

        ready = {
            "facebook_publish": bool(content_pages),
            "instagram_publish": bool(ig_pages and content_pages and permission_ok("instagram_publish")),
            "instagram_insights": bool(analyze_ig and permission_ok("instagram_insights")),
            "ads_read": bool(ad_accounts and permission_ok("ads_read")),
            "ads_create": bool(ad_accounts and advertise_pages and permission_ok("ads_create")),
        }
        core_ready = ready["facebook_publish"] and ready["ads_read"] and ready["ads_create"]
        if core_ready:
            checks.append(_check("uat_core", "PASS", "UAT central listo", "Facebook publishing y la estructura Ads PAUSED tienen capacidades funcionales disponibles."))
        else:
            blocked = [key for key in ("facebook_publish", "ads_read", "ads_create") if not ready[key]]
            checks.append(_check("uat_core", "FAIL", "UAT central bloqueado", ", ".join(blocked), "Corrige los checks anteriores antes de intentar publicación real o crear la jerarquía de pauta."))
        status = "PASS" if core_ready and not any(row["state"] == "FAIL" for row in checks[:-1]) else "ACTION_REQUIRED"
        return {
            "status": status,
            "graph_version": self.client.graph_version,
            "credential_source": credential.source,
            "identity": identity,
            "permissions": {**permissions, "expected": expected, "missing": missing},
            "pages": pages,
            "ad_accounts": ad_accounts,
            "ready": ready,
            "checks": checks,
            "security": {"token_included": False, "mutation_performed": False},
        }


__all__ = ["MetaDiagnostics"]
