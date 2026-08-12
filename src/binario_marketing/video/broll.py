from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrollAsset:
    id: str
    tags: tuple[str, ...]


def contextual_broll(text: str, assets: list[BrollAsset], limit: int = 3) -> list[BrollAsset]:
    tokens = {token.strip(".,:;!?¡¿()[]{}\"'").lower() for token in text.split()}
    scored = []
    for asset in assets:
        score = len(tokens & {tag.lower() for tag in asset.tags})
        if score:
            scored.append((score, asset.id, asset))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit]]
