from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.compliance.services.gdpr_ropa_builder import GDPRArticle30Builder
from app.models.data_asset import DataAsset
from app.models.dpia import DPIA
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.processing_activity import ProcessingActivity
from app.models.subprocessor import Subprocessor
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/privacy/ropa"


def _create_framework(db_session, code: str, name: str) -> Framework:
    existing = db_session.query(Framework).filter(Framework.code == code).first()
    if existing is not None:
        return existing
    row = Framework(
        code=code,
        name=name,
        description=f"{name} framework",
        category="Privacy",
        jurisdiction="EU",
        authority=name,
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_obligation(db_session, framework_id: uuid.UUID, ref: str, title: str) -> Obligation:
    row = Obligation(
        framework_id=framework_id,
        framework_section_id=None,
        reference_code=ref,
        title=title,
        description=title,
        plain_language_summary=None,
        obligation_type="requirement",
        jurisdiction="EU",
        source_url=None,
        version="1.0",
        status="active",
        effective_date=None,
        parent_obligation_id=None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_activity(client, headers: dict[str, str], owner_id: str, **overrides):
    payload = {
        "name": "Customer Support Processing",
        "description": "Handles customer support tickets",
        "purpose": "Resolve customer incidents",
        "legal_basis": "contract",
        "data_categories": ["name", "email"],
        "special_categories": [],
        "data_subject_types": ["customers"],
        "retention_period": "2 years",
        "recipients": ["support team"],
        "international_transfers": False,
        "status": "active",
        "risk_level": "low",
        "owner_id": owner_id,
        "linked_data_asset_ids": [],
        "linked_subprocessor_ids": [],
    }
    payload.update(overrides)
    response = client.post(f"{BASE}/activities", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _activity_payload(owner_id: str, **overrides) -> dict:
    payload = {
        "name": "Cross tenant probe",
        "description": "Attempts to store foreign references",
        "purpose": "Security validation",
        "legal_basis": "contract",
        "data_categories": ["email"],
        "special_categories": [],
        "data_subject_types": ["customers"],
        "retention_period": "2 years",
        "recipients": ["support team"],
        "international_transfers": False,
        "status": "active",
        "risk_level": "low",
        "owner_id": owner_id,
        "linked_data_asset_ids": [],
        "linked_subprocessor_ids": [],
    }
    payload.update(overrides)
    return payload


def test_d83_ropa_activity_obligation_and_report(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d83-org")

    created = _create_activity(client, org["org_headers"], org["user_id"]) 
    assert created["name"] == "Customer Support Processing"
    assert created["requires_dpia"] is False

    with_special = _create_activity(
        client,
        org["org_headers"],
        org["user_id"],
        name="Health processing",
        special_categories=["health"],
    )
    assert with_special["requires_dpia"] is True

    with_high_risk = _create_activity(
        client,
        org["org_headers"],
        org["user_id"],
        name="High risk processing",
        risk_level="high",
    )
    assert with_high_risk["requires_dpia"] is True

    fw = _create_framework(db_session, code="GDPR", name="GDPR")
    obligation = _create_obligation(db_session, fw.id, "GDPR-ART-30", "Records of processing activities")

    link = client.post(
        f"{BASE}/activities/{created['id']}/obligation-links",
        headers=org["org_headers"],
        json={"obligation_id": str(obligation.id)},
    )
    assert link.status_code == 201

    duplicate = client.post(
        f"{BASE}/activities/{created['id']}/obligation-links",
        headers=org["org_headers"],
        json={"obligation_id": str(obligation.id)},
    )
    assert duplicate.status_code == 409

    links = client.get(f"{BASE}/activities/{created['id']}/obligation-links", headers=org["org_headers"])
    assert links.status_code == 200
    assert len(links.json()) == 1

    summary = client.get(f"{BASE}/activities/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["requires_dpia_count"] == 2

    report = client.get(f"{BASE}/article30-report", headers=org["org_headers"])
    assert report.status_code == 200
    report_body = report.json()
    assert report_body["status"] == "complete"
    assert report_body["report_type"] == "gdpr_article30_ropa"
    assert report_body["total_activities"] >= 3
    assert isinstance(report_body["activities"], list)

    gdpr_payload = GDPRArticle30Builder.build(uuid.UUID(org["organization_id"]), db_session)
    assert gdpr_payload["status"] == "complete"

    unlink = client.delete(
        f"{BASE}/activities/{created['id']}/obligation-links/{obligation.id}",
        headers=org["org_headers"],
    )
    assert unlink.status_code == 204

    links_after = client.get(f"{BASE}/activities/{created['id']}/obligation-links", headers=org["org_headers"])
    assert links_after.status_code == 200
    assert links_after.json() == []


def test_d83_soft_delete_requires_discontinued_and_org_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="d83-org-a")
    org_b = bootstrap_org_user(client, email_prefix="d83-org-b")

    activity = _create_activity(client, org_a["org_headers"], org_a["user_id"]) 

    delete_active = client.delete(f"{BASE}/activities/{activity['id']}", headers=org_a["org_headers"])
    assert delete_active.status_code == 422

    updated = client.patch(
        f"{BASE}/activities/{activity['id']}",
        headers=org_a["org_headers"],
        json={"status": "discontinued"},
    )
    assert updated.status_code == 200

    delete_ok = client.delete(f"{BASE}/activities/{activity['id']}", headers=org_a["org_headers"])
    assert delete_ok.status_code == 200
    assert delete_ok.json()["deleted_at"] is not None

    foreign_get = client.get(f"{BASE}/activities/{activity['id']}", headers=org_b["org_headers"])
    assert foreign_get.status_code == 404


def test_d83_rejects_cross_tenant_owner_and_linked_references(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="d83-cross-a")
    org_b = bootstrap_org_user(client, email_prefix="d83-cross-b")

    foreign_activity = _create_activity(
        client,
        org_b["org_headers"],
        org_b["user_id"],
        name="Foreign DPIA Activity",
    )
    now = datetime.now(UTC)
    foreign_dpia = DPIA(
        organization_id=uuid.UUID(org_b["organization_id"]),
        processing_activity_id=uuid.UUID(foreign_activity["id"]),
        title="Foreign DPIA",
        status="draft",
        risks_identified=[],
        mitigation_measures=[],
        dpo_consulted=False,
        supervisory_authority_consulted=False,
        created_by=uuid.UUID(org_b["user_id"]),
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    foreign_asset = DataAsset(
        organization_id=uuid.UUID(org_b["organization_id"]),
        name="Foreign Asset",
        asset_type="database",
        owner_id=uuid.UUID(org_b["user_id"]),
        custodian_id=None,
        geographic_locations=[],
        permitted_regions=[],
        tags=[],
        is_phi=False,
        status="active",
        created_by=uuid.UUID(org_b["user_id"]),
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    foreign_subprocessor = Subprocessor(
        organization_id=uuid.UUID(org_b["organization_id"]),
        name="Foreign Subprocessor",
        service_description="Processes support data",
        data_types_processed=["email"],
        legal_basis="contract",
        geographic_locations=["US"],
        data_transfer_mechanism="sccs",
        dpa_status="signed",
        controller_type="processor",
        risk_level="medium",
        status="active",
        created_by=uuid.UUID(org_b["user_id"]),
        deleted_at=None,
    )
    db_session.add_all([foreign_dpia, foreign_asset, foreign_subprocessor])
    db_session.commit()

    bad_owner = client.post(
        f"{BASE}/activities",
        headers=org_a["org_headers"],
        json=_activity_payload(org_b["user_id"], name="Foreign owner probe"),
    )
    assert bad_owner.status_code == 422
    assert "owner_id" in bad_owner.json()["detail"]

    bad_dpia = client.post(
        f"{BASE}/activities",
        headers=org_a["org_headers"],
        json=_activity_payload(org_a["user_id"], linked_dpia_id=str(foreign_dpia.id)),
    )
    assert bad_dpia.status_code == 422
    assert "linked_dpia_id" in bad_dpia.json()["detail"]

    bad_asset = client.post(
        f"{BASE}/activities",
        headers=org_a["org_headers"],
        json=_activity_payload(org_a["user_id"], linked_data_asset_ids=[str(foreign_asset.id)]),
    )
    assert bad_asset.status_code == 422
    assert "linked_data_asset_ids" in bad_asset.json()["detail"]

    bad_subprocessor = client.post(
        f"{BASE}/activities",
        headers=org_a["org_headers"],
        json=_activity_payload(org_a["user_id"], linked_subprocessor_ids=[str(foreign_subprocessor.id)]),
    )
    assert bad_subprocessor.status_code == 422
    assert "linked_subprocessor_ids" in bad_subprocessor.json()["detail"]

    org_a_poisoned_rows = (
        db_session.query(ProcessingActivity)
        .filter(
            ProcessingActivity.organization_id == uuid.UUID(org_a["organization_id"]),
            ProcessingActivity.name == "Cross tenant probe",
        )
        .count()
    )
    assert org_a_poisoned_rows == 0
