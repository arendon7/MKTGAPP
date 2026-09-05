"""Stable explicit entrypoint for the evolving post-W99 development chain.

Canonical release `serve` remains separate. New post-W99 product increments should
advance this alias rather than teaching the CLI about every individual feature.
"""

# Cumulative prior terminals retained explicitly for auditability:
# service_post_w99_campaign_execution_owner_cardinality_hardening_app
# service_post_w99_planned_only_actionability_app
# service_post_w99_setup_shadow_action_deduplication_app
# service_post_w99_campaign_media_candidate_selection_handoff_app
# service_post_w99_campaign_coordinate_actionability_app
# service_post_w99_campaign_attention_actionability_app
# Immediate parents retained as explicit compatibility imports for cumulative audits.
from .service_post_w99_setup_readiness_owner_handoff_app import (
    AppRuntime as _SetupReadinessAppRuntime,
)
from .service_post_w99_campaign_execution_owner_drift_guard_app import (
    AppRuntime as _OwnerDriftAppRuntime,
)
from .service_post_w99_operator_session_progress_app import (
    AppRuntime as _OperatorSessionProgressAppRuntime,
)
from .service_post_w99_operator_current_priority_continuity_app import (
    AppRuntime as _OperatorCurrentPriorityContinuityAppRuntime,
)
from .service_post_w99_operator_return_evidence_delta_app import (
    AppRuntime as _OperatorReturnEvidenceDeltaAppRuntime,
)
from .service_post_w99_operator_session_evidence_integration_app import (
    AppRuntime as _OperatorSessionEvidenceIntegrationAppRuntime,
)
from .service_post_w99_primary_navigation_app import (
    AppRuntime as _PrimaryNavigationAppRuntime,
)
from .service_post_w99_social_background_control_app import (
    AppRuntime as _SocialBackgroundControlAppRuntime,
)
from .service_post_w99_today_portfolio_app import (
    AppRuntime,
    MarketingHandler,
    MarketingHTTPServer,
    create_server,
    serve,
)

__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
