import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.role import Role
from app.models.sod_conflict import SodConflictFinding, SodConflictRule  # noqa: F401 - registers metadata
from app.models.user import User
from app.services.sod_conflict_service import SodConflictService


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id:
        headers["X-Organization-ID"] = organization_id
    return headers


def _create_active_user_with_role(db_session, organization_id: uuid.UUID, email: str, role_name: str) -> User:
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

    role = db_session.query(Role).filter(Role.organization_id == organization_id, Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=organization_id,
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def test_sod_detection_creates_only_real_conflicts_and_avoids_duplicates(client, db_session):
    token = _register(client, "t44-sod-owner@example.com", "Pass1234!@", "T44 SoD Org")
    org_id = uuid.UUID(client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"])
    owner = db_session.query(User).filter(User.email == "t44-sod-owner@example.com").one()

    service = SodConflictService(db_session)
    rule = service.create_rule(
        org_id,
        permission_a="users:read",
        permission_b="users:update_role",
        severity="high",
        actor_user_id=owner.id,
    )
    created, permission_codes = service.detect_for_user(org_id, owner.id, actor_user_id=owner.id, source="unit_test")
    db_session.commit()

    assert {"users:read", "users:update_role"}.issubset(permission_codes)
    assert len(created) == 1
    assert created[0].rule_id == rule.id
    assert created[0].status == "open"

    created_again, _ = service.detect_for_user(org_id, owner.id, actor_user_id=owner.id, source="unit_test")
    db_session.commit()

    assert created_again == []
    assert db_session.query(SodConflictFinding).filter_by(organization_id=org_id, user_id=owner.id, rule_id=rule.id).count() == 1

    audit_actions = [row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == org_id).all()]
    assert "sod_conflict_rule.created" in audit_actions
    assert "sod_conflict_finding.created" in audit_actions


def test_sod_detection_does_not_create_finding_when_user_lacks_pair_permission(client, db_session):
    token = _register(client, "t44-sod-owner2@example.com", "Pass1234!@", "T44 SoD Org 2")
    org_id = uuid.UUID(client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"])
    owner = db_session.query(User).filter(User.email == "t44-sod-owner2@example.com").one()
    reviewer = _create_active_user_with_role(db_session, org_id, "t44-sod-reviewer@example.com", "reviewer")

    service = SodConflictService(db_session)
    service.create_rule(
        org_id,
        permission_a="users:invite",
        permission_b="users:update_role",
        severity="critical",
        actor_user_id=owner.id,
    )
    created, reviewer_permissions = service.detect_for_user(org_id, reviewer.id, actor_user_id=owner.id, source="unit_test")
    db_session.commit()

    assert "users:update_role" not in reviewer_permissions
    assert created == []
    assert db_session.query(SodConflictFinding).filter_by(organization_id=org_id, user_id=reviewer.id).count() == 0


def test_sod_rule_soft_deactivate_and_finding_state_changes_are_audited(client, db_session):
    token = _register(client, "t44-sod-owner3@example.com", "Pass1234!@", "T44 SoD Org 3")
    org_id = uuid.UUID(client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"])
    owner = db_session.query(User).filter(User.email == "t44-sod-owner3@example.com").one()

    service = SodConflictService(db_session)
    rule = service.create_rule(
        org_id,
        permission_a="users:read",
        permission_b="users:update_role",
        severity="medium",
        actor_user_id=owner.id,
    )
    findings, _ = service.detect_for_user(org_id, owner.id, actor_user_id=owner.id, source="unit_test")
    finding = findings[0]

    service.acknowledge_finding(org_id, finding.id, actor_user_id=owner.id, note="reviewed")
    service.waive_finding(org_id, finding.id, actor_user_id=owner.id, note="break-glass approved")
    service.deactivate_rule(org_id, rule.id, actor_user_id=owner.id)
    db_session.commit()

    db_session.refresh(rule)
    db_session.refresh(finding)
    assert rule.active is False
    assert rule.status == "inactive"
    assert finding.status == "waived"
    assert finding.note == "break-glass approved"

    audit_actions = [row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == org_id).all()]
    assert "sod_conflict_finding.acknowledged" in audit_actions
    assert "sod_conflict_finding.waived" in audit_actions
    assert "sod_conflict_rule.deactivated" in audit_actions
