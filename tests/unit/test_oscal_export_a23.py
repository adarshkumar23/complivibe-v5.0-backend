import json
import uuid
from datetime import UTC, date, datetime

from app.compliance.services.oscal_export_service import OSCALExportService
from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.oscal_export_job import OscalExportJob
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/oscal"


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "title": title,
            "evidence_type": "policy_document",
            "source": "manual",
            "valid_until": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_framework_obligation(db_session, *, code: str, name: str, reference_code: str) -> tuple[Framework, Obligation]:
    framework = Framework(
        code=code,
        name=name,
        description=f"{name} description",
        category="Security",
        jurisdiction="United States",
        authority="Test Authority",
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=date.today(),
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        framework_section_id=None,
        reference_code=reference_code,
        title=f"{reference_code} obligation",
        description="obligation description",
        plain_language_summary="summary",
        obligation_type="control",
        jurisdiction="United States",
        source_url=None,
        version="1.0",
        status="active",
        effective_date=date.today(),
        parent_obligation_id=None,
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.commit()
    return framework, obligation


def _activate_framework_for_org(db_session, org_id: str, framework_id: uuid.UUID, actor_user_id: str | None = None) -> None:
    row = OrganizationFramework(
        organization_id=uuid.UUID(org_id),
        framework_id=framework_id,
        status="active",
        activated_by_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        activated_at=datetime.now(UTC),
        deactivated_by_user_id=None,
        deactivated_at=None,
        notes="test",
    )
    db_session.add(row)
    db_session.commit()


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "admin") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _set_control_status(db_session, control_id: str, status_value: str) -> None:
    row = db_session.query(Control).filter(Control.id == uuid.UUID(control_id)).one_or_none()
    assert row is not None
    row.status = status_value
    db_session.commit()


def test_a23_create_job_pending_then_complete_build_and_ssp_mapping(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a23-ssp")

    control_active = _create_control(client, org["org_headers"], title="A23 Active")
    control_draft = _create_control(client, org["org_headers"], title="A23 Draft")
    control_failed = _create_control(client, org["org_headers"], title="A23 Failed")

    _set_control_status(db_session, control_active["id"], "active")
    _set_control_status(db_session, control_draft["id"], "draft")
    _set_control_status(db_session, control_failed["id"], "failed")

    fw, ob = _create_framework_obligation(db_session, code="A23-SSP", name="A23 SSP Framework", reference_code="CC6.1")
    _activate_framework_for_org(db_session, org["organization_id"], fw.id, org["user_id"])

    db_session.add(
        ControlObligationMapping(
            organization_id=uuid.UUID(org["organization_id"]),
            control_id=uuid.UUID(control_active["id"]),
            obligation_id=ob.id,
            mapping_type="supports",
            confidence="manual_confirmed",
            rationale="maps",
            status="active",
            created_by_user_id=uuid.UUID(org["user_id"]),
        )
    )
    db_session.commit()

    service = OSCALExportService(db_session)
    job = service.create_job(
        export_type="ssp",
        framework_id=None,
        org_id=uuid.UUID(org["organization_id"]),
        requested_by_user_id=uuid.UUID(org["user_id"]),
    )
    assert job.status == "pending"

    built = service.build(job.id, uuid.UUID(org["organization_id"]))
    db_session.commit()
    db_session.refresh(built)

    assert built.status == "complete"
    assert built.result_size_bytes == len(json.dumps(built.result_json).encode("utf-8"))

    ssp = built.result_json["system-security-plan"]
    assert ssp["system-characteristics"]["system-name"] is not None

    components = ssp["system-implementation"]["components"]
    assert len(components) == 3
    by_title = {item["title"]: item["status"]["state"] for item in components}
    assert by_title["A23 Active"] == "operational"
    assert by_title["A23 Draft"] == "under-development"
    assert by_title["A23 Failed"] == "other"

    impl = ssp["control-implementation"]["implemented-requirements"]
    assert len(impl) == 1
    assert impl[0]["control-id"] == "CC6.1"
    assert impl[0]["by-components"][0]["component-uuid"] == control_active["id"]


def test_a23_ap_ar_and_full_package_exports(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a23-apar")

    control1 = _create_control(client, org["org_headers"], title="A23 AP Control 1")
    control2 = _create_control(client, org["org_headers"], title="A23 AP Control 2")

    fw1, ob1 = _create_framework_obligation(db_session, code="A23-AP1", name="A23 AP Framework 1", reference_code="IA-2")
    fw2, ob2 = _create_framework_obligation(db_session, code="A23-AP2", name="A23 AP Framework 2", reference_code="A.9.4.2")
    _activate_framework_for_org(db_session, org["organization_id"], fw1.id, org["user_id"])
    _activate_framework_for_org(db_session, org["organization_id"], fw2.id, org["user_id"])

    db_session.add_all(
        [
            ControlObligationMapping(
                organization_id=uuid.UUID(org["organization_id"]),
                control_id=uuid.UUID(control1["id"]),
                obligation_id=ob1.id,
                mapping_type="supports",
                confidence="manual_confirmed",
                rationale="maps1",
                status="active",
                created_by_user_id=uuid.UUID(org["user_id"]),
            ),
            ControlObligationMapping(
                organization_id=uuid.UUID(org["organization_id"]),
                control_id=uuid.UUID(control2["id"]),
                obligation_id=ob2.id,
                mapping_type="supports",
                confidence="manual_confirmed",
                rationale="maps2",
                status="active",
                created_by_user_id=uuid.UUID(org["user_id"]),
            ),
        ]
    )
    db_session.commit()

    owner_user = _create_active_user_with_role(
        db_session,
        org["organization_id"],
        "a23-ap-owner@example.com",
        role_name="admin",
    )

    t1 = client.post(
        f"/api/v1/controls/{control1['id']}/tests",
        headers=org["org_headers"],
        json={
            "name": "Control 1 test",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
            "cadence": "weekly",
            "owner_user_id": str(owner_user.id),
        },
    )
    assert t1.status_code == 201

    t2 = client.post(
        f"/api/v1/controls/{control2['id']}/tests",
        headers=org["org_headers"],
        json={
            "name": "Control 2 test",
            "test_type": "manual_attestation",
            "check_key": "manual_attestation",
            "cadence": "weekly",
            "owner_user_id": str(owner_user.id),
        },
    )
    assert t2.status_code == 201

    ev1 = _create_evidence(client, org["org_headers"], title="A23 Evidence 1")
    ev2 = _create_evidence(client, org["org_headers"], title="A23 Evidence 2")

    ev1_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(ev1["id"])).one()
    ev1_row.review_status = "approved"
    ev1_row.legacy_control_id = uuid.UUID(control1["id"])
    ev2_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(ev2["id"])).one()
    ev2_row.review_status = "approved"
    ev2_row.legacy_control_id = uuid.UUID(control2["id"])
    db_session.commit()

    run1 = client.post(
        f"/api/v1/control-tests/{t1.json()['id']}/run",
        headers=org["org_headers"],
        json={"evidence_item_id": ev1["id"], "manual_result": "passed", "result_reason": "ok"},
    )
    assert run1.status_code == 200

    run2 = client.post(
        f"/api/v1/control-tests/{t2.json()['id']}/run",
        headers=org["org_headers"],
        json={"evidence_item_id": ev2["id"], "manual_result": "failed", "result_reason": "bad"},
    )
    assert run2.status_code == 200

    risk = Risk(
        organization_id=uuid.UUID(org["organization_id"]),
        title="A23 Open Risk",
        description="risk desc",
        category="security",
        severity="high",
        likelihood=4,
        impact=3,
        inherent_score=12,
        residual_score=9,
        status="identified",
        treatment_strategy="mitigate",
        owner_user_id=uuid.UUID(org["user_id"]),
        created_by_user_id=uuid.UUID(org["user_id"]),
    )
    db_session.add(risk)
    db_session.flush()
    db_session.add(
        RiskControlLink(
            organization_id=uuid.UUID(org["organization_id"]),
            risk_id=risk.id,
            control_id=uuid.UUID(control1["id"]),
            link_type="mitigates",
            status="active",
            rationale="linked",
            linked_by_user_id=uuid.UUID(org["user_id"]),
            linked_at=datetime.now(UTC),
        )
    )
    db_session.add(
        EvidenceControlLink(
            organization_id=uuid.UUID(org["organization_id"]),
            evidence_item_id=uuid.UUID(ev1["id"]),
            control_id=uuid.UUID(control1["id"]),
            link_status="active",
            confidence="manual_confirmed",
            rationale="linked",
            linked_by_user_id=uuid.UUID(org["user_id"]),
            linked_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    ap_resp = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "assessment_plan"})
    assert ap_resp.status_code == 200
    ap_body = ap_resp.json()
    assert ap_body["status"] == "complete"
    ap_doc = ap_body["result_json"]["assessment-plan"]
    reviewed = ap_doc["reviewed-controls"]["control-selections"][0]["include-controls"]
    control_ids = {item["control-id"] for item in reviewed}
    assert "IA-2" in control_ids
    assert "A.9.4.2" in control_ids
    assert len(ap_doc["tasks"]) == 2

    ar_resp = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "assessment_results"})
    assert ar_resp.status_code == 200
    assert ar_resp.json()["status"] == "complete", ar_resp.json()
    ar_doc = ar_resp.json()["result_json"]["assessment-results"]
    result = ar_doc["results"][0]
    assert len(result["observations"]) == 2

    finding_states = {item["target"]["status"]["state"] for item in result["findings"]}
    assert "satisfied" in finding_states
    assert "not-satisfied" in finding_states

    assert len(result["risks"]) == 1
    facets = result["risks"][0]["characterizations"][0]["facets"]
    by_name = {f["name"]: f["value"] for f in facets}
    assert by_name["likelihood"] == "high"
    assert by_name["impact"] == "moderate"

    full_resp = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "full_package"})
    assert full_resp.status_code == 200
    full_doc = full_resp.json()["result_json"]["oscal-complete"]
    assert "system-security-plan" in full_doc
    assert "assessment-plan" in full_doc
    assert "assessment-results" in full_doc


def test_a23_framework_scope_validate_download_pending_failed_summary_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a23-scope-a")
    org2 = bootstrap_org_user(client, email_prefix="a23-scope-b")

    control1 = _create_control(client, org1["org_headers"], title="A23 Scope Control 1")
    control2 = _create_control(client, org1["org_headers"], title="A23 Scope Control 2")

    fw1, ob1 = _create_framework_obligation(db_session, code="A23-SC1", name="Scope FW 1", reference_code="SC-1")
    fw2, ob2 = _create_framework_obligation(db_session, code="A23-SC2", name="Scope FW 2", reference_code="SC-2")
    _activate_framework_for_org(db_session, org1["organization_id"], fw1.id, org1["user_id"])
    _activate_framework_for_org(db_session, org1["organization_id"], fw2.id, org1["user_id"])

    db_session.add_all(
        [
            ControlObligationMapping(
                organization_id=uuid.UUID(org1["organization_id"]),
                control_id=uuid.UUID(control1["id"]),
                obligation_id=ob1.id,
                mapping_type="supports",
                confidence="manual_confirmed",
                rationale="maps1",
                status="active",
                created_by_user_id=uuid.UUID(org1["user_id"]),
            ),
            ControlObligationMapping(
                organization_id=uuid.UUID(org1["organization_id"]),
                control_id=uuid.UUID(control2["id"]),
                obligation_id=ob2.id,
                mapping_type="supports",
                confidence="manual_confirmed",
                rationale="maps2",
                status="active",
                created_by_user_id=uuid.UUID(org1["user_id"]),
            ),
        ]
    )
    db_session.commit()

    scoped = client.post(
        f"{BASE}/export",
        headers=org1["org_headers"],
        json={"export_type": "assessment_plan", "framework_id": str(fw1.id)},
    )
    assert scoped.status_code == 200
    scoped_doc = scoped.json()["result_json"]["assessment-plan"]
    include_controls = scoped_doc["reviewed-controls"]["control-selections"][0]["include-controls"]
    assert {item["control-id"] for item in include_controls} == {"SC-1"}

    scoped_job_id = scoped.json()["id"]
    valid = client.get(f"{BASE}/exports/{scoped_job_id}/validate", headers=org1["org_headers"])
    assert valid.status_code == 200
    valid_body = valid.json()
    assert valid_body["valid"] is True
    assert valid_body["errors"] == []

    row = db_session.get(OscalExportJob, uuid.UUID(scoped_job_id))
    assert row is not None
    row.result_json = {"assessment-plan": {"metadata": {}}}
    db_session.commit()

    invalid = client.get(f"{BASE}/exports/{scoped_job_id}/validate", headers=org1["org_headers"])
    assert invalid.status_code == 200
    invalid_body = invalid.json()
    assert invalid_body["valid"] is False
    assert len(invalid_body["errors"]) > 0

    complete_job = client.post(f"{BASE}/export", headers=org1["org_headers"], json={"export_type": "ssp"})
    assert complete_job.status_code == 200
    download = client.get(f"{BASE}/exports/{complete_job.json()['id']}/download", headers=org1["org_headers"])
    assert download.status_code == 200
    assert "attachment; filename=\"complivibe-oscal-ssp-" in download.headers["content-disposition"]

    pending_row = OSCALExportService(db_session).create_job(
        export_type="ssp",
        framework_id=None,
        org_id=uuid.UUID(org1["organization_id"]),
        requested_by_user_id=uuid.UUID(org1["user_id"]),
    )
    db_session.commit()

    pending_download = client.get(f"{BASE}/exports/{pending_row.id}/download", headers=org1["org_headers"])
    assert pending_download.status_code == 422

    failed = client.post(
        f"{BASE}/export",
        headers=org1["org_headers"],
        json={"export_type": "ssp", "framework_id": str(uuid.uuid4())},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_message"]

    summary = client.get(f"{BASE}/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_exports"] >= 4
    assert body["by_type"]["ssp"] >= 2
    assert body["by_status"]["complete"] >= 2
    assert body["by_status"]["failed"] >= 1

    list_org1 = client.get(f"{BASE}/exports", headers=org1["org_headers"])
    list_org2 = client.get(f"{BASE}/exports", headers=org2["org_headers"])
    assert list_org1.status_code == 200
    assert list_org2.status_code == 200
    assert len(list_org1.json()) >= 1
    assert list_org2.json() == []


def test_a23_empty_org_valid_documents_uuid_v4_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a23-empty")

    ssp = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "ssp"})
    ap = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "assessment_plan"})
    ar = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "assessment_results"})

    assert ssp.status_code == 200
    assert ap.status_code == 200
    assert ar.status_code == 200

    ssp_doc = ssp.json()["result_json"]["system-security-plan"]
    assert isinstance(ssp_doc["system-implementation"]["components"], list)
    assert ssp_doc["system-implementation"]["components"] == []

    ap_doc = ap.json()["result_json"]["assessment-plan"]
    assert isinstance(ap_doc["tasks"], list)
    assert ap_doc["tasks"] == []

    ar_doc = ar.json()["result_json"]["assessment-results"]
    assert isinstance(ar_doc["results"][0]["observations"], list)
    assert ar_doc["results"][0]["observations"] == []

    for value in [
        ssp_doc["uuid"],
        ap_doc["uuid"],
        ar_doc["uuid"],
        ar_doc["results"][0]["uuid"],
    ]:
        parsed = uuid.UUID(value)
        assert parsed.version == 4

    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org["organization_id"])).all()
    }
    assert "oscal_export.job_created" in actions
    assert "oscal_export.job_completed" in actions
