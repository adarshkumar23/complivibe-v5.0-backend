from datetime import UTC, datetime
import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.policy_template import PolicyTemplate
from app.models.policy_template_clone import PolicyTemplateClone
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policy-templates"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "readonly") -> User:
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


def _create_template(
    db_session,
    *,
    slug: str,
    name: str,
    description: str,
    category: str = "Security",
    framework_tags: list[str] | None = None,
    content: str = "## Purpose\nPolicy\n\n## Scope\nAll\n\n## Policy Statement\nApply controls\n\n## Responsibilities\nOwners maintain controls\n\n## Enforcement\nViolations are escalated\n\n## Review Cycle\nAnnual",
    version: str = "1.0",
    is_active: bool = True,
) -> PolicyTemplate:
    row = PolicyTemplate(
        slug=slug,
        name=name,
        description=description,
        category=category,
        framework_tags=framework_tags or ["SOC2"],
        content=content,
        version=version,
        is_active=is_active,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _clone_template(client, headers: dict[str, str], template_id: str, *, policy_name: str | None = None, notes: str | None = None):
    body = {}
    if policy_name is not None:
        body["policy_name"] = policy_name
    if notes is not None:
        body["customization_notes"] = notes
    return client.post(f"{BASE}/{template_id}/clone", headers=headers, json=body)


def test_a33_list_filters_search_inactive_and_clone_count(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a33-list")

    baseline = client.get(BASE, headers=org["org_headers"])
    assert baseline.status_code == 200
    baseline_count = len(baseline.json())

    token = f"a33-list-{uuid.uuid4().hex[:8]}"
    template_a = _create_template(
        db_session,
        slug=f"{token}-a",
        name=f"{token} Alpha",
        description=f"Description for {token} alpha",
        category="Legal",
        framework_tags=["A33_FRAME_ALPHA", "ISO27001"],
    )
    template_b = _create_template(
        db_session,
        slug=f"{token}-b",
        name=f"{token} Beta",
        description=f"Description for {token} beta",
        category="Security",
        framework_tags=["A33_FRAME_BETA"],
    )
    _ = template_b
    _create_template(
        db_session,
        slug=f"{token}-inactive",
        name=f"{token} Inactive",
        description=f"Description for {token} inactive",
        category="Security",
        framework_tags=["A33_FRAME_ALPHA"],
        is_active=False,
    )

    _clone_template(client, org["org_headers"], str(template_a.id), policy_name=f"{token} Policy 1")
    _clone_template(client, org["org_headers"], str(template_a.id), policy_name=f"{token} Policy 2")

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == baseline_count + 2

    search_by_name = client.get(BASE, headers=org["org_headers"], params={"search": f"{token} Alpha"})
    assert search_by_name.status_code == 200
    assert len(search_by_name.json()) == 1
    assert search_by_name.json()[0]["slug"] == f"{token}-a"

    search_by_desc = client.get(BASE, headers=org["org_headers"], params={"search": f"{token} beta"})
    assert search_by_desc.status_code == 200
    assert len(search_by_desc.json()) == 1
    assert search_by_desc.json()[0]["slug"] == f"{token}-b"

    by_category = client.get(BASE, headers=org["org_headers"], params={"category": "Legal", "search": token})
    assert by_category.status_code == 200
    assert [row["slug"] for row in by_category.json()] == [f"{token}-a"]

    by_framework = client.get(BASE, headers=org["org_headers"], params={"framework_tag": "A33_FRAME_ALPHA", "search": token})
    assert by_framework.status_code == 200
    assert [row["slug"] for row in by_framework.json()] == [f"{token}-a"]

    clone_counts = client.get(BASE, headers=org["org_headers"], params={"search": token})
    assert clone_counts.status_code == 200
    by_slug = {row["slug"]: row for row in clone_counts.json()}
    assert by_slug[f"{token}-a"]["clone_count"] == 2
    assert by_slug[f"{token}-b"]["clone_count"] == 0


def test_a33_detail_by_id_and_slug_and_not_found_behaviors(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a33-detail")
    token = f"a33-detail-{uuid.uuid4().hex[:8]}"
    active = _create_template(
        db_session,
        slug=f"{token}-active",
        name=f"{token} Active",
        description="detail active",
        framework_tags=["A33_FRAME_DETAIL"],
        content="## Purpose\nActive content\n\n## Scope\nAll\n\n## Policy Statement\nDo work\n\n## Responsibilities\nOwner\n\n## Enforcement\nEnforced\n\n## Review Cycle\nAnnual",
    )
    inactive = _create_template(
        db_session,
        slug=f"{token}-inactive",
        name=f"{token} Inactive",
        description="detail inactive",
        is_active=False,
    )

    by_id = client.get(f"{BASE}/{active.id}", headers=org["org_headers"])
    assert by_id.status_code == 200
    assert "content" in by_id.json()
    assert by_id.json()["slug"] == active.slug

    by_slug = client.get(f"{BASE}/slug/{active.slug}", headers=org["org_headers"])
    assert by_slug.status_code == 200
    assert by_slug.json()["id"] == str(active.id)
    assert by_slug.json()["content"] == by_id.json()["content"]

    inactive_detail = client.get(f"{BASE}/{inactive.id}", headers=org["org_headers"])
    assert inactive_detail.status_code == 404

    missing = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert missing.status_code == 404


def test_a33_categories_and_framework_counts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a33-cats")

    base_categories = client.get(f"{BASE}/categories", headers=org["org_headers"]).json()
    base_frameworks = client.get(f"{BASE}/frameworks", headers=org["org_headers"]).json()
    cat_baseline = {item["category"]: item["template_count"] for item in base_categories}
    fw_baseline = {item["framework_tag"]: item["template_count"] for item in base_frameworks}

    token = f"a33-cats-{uuid.uuid4().hex[:8]}"
    _create_template(
        db_session,
        slug=f"{token}-1",
        name=f"{token} One",
        description="x",
        category="HR",
        framework_tags=["A33_FRAME_SHARED", "A33_FRAME_ONE"],
    )
    _create_template(
        db_session,
        slug=f"{token}-2",
        name=f"{token} Two",
        description="x",
        category="HR",
        framework_tags=["A33_FRAME_SHARED", "A33_FRAME_TWO"],
    )

    categories = client.get(f"{BASE}/categories", headers=org["org_headers"])
    assert categories.status_code == 200
    cat_now = {item["category"]: item["template_count"] for item in categories.json()}
    assert cat_now["HR"] == cat_baseline.get("HR", 0) + 2

    frameworks = client.get(f"{BASE}/frameworks", headers=org["org_headers"])
    assert frameworks.status_code == 200
    fw_now = {item["framework_tag"]: item["template_count"] for item in frameworks.json()}
    assert fw_now["A33_FRAME_SHARED"] == fw_baseline.get("A33_FRAME_SHARED", 0) + 2
    assert fw_now["A33_FRAME_ONE"] == fw_baseline.get("A33_FRAME_ONE", 0) + 1
    assert fw_now["A33_FRAME_TWO"] == fw_baseline.get("A33_FRAME_TWO", 0) + 1


def test_a33_clone_action_success_custom_name_default_name_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a33-clone")
    token = f"a33-clone-{uuid.uuid4().hex[:8]}"
    template = _create_template(
        db_session,
        slug=f"{token}-template",
        name=f"{token} Template Name",
        description="clone template",
        framework_tags=["A33_FRAME_CLONE"],
    )

    cloned_custom = _clone_template(
        client,
        org["org_headers"],
        str(template.id),
        policy_name=f"{token} Custom Policy",
        notes="Adjusted control ownership.",
    )
    assert cloned_custom.status_code == 201
    custom_body = cloned_custom.json()
    assert custom_body["policy"]["name"] == f"{token} Custom Policy"

    cloned_default = _clone_template(client, org["org_headers"], str(template.id))
    assert cloned_default.status_code == 201
    assert cloned_default.json()["policy"]["name"] == template.name

    policies = (
        db_session.query(CompliancePolicy)
        .filter(CompliancePolicy.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    )
    policy_titles = {row.title for row in policies}
    assert f"{token} Custom Policy" in policy_titles
    assert template.name in policy_titles

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .filter(AuditLog.action == "policy_template.cloned")
        .all()
    )
    assert len(logs) >= 2


def test_a33_clone_inactive_nonexistent_and_non_manager_forbidden(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a33-clone-guard")
    token = f"a33-clone-guard-{uuid.uuid4().hex[:8]}"
    active = _create_template(
        db_session,
        slug=f"{token}-active",
        name=f"{token} Active",
        description="active",
    )
    inactive = _create_template(
        db_session,
        slug=f"{token}-inactive",
        name=f"{token} Inactive",
        description="inactive",
        is_active=False,
    )
    _ = active

    readonly_user = _create_active_user_with_role(db_session, org["organization_id"], f"{token}@example.com", role_name="readonly")
    readonly_headers = org_headers(login_user(client, readonly_user.email), org["organization_id"])

    forbidden = _clone_template(client, readonly_headers, str(active.id))
    assert forbidden.status_code == 403

    inactive_clone = _clone_template(client, org["org_headers"], str(inactive.id))
    assert inactive_clone.status_code == 404

    missing_clone = _clone_template(client, org["org_headers"], str(uuid.uuid4()))
    assert missing_clone.status_code == 404


def test_a33_clone_history_filter_tenant_isolation_and_stats(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a33-history-a")
    org_b = bootstrap_org_user(client, email_prefix="a33-history-b")

    token = f"a33-history-{uuid.uuid4().hex[:8]}"
    template = _create_template(
        db_session,
        slug=f"{token}-template",
        name=f"{token} Template",
        description="history",
        category="Compliance",
        framework_tags=["A33_FRAME_HISTORY"],
    )

    first = _clone_template(client, org_a["org_headers"], str(template.id), policy_name=f"{token} Policy A1")
    second = _clone_template(client, org_a["org_headers"], str(template.id), policy_name=f"{token} Policy A2")
    third = _clone_template(client, org_b["org_headers"], str(template.id), policy_name=f"{token} Policy B1")
    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 201

    org_a_clones = client.get(f"{BASE}/clones", headers=org_a["org_headers"])
    assert org_a_clones.status_code == 200
    assert len(org_a_clones.json()) == 2

    org_b_clones = client.get(f"{BASE}/clones", headers=org_b["org_headers"])
    assert org_b_clones.status_code == 200
    assert len(org_b_clones.json()) == 1

    filtered = client.get(f"{BASE}/clones", headers=org_a["org_headers"], params={"template_id": str(template.id)})
    assert filtered.status_code == 200
    assert len(filtered.json()) == 2

    stats = client.get(f"{BASE}/{template.id}/stats", headers=org_a["org_headers"])
    assert stats.status_code == 200
    body = stats.json()
    assert body["template_id"] == str(template.id)
    assert body["total_clones"] == 3
    assert body["unique_orgs"] == 2
    assert body["most_recent_clone_at"] is not None

    clone_rows = db_session.query(PolicyTemplateClone).filter(PolicyTemplateClone.template_id == template.id).all()
    assert len(clone_rows) == 3
    latest = max(row.cloned_at for row in clone_rows)
    reported = datetime.fromisoformat(body["most_recent_clone_at"].replace("Z", "+00:00"))
    assert abs((reported - latest).total_seconds()) < 5
