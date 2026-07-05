import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.data_asset import DataAsset
from app.models.membership import Membership
from app.models.ot_ics_agent import OtIcsAgent  # noqa: F401  (ensures table registered on Base.metadata)
from app.models.ot_ics_asset import OtIcsAsset  # noqa: F401
from app.models.ot_ics_finding import OtIcsFinding  # noqa: F401
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

AGENTS_BASE = "/api/v1/ot-ics/agents"
ASSETS_BASE = "/api/v1/ot-ics/assets"
FINDINGS_BASE = "/api/v1/ot-ics/findings"
INGEST_URL = "/api/v1/ot-ics/findings/ingest"

# These are the two NEW permission codes this feature introduces. The shared
# seed_service.py PERMISSIONS dict / role grant sets are owned by the
# coordinator workstream and are not edited here, so this test grants them
# directly to the bootstrapped org's "owner" role via the RBAC tables so the
# endpoints (which gate on these exact codes) are reachable in this isolated
# test run.
_PERMISSION_CODES = ("ot_ics_assets:read", "ot_ics_assets:manage")


@pytest.fixture(scope="session", autouse=True)
def _register_ot_ics_router(_test_app):
    from app.api.v1 import ot_ics as ot_ics_router_module

    already_mounted = any(getattr(route, "path", "").startswith("/api/v1/ot-ics") for route in _test_app.routes)
    if not already_mounted:
        _test_app.include_router(ot_ics_router_module.router, prefix="/api/v1")
        _test_app.include_router(ot_ics_router_module.ingest_router, prefix="/api/v1")
    yield


def _grant_ot_ics_permissions(db_session, organization_id: str) -> None:
    org_uuid = uuid.UUID(organization_id)
    owner_role = db_session.query(Role).filter(Role.organization_id == org_uuid, Role.name == "owner").one()

    for code in _PERMISSION_CODES:
        permission = db_session.query(Permission).filter(Permission.key == code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=code)
            db_session.add(permission)
            db_session.flush()

        existing_link = db_session.query(RolePermission).filter(
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id == permission.id,
        ).one_or_none()
        if existing_link is None:
            db_session.add(RolePermission(role_id=owner_role.id, permission_id=permission.id))

    db_session.commit()


def _bootstrap(client, db_session, prefix: str) -> dict:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _grant_ot_ics_permissions(db_session, org["organization_id"])
    return org


def _create_data_asset(db_session, org_id: str, *, name: str = "customer_db") -> DataAsset:
    owner = User(
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Data Owner",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()

    now = datetime.now(UTC)
    asset = DataAsset(
        organization_id=uuid.UUID(org_id),
        name=name,
        asset_type="database",
        owner_id=owner.id,
        status="active",
        created_by=owner.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _register_agent(client, org_headers_map: dict[str, str], *, name: str) -> dict:
    response = client.post(AGENTS_BASE, headers=org_headers_map, json={"name": name})
    assert response.status_code == 201
    return response.json()


def _create_asset(
    client,
    org_headers_map: dict[str, str],
    *,
    name: str = "PLC-1",
    asset_type: str = "plc",
    criticality: str = "high",
    network_segment: str | None = "vlan-100",
    linked_data_asset_id: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "asset_type": asset_type,
        "criticality": criticality,
        "network_segment": network_segment,
    }
    if linked_data_asset_id is not None:
        payload["linked_data_asset_id"] = linked_data_asset_id
    response = client.post(ASSETS_BASE, headers=org_headers_map, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _ingest(client, token: str, payload: dict) -> dict:
    response = client.post(INGEST_URL, headers={"Authorization": f"Bearer {token}"}, json=payload)
    return {"status_code": response.status_code, "json": (response.json() if response.content else None)}


def test_agent_registration_returns_usable_token_and_ingest_creates_row(client, db_session):
    org = _bootstrap(client, db_session, "otics-agent")
    agent = _register_agent(client, org["org_headers"], name="ot-collector-1")
    assert agent["token"]

    from app.models.ot_ics_agent import OtIcsAgent as _Agent

    stored = db_session.query(_Agent).filter_by(id=uuid.UUID(agent["id"])).one()
    assert stored.token_hash != agent["token"]
    assert len(stored.token_hash) == 64

    asset = _create_asset(client, org["org_headers"], name="PLC-Main")

    result = _ingest(
        client,
        agent["token"],
        {
            "asset_id": asset["id"],
            "finding_type": "default_credentials",
            "severity": "high",
            "description": "default admin/admin creds found",
            "raw_payload": {"user": "admin"},
        },
    )
    assert result["status_code"] == 200, result
    finding_id = result["json"]["finding_id"]

    from app.models.ot_ics_finding import OtIcsFinding as _Finding

    stored_finding = db_session.query(_Finding).filter_by(id=uuid.UUID(finding_id)).one()
    assert stored_finding.asset_id == uuid.UUID(asset["id"])
    assert stored_finding.finding_type == "default_credentials"
    assert stored_finding.severity == "high"


def test_ingest_for_nonexistent_asset_returns_404_and_no_orphan_row(client, db_session):
    org = _bootstrap(client, db_session, "otics-orphan")
    agent = _register_agent(client, org["org_headers"], name="ot-collector-2")

    from app.models.ot_ics_finding import OtIcsFinding as _Finding

    before_count = db_session.query(_Finding).count()

    result = _ingest(
        client,
        agent["token"],
        {
            "asset_id": str(uuid.uuid4()),
            "finding_type": "anomalous_traffic",
            "severity": "critical",
            "raw_payload": {},
        },
    )
    assert result["status_code"] == 404

    after_count = db_session.query(_Finding).count()
    assert after_count == before_count


def test_asset_crud_happy_path_including_soft_delete(client, db_session):
    org = _bootstrap(client, db_session, "otics-crud")

    created = _create_asset(client, org["org_headers"], name="RTU-7", asset_type="rtu", criticality="medium")
    asset_id = created["id"]

    fetched = client.get(f"{ASSETS_BASE}/{asset_id}", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "RTU-7"

    listed = client.get(ASSETS_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert any(item["id"] == asset_id for item in listed.json())

    updated = client.patch(
        f"{ASSETS_BASE}/{asset_id}",
        headers=org["org_headers"],
        json={"criticality": "critical", "status": "under_maintenance"},
    )
    assert updated.status_code == 200
    assert updated.json()["criticality"] == "critical"
    assert updated.json()["status"] == "under_maintenance"

    deleted = client.delete(f"{ASSETS_BASE}/{asset_id}", headers=org["org_headers"])
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "decommissioned"

    after_delete = client.get(f"{ASSETS_BASE}/{asset_id}", headers=org["org_headers"])
    assert after_delete.status_code == 404


def test_linking_asset_to_cross_org_data_asset_returns_404(client, db_session):
    org1 = _bootstrap(client, db_session, "otics-cross-a")
    org2 = _bootstrap(client, db_session, "otics-cross-b")

    other_org_data_asset = _create_data_asset(db_session, org2["organization_id"])

    response = client.post(
        ASSETS_BASE,
        headers=org1["org_headers"],
        json={
            "name": "HMI-1",
            "asset_type": "hmi",
            "criticality": "low",
            "linked_data_asset_id": str(other_org_data_asset.id),
        },
    )
    assert response.status_code == 404

    same_org_data_asset = _create_data_asset(db_session, org1["organization_id"])
    ok_response = client.post(
        ASSETS_BASE,
        headers=org1["org_headers"],
        json={
            "name": "HMI-2",
            "asset_type": "hmi",
            "criticality": "low",
            "linked_data_asset_id": str(same_org_data_asset.id),
        },
    )
    assert ok_response.status_code == 201
    assert ok_response.json()["linked_data_asset_id"] == str(same_org_data_asset.id)


def test_invalid_enum_values_return_422_listing_allowed_values(client, db_session):
    org = _bootstrap(client, db_session, "otics-enum")

    bad_asset_type = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={"name": "Weird", "asset_type": "toaster", "criticality": "low"},
    )
    assert bad_asset_type.status_code == 422

    bad_criticality = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={"name": "Weird2", "asset_type": "plc", "criticality": "meh"},
    )
    assert bad_criticality.status_code == 422

    agent = _register_agent(client, org["org_headers"], name="ot-collector-enum")
    asset = _create_asset(client, org["org_headers"], name="PLC-enum")
    bad_finding_type = _ingest(
        client,
        agent["token"],
        {"asset_id": asset["id"], "finding_type": "not_a_real_type", "severity": "high"},
    )
    assert bad_finding_type["status_code"] == 422


def test_duplicate_agent_registration_name_in_same_org_returns_409(client, db_session):
    org = _bootstrap(client, db_session, "otics-dupe")
    _register_agent(client, org["org_headers"], name="dup-collector")

    duplicate = client.post(AGENTS_BASE, headers=org["org_headers"], json={"name": "dup-collector"})
    assert duplicate.status_code == 409


def test_findings_summary_reflects_real_counts_by_severity(client, db_session):
    org = _bootstrap(client, db_session, "otics-summary")
    agent = _register_agent(client, org["org_headers"], name="ot-collector-summary")

    asset_a = _create_asset(client, org["org_headers"], name="PLC-A", network_segment="vlan-200", criticality="critical")
    asset_b = _create_asset(client, org["org_headers"], name="PLC-B", network_segment="vlan-200", criticality="high")
    asset_c = _create_asset(client, org["org_headers"], name="PLC-C", network_segment="vlan-300", criticality="low")

    for asset, severity, finding_type in [
        (asset_a, "critical", "unpatched_firmware"),
        (asset_a, "high", "protocol_violation"),
        (asset_b, "high", "default_credentials"),
        (asset_c, "low", "other"),
        (asset_c, "medium", "anomalous_traffic"),
    ]:
        result = _ingest(
            client,
            agent["token"],
            {"asset_id": asset["id"], "finding_type": finding_type, "severity": severity},
        )
        assert result["status_code"] == 200

    summary = client.get(f"{FINDINGS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()

    assert body["total_findings"] == 5
    assert body["open_findings"] == 5
    assert body["resolved_findings"] == 0
    assert body["counts_by_severity"]["critical"] == 1
    assert body["counts_by_severity"]["high"] == 2
    assert body["counts_by_severity"]["low"] == 1
    assert body["counts_by_severity"]["medium"] == 1
    assert body["counts_by_finding_type"]["unpatched_firmware"] == 1
    assert set(body["assets_with_open_high_or_critical"]) == {asset_a["id"], asset_b["id"]}
    # vlan-200 has 3 concentrated open high/critical findings (2 from asset_a + 1 from asset_b) -> flagged
    flagged_segments = {row["network_segment"]: row["open_high_or_critical_count"] for row in body["flagged_network_segments"]}
    assert flagged_segments.get("vlan-200") == 3
    assert "vlan-300" not in flagged_segments


def test_audit_log_rows_exist_for_agent_and_asset_lifecycle(client, db_session):
    org = _bootstrap(client, db_session, "otics-audit")

    agent = _register_agent(client, org["org_headers"], name="ot-collector-audit")
    asset = _create_asset(client, org["org_headers"], name="PLC-audit")

    client.patch(f"{ASSETS_BASE}/{asset['id']}", headers=org["org_headers"], json={"criticality": "critical"})
    client.delete(f"{ASSETS_BASE}/{asset['id']}", headers=org["org_headers"])
    client.delete(f"{AGENTS_BASE}/{agent['id']}", headers=org["org_headers"])

    actions = {
        item.action
        for item in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org["organization_id"])).all()
    }
    assert "ot_ics.agent_registered" in actions
    assert "ot_ics.agent_deregistered" in actions
    assert "ot_ics.asset_created" in actions
    assert "ot_ics.asset_updated" in actions
    assert "ot_ics.asset_deleted" in actions


def _create_readonly_user_without_ot_ics_permission(db_session, org_id: str, email: str) -> User:
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

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == "readonly").one()
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


def test_resolve_finding_sets_resolved_at_is_idempotent_and_audited(client, db_session):
    org = _bootstrap(client, db_session, "otics-resolve")
    agent = _register_agent(client, org["org_headers"], name="ot-collector-resolve")
    asset = _create_asset(client, org["org_headers"], name="PLC-resolve")

    ingested = _ingest(
        client,
        agent["token"],
        {"asset_id": asset["id"], "finding_type": "unpatched_firmware", "severity": "critical"},
    )
    assert ingested["status_code"] == 200
    finding_id = ingested["json"]["finding_id"]

    # Before resolving: summary counts it as open.
    summary_before = client.get(f"{FINDINGS_BASE}/summary", headers=org["org_headers"]).json()
    assert summary_before["open_findings"] == 1
    assert summary_before["resolved_findings"] == 0

    resolved = client.post(
        f"{FINDINGS_BASE}/{finding_id}/resolve",
        headers=org["org_headers"],
        json={"resolution_note": "firmware patched to v2.3.1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None

    from app.models.ot_ics_finding import OtIcsFinding as _Finding

    stored = db_session.query(_Finding).filter_by(id=uuid.UUID(finding_id)).one()
    assert stored.resolved_at is not None

    summary_after = client.get(f"{FINDINGS_BASE}/summary", headers=org["org_headers"]).json()
    assert summary_after["open_findings"] == 0
    assert summary_after["resolved_findings"] == 1

    audit_rows = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org["organization_id"]),
        AuditLog.action == "ot_ics.finding_resolved",
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].entity_id == uuid.UUID(finding_id)
    assert audit_rows[0].metadata_json["resolution_note"] == "firmware patched to v2.3.1"

    # Resolving again is idempotent: no duplicate audit row, still 200.
    resolved_again = client.post(f"{FINDINGS_BASE}/{finding_id}/resolve", headers=org["org_headers"], json={})
    assert resolved_again.status_code == 200
    audit_rows_after_second_call = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org["organization_id"]),
        AuditLog.action == "ot_ics.finding_resolved",
    ).all()
    assert len(audit_rows_after_second_call) == 1

    # Resolving a finding from another org (or nonexistent) 404s, no cross-org leak.
    other_org = _bootstrap(client, db_session, "otics-resolve-other")
    cross_org_attempt = client.post(
        f"{FINDINGS_BASE}/{finding_id}/resolve", headers=other_org["org_headers"], json={}
    )
    assert cross_org_attempt.status_code == 404

    missing = client.post(
        f"{FINDINGS_BASE}/{uuid.uuid4()}/resolve", headers=org["org_headers"], json={}
    )
    assert missing.status_code == 404


def test_permission_enforcement_403_for_manage_but_agent_ingest_uses_token_auth_401(client, db_session):
    from tests.helpers.auth_org import login_user, org_headers

    org = _bootstrap(client, db_session, "otics-perm")

    _create_readonly_user_without_ot_ics_permission(db_session, org["organization_id"], "otics-readonly@example.com")
    token = login_user(client, "otics-readonly@example.com")
    readonly_headers = org_headers(token, org["organization_id"])

    forbidden = client.post(
        ASSETS_BASE,
        headers=readonly_headers,
        json={"name": "Blocked", "asset_type": "plc", "criticality": "low"},
    )
    assert forbidden.status_code == 403

    # The ingest endpoint uses agent-token auth (not user/permission auth), so an
    # invalid/missing token there must be 401, not 403.
    missing_token = client.post(
        INGEST_URL,
        json={"asset_id": str(uuid.uuid4()), "finding_type": "other", "severity": "low"},
    )
    assert missing_token.status_code == 401

    bad_token = client.post(
        INGEST_URL,
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"asset_id": str(uuid.uuid4()), "finding_type": "other", "severity": "low"},
    )
    assert bad_token.status_code == 401
