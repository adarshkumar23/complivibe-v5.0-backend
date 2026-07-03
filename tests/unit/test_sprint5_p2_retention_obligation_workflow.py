from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.data_asset import DataAsset
from app.models.data_asset_obligation_link import DataAssetObligationLink
from app.models.data_obligation_suggestion import DataObligationSuggestion
from app.models.data_retention_review import DataRetentionReview
from app.models.framework import Framework
from app.models.obligation import Obligation
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
RETENTION_BASE = "/api/v1/data-observability/retention"
SUGGESTIONS_BASE = "/api/v1/data-observability/obligation-suggestions"


def _create_asset(client, headers: dict[str, str], owner_id: str, *, name: str) -> str:
    response = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "Asset for sprint 5 prompt 2 tests",
            "schema_column_names": ["customer_id", "email"],
            "permitted_regions": ["US"],
            "classification_type": "personal_data",
            "sensitivity_tier": "confidential",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_policy(client, headers: dict[str, str], *, retention_days: int = 30, legal_hold: bool = False) -> str:
    response = client.post(
        f"{RETENTION_BASE}/policies",
        headers=headers,
        json={
            "name": f"Retention {retention_days}",
            "retention_days": retention_days,
            "action_on_expiry": "flag",
            "legal_hold": legal_hold,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _apply_policy(client, headers: dict[str, str], policy_id: str, asset_id: str) -> None:
    response = client.post(
        f"{RETENTION_BASE}/policies/{policy_id}/apply-to-asset",
        headers=headers,
        json={"data_asset_id": asset_id},
    )
    assert response.status_code == 200


def _seed_framework_and_obligation(db_session, *, code: str, name: str, ref: str, title: str) -> Obligation:
    framework = Framework(
        code=code,
        name=name,
        description=f"{name} framework",
        category="Privacy",
        jurisdiction="International",
        authority=name,
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=None,
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        framework_section_id=None,
        reference_code=ref,
        title=title,
        description=title,
        plain_language_summary=None,
        obligation_type="requirement",
        jurisdiction="International",
        source_url=None,
        version="1.0",
        status="active",
        effective_date=None,
        parent_obligation_id=None,
    )
    db_session.add(obligation)
    db_session.commit()
    db_session.refresh(obligation)
    return obligation


def test_s5_p2_retention_legal_hold_and_org_wide_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p2-ret")
    asset_hold = _create_asset(client, org["org_headers"], org["user_id"], name="asset_hold")
    asset_open = _create_asset(client, org["org_headers"], org["user_id"], name="asset_open")
    asset_orgwide_1 = _create_asset(client, org["org_headers"], org["user_id"], name="asset_orgwide_1")
    asset_orgwide_2 = _create_asset(client, org["org_headers"], org["user_id"], name="asset_orgwide_2")

    hold_policy_id = _create_policy(client, org["org_headers"], retention_days=31, legal_hold=False)
    open_policy_id = _create_policy(client, org["org_headers"], retention_days=30, legal_hold=False)
    orgwide_policy_id = _create_policy(client, org["org_headers"], retention_days=15, legal_hold=False)

    _apply_policy(client, org["org_headers"], hold_policy_id, asset_hold)
    _apply_policy(client, org["org_headers"], open_policy_id, asset_open)
    _apply_policy(client, org["org_headers"], orgwide_policy_id, asset_orgwide_1)
    _apply_policy(client, org["org_headers"], orgwide_policy_id, asset_orgwide_2)

    old_review_date = (datetime.now(UTC) - timedelta(days=15)).date()
    for asset_id in (asset_hold, asset_open, asset_orgwide_1, asset_orgwide_2):
        row = db_session.get(DataAsset, uuid.UUID(asset_id))
        assert row is not None
        row.retention_review_date = old_review_date
    db_session.commit()

    # (a) legal_hold=true skips retention action.
    hold_resp = client.post(
        f"{RETENTION_BASE}/{hold_policy_id}/legal-hold",
        headers=org["org_headers"],
        json={"legal_hold": True},
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["legal_hold"] is True

    sweep = client.post(f"{RETENTION_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep.status_code == 200

    hold_reviews = db_session.execute(
        select(DataRetentionReview).where(
            DataRetentionReview.organization_id == uuid.UUID(org["organization_id"]),
            DataRetentionReview.data_asset_id == uuid.UUID(asset_hold),
        )
    ).scalars().all()
    assert hold_reviews == []

    # (b) non-legal-hold expired assets are still enforced.
    open_reviews = db_session.execute(
        select(DataRetentionReview).where(
            DataRetentionReview.organization_id == uuid.UUID(org["organization_id"]),
            DataRetentionReview.data_asset_id == uuid.UUID(asset_open),
        )
    ).scalars().all()
    assert len(open_reviews) == 1

    # (c) org-wide policy behavior (one policy applies to multiple assets).
    orgwide_reviews = db_session.execute(
        select(DataRetentionReview).where(
            DataRetentionReview.organization_id == uuid.UUID(org["organization_id"]),
            DataRetentionReview.data_asset_id.in_([uuid.UUID(asset_orgwide_1), uuid.UUID(asset_orgwide_2)]),
        )
    ).scalars().all()
    assert len(orgwide_reviews) == 2


def test_s5_p2_obligation_suggestions_generate_apply_dismiss_and_cross_org(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s5p2-obl-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p2-obl-b")
    asset_id = _create_asset(client, org_a["org_headers"], org_a["user_id"], name="asset_obl")

    _seed_framework_and_obligation(
        db_session,
        code="GDPR",
        name="GDPR",
        ref="GDPR-ART30",
        title="Records of processing activities",
    )
    _seed_framework_and_obligation(
        db_session,
        code="INDIA_DPDP",
        name="India DPDP",
        ref="DPDP-SEC8",
        title="Data fiduciary obligations",
    )

    # (d) Persisted generation with dedupe on repeat.
    gen_1 = client.post(f"{ASSETS_BASE}/{asset_id}/suggest-obligations", headers=org_a["org_headers"])
    assert gen_1.status_code == 200
    body_1 = gen_1.json()
    assert len(body_1) >= 2
    assert all(item["status"] == "pending" for item in body_1)

    gen_2 = client.post(f"{ASSETS_BASE}/{asset_id}/suggest-obligations", headers=org_a["org_headers"])
    assert gen_2.status_code == 200
    body_2 = gen_2.json()
    assert len(body_2) == len(body_1)

    persisted_count = db_session.execute(
        select(DataObligationSuggestion).where(
            DataObligationSuggestion.organization_id == uuid.UUID(org_a["organization_id"]),
            DataObligationSuggestion.data_asset_id == uuid.UUID(asset_id),
        )
    ).scalars().all()
    assert len(persisted_count) == len(body_1)

    pending_suggestion_id = body_1[0]["id"]
    dismiss_suggestion_id = body_1[1]["id"] if len(body_1) > 1 else body_1[0]["id"]

    # (e) Apply suggestion -> real link + status + audit.
    apply_resp = client.post(f"{SUGGESTIONS_BASE}/{pending_suggestion_id}/apply", headers=org_a["org_headers"])
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "applied"

    linked = db_session.execute(
        select(DataAssetObligationLink).where(
            DataAssetObligationLink.organization_id == uuid.UUID(org_a["organization_id"]),
            DataAssetObligationLink.data_asset_id == uuid.UUID(asset_id),
            DataAssetObligationLink.obligation_id == uuid.UUID(apply_resp.json()["obligation_id"]),
        )
    ).scalar_one_or_none()
    assert linked is not None

    apply_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_a["organization_id"]),
            AuditLog.action == "data_obligation.suggestion_applied",
            AuditLog.entity_id == uuid.UUID(pending_suggestion_id),
        )
    ).scalar_one_or_none()
    assert apply_audit is not None

    # (f) Dismiss suggestion -> status + audit.
    dismiss_resp = client.post(f"{SUGGESTIONS_BASE}/{dismiss_suggestion_id}/dismiss", headers=org_a["org_headers"])
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["status"] == "dismissed"

    dismiss_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_a["organization_id"]),
            AuditLog.action == "data_obligation.suggestion_dismissed",
            AuditLog.entity_id == uuid.UUID(dismiss_suggestion_id),
        )
    ).scalar_one_or_none()
    assert dismiss_audit is not None

    # (g) Cross-org access to suggestion actions -> 404.
    cross_apply = client.post(f"{SUGGESTIONS_BASE}/{pending_suggestion_id}/apply", headers=org_b["org_headers"])
    assert cross_apply.status_code == 404
    cross_dismiss = client.post(f"{SUGGESTIONS_BASE}/{dismiss_suggestion_id}/dismiss", headers=org_b["org_headers"])
    assert cross_dismiss.status_code == 404

    # Cross-org list isolation: org B must never receive org A suggestion rows.
    cross_list = client.get(
        f"{SUGGESTIONS_BASE}?data_asset_id={asset_id}",
        headers=org_b["org_headers"],
    )
    assert cross_list.status_code in (200, 404)
    if cross_list.status_code == 200:
        suggestion_ids_org_a = {pending_suggestion_id, dismiss_suggestion_id}
        returned_ids = {row["id"] for row in cross_list.json()}
        assert returned_ids.isdisjoint(suggestion_ids_org_a)
