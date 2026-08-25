"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.

The current terminal inherits `service_post_w99_evidence_observability_integrated_app`
through Contextual Action Handoff, preserving the previously certified evidence layer.
"""

from .service_post_w99_contextual_action_handoff_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
