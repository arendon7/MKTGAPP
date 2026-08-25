from binario_marketing.service_post_w99_evidence_observability_app import compose_evidence_observability


AS_OF = "2026-08-24T20:00:00+00:00"


def test_future_snapshot_is_partial_and_never_declared_fresh_or_stale():
    payload = compose_evidence_observability(
        company={"id": "c1"},
        results={
            "latest_snapshot": {"created_at": "2026-08-25T20:00:00+00:00"},
            "summary": {"campaigns": 1},
            "campaigns": [],
        },
        outcomes={"summary": {}, "campaigns": []},
        review={"summary": {}, "campaigns": []},
        projected_at=AS_OF,
    )
    snapshot = payload["domains"][0]
    assert snapshot["status"] == "PARTIAL"
    assert snapshot["freshness"]["classification"] == "FUTURE_OBSERVATION"
    assert snapshot["freshness"]["fresh"] is None
    assert snapshot["freshness"]["stale"] is None


def test_attribution_only_campaign_signal_does_not_inherit_marketing_snapshot_timestamp():
    payload = compose_evidence_observability(
        company={"id": "c1"},
        results={
            "latest_snapshot": {"created_at": "2026-08-24T18:00:00+00:00"},
            "summary": {"campaigns": 1},
            "campaigns": [{
                "campaign": {"id": "camp-1"},
                "evidence": {"has_signal": True, "observed": False},
                "attribution": {"attributed_opportunities": 1},
            }],
        },
        outcomes={"summary": {}, "campaigns": []},
        review={"summary": {}, "campaigns": []},
        projected_at=AS_OF,
    )
    campaign = {row["key"]: row for row in payload["domains"]}["CAMPAIGN_EVIDENCE"]
    assert campaign["status"] == "OBSERVED"
    assert campaign["coverage"]["with_signal"] == 1
    assert campaign["coverage"]["with_observed_marketing"] == 0
    assert campaign["freshness"]["observed_at"] is None
    assert campaign["freshness"]["classification"] == "NO_OBSERVATION_TIMESTAMP"
