from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.ai_governance.services.mlops_adapter_service import MLopsAdapterService
from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.audit_log import AuditLog
from app.models.mlflow_connection import MLflowConnection
from app.models.mlflow_drift_event import MLflowDriftEvent
from app.models.mlflow_model_registration import MLflowModelRegistration
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _create_connection(client, headers, name="Production MLflow"):
    resp = client.post(
        "/api/v1/organizations/mlflow-connection",
        headers=headers,
        json={"connection_name": name, "tracking_server_url": "https://mlflow.example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_ingest_model_registered_valid_token_persists_and_auto_links(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-ingest")
    org_id = UUID(owner["organization_id"])

    system = AISystem(organization_id=org_id, name="Fraud Detection System", model_name="FraudModel", system_type="model")
    db_session.add(system)
    db_session.commit()

    conn = _create_connection(client, owner["org_headers"])
    token = conn["ingest_token"]

    ingest = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": token},
        json={
            "event_type": "model.registered",
            "model_name": "FraudModel",
            "model_version": "1",
            "stage": "staging",
            "run_id": "run-1",
            "metrics": {"accuracy": 0.91},
        },
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json() == {"received": True}

    row = db_session.execute(
        select(MLflowModelRegistration).where(
            MLflowModelRegistration.organization_id == org_id,
            MLflowModelRegistration.model_name == "FraudModel",
        )
    ).scalar_one()
    assert row.ai_system_id == system.id
    assert row.auto_linked is True


def test_ingest_model_deployed_without_assessment_auto_creates_risk(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-deploy")
    org_id = UUID(owner["organization_id"])

    system = AISystem(organization_id=org_id, name="Credit Scoring System", model_name="CreditModel", system_type="model")
    db_session.add(system)
    db_session.commit()

    conn = _create_connection(client, owner["org_headers"])

    resp = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={
            "event_type": "model.deployed",
            "model_name": "CreditModel",
            "model_version": "4",
            "stage": "production",
        },
    )
    assert resp.status_code == 200, resp.text

    risk = db_session.execute(
        select(Risk).where(
            Risk.organization_id == org_id,
            Risk.title.ilike("AI Model deployed without compliance review:%"),
        )
    ).scalar_one_or_none()
    assert risk is not None
    registration = db_session.execute(
        select(MLflowModelRegistration).where(
            MLflowModelRegistration.organization_id == org_id,
            MLflowModelRegistration.model_name == "CreditModel",
            MLflowModelRegistration.event_type == "model.deployed",
        )
    ).scalar_one()
    assert registration.auto_risk_created is True
    assert registration.linked_risk_id is not None
    assert registration.linked_risk_id == risk.id


def test_ingest_drift_detected_threshold_and_auto_risk(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-drift")
    org_id = UUID(owner["organization_id"])

    system = AISystem(organization_id=org_id, name="Pricing Engine System", model_name="PricingModel", system_type="model")
    db_session.add(system)
    db_session.commit()

    conn = _create_connection(client, owner["org_headers"])

    client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={
            "event_type": "model.registered",
            "model_name": "PricingModel",
            "model_version": "2",
            "stage": "production",
        },
    )

    drift = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={
            "event_type": "drift.detected",
            "model_name": "PricingModel",
            "model_version": "2",
            "drift_metric": "psi",
            "drift_value": 0.35,
            "drift_threshold": 0.15,
        },
    )
    assert drift.status_code == 200, drift.text

    row = db_session.execute(
        select(MLflowDriftEvent).where(
            MLflowDriftEvent.organization_id == org_id,
            MLflowDriftEvent.model_name == "PricingModel",
        )
    ).scalar_one()
    assert row.severity in {"high", "critical"}
    assert row.auto_risk_created is True
    assert row.linked_risk_id is not None


def test_ingest_invalid_missing_or_inactive_token_returns_401(client):
    missing = client.post(
        "/api/v1/ingest/mlflow",
        json={"event_type": "model.registered", "model_name": "X", "model_version": "1", "stage": "none"},
    )
    assert missing.status_code == 401

    invalid = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": "bad-token"},
        json={"event_type": "model.registered", "model_name": "X", "model_version": "1", "stage": "none"},
    )
    assert invalid.status_code == 401

    owner = bootstrap_org_user(client, email_prefix="mlops-inactive")
    conn = _create_connection(client, owner["org_headers"])
    deact = client.delete("/api/v1/organizations/mlflow-connection", headers=owner["org_headers"])
    assert deact.status_code == 200

    inactive = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={"event_type": "model.registered", "model_name": "X", "model_version": "1", "stage": "none"},
    )
    assert inactive.status_code == 401


def test_drift_severity_tiers_with_and_without_threshold(db_session):
    svc = MLopsAdapterService(db_session)

    assert svc._compute_severity(drift_metric="psi", drift_value=Decimal("0.11"), drift_threshold=None) == "medium"
    assert svc._compute_severity(drift_metric="psi", drift_value=Decimal("0.21"), drift_threshold=None) == "high"
    assert svc._compute_severity(drift_metric="accuracy_drop", drift_value=Decimal("0.06"), drift_threshold=None) == "medium"
    assert svc._compute_severity(drift_metric="accuracy_drop", drift_value=Decimal("0.12"), drift_threshold=None) == "high"
    assert svc._compute_severity(drift_metric="accuracy_drop", drift_value=Decimal("0.30"), drift_threshold=None) == "critical"

    # threshold-based buckets
    assert svc._compute_severity(drift_metric="custom", drift_value=Decimal("10"), drift_threshold=Decimal("9")) == "low"
    assert svc._compute_severity(drift_metric="custom", drift_value=Decimal("12"), drift_threshold=Decimal("9")) == "medium"
    assert svc._compute_severity(drift_metric="custom", drift_value=Decimal("15"), drift_threshold=Decimal("9")) == "high"
    assert svc._compute_severity(drift_metric="custom", drift_value=Decimal("20"), drift_threshold=Decimal("9")) == "critical"


def test_auto_link_zero_match_pending_and_manual_link_sets_auto_false(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-link")
    org_id = UUID(owner["organization_id"])
    conn = _create_connection(client, owner["org_headers"])

    ingest = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={
            "event_type": "model.registered",
            "model_name": "NoMatchingAISystem",
            "model_version": "1",
            "stage": "staging",
        },
    )
    assert ingest.status_code == 200, ingest.text

    reg = db_session.execute(
        select(MLflowModelRegistration).where(
            MLflowModelRegistration.organization_id == org_id,
            MLflowModelRegistration.model_name == "NoMatchingAISystem",
        )
    ).scalar_one()
    assert reg.ai_system_id is None
    assert reg.compliance_status == "pending_review"

    ai_system = AISystem(organization_id=org_id, name="Mapped System", system_type="model")
    db_session.add(ai_system)
    db_session.commit()

    link = client.post(
        f"/api/v1/ai-governance/mlflow/models/{reg.id}/link",
        headers=owner["org_headers"],
        json={"ai_system_id": str(ai_system.id)},
    )
    assert link.status_code == 200, link.text
    assert link.json()["ai_system_id"] == str(ai_system.id)
    assert link.json()["auto_linked"] is False


def test_mlops_coverage_health_states(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-cov")
    org_id = UUID(owner["organization_id"])
    conn = _create_connection(client, owner["org_headers"])
    token = conn["ingest_token"]

    good_sys = AISystem(organization_id=org_id, name="Good System", model_name="GoodSystem", system_type="model")
    attention_sys = AISystem(
        organization_id=org_id, name="Needs Attention System", model_name="NeedsAttentionSystem", system_type="model"
    )
    risk_sys = AISystem(organization_id=org_id, name="At Risk System", model_name="AtRiskSystem", system_type="model")
    db_session.add_all([good_sys, attention_sys, risk_sys])
    db_session.flush()

    # Completed assessment for good system
    db_session.add(
        AISystemRiskAssessment(
            organization_id=org_id,
            ai_system_id=good_sys.id,
            title="Assessment",
            assessment_type="standard",
            status="completed",
            risk_level="medium",
            likelihood="medium",
            impact="medium",
            methodology_version="v1",
        )
    )
    db_session.commit()

    # good: deployed + reviewed + no active drift
    client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": token},
        json={"event_type": "model.deployed", "model_name": "GoodSystem", "model_version": "1", "stage": "production"},
    )
    reg_good = db_session.execute(
        select(MLflowModelRegistration).where(
            MLflowModelRegistration.organization_id == org_id,
            MLflowModelRegistration.model_name == "GoodSystem",
        )
    ).scalar_one()
    reg_good.compliance_status = "approved"

    # needs_attention: pending review
    client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": token},
        json={"event_type": "model.registered", "model_name": "NeedsAttentionSystem", "model_version": "1", "stage": "staging"},
    )

    # at_risk: deployed without completed assessment
    client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": token},
        json={"event_type": "model.deployed", "model_name": "AtRiskSystem", "model_version": "1", "stage": "production"},
    )
    db_session.commit()

    good = client.get(f"/api/v1/ai-governance/ai-systems/{good_sys.id}/mlops-coverage", headers=owner["org_headers"])
    assert good.status_code == 200, good.text
    good_body = good.json()
    assert good_body["is_mlflow_connected"] is True
    assert good_body["latest_model_version"] == "1"
    assert isinstance(good_body["days_since_last_deployment"], int)
    assert good_body["days_since_last_deployment"] >= 0
    assert good_body["active_drift_alerts"] == 0
    assert good_body["has_risk_assessment"] is True
    assert good_body["pending_compliance_review"] is False
    assert good_body["overall_governance_health"] == "good"

    attention = client.get(
        f"/api/v1/ai-governance/ai-systems/{attention_sys.id}/mlops-coverage",
        headers=owner["org_headers"],
    )
    assert attention.status_code == 200, attention.text
    assert attention.json()["overall_governance_health"] == "needs_attention"

    at_risk = client.get(
        f"/api/v1/ai-governance/ai-systems/{risk_sys.id}/mlops-coverage",
        headers=owner["org_headers"],
    )
    assert at_risk.status_code == 200, at_risk.text
    assert at_risk.json()["overall_governance_health"] == "at_risk"


def test_token_not_logged_full_and_returned_once_with_rotation_invalidation(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="mlops-token")
    org_id = UUID(owner["organization_id"])

    created = _create_connection(client, owner["org_headers"])
    full_token = created["ingest_token"]

    get_conn = client.get("/api/v1/organizations/mlflow-connection", headers=owner["org_headers"])
    assert get_conn.status_code == 200, get_conn.text
    assert "ingest_token" not in get_conn.json()
    assert get_conn.json()["has_ingest_token"] is True

    logs = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action.in_(["mlops.connection_created", "mlops.connection_token_rotated"]),
        )
    ).scalars().all()
    assert logs
    for log in logs:
        md = log.metadata_json or {}
        assert full_token not in str(md)

    rotate = client.post("/api/v1/organizations/mlflow-connection/rotate-token", headers=owner["org_headers"])
    assert rotate.status_code == 200, rotate.text
    new_token = rotate.json()["ingest_token"]
    assert new_token != full_token

    old_try = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": full_token},
        json={"event_type": "model.registered", "model_name": "OldTokenModel", "model_version": "1", "stage": "staging"},
    )
    assert old_try.status_code == 401

    new_try = client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": new_token},
        json={"event_type": "model.registered", "model_name": "NewTokenModel", "model_version": "1", "stage": "staging"},
    )
    assert new_try.status_code == 200, new_try.text


def test_cross_org_access_rejected_for_model_ops_endpoints(client, db_session):
    owner_a = bootstrap_org_user(client, email_prefix="mlops-xorg-a")
    owner_b = bootstrap_org_user(client, email_prefix="mlops-xorg-b")

    conn = _create_connection(client, owner_a["org_headers"])
    client.post(
        "/api/v1/ingest/mlflow",
        headers={"X-MLflow-Ingest-Token": conn["ingest_token"]},
        json={"event_type": "model.registered", "model_name": "CrossOrg", "model_version": "1", "stage": "staging"},
    )

    reg = db_session.execute(
        select(MLflowModelRegistration).where(MLflowModelRegistration.model_name == "CrossOrg")
    ).scalar_one()

    get_other = client.patch(
        f"/api/v1/ai-governance/mlflow/models/{reg.id}/compliance-status",
        headers=owner_b["org_headers"],
        json={"status": "approved"},
    )
    assert get_other.status_code == 404

    sys_b = AISystem(organization_id=UUID(owner_b["organization_id"]), name="B System", system_type="model")
    db_session.add(sys_b)
    db_session.commit()

    link_other = client.post(
        f"/api/v1/ai-governance/mlflow/models/{reg.id}/link",
        headers=owner_b["org_headers"],
        json={"ai_system_id": str(sys_b.id)},
    )
    assert link_other.status_code == 404
