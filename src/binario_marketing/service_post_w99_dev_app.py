"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.

Current terminal: service_post_w99_execution_owner_relay_app, which extends
service_post_w99_campaign_results_owner_handoff_app and preserves every prior layer.
"""

from .service_post_w99_execution_owner_relay_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
