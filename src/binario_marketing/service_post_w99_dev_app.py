"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.
"""

# Cumulative prior terminals retained explicitly for auditability:
# service_post_w99_campaign_execution_owner_cardinality_hardening_app
# service_post_w99_planned_only_actionability_app
from .service_post_w99_setup_shadow_action_deduplication_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
