from __future__ import annotations

import os

from gateway.social_api import SocialQueueGatewayService
from gateway.social_supabase_storage import SupabaseSocialQueueStorage


def social_service() -> SocialQueueGatewayService:
    master = os.environ.get("BINARIO_GATEWAY_MASTER_SECRET", "")
    return SocialQueueGatewayService(SupabaseSocialQueueStorage(), master)


__all__ = ["social_service"]
