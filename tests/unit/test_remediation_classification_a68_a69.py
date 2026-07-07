from __future__ import annotations

import uuid
from pathlib import Path

from app.compliance.engines.classification_engine import ClassificationEngine
from app.compliance.engines.remediation_engine import GENERIC_SUGGESTIONS, REMEDIATION_TEMPLATES, RemediationEngine
from app.models.email_outbox import EmailOutbox
from app.models.incident_classification import IncidentClassification
from app.models.issue import Issue
from app.models.remediation_suggestion import RemediationSuggestion
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user


ISSUES_BASE = "/api/v1/compliance/issues"
INCIDENTS_BASE = "/api/v1/compliance/incidents"


def _create_issue(client, headers: dict[str, str], owner_id: str, *, issue_type: str, severity: str = "high") -> dict:
    resp = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": f"{issue_type}-{severity}",
            "description": "Issue description",
            "issue_type": issue_type,
            "severity": severity,
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_control(client, headers: dict[str, str], *, title: str, control_type: str = "process") -> dict:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": control_type, "criticality": "high"},
    )
    assert resp.status_code == 201
    return resp.json()


def test_a68_remediation_engine_and_service_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a68-main")

    issue = _create_issue(client, org["org_headers"], org["user_id"], issue_type="data_loss", severity="high")

    # No linked control => (issue_type, None) fallback suggestions.
    generated = client.post(f"{ISSUES_BASE}/{issue['id']}/generate-suggestions", headers=org["org_headers"])
    assert generated.status_code == 200
    suggestions = generated.json()
    assert len(suggestions) >= 2
    for row in suggestions:
        assert row["suggestion_text"] in REMEDIATION_TEMPLATES[("data_loss", None)]

    # Idempotent generation.
    generated_again = client.post(f"{ISSUES_BASE}/{issue['id']}/generate-suggestions", headers=org["org_headers"])
    assert generated_again.status_code == 200
    assert len(generated_again.json()) == len(suggestions)

    count_rows = db_session.query(RemediationSuggestion).filter(
        RemediationSuggestion.organization_id == uuid.UUID(org["organization_id"]),
        RemediationSuggestion.issue_id == uuid.UUID(issue["id"]),
    ).count()
    assert count_rows == len(suggestions)

    # Apply suggestion => task created.
    suggestion_id = suggestions[0]["id"]
    applied = client.post(
        f"/api/v1/compliance/remediation-suggestions/{suggestion_id}/apply",
        headers=org["org_headers"],
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] is True

    task = db_session.query(Task).filter(
        Task.organization_id == uuid.UUID(org["organization_id"]),
        Task.linked_entity_type == "issue",
        Task.linked_entity_id == uuid.UUID(issue["id"]),
    ).one_or_none()
    assert task is not None

    # Dismiss suggestion.
    suggestion_id_2 = suggestions[1]["id"]
    dismissed = client.post(
        f"/api/v1/compliance/remediation-suggestions/{suggestion_id_2}/dismiss",
        headers=org["org_headers"],
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed"] is True

    # Engine exact-key by linked control category with fake control object.
    issue_obj = db_session.query(Issue).filter(Issue.id == uuid.UUID(issue["id"])).one()
    fake_control = type("FakeControl", (), {"category": "encryption_at_rest"})()
    exact = RemediationEngine.generate(issue_obj, [fake_control], db_session)
    assert exact == REMEDIATION_TEMPLATES[("data_loss", "encryption_at_rest")]

    # Unknown issue_type => generic suggestions.
    fake_issue = type("FakeIssue", (), {"issue_type": "unknown_issue"})()
    generic = RemediationEngine.generate(fake_issue, [], db_session)
    assert generic == GENERIC_SUGGESTIONS

    # No LLM imports.
    source = Path("app/compliance/engines/remediation_engine.py").read_text(encoding="utf-8").lower()
    assert "openai" not in source
    assert "anthropic" not in source

    # Pre-written templates only.
    all_template_values = {x for values in REMEDIATION_TEMPLATES.values() for x in values}
    all_template_values.update(GENERIC_SUGGESTIONS)
    for row in generated_again.json():
        assert row["suggestion_text"] in all_template_values


def test_a69_incident_classification_and_analytics(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a69-main")

    data_loss_critical = _create_issue(client, org["org_headers"], org["user_id"], issue_type="data_loss", severity="critical")
    sec_incident_high = _create_issue(client, org["org_headers"], org["user_id"], issue_type="security_incident", severity="high")
    vendor_low = _create_issue(client, org["org_headers"], org["user_id"], issue_type="vendor_failure", severity="low")

    c1 = client.post(f"{ISSUES_BASE}/{data_loss_critical['id']}/classification", headers=org["org_headers"])
    assert c1.status_code == 200
    assert c1.json()["category"] == "privacy_violation"
    assert c1.json()["regulatory_implications"] == ["gdpr_72hr", "dpdp_72hr"]
    assert c1.json()["notification_required"] is True

    outbox = db_session.query(EmailOutbox).filter(
        EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
        EmailOutbox.event_type == "classification.breach_notification_feed",
    ).one_or_none()
    assert outbox is not None
    assert outbox.recipient_user_id == uuid.UUID(org["user_id"])

    c2 = client.post(f"{ISSUES_BASE}/{sec_incident_high['id']}/classification", headers=org["org_headers"])
    assert c2.status_code == 200
    assert c2.json()["category"] == "security_breach"
    assert c2.json()["notification_required"] is True

    c3 = client.post(f"{ISSUES_BASE}/{vendor_low['id']}/classification", headers=org["org_headers"])
    assert c3.status_code == 200
    assert c3.json()["category"] == "service_disruption"

    # Upsert on second auto classify.
    c1_again = client.post(f"{ISSUES_BASE}/{data_loss_critical['id']}/classification", headers=org["org_headers"])
    assert c1_again.status_code == 200
    count = db_session.query(IncidentClassification).filter(
        IncidentClassification.organization_id == uuid.UUID(org["organization_id"]),
        IncidentClassification.issue_id == uuid.UUID(data_loss_critical["id"]),
    ).count()
    assert count == 1

    # Override classification.
    override = client.patch(
        f"{ISSUES_BASE}/{vendor_low['id']}/classification",
        headers=org["org_headers"],
        json={
            "category": "third_party_failure",
            "sub_category": "manual override",
            "regulatory_implications": ["pci_dss_incident"],
        },
    )
    assert override.status_code == 200
    assert override.json()["auto_classified"] is False
    assert override.json()["category"] == "third_party_failure"

    analytics = client.get(f"{INCIDENTS_BASE}/by-category", headers=org["org_headers"])
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["total_classified"] == 3
    assert body["notification_required_count"] >= 2
    assert body["by_category"].get("privacy_violation", 0) == 1
    assert body["regulatory_breakdown"].get("gdpr_72hr", 0) >= 2

    # Engine fallback sanity.
    fallback = ClassificationEngine.classify("vendor_failure", "low")
    assert fallback["category"] == "service_disruption"


def test_a69_classification_flags_stale_when_issue_re_triaged(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a69-stale")
    issue = _create_issue(client, org["org_headers"], org["user_id"], issue_type="vendor_failure", severity="low")

    classify = client.post(f"{ISSUES_BASE}/{issue['id']}/classification", headers=org["org_headers"])
    assert classify.status_code == 200
    assert classify.json()["stale"] is False

    fresh = client.get(f"{ISSUES_BASE}/{issue['id']}/classification", headers=org["org_headers"])
    assert fresh.status_code == 200
    assert fresh.json()["stale"] is False

    # Simulate a re-triage that bumps severity after the classification was
    # derived (severity has no public update endpoint today, so this mirrors
    # how an internal re-triage pipeline would mutate the row directly).
    issue_row = db_session.query(Issue).filter(Issue.id == uuid.UUID(issue["id"])).one()
    issue_row.severity = "critical"
    db_session.commit()

    after_retriage = client.get(f"{ISSUES_BASE}/{issue['id']}/classification", headers=org["org_headers"])
    assert after_retriage.status_code == 200
    assert after_retriage.json()["stale"] is True

    # Re-classifying (or overriding) refreshes the snapshot and clears staleness.
    reclassify = client.post(f"{ISSUES_BASE}/{issue['id']}/classification", headers=org["org_headers"])
    assert reclassify.status_code == 200
    assert reclassify.json()["stale"] is False
