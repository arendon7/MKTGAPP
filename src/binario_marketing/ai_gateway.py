from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .ledger import JsonlLedger


@dataclass(frozen=True)
class GatewayRequest:
    provider: str
    model: str
    purpose: str
    prompt: str
    context_capsule: dict


@dataclass(frozen=True)
class GatewayResponse:
    text: str
    input_units: int
    output_units: int
    provider_request_id: str | None = None


class AIGateway:
    """Optional guarded gateway. Records usage and never writes canonical project memory."""

    def __init__(self, ledger_path: Path, adapters: dict[str, Callable[[GatewayRequest], GatewayResponse]] | None = None):
        self.ledger = JsonlLedger(ledger_path)
        self.adapters = dict(adapters or {})

    def register(self, provider: str, adapter: Callable[[GatewayRequest], GatewayResponse]) -> None:
        self.adapters[provider] = adapter

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.provider not in self.adapters:
            raise KeyError(f"provider adapter unavailable: {request.provider}")
        if not request.purpose.strip():
            raise ValueError("purpose is required")
        if not isinstance(request.context_capsule, dict):
            raise TypeError("context_capsule must be a dict")
        response = self.adapters[request.provider](request)
        self.ledger.append("ai.usage", {
            "provider": request.provider,
            "model": request.model,
            "purpose": request.purpose,
            "input_units": response.input_units,
            "output_units": response.output_units,
            "provider_request_id": response.provider_request_id,
            "canonical_memory_write": False,
        })
        return response
