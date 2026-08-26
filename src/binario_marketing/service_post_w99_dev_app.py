"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.
The current terminal extends service_post_w99_campaign_execution_owner_cardinality_hardening_app
through the explicit MEDIA candidate-selection handoff; the parent contract remains accumulated.
"""

from .service_post_w99_campaign_media_candidate_selection_handoff_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
