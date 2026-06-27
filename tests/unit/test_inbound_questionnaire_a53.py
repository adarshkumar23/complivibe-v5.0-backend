from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/inbound-questionnaires"


def _create_session(client, headers: dict[str, str], *, title: str = "Inbound Sheet") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "title": title,
            "sender_name": "Customer Security Team",
            "sender_email": "security@example.com",
            "description": "Quarterly security questionnaire",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_item(
    client,
    headers: dict[str, str],
    session_id: str,
    *,
    question_text: str,
    category_tag: str | None = None,
    framework_ref: str | None = None,
    question_type: str = "yes_no",
    order_index: int = 0,
) -> dict:
    payload = {
        "question_text": question_text,
        "question_type": question_type,
        "order_index": order_index,
    }
    if category_tag is not None:
        payload["category_tag"] = category_tag
    if framework_ref is not None:
        payload["framework_ref"] = framework_ref

    response = client.post(f"{BASE}/{session_id}/items", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _draft_item(client, headers: dict[str, str], session_id: str, item_id: str) -> dict:
    response = client.post(f"{BASE}/{session_id}/items/{item_id}/draft", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_a53_sourcing_evidence_control_cert_policy_and_no_source(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-source")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Sources")

    evidence_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Do you enforce MFA for privileged accounts?",
        category_tag="access_control_mfa",
        order_index=0,
    )
    control_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Which control maps to SOC2 CC6.1?",
        framework_ref="SOC2 CC6.1",
        order_index=1,
    )
    cert_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Do you maintain SOC 2 certification?",
        order_index=2,
    )
    policy_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Describe privileged access policy controls.",
        order_index=3,
    )
    no_source_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Explain your quantum-resistant key schedule.",
        order_index=4,
    )

    now = datetime.now(UTC)

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="MFA Enforcement Screenshot",
            description="Privileged account MFA policy evidence.",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=now - timedelta(days=5),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        )
    )

    framework = Framework(
        code="SOC2_A53",
        name="SOC 2",
        description="SOC2",
        category="Security",
        jurisdiction="US",
        authority="AICPA",
        version="2017",
        status="active",
        coverage_level="starter",
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        reference_code="SOC2 CC6.1",
        title="MFA control",
        description="Require MFA",
        jurisdiction="US",
        status="active",
    )
    db_session.add(obligation)
    db_session.flush()

    control = Control(
        organization_id=org_id,
        title="Privileged Access Control",
        description="Implemented privileged control",
        control_type="process",
        status="implemented",
        criticality="high",
        source="custom",
    )
    db_session.add(control)
    db_session.flush()

    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=control.id,
            obligation_id=obligation.id,
            mapping_type="supports",
            confidence="manual_confirmed",
            status="active",
        )
    )

    db_session.add(
        ComplianceCertification(
            organization_id=org_id,
            name="SOC 2 Type II",
            certification_type="soc2",
            status="active",
            issued_at=date.today() - timedelta(days=30),
            valid_until=date.today() + timedelta(days=335),
            created_by=user_id,
        )
    )

    db_session.add(
        CompliancePolicy(
            organization_id=org_id,
            title="Privileged Access Policy",
            description="Policy requires privileged access approvals and MFA.",
            policy_type="access_control",
            status="approved",
            owner_user_id=user_id,
            version="1.0",
        )
    )
    db_session.commit()

    drafted_evidence = _draft_item(client, org["org_headers"], session["id"], evidence_item["id"])
    assert drafted_evidence["source_type"] == "evidence"
    assert drafted_evidence["confidence_score"] >= 35
    assert drafted_evidence["suggested_answer_text"].startswith("Yes. Based on")
    assert drafted_evidence["requires_human_review"] is True

    drafted_control = _draft_item(client, org["org_headers"], session["id"], control_item["id"])
    assert drafted_control["source_type"] == "control"
    assert drafted_control["confidence_score"] >= 25

    drafted_cert = _draft_item(client, org["org_headers"], session["id"], cert_item["id"])
    assert drafted_cert["source_type"] == "certification"
    assert drafted_cert["confidence_score"] >= 25

    drafted_policy = _draft_item(client, org["org_headers"], session["id"], policy_item["id"])
    assert drafted_policy["source_type"] == "policy"
    assert drafted_policy["confidence_score"] >= 15

    drafted_none = _draft_item(client, org["org_headers"], session["id"], no_source_item["id"])
    assert drafted_none["suggested_answer_text"] == (
        "Manual review required. No supporting evidence, "
        "policy, or certification was found for this item."
    )
    assert drafted_none["confidence_score"] == 0
    assert drafted_none["status"] == "needs_review"
    assert drafted_none["source_type"] is None
    assert drafted_none["requires_human_review"] is True


def test_a53_confidence_recent_old_expired_and_unapproved_not_primary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-confidence")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Confidence")

    recent_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="MFA recent evidence",
        category_tag="access_control_mfa",
        order_index=0,
    )
    old_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Patching old evidence",
        category_tag="patch_management",
        order_index=1,
    )
    expired_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Old expired source",
        category_tag="incident_response",
        order_index=2,
    )
    unapproved_item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Draft evidence should not match",
        category_tag="draft_only",
        order_index=3,
    )

    now = datetime.now(UTC)
    rows = [
            EvidenceItem(
                organization_id=org_id,
            title="Recent MFA Evidence",
            description="Recent mfa proof",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=now - timedelta(days=10),
                uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        ),
            EvidenceItem(
                organization_id=org_id,
            title="Old Patch Evidence",
            description="Old patch proof",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=now - timedelta(days=120),
                uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "patch_management"},
        ),
            EvidenceItem(
                organization_id=org_id,
            title="Expired IR Evidence",
            description="Expired IR proof",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="expired",
            collected_at=now - timedelta(days=140),
                uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "incident_response"},
        ),
            EvidenceItem(
                organization_id=org_id,
            title="Draft Evidence",
            description="Should not be used",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="not_reviewed",
            freshness_status="current",
            collected_at=now - timedelta(days=3),
                uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "draft_only"},
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    recent = _draft_item(client, org["org_headers"], session["id"], recent_item["id"])
    assert recent["confidence_score"] >= 45

    old = _draft_item(client, org["org_headers"], session["id"], old_item["id"])
    assert old["confidence_score"] == 35

    expired = _draft_item(client, org["org_headers"], session["id"], expired_item["id"])
    assert expired["confidence_score"] == 5

    unapproved = _draft_item(client, org["org_headers"], session["id"], unapproved_item["id"])
    assert unapproved["source_id"] is None
    assert unapproved["confidence_score"] == 0


def test_a53_safety_no_fabricated_answers_and_no_llm_imports(client):
    org = bootstrap_org_user(client, email_prefix="a53-safety")
    session = _create_session(client, org["org_headers"], title="A53 Safety")
    item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Do you support zero-touch SCITT notarization?",
        category_tag="nonexistent_control",
    )

    drafted = _draft_item(client, org["org_headers"], session["id"], item["id"])
    assert drafted["requires_human_review"] is True
    assert drafted["status"] == "needs_review"
    assert drafted["source_type"] is None

    with open("app/compliance/services/inbound_questionnaire_service.py", "r", encoding="utf-8") as handle:
        source = handle.read().lower()
    assert "openai" not in source
    assert "anthropic" not in source
    assert "groq" not in source
    assert "embedding" not in source


def test_a53_review_workflow_mark_sent_and_complete_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-review")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Review")
    item1 = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="MFA evidence review",
        category_tag="access_control_mfa",
        order_index=0,
    )
    item2 = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Second review item",
        category_tag="incident_response",
        order_index=1,
    )

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Review Evidence",
            description="review evidence",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=datetime.now(UTC) - timedelta(days=3),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        )
    )
    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Review Evidence 2",
            description="review evidence 2",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=datetime.now(UTC) - timedelta(days=12),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "incident_response"},
        )
    )
    db_session.commit()

    _draft_item(client, org["org_headers"], session["id"], item1["id"])
    _draft_item(client, org["org_headers"], session["id"], item2["id"])

    approve = client.post(
        f"{BASE}/{session['id']}/items/{item1['id']}/review",
        headers=org["org_headers"],
        json={"action": "approve", "review_notes": "Approved as is"},
    )
    assert approve.status_code == 200
    approve_body = approve.json()
    assert approve_body["status"] == "approved"
    assert approve_body["final_answer_text"]
    assert approve_body["reviewer_id"] == org["user_id"]

    edit = client.post(
        f"{BASE}/{session['id']}/items/{item2['id']}/review",
        headers=org["org_headers"],
        json={"action": "edit", "edited_answer": "Edited and approved", "review_notes": "Custom"},
    )
    assert edit.status_code == 200
    assert edit.json()["status"] == "approved"
    assert edit.json()["final_answer_text"] == "Edited and approved"

    reject = client.post(
        f"{BASE}/{session['id']}/items/{item2['id']}/review",
        headers=org["org_headers"],
        json={"action": "reject", "review_notes": "Rejected"},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
    assert reject.json()["final_answer_text"] is None

    mark_rejected = client.post(
        f"{BASE}/{session['id']}/items/{item2['id']}/mark-sent",
        headers=org["org_headers"],
    )
    assert mark_rejected.status_code == 422

    complete_with_rejected = client.post(f"{BASE}/{session['id']}/complete", headers=org["org_headers"])
    assert complete_with_rejected.status_code == 422

    pending_session = _create_session(client, org["org_headers"], title="Pending Guard")
    pending_item = _add_item(
        client,
        org["org_headers"],
        pending_session["id"],
        question_text="Unreviewed item",
        category_tag="x",
    )
    assert pending_item["status"] == "pending"

    complete_pending = client.post(f"{BASE}/{pending_session['id']}/complete", headers=org["org_headers"])
    assert complete_pending.status_code == 422


def test_a53_mark_sent_and_complete_allows_approved_or_sent_only(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-send")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Send")
    item = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="MFA send flow",
        category_tag="access_control_mfa",
    )

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Send Flow Evidence",
            description="send evidence",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=datetime.now(UTC) - timedelta(days=1),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        )
    )
    db_session.commit()

    _draft_item(client, org["org_headers"], session["id"], item["id"])
    approve = client.post(
        f"{BASE}/{session['id']}/items/{item['id']}/review",
        headers=org["org_headers"],
        json={"action": "approve"},
    )
    assert approve.status_code == 200

    sent = client.post(f"{BASE}/{session['id']}/items/{item['id']}/mark-sent", headers=org["org_headers"])
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    complete = client.post(f"{BASE}/{session['id']}/complete", headers=org["org_headers"])
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"


def test_a53_draft_all_integration_counts_and_human_review(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-all")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Draft All")

    item_evidence = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Do you enforce MFA?",
        category_tag="access_control_mfa",
        order_index=0,
    )
    item_policy = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Describe privileged access policy controls.",
        order_index=1,
    )
    _ = _add_item(
        client,
        org["org_headers"],
        session["id"],
        question_text="Explain lattice cryptography rollouts.",
        order_index=2,
    )

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Draft All Evidence",
            description="MFA implemented",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=datetime.now(UTC) - timedelta(days=5),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        )
    )
    db_session.add(
        CompliancePolicy(
            organization_id=org_id,
            title="Privileged Access Policy",
            description="Privileged access control expectations and approvals.",
            policy_type="access_control",
            status="approved",
            owner_user_id=user_id,
            version="1.0",
        )
    )
    db_session.commit()

    drafted_all = client.post(f"{BASE}/{session['id']}/draft-all", headers=org["org_headers"])
    assert drafted_all.status_code == 200
    body = drafted_all.json()
    assert body["drafted"] == 2
    assert body["needs_review"] == 1
    assert body["no_source"] == 1

    items = client.get(f"{BASE}/{session['id']}/items", headers=org["org_headers"])
    assert items.status_code == 200
    assert len(items.json()) == 3
    assert all(row["requires_human_review"] is True for row in items.json())

    # sanity: sourced evidence item stays deterministic and sourced
    drafted_item_ids = {row["id"] for row in items.json() if row["source_type"] is not None}
    assert item_evidence["id"] in drafted_item_ids
    assert item_policy["id"] in drafted_item_ids


def test_a53_summary_distribution(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-summary")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])
    session = _create_session(client, org["org_headers"], title="A53 Summary")
    _ = _add_item(client, org["org_headers"], session["id"], question_text="mfa", category_tag="access_control_mfa", order_index=0)
    _ = _add_item(client, org["org_headers"], session["id"], question_text="none", order_index=1)

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Summary Evidence",
            description="summary",
            evidence_type="audit_report",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            collected_at=datetime.now(UTC) - timedelta(days=1),
            uploaded_by_user_id=user_id,
            metadata_json={"category_tag": "access_control_mfa"},
        )
    )
    db_session.commit()

    draft_all = client.post(f"{BASE}/{session['id']}/draft-all", headers=org["org_headers"])
    assert draft_all.status_code == 200

    summary = client.get(f"{BASE}/{session['id']}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_questions"] == 2
    assert payload["source_type_distribution"]["evidence"] == 1
    assert payload["source_type_distribution"]["no_source"] == 1
