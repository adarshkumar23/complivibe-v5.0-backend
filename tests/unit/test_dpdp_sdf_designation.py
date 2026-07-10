from __future__ import annotations

from app.models.audit_schedule import AuditSchedule
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.sdf_designation_suggestion import SDFDesignationSuggestion
from app.privacy.services.sdf_designation_service import SDFDesignationService
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user
from uuid import UUID

ASSETS_BASE = "/api/v1/data-observability/assets"


def _create_sensitive_asset(client, headers, owner_id, name):
    response = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "sensitive data asset for SDF suggestion test",
            "schema_column_names": ["email", "customer_id"],
            "geographic_locations": ["IN"],
        },
    )
    assert response.status_code == 201
    asset_id = response.json()["id"]
    patch = client.patch(
        f"{ASSETS_BASE}/{asset_id}",
        headers=headers,
        json={"classification_type": "sensitive_personal_data", "classification_confirmed": True},
    )
    assert patch.status_code == 200
    return asset_id


def test_sdf_suggestion_and_confirmation_wires_obligations_and_audit_schedule(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dpdp-sdf")
    org_id = UUID(org["organization_id"])
    user_id = UUID(org["user_id"])

    SeedService.ensure_dpdp_framework(db_session)
    db_session.commit()

    for i in range(6):
        _create_sensitive_asset(client, org["org_headers"], org["user_id"], f"sensitive-asset-{i}")

    service = SDFDesignationService(db_session)
    suggestion = service.suggest_sdf_designation(org_id)
    assert suggestion.suggested_sdf is True
    assert suggestion.sensitive_asset_count == 6

    result = service.confirm_sdf_designation(
        org_id, confirmed_value=True, sdf_category="critical_digital_service", actor_user_id=user_id
    )
    assert result["is_significant_data_fiduciary"] is True
    assert len(result["obligation_state_ids"]) == 3
    assert result["audit_schedule_id"] is not None

    org_row = db_session.get(Organization, org_id)
    assert org_row.is_significant_data_fiduciary is True
    assert org_row.sdf_category == "critical_digital_service"

    framework = db_session.query(Framework).filter(Framework.code == "INDIA_DPDP").one()
    obligations = {
        row.reference_code: row
        for row in db_session.query(Obligation).filter(Obligation.framework_id == framework.id).all()
        if row.reference_code in ("DPDP-SDF-1", "DPDP-SDF-2", "DPDP-SDF-3")
    }
    assert len(obligations) == 3
    for ref_code, obligation in obligations.items():
        state = (
            db_session.query(OrganizationObligationState)
            .filter(
                OrganizationObligationState.organization_id == org_id,
                OrganizationObligationState.obligation_id == obligation.id,
            )
            .one()
        )
        assert state.applicability_status == "applicable"

    schedule = db_session.get(AuditSchedule, result["audit_schedule_id"])
    assert schedule is not None
    assert schedule.recurrence == "annual"
    assert schedule.framework_id == framework.id

    suggestion_row = db_session.get(SDFDesignationSuggestion, suggestion.id)
    assert suggestion_row.confirmed is True
    assert suggestion_row.confirmed_value is True


def test_sdf_confirmation_false_marks_obligations_not_applicable(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dpdp-sdf-no")
    org_id = UUID(org["organization_id"])
    user_id = UUID(org["user_id"])

    SeedService.ensure_dpdp_framework(db_session)
    db_session.commit()

    service = SDFDesignationService(db_session)
    suggestion = service.suggest_sdf_designation(org_id)
    assert suggestion.suggested_sdf is False

    result = service.confirm_sdf_designation(org_id, confirmed_value=False, sdf_category=None, actor_user_id=user_id)
    assert result["is_significant_data_fiduciary"] is False
    assert result["audit_schedule_id"] is None

    org_row = db_session.get(Organization, org_id)
    assert org_row.is_significant_data_fiduciary is False
    assert org_row.sdf_category is None
