from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    required_env: tuple[str, ...]
    local: bool
    help_text: str


PROVIDERS = (
    ProviderSpec("openai", "OpenAI", ("OPENAI_API_KEY",), False, "Crea una API key en tu cuenta del proveedor y guárdala como variable de entorno; la app no debe persistirla en proyectos."),
    ProviderSpec("anthropic", "Anthropic", ("ANTHROPIC_API_KEY",), False, "Configura la API key como variable de entorno y valida la conexión antes de usarla en un workflow."),
    ProviderSpec("gemini", "Google Gemini", ("GEMINI_API_KEY",), False, "Configura la credencial como variable de entorno y prueba el provider desde Runtime Center."),
    ProviderSpec("ollama", "Ollama", (), True, "Provider local: verifica que el servicio local esté iniciado antes de seleccionar un modelo."),
)


def diagnose_provider(provider_id: str) -> dict:
    spec = next((item for item in PROVIDERS if item.id == provider_id), None)
    if spec is None:
        raise KeyError(provider_id)
    missing = [name for name in spec.required_env if not os.environ.get(name)]
    return {
        "id": spec.id,
        "name": spec.name,
        "configured": not missing,
        "missing": missing,
        "local": spec.local,
        "help": spec.help_text,
    }
