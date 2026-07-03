from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.commitment_notification_log import CommitmentNotificationLog
from app.models.customer_commitment import CustomerCommitment
from app.models.data_asset import DataAsset
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


VENDORS_BASE = "/api/v1/compliance/vendors"
COMMITMENT_BASE = "/api/v1/compliance/customer-commitments"
INCIDENT_BASE = "/api/v1/data-observability/incidents"
AI_VENDOR_BASE = "/api/v1/compliance/ai-vendor-assessments"
Q_RESP_BASE = "/api/v1/compliance/questionnaire-responses"
AI_TEMPLATE_NAME = "AI Vendor Governance Assessment"


def _create_vendor(client, headers: dict[str, str], owner_user_id: str, *, name: str) -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_vendor_assessment(client, headers: dict[str, str], vendor_id: str) -> dict:
    response = client.post(
        f"{VENDORS_BASE}/{vendor_id}/assessments",
        headers=headers,
        json={
            "title": "Auto Mitigation Assessment",
            "assessment_type": "initial",
            "overall_rating": "not_rated",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_data_asset(db_session, *, org_id: str, user_id: str, name: str) -> DataAsset:
    now = datetime.now(UTC)
    row = DataAsset(
        organization_id=uuid.UUID(org_id),
        name=name,
        asset_type="database",
        description="Source datastore",
        owner_id=uuid.UUID(user_id),
        custodian_id=uuid.UUID(user_id),
        sensitivity_tier="confidential",
        classification_type="personal_data",
        classification_confidence=0.95,
        classification_source="manual",
        classification_confirmed=True,
        geographic_locations=["US"],
        permitted_regions=["US"],
        schema_column_names=["id", "email"],
        retention_policy_days=365,
        retention_review_date=now.date(),
        data_volume_estimate="small",
        source_system="core",
        import_source="manual",
        import_key=None,
        tags=[],
        is_phi=False,
        hipaa_safeguard_required=None,
        status="active",
        created_by=uuid.UUID(user_id),
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _ai_template(db_session) -> QuestionnaireTemplate:
    SeedService.ensure_questionnaire_templates(db_session)
    row = db_session.execute(
        select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.organization_id.is_(None),
            QuestionnaireTemplate.is_system_template.is_(True),
            QuestionnaireTemplate.name == AI_TEMPLATE_NAME,
            QuestionnaireTemplate.is_active.is_(True),
            QuestionnaireTemplate.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    assert row is not None
    return row


def test_s4_p3_incident_triggers_matching_commitment(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-inc-match")

    commitment = client.post(
        COMMITMENT_BASE,
        headers=org["org_headers"],
        json={
            "customer_name": "Acme",
            "customer_email": "security@acme.example",
            "commitment_type": "breach_notification",
            "title": "Breach notify within 72h",
            "description": "Regulatory notification obligation",
            "trigger_condition": "security_incident notification workflow",
            "triggering_incident_type": "anomaly_rule",
            "trigger_date": None,
            "notification_days_before": 7,
            "sla_hours": 72,
            "assigned_owner_id": org["user_id"],
        },
    )
    assert commitment.status_code == 201
    commitment_id = commitment.json()["id"]

    asset = _create_data_asset(
        db_session,
        org_id=org["organization_id"],
        user_id=org["user_id"],
        name="Customer PI Database",
    )
    incident = client.post(
        INCIDENT_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": str(asset.id),
            "detector_type": "anomaly_rule",
            "title": "Suspicious data access",
            "description": "Unexpected read volume",
            "severity": "high",
            "detected_by": "manual",
        },
    )
    assert incident.status_code == 201

    row = db_session.get(CustomerCommitment, uuid.UUID(commitment_id))
    assert row is not None
    assert row.status == "triggered"
    assert row.triggered_at is not None

    notif = db_session.execute(
        select(CommitmentNotificationLog).where(
            CommitmentNotificationLog.organization_id == uuid.UUID(org["organization_id"]),
            CommitmentNotificationLog.commitment_id == row.id,
            CommitmentNotificationLog.notification_type == "triggered",
        )
    ).scalar_one_or_none()
    assert notif is not None

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "customer_commitment.incident_triggered",
            AuditLog.entity_id == row.id,
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_s4_p3_incident_non_matching_does_not_trigger(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-inc-nomatch")

    commitment = client.post(
        COMMITMENT_BASE,
        headers=org["org_headers"],
        json={
            "customer_name": "Beta",
            "customer_email": "security@beta.example",
            "commitment_type": "breach_notification",
            "title": "Retention breach workflow",
            "description": "Only retention violations should trigger",
            "trigger_condition": "retention_violation response",
            "triggering_incident_type": "retention_violation",
            "trigger_date": None,
            "notification_days_before": 7,
            "sla_hours": 24,
            "assigned_owner_id": org["user_id"],
        },
    )
    assert commitment.status_code == 201
    commitment_id = commitment.json()["id"]

    asset = _create_data_asset(
        db_session,
        org_id=org["organization_id"],
        user_id=org["user_id"],
        name="Telemetry Warehouse",
    )
    incident = client.post(
        INCIDENT_BASE,
        headers=org["org_headers"],
        json={
            "data_asset_id": str(asset.id),
            "detector_type": "anomaly_rule",
            "title": "Network anomaly",
            "description": "No retention issue",
            "severity": "medium",
            "detected_by": "manual",
        },
    )
    assert incident.status_code == 201

    row = db_session.get(CustomerCommitment, uuid.UUID(commitment_id))
    assert row is not None
    assert row.status == "active"
    assert row.triggered_at is None


def test_s4_p3_ai_vendor_assessment_auto_applies_template(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-ai-template")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="AI Vendor Auto")

    created = client.post(
        f"{AI_VENDOR_BASE}?vendor_id={vendor['id']}",
        headers=org["org_headers"],
        json={"ai_model_name": "Vendor LLM", "model_type": "llm"},
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    template = _ai_template(db_session)
    response = db_session.execute(
        select(VendorQuestionnaireResponse).where(
            VendorQuestionnaireResponse.organization_id == uuid.UUID(org["organization_id"]),
            VendorQuestionnaireResponse.vendor_id == uuid.UUID(vendor["id"]),
            VendorQuestionnaireResponse.template_id == template.id,
            VendorQuestionnaireResponse.deleted_at.is_(None),
        ).order_by(VendorQuestionnaireResponse.created_at.desc())
    ).scalars().first()
    assert response is not None

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "ai_vendor_assessment.template_auto_applied",
            AuditLog.entity_id == uuid.UUID(assessment_id),
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_s4_p3_ai_template_is_substantive(db_session):
    template = _ai_template(db_session)
    questions = db_session.execute(
        select(QuestionnaireTemplateQuestion).where(
            QuestionnaireTemplateQuestion.template_id == template.id
        )
    ).scalars().all()
    assert len(questions) >= 10
    assert all((q.question_text or "").strip() for q in questions)
    assert all("lorem" not in q.question_text.lower() for q in questions)
    assert all("placeholder" not in q.question_text.lower() for q in questions)


def test_s4_p3_scoring_above_threshold_auto_creates_mitigation_case(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-score-high")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="High Risk Vendor")
    assessment = _create_vendor_assessment(client, org["org_headers"], vendor["id"])
    template = _ai_template(db_session)

    created = client.post(
        Q_RESP_BASE,
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "template_id": str(template.id), "title": "AI Vendor Q1"},
    )
    assert created.status_code == 201
    response_id = created.json()["id"]

    detail = client.get(f"{Q_RESP_BASE}/{response_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    answers = [{"question_id": row["question_id"], "answer_value": "No", "answer_text": "No"} for row in detail.json()["answers"]]
    bulk = client.post(f"{Q_RESP_BASE}/{response_id}/answers/bulk", headers=org["org_headers"], json={"answers": answers})
    assert bulk.status_code == 200
    assert bulk.json()["score"] >= 70

    marker = f"[auto_response_id:{response_id}]"
    case = db_session.execute(
        select(VendorMitigationCase).where(
            VendorMitigationCase.organization_id == uuid.UUID(org["organization_id"]),
            VendorMitigationCase.vendor_id == uuid.UUID(vendor["id"]),
            VendorMitigationCase.assessment_id == uuid.UUID(assessment["id"]),
            VendorMitigationCase.description.ilike(f"%{marker}%"),
            VendorMitigationCase.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    assert case is not None

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "vendor_mitigation.auto_created_threshold_breach",
            AuditLog.entity_id == case.id,
        )
    ).scalar_one_or_none()
    assert audit is not None


def test_s4_p3_scoring_below_threshold_does_not_create_case(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-score-low")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Low Risk Vendor")
    _create_vendor_assessment(client, org["org_headers"], vendor["id"])
    template = _ai_template(db_session)

    created = client.post(
        Q_RESP_BASE,
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "template_id": str(template.id), "title": "AI Vendor Q2"},
    )
    assert created.status_code == 201
    response_id = created.json()["id"]

    detail = client.get(f"{Q_RESP_BASE}/{response_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    answers = [{"question_id": row["question_id"], "answer_value": "Yes", "answer_text": "Yes"} for row in detail.json()["answers"]]
    bulk = client.post(f"{Q_RESP_BASE}/{response_id}/answers/bulk", headers=org["org_headers"], json={"answers": answers})
    assert bulk.status_code == 200
    assert bulk.json()["score"] < 70

    marker = f"[auto_response_id:{response_id}]"
    case = db_session.execute(
        select(VendorMitigationCase).where(
            VendorMitigationCase.organization_id == uuid.UUID(org["organization_id"]),
            VendorMitigationCase.vendor_id == uuid.UUID(vendor["id"]),
            VendorMitigationCase.description.ilike(f"%{marker}%"),
            VendorMitigationCase.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    assert case is None


def test_s4_p3_no_duplicate_case_for_same_response(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p3-score-dedupe")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Dedup Vendor")
    _create_vendor_assessment(client, org["org_headers"], vendor["id"])
    template = _ai_template(db_session)

    created = client.post(
        Q_RESP_BASE,
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "template_id": str(template.id), "title": "AI Vendor Q3"},
    )
    assert created.status_code == 201
    response_id = created.json()["id"]

    detail = client.get(f"{Q_RESP_BASE}/{response_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    answers = [{"question_id": row["question_id"], "answer_value": "No", "answer_text": "No"} for row in detail.json()["answers"]]

    first = client.post(f"{Q_RESP_BASE}/{response_id}/answers/bulk", headers=org["org_headers"], json={"answers": answers})
    assert first.status_code == 200
    assert first.json()["score"] >= 70

    second = client.post(f"{Q_RESP_BASE}/{response_id}/answers/bulk", headers=org["org_headers"], json={"answers": answers})
    assert second.status_code == 200
    assert second.json()["score"] >= 70

    marker = f"[auto_response_id:{response_id}]"
    rows = db_session.execute(
        select(VendorMitigationCase).where(
            VendorMitigationCase.organization_id == uuid.UUID(org["organization_id"]),
            VendorMitigationCase.vendor_id == uuid.UUID(vendor["id"]),
            VendorMitigationCase.description.ilike(f"%{marker}%"),
            VendorMitigationCase.deleted_at.is_(None),
        )
    ).scalars().all()
    assert len(rows) == 1
