from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.mlops_sync_service import MLOPSSyncService
from app.compliance.services.ai_drafting_service import AIDraftingService
from app.models.aibom_component import AIBOMComponent
from app.models.ai_system import AISystem
from app.models.draft_request import DraftRequest
from app.models.mlops_integration import MLOpsIntegration
from app.schemas.ai_drafting import DraftRequestRead
from tests.helpers.auth_org import bootstrap_org_user

DRAFT_BASE = "/api/v1/compliance/drafts"
SYSTEMS_BASE = "/api/v1/ai-governance/systems"
MLOPS_BASE = "/api/v1/ai-governance/mlops-integrations"


class _FakeAdapter:
    def fetch_registered_models(self) -> list[dict]:
        return [
            {
                "name": "mlflow-model-a",
                "version": "1",
                "stage": "Production",
                "description": "A model",
                "training_data_source": "dataset_a",
                "run_id": "run-a",
            },
            {
                "name": "mlflow-model-b",
                "version": "3",
                "stage": "Staging",
                "description": "B model",
                "training_data_source": "dataset_b",
                "run_id": "run-b",
            },
        ]

    def map_to_aibom_components(self, models: list[dict]) -> list[dict]:
        components: list[dict] = []
        for model in models:
            components.append(
                {
                    "component_type": "base_model",
                    "name": model["name"],
                    "version": model["version"],
                    "source": "mlflow_registry",
                    "source_integration": "mlflow",
                    "is_third_party": False,
                }
            )
            components.append(
                {
                    "component_type": "training_data",
                    "name": model["training_data_source"],
                    "source": "mlflow_run_tag",
                    "source_integration": "mlflow",
                    "is_third_party": False,
                }
            )
        return components


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
            "purpose": "Testing",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_a70_ai_copilot_draft_mode(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="a70-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "A70 System")

    monkeypatch.setattr(
        AIDraftingService,
        "_call_azure_openai",
        lambda self, system_prompt, user_prompt: ("mocked draft", False),
    )

    blocked = client.post(
        f"{DRAFT_BASE}/ai-risk-assessment",
        headers=org["org_headers"],
        json={"ai_system_id": system_id},
    )
    assert blocked.status_code == 403

    enabled = client.post(f"{DRAFT_BASE}/ai-config/enable", headers=org["org_headers"])
    assert enabled.status_code == 200

    risk_draft = client.post(
        f"{DRAFT_BASE}/ai-risk-assessment",
        headers=org["org_headers"],
        json={"ai_system_id": system_id},
    )
    assert risk_draft.status_code == 201
    assert risk_draft.json()["draft_type"] == "ai_risk_assessment_narrative"

    model_card_draft = client.post(
        f"{DRAFT_BASE}/model-card",
        headers=org["org_headers"],
        json={"ai_system_id": system_id},
    )
    assert model_card_draft.status_code == 201
    assert model_card_draft.json()["draft_type"] == "model_card_content"

    outsider = bootstrap_org_user(client, email_prefix="a70-outsider")
    outsider_headers = {
        "Authorization": f"Bearer {outsider['access_token']}",
        "X-Organization-ID": org["organization_id"],
    }
    forbidden = client.post(
        f"{DRAFT_BASE}/ai-policy",
        headers=outsider_headers,
        json={"industry": "finance"},
    )
    assert forbidden.status_code == 403

    created_types = set(
        db_session.execute(
            select(DraftRequest.draft_type).where(DraftRequest.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    )
    assert "ai_risk_assessment_narrative" in created_types
    assert "model_card_content" in created_types

    validated = DraftRequestRead(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        draft_type="eu_act_conformity_narrative",
        context_json={},
        draft_output="x",
        model_used="m",
        prompt_used="p",
        created_by=uuid.uuid4(),
        applied=False,
        created_at=risk_draft.json()["created_at"],
        updated_at=risk_draft.json()["updated_at"],
        applied_at=None,
        applied_by=None,
    )
    assert validated.draft_type == "eu_act_conformity_narrative"


def test_ai_copilot_draft_rejects_cross_org_ai_system_context(client, monkeypatch):
    org_a = bootstrap_org_user(client, email_prefix="a70-leak-a")
    org_b = bootstrap_org_user(client, email_prefix="a70-leak-b")
    system_a_id = _create_system(
        client,
        org_a["org_headers"],
        org_a["user_id"],
        "CONFIDENTIAL Org A Revenue Model",
    )

    enabled = client.post(f"{DRAFT_BASE}/ai-config/enable", headers=org_b["org_headers"])
    assert enabled.status_code == 200

    def _should_not_call(self, system_prompt, user_prompt):  # noqa: ANN001
        raise AssertionError(f"cross-org prompt leaked to model: {user_prompt}")

    monkeypatch.setattr(AIDraftingService, "_call_azure_openai", _should_not_call)

    for path in ["ai-risk-assessment", "model-card"]:
        response = client.post(
            f"{DRAFT_BASE}/{path}",
            headers=org_b["org_headers"],
            json={"ai_system_id": system_a_id},
        )
        assert response.status_code == 404, (path, response.text)


def test_a71_mlops_integration_sync_workflow(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="a71-org")

    created = client.post(
        MLOPS_BASE,
        headers=org["org_headers"],
        json={
            "integration_type": "mlflow",
            "name": "Primary MLflow",
            "config_json": {"tracking_uri": "http://mlflow.local", "token": "secret-token"},
        },
    )
    assert created.status_code == 201
    integration_id = created.json()["id"]
    assert "config_json" not in created.json()

    integration_row = db_session.execute(
        select(MLOpsIntegration).where(MLOpsIntegration.id == uuid.UUID(integration_id))
    ).scalar_one()
    assert integration_row.config_json != '{"tracking_uri": "http://mlflow.local", "token": "secret-token"}'
    assert "mlflow.local" not in integration_row.config_json

    get_resp = client.get(f"{MLOPS_BASE}/{integration_id}", headers=org["org_headers"])
    assert get_resp.status_code == 200
    assert "config_json" not in get_resp.json()

    monkeypatch.setattr("app.ai_governance.services.mlops_sync_service.get_adapter", lambda integration, db=None: _FakeAdapter())

    synced = client.post(f"{MLOPS_BASE}/{integration_id}/sync", headers=org["org_headers"])
    assert synced.status_code == 200
    assert synced.json()["models_found"] == 2
    assert synced.json()["systems_created"] == 2
    assert synced.json()["aiboms_updated"] == 1

    refreshed = db_session.execute(
        select(MLOpsIntegration).where(MLOpsIntegration.id == uuid.UUID(integration_id))
    ).scalar_one()
    assert refreshed.sync_status == "success"
    assert refreshed.last_synced_at is not None

    model_systems = db_session.execute(
        select(AISystem).where(
            AISystem.organization_id == uuid.UUID(org["organization_id"]),
            AISystem.system_type == "model",
            AISystem.name.in_(["mlflow-model-a", "mlflow-model-b"]),
        )
    ).scalars().all()
    assert len(model_systems) == 2

    component_names = set(
        db_session.execute(
            select(AIBOMComponent.name).where(AIBOMComponent.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    )
    assert "mlflow-model-a" in component_names
    assert "dataset_a" in component_names

    service = MLOPSSyncService(db_session)
    monkeypatch.setattr(
        "app.ai_governance.services.mlops_sync_service.get_adapter",
        lambda integration, db=None: (_ for _ in ()).throw(RuntimeError("simulated sync failure")),
    )
    with pytest.raises(RuntimeError):
        service.sync(uuid.UUID(org["organization_id"]), uuid.UUID(integration_id), uuid.UUID(org["user_id"]))

    failed_row = db_session.execute(
        select(MLOpsIntegration).where(MLOpsIntegration.id == uuid.UUID(integration_id))
    ).scalar_one()
    assert failed_row.sync_status == "failed"
    assert "simulated sync failure" in (failed_row.last_sync_error or "")

    deactivated = client.post(f"{MLOPS_BASE}/{integration_id}/deactivate", headers=org["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False


def test_a72_contract_registry_static_content_requires_permission(client, db_session):
    """The contracts manifest is static, but it is no longer served unauthenticated.

    This test previously asserted the endpoint took NO auth and issued NO DB query.
    That was a deliberate design choice, but the manifest enumerates the platform's
    AI-governance endpoint layout, its enforcement invariants, and its patent-deferral
    roadmap -- none of which belongs in an anonymous response. It now requires
    `ai_governance:read`, which necessarily means a permission lookup hits the DB, so
    the old "no DB query" assertion no longer applies. The payload itself is still a
    module-level constant and is unchanged.
    """
    org_user = bootstrap_org_user(client, email_prefix="contracts-a72")

    response = client.get("/api/v1/ai-governance/contracts", headers=org_user["org_headers"])
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("groups"), list)
    assert any(group.get("name") == "guardrails" for group in payload["groups"])
    assert "patent_protected_features" in payload

    # And an anonymous caller is refused.
    client.cookies.clear()
    anonymous = client.get(
        "/api/v1/ai-governance/contracts",
        headers={"X-Organization-ID": org_user["organization_id"]},
    )
    assert anonymous.status_code in (401, 403), anonymous.text
