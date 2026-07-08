import uuid
from datetime import UTC, date, datetime, timedelta

from app.core.security import get_password_hash
from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework import Framework
from app.models.issue import Issue
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.role import Role
from app.models.risk import Risk
from app.models.score_snapshot import ScoreSnapshot
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def test_generate_board_scorecard_includes_expected_content_and_report_type(client, db_session):
    token = _register(client, "a71-owner1@example.com", "Pass1234!@", "A71 Org1")
    org = uuid.UUID(_org_id(client, token))

    owner = _create_active_user_with_role(db_session, str(org), "a71-riskowner@example.com", "compliance_manager")
    now = datetime.now(UTC)

    framework = Framework(
        code=f"A71-{uuid.uuid4().hex[:8]}",
        name="A71 Framework",
        category="regulatory",
        jurisdiction="global",
        status="active",
        coverage_level="starter",
    )
    db_session.add(framework)
    db_session.flush()
    obligation = Obligation(
        framework_id=framework.id,
        reference_code="A71-REQ-1",
        title="A71 Requirement 1",
        jurisdiction="global",
        status="active",
    )
    db_session.add(obligation)
    db_session.flush()

    db_session.add_all(
        [
            ScoreSnapshot(
                organization_id=org,
                snapshot_type="compliance_readiness",
                score=76,
                grade="C",
                inputs_json={},
                breakdown_json={},
                calculated_at=now,
            ),
            ScoreSnapshot(
                organization_id=org,
                snapshot_type="compliance_readiness",
                score=61,
                grade="D",
                inputs_json={},
                breakdown_json={},
                calculated_at=now - timedelta(days=90),
            ),
            Risk(
                organization_id=org,
                title="Critical concentration risk",
                description="desc",
                category="operational",
                severity="critical",
                likelihood=5,
                impact=5,
                inherent_score=25,
                status="identified",
                treatment_strategy="mitigate",
                owner_user_id=owner.id,
            ),
            Issue(
                organization_id=org,
                title="Critical issue",
                description="desc",
                issue_type="security_incident",
                severity="critical",
                source_type="manual",
                status="open",
                owner_id=owner.id,
                created_by=owner.id,
            ),
            ComplianceCertification(
                organization_id=org,
                name="SOC 2",
                certification_type="soc2",
                status="active",
                valid_until=date.today() + timedelta(days=45),
            ),
            ComplianceCertification(
                organization_id=org,
                name="ISO 27001",
                certification_type="iso27001",
                status="expired",
                valid_until=date.today() - timedelta(days=2),
            ),
            ComplianceDeadline(
                organization_id=org,
                title="Quarterly policy review",
                deadline_type="policy_review",
                due_date=date.today() + timedelta(days=20),
                status="upcoming",
                priority="high",
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
            ),
            OrganizationObligationState(
                organization_id=org,
                obligation_id=obligation.id,
                applicability_status="applicable",
                implementation_status="implemented",
            ),
        ]
    )
    db_session.commit()

    resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(token, str(org)))
    assert resp.status_code == 200
    report = resp.json()
    assert report["report_type"] == "board_scorecard"

    detail = client.get(f"/api/v1/reports/{report['id']}", headers=_headers(token, str(org)))
    assert detail.status_code == 200
    section = next(item for item in detail.json()["sections"] if item["section_key"] == "board_scorecard")
    content = section["data_json"]

    assert "score" in content
    assert "score_delta" in content
    assert "narrative" in content
    assert "risks_summary" in content
    assert "issues_summary" in content
    assert "certifications" in content
    assert "upcoming_deadlines" in content
    assert "coverage_improvements" in content
    assert "76" in content["narrative"]
    assert str(owner.id) not in content["narrative"]


def test_board_scorecard_score_delta_none_without_historical_snapshot(client, db_session):
    token = _register(client, "a71-owner2@example.com", "Pass1234!@", "A71 Org2")
    org = uuid.UUID(_org_id(client, token))
    owner = _create_active_user_with_role(db_session, str(org), "a71-owner2-user@example.com", "compliance_manager")

    db_session.add(
        ScoreSnapshot(
            organization_id=org,
            snapshot_type="compliance_readiness",
            score=80,
            grade="B",
            inputs_json={},
            breakdown_json={},
            calculated_at=datetime.now(UTC),
            created_by_user_id=owner.id,
        )
    )
    db_session.commit()

    resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(token, str(org)))
    assert resp.status_code == 200
    detail = client.get(f"/api/v1/reports/{resp.json()['id']}", headers=_headers(token, str(org)))
    payload = next(item for item in detail.json()["sections"] if item["section_key"] == "board_scorecard")["data_json"]
    assert payload["score_delta"] is None


def test_board_scorecard_org_isolation(client, db_session):
    token_a = _register(client, "a71-owner3a@example.com", "Pass1234!@", "A71 Org3A")
    token_b = _register(client, "a71-owner3b@example.com", "Pass1234!@", "A71 Org3B")
    org_a = uuid.UUID(_org_id(client, token_a))
    org_b = uuid.UUID(_org_id(client, token_b))
    owner_a = _create_active_user_with_role(db_session, str(org_a), "a71-owner3a-user@example.com", "compliance_manager")

    db_session.add(
        Risk(
            organization_id=org_a,
            title="Org A risk only",
            description="desc",
            category="operational",
            severity="high",
            likelihood=4,
            impact=4,
            inherent_score=16,
            status="identified",
            treatment_strategy="mitigate",
            owner_user_id=owner_a.id,
        )
    )
    db_session.commit()

    resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(token_b, str(org_b)))
    assert resp.status_code == 200
    detail = client.get(f"/api/v1/reports/{resp.json()['id']}", headers=_headers(token_b, str(org_b)))
    payload = next(item for item in detail.json()["sections"] if item["section_key"] == "board_scorecard")["data_json"]
    titles = [row["title"] for row in payload["risks_summary"]]
    assert "Org A risk only" not in titles


def test_board_scorecard_readonly_role_forbidden(client, db_session):
    """G9 item 5: board-scorecard generation is a write action (persists a new
    ComplianceReport) and must require reports:generate, not just reports:read --
    the readonly/exec-viewer role must not be able to trigger it."""
    owner_token = _register(client, "g9-rbac-owner@example.com", "Pass1234!@", "G9 RBAC Org")
    org_id = _org_id(client, owner_token)

    readonly_user = _create_active_user_with_role(db_session, org_id, "g9-rbac-readonly@example.com", "readonly", password="Pass1234!@")
    login = client.post("/api/v1/auth/login", json={"email": readonly_user.email, "password": "Pass1234!@"})
    assert login.status_code == 200
    readonly_token = login.json()["access_token"]

    resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(readonly_token, org_id))
    assert resp.status_code == 403, resp.text

    # Sanity: the owner (who has reports:generate) can still generate it.
    owner_resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(owner_token, org_id))
    assert owner_resp.status_code == 200


def test_generate_executive_narrative_sections_and_fallbacks(client, db_session):
    token = _register(client, "a74-owner1@example.com", "Pass1234!@", "A74 Org1")
    org = uuid.UUID(_org_id(client, token))
    owner = _create_active_user_with_role(db_session, str(org), "a74-owner1-user@example.com", "compliance_manager")
    now = datetime.now(UTC)

    framework = Framework(
        code=f"TST-{uuid.uuid4().hex[:8]}",
        name="Test Framework",
        category="regulatory",
        jurisdiction="global",
        status="active",
        coverage_level="starter",
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        reference_code="REQ-1",
        title="Requirement 1",
        jurisdiction="global",
        status="active",
    )
    db_session.add(obligation)
    db_session.flush()

    implemented_control = Control(
        organization_id=org,
        title="Implemented Control",
        status="implemented",
        control_type="process",
        criticality="high",
        source="custom",
        created_by_user_id=owner.id,
    )
    db_session.add(implemented_control)
    db_session.flush()

    db_session.add(
        ControlObligationMapping(
            organization_id=org,
            control_id=implemented_control.id,
            obligation_id=obligation.id,
            status="active",
            created_by_user_id=owner.id,
        )
    )
    db_session.add(
        ScoreSnapshot(
            organization_id=org,
            snapshot_type="compliance_readiness",
            score=88,
            grade="B",
            inputs_json={},
            breakdown_json={},
            calculated_at=now,
            created_by_user_id=owner.id,
        )
    )
    db_session.add(
        ScoreSnapshot(
            organization_id=org,
            snapshot_type="compliance_readiness",
            score=80,
            grade="B",
            inputs_json={},
            breakdown_json={},
            calculated_at=now - timedelta(days=90),
            created_by_user_id=owner.id,
        )
    )
    db_session.add(
        ComplianceDeadline(
            organization_id=org,
            title="Nearest deadline",
            deadline_type="audit_preparation",
            due_date=date.today() + timedelta(days=15),
            status="upcoming",
            priority="medium",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
        )
    )
    db_session.commit()

    resp = client.post("/api/v1/reports/executive-narrative", headers=_headers(token, str(org)))
    assert resp.status_code == 200
    assert resp.json()["report_type"] == "executive_narrative"

    detail = client.get(f"/api/v1/reports/{resp.json()['id']}", headers=_headers(token, str(org)))
    assert detail.status_code == 200
    section_map = {item["section_key"]: item for item in detail.json()["sections"]}
    assert {"where_we_stand", "needs_attention", "achievements_this_quarter", "upcoming", "caveats"}.issubset(section_map.keys())

    where_text = section_map["where_we_stand"]["body_markdown"]
    assert "Test Framework" in where_text
    assert "{" not in where_text and "}" not in where_text
    assert str(owner.id) not in where_text

    needs_attention = section_map["needs_attention"]["body_markdown"]
    assert needs_attention == "No high-severity risks currently open."

    achievements = section_map["achievements_this_quarter"]["body_markdown"]
    assert achievements == "No new certifications or risk closures recorded this quarter."

    caveat = section_map["caveats"]["body_markdown"]
    assert "not legal advice" in caveat


def test_item5_needs_attention_flags_high_severity_issue_with_zero_open_risks(client, db_session):
    token = _register(client, "item5-owner@example.com", "Pass1234!@", "Item5 Org")
    org = uuid.UUID(_org_id(client, token))
    owner = _create_active_user_with_role(db_session, str(org), "item5-owner-user@example.com", "compliance_manager")

    db_session.add(
        Issue(
            organization_id=org,
            title="Unpatched high-severity vulnerability",
            description="desc",
            issue_type="security_incident",
            severity="high",
            status="open",
            owner_id=owner.id,
            created_by=owner.id,
        )
    )
    db_session.commit()

    resp = client.post("/api/v1/reports/executive-narrative", headers=_headers(token, str(org)))
    assert resp.status_code == 200

    detail = client.get(f"/api/v1/reports/{resp.json()['id']}", headers=_headers(token, str(org)))
    assert detail.status_code == 200
    section_map = {item["section_key"]: item for item in detail.json()["sections"]}
    needs_attention = section_map["needs_attention"]["body_markdown"]
    assert needs_attention != "No high-severity risks currently open."
    assert "Unpatched high-severity vulnerability" in needs_attention
