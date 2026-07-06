from __future__ import annotations

from uuid import UUID

from app.models.ai_system import AISystem
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.vendor import Vendor
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/import"


def test_import_gap_report_computes_real_gaps_for_active_frameworks(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-gap-report")
    org_id = UUID(org["organization_id"])
    user_id = UUID(org["user_id"])

    framework = Framework(
        code="IMP-GAP-FW",
        name="Import Gap Framework",
        description="gap coverage",
        category="security",
        jurisdiction="global",
        status="active",
        coverage_level="starter",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )

    obligation_a = Obligation(
        framework_id=framework.id,
        reference_code="IMP-1",
        title="Imported Covered Obligation",
        description="covered",
        jurisdiction="global",
        status="active",
    )
    obligation_b = Obligation(
        framework_id=framework.id,
        reference_code="IMP-2",
        title="Uncovered Obligation",
        description="gap",
        jurisdiction="global",
        status="active",
    )
    db_session.add_all([obligation_a, obligation_b])
    db_session.flush()

    covered_control = Control(
        organization_id=org_id,
        control_code="IMP-C-1",
        title="Imported Gap Control",
        description="Imported control",
        source="imported",
        source_import_tool="drata",
        status="implemented",
        control_type="process",
        criticality="medium",
        created_by_user_id=user_id,
    )
    local_control = Control(
        organization_id=org_id,
        control_code="IMP-C-2",
        title="Local Gap Control",
        description="No imported evidence",
        source="manual",
        status="implemented",
        control_type="process",
        criticality="medium",
        created_by_user_id=user_id,
    )
    db_session.add_all([covered_control, local_control])
    db_session.flush()

    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=covered_control.id,
            obligation_id=obligation_a.id,
            mapping_type="supports",
            confidence="manual_confirmed",
            status="active",
            created_by_user_id=user_id,
        )
    )

    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Imported Vendor Security Report",
            description="Vendor Alpha evidence pack",
            evidence_type="document",
            source="imported",
            source_import_tool="drata",
            status="active",
            review_status="verified",
            freshness_status="current",
            uploaded_by_user_id=user_id,
        )
    )

    db_session.add(
        Vendor(
            organization_id=org_id,
            name="Vendor Alpha",
            vendor_type="software",
            website=None,
            primary_contact_name=None,
            primary_contact_email=None,
            risk_tier="not_assessed",
            status="active",
            owner_user_id=user_id,
            data_access=False,
            processes_personal_data=False,
            sub_processor=False,
            nth_party_risk_flag=False,
        )
    )
    db_session.add(
        Vendor(
            organization_id=org_id,
            name="Vendor Beta",
            vendor_type="software",
            website=None,
            primary_contact_name=None,
            primary_contact_email=None,
            risk_tier="not_assessed",
            status="active",
            owner_user_id=user_id,
            data_access=False,
            processes_personal_data=False,
            sub_processor=False,
            nth_party_risk_flag=False,
        )
    )

    db_session.add(
        AISystem(
            organization_id=org_id,
            name="Gamma Assistant",
            system_type="model",
            lifecycle_status="production",
            deployment_status="production",
            vendor_name="Vendor Alpha",
            provider_name="Vendor Alpha",
            model_name="gamma-v1",
            created_by=user_id,
            created_by_user_id=user_id,
        )
    )
    db_session.add(
        AISystem(
            organization_id=org_id,
            name="Delta Analyzer",
            system_type="model",
            lifecycle_status="production",
            deployment_status="production",
            vendor_name="Unknown Vendor",
            provider_name="Unknown Vendor",
            model_name="delta-v1",
            created_by=user_id,
            created_by_user_id=user_id,
        )
    )
    db_session.flush()

    job_create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "Gap seed control", "code": "GAP-SEED"}],
        },
    )
    assert job_create.status_code == 201
    job_id = job_create.json()["id"]
    assert client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"]).status_code == 200

    report = client.get(f"{BASE}/{job_id}/gap-report", headers=org["org_headers"])
    assert report.status_code == 200
    payload = report.json()

    assert payload["summary"]["framework_count"] == 1
    assert payload["summary"]["obligation_gap_count"] >= 1
    assert any("IMP-2" in row["name"] for row in payload["obligations_without_coverage"])
    assert any(row["name"] == "Local Gap Control" for row in payload["controls_without_coverage"])
    assert any(row["name"] == "Delta Analyzer" for row in payload["ai_systems_without_coverage"])
    assert any(row["name"] == "Vendor Beta" for row in payload["vendors_without_coverage"])
    assert not any(row["name"] == "Vendor Alpha" for row in payload["vendors_without_coverage"])


def test_import_gap_report_marks_stale_when_newer_job_exists(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-gap-stale")

    first = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "older", "code": "OLD-C"}],
        },
    )
    assert first.status_code == 201
    first_id = first.json()["id"]
    assert client.post(f"{BASE}/{first_id}/commit", headers=org["org_headers"]).status_code == 200

    second = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "newer", "code": "NEW-C"}],
        },
    )
    assert second.status_code == 201
    second_id = second.json()["id"]
    assert client.post(f"{BASE}/{second_id}/commit", headers=org["org_headers"]).status_code == 200

    stale = client.get(f"{BASE}/{first_id}/gap-report", headers=org["org_headers"])
    assert stale.status_code == 200
    assert stale.json()["stale"] is True
    assert "Newer import job" in (stale.json()["stale_reason"] or "")
