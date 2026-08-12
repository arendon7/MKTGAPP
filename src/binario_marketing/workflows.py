from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Recipe:
    id: str
    steps: tuple[str, ...]


class WorkflowEngine:
    def __init__(self, handlers: dict[str, Callable[[dict], dict]]):
        self.handlers = dict(handlers)

    def run(self, recipe: Recipe, context: dict) -> dict:
        state = dict(context)
        trace: list[dict] = []
        for step in recipe.steps:
            handler = self.handlers.get(step)
            if handler is None:
                raise KeyError(f"unknown workflow step: {step}")
            state = handler(state)
            trace.append({"step": step, "status": "PASS"})
        state["_trace"] = trace
        return state
