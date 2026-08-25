"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.

Current terminal: `service_post_w99_contextual_action_handoff_app`.
It inherits `service_post_w99_portfolio_cadence_app`, which inherits
`service_post_w99_evidence_observability_integrated_app`, preserving both
previously certified post-W99 layers instead of replacing them.
"""

from .service_post_w99_contextual_action_handoff_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
