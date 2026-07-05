import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.security import get_password_hash
from app.models.ai_system import AISystem
from app.models.ai_usage_policy_check import AiUsagePolicyCheck  # noqa: F401  (ensures table registered on Base.metadata)
from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/ai-usage-compliance"

# These are the two NEW permission codes this feature introduces. The shared
# seed_service.py PERMISSIONS dict / ROLE_PERMISSION_MAP are owned by another
# workstream and are not edited here, so this test grants them directly to the
# bootstrapped org's "owner" role via the RBAC tables so the endpoints (which
# gate on these exact codes) are reachable in this isolated test run.
_READ_PERMISSION = "ai_usage_policy:read"
_WRITE_PERMISSION = "ai_usage_policy:write"


@pytest.fixture(scope="session", autouse=True)
def _register_ai_usage_compliance_router(_test_app):
    from app.api.v1 import ai_usage_compliance as ai_usage_compliance_router_module

    already_mounted = any(
        getattr(route, "path", "").startswith("/api/v1/ai-usage-compliance") for route in _test_app.routes
    )
    if not already_mounted:
        _test_app.include_router(ai_usage_compliance_router_module.router, prefix="/api/v1")
    yield


def _grant_permissions(db_session, organization_id: str, codes: tuple[str, ...] = (_READ_PERMISSION, _WRITE_PERMISSION)) -> None:
    org_uuid = uuid.UUID(organization_id)
    owner_role = db_session.query(Role).filter(
        Role.organization_id == org_uuid, Role.name == "owner"
    ).one()

    for code in codes:
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


def _bootstrap(client, db_session, prefix: str, *, codes: tuple[str, ...] = (_READ_PERMISSION, _WRITE_PERMISSION)) -> dict:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _grant_permissions(db_session, org["organization_id"], codes)
    return org


def _create_ai_system(db_session, org_id: str, *, name: str = "Chat Assistant", archived: bool = False) -> AISystem:
    row = AISystem(
        organization_id=uuid.UUID(org_id),
        name=name,
        system_type="model",
        archived_at=datetime.now(UTC) if archived else None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_policy(db_session, org_id: str, owner_id: str, *, policy_type: str = "acceptable_use") -> CompliancePolicy:
    row = CompliancePolicy(
        organization_id=uuid.UUID(org_id),
        title="AI Acceptable Use Policy",
        policy_type=policy_type,
        owner_user_id=uuid.UUID(owner_id),
        status="approved",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_campaign(db_session, org_id: str, policy: CompliancePolicy, created_by: str) -> PolicyAttestationCampaign:
    row = PolicyAttestationCampaign(
        organization_id=uuid.UUID(org_id),
        policy_id=policy.id,
        policy_version=policy.version,
        name=f"Campaign for {policy.title}",
        title=policy.title,
        due_date=date.today() + timedelta(days=30),
        status="active",
        created_by=uuid.UUID(created_by),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_attestation_record(
    db_session,
    org_id: str,
    campaign: PolicyAttestationCampaign,
    user_id: str,
    *,
    status_value: str,
    attested_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> PolicyAttestationRecord:
    row = PolicyAttestationRecord(
        organization_id=uuid.UUID(org_id),
        campaign_id=campaign.id,
        user_id=uuid.UUID(user_id),
        status=status_value,
        attested_at=attested_at,
        expires_at=expires_at,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_gaps_shows_no_policy_reason(client, db_session):
    org = _bootstrap(client, db_session, "aup-nopolicy")
    ai_system = _create_ai_system(db_session, org["organization_id"], name="No Policy System")

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200
    assert run_resp.json()["checked_count"] == 1

    gaps_resp = client.get(f"{BASE}/gaps", headers=org["org_headers"])
    assert gaps_resp.status_code == 200
    gaps = gaps_resp.json()["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["ai_system_id"] == str(ai_system.id)
    assert gaps[0]["compliance_status"] == "non_compliant_no_policy"


def test_gaps_shows_expired_attestation_reason(client, db_session):
    org = _bootstrap(client, db_session, "aup-expired")
    ai_system = _create_ai_system(db_session, org["organization_id"], name="Expired Attestation System")
    policy = _create_policy(db_session, org["organization_id"], org["user_id"])
    campaign = _create_campaign(db_session, org["organization_id"], policy, org["user_id"])
    _create_attestation_record(
        db_session,
        org["organization_id"],
        campaign,
        org["user_id"],
        status_value="expired",
        attested_at=datetime.now(UTC) - timedelta(days=400),
        expires_at=datetime.now(UTC) - timedelta(days=35),
    )

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200

    gaps = client.get(f"{BASE}/gaps", headers=org["org_headers"]).json()["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["ai_system_id"] == str(ai_system.id)
    assert gaps[0]["compliance_status"] == "non_compliant_expired_attestation"


def test_gaps_shows_never_attested_reason(client, db_session):
    org = _bootstrap(client, db_session, "aup-never")
    ai_system = _create_ai_system(db_session, org["organization_id"], name="Never Attested System")
    policy = _create_policy(db_session, org["organization_id"], org["user_id"])
    campaign = _create_campaign(db_session, org["organization_id"], policy, org["user_id"])
    _create_attestation_record(
        db_session,
        org["organization_id"],
        campaign,
        org["user_id"],
        status_value="pending",
    )

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200

    gaps = client.get(f"{BASE}/gaps", headers=org["org_headers"]).json()["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["ai_system_id"] == str(ai_system.id)
    assert gaps[0]["compliance_status"] == "non_compliant_never_attested"


def test_compliant_system_absent_from_gaps(client, db_session):
    org = _bootstrap(client, db_session, "aup-compliant")
    ai_system = _create_ai_system(db_session, org["organization_id"], name="Compliant System")
    policy = _create_policy(db_session, org["organization_id"], org["user_id"])
    campaign = _create_campaign(db_session, org["organization_id"], policy, org["user_id"])
    _create_attestation_record(
        db_session,
        org["organization_id"],
        campaign,
        org["user_id"],
        status_value="attested",
        attested_at=datetime.now(UTC) - timedelta(days=10),
        expires_at=datetime.now(UTC) + timedelta(days=355),
    )

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200
    assert run_resp.json()["results"][0]["compliance_status"] == "compliant"

    gaps = client.get(f"{BASE}/gaps", headers=org["org_headers"]).json()["gaps"]
    assert gaps == []

    single = client.get(f"{BASE}/ai-systems/{ai_system.id}", headers=org["org_headers"])
    assert single.status_code == 200
    assert single.json()["compliance_status"] == "compliant"

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"]).json()
    assert summary["total_checked"] == 1
    assert summary["by_status"] == {"compliant": 1}


def test_archived_ai_system_excluded_from_bulk_run_and_gaps(client, db_session):
    org = _bootstrap(client, db_session, "aup-archived")
    _create_ai_system(db_session, org["organization_id"], name="Active System")
    _create_ai_system(db_session, org["organization_id"], name="Archived System", archived=True)

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200
    assert run_resp.json()["checked_count"] == 1

    gaps = client.get(f"{BASE}/gaps", headers=org["org_headers"]).json()["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["ai_system_name"] == "Active System"


def test_audit_log_rows_exist_for_bulk_run(client, db_session):
    org = _bootstrap(client, db_session, "aup-audit")
    _create_ai_system(db_session, org["organization_id"])

    run_resp = client.post(f"{BASE}/run", headers=org["org_headers"])
    assert run_resp.status_code == 200

    actions = {
        item.action
        for item in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "ai_usage_policy.bulk_run" in actions


def test_permission_enforcement_write_requires_permission(client, db_session):
    # The org owner/admin roles get every registered permission automatically
    # (full permission set), so exercising the owner role here would be a
    # tautological test now that ai_usage_policy:read/write are genuinely
    # registered in seed_service.py. Use a role that only carries the read
    # permission instead -- "readonly" gets ai_usage_policy:read but not
    # ai_usage_policy:write per seed_service.py's ROLE_PERMISSION_MAP.
    org = _bootstrap(client, db_session, "aup-perm", codes=(_READ_PERMISSION, _WRITE_PERMISSION))

    email = "aup-perm-readonly@example.com"
    user = User(
        email=email,
        full_name="aup-perm-readonly",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    role = db_session.query(Role).filter(
        Role.organization_id == uuid.UUID(org["organization_id"]), Role.name == "readonly"
    ).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org["organization_id"]),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()

    token = login_user(client, email)
    headers = org_headers(token, org["organization_id"])

    response = client.post(f"{BASE}/run", headers=headers)
    assert response.status_code == 403

    summary_response = client.get(f"{BASE}/summary", headers=headers)
    assert summary_response.status_code == 200
