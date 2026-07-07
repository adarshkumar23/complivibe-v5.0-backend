import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
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
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str = "Vendor") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_control(client, headers: dict[str, str], *, title: str = "Control") -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "control_type": "policy",
            "criticality": "medium",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_score(client, headers: dict[str, str], vendor_id: str, *, likelihood: str, impact: str, notes: str | None = None) -> dict:
    payload = {"likelihood": likelihood, "impact": impact}
    if notes is not None:
        payload["notes"] = notes
    response = client.post(f"{VENDORS_BASE}/{vendor_id}/risk-scores", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _archive_vendor(client, headers: dict[str, str], vendor_id: str) -> None:
    archived = client.post(f"{VENDORS_BASE}/{vendor_id}/archive", headers=headers, json={"reason": "archived"})
    assert archived.status_code == 200


def test_phase95_deterministic_scoring_formula_and_explanation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-score")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p95-owner@example.com", "admin")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Score Vendor")

    score1 = _create_score(client, org["org_headers"], vendor["id"], likelihood="high", impact="medium")
    score2 = _create_score(client, org["org_headers"], vendor["id"], likelihood="high", impact="medium")

    assert score1["inherent_risk_score"] == 12
    assert score1["risk_level"] == "high"
    assert score2["inherent_risk_score"] == 12
    assert score2["risk_level"] == "high"

    exp = score1["score_explanation_json"]
    assert exp["likelihood_value"] == 4
    assert exp["impact_value"] == 3
    assert exp["formula"] == "likelihood_value * impact_value"
    assert exp["thresholds"]["critical"] == [17, 25]
    assert exp["provenance"] == "manual_vendor_risk_scoring_v1"


def test_phase95_risk_level_thresholds(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-threshold")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p95-threshold-owner@example.com", "admin")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Threshold Vendor")

    low = _create_score(client, org["org_headers"], vendor["id"], likelihood="very_low", impact="very_high")
    medium = _create_score(client, org["org_headers"], vendor["id"], likelihood="medium", impact="medium")
    high = _create_score(client, org["org_headers"], vendor["id"], likelihood="high", impact="high")
    critical = _create_score(client, org["org_headers"], vendor["id"], likelihood="very_high", impact="very_high")

    assert low["inherent_risk_score"] == 5
    assert low["risk_level"] == "medium"
    assert medium["inherent_risk_score"] == 9
    assert medium["risk_level"] == "medium"
    assert high["inherent_risk_score"] == 16
    assert high["risk_level"] == "high"
    assert critical["inherent_risk_score"] == 25
    assert critical["risk_level"] == "critical"


def test_phase95_manual_risk_score_updates_cached_vendor_tier_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-tier-cache")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p95-tier-cache-owner@example.com", "admin")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Tier Cache Vendor")
    assert vendor["risk_tier"] == "not_assessed"

    high = _create_score(client, org["org_headers"], vendor["id"], likelihood="high", impact="high")
    assert high["risk_level"] == "high"

    after_high = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=org["org_headers"])
    assert after_high.status_code == 200
    assert after_high.json()["risk_tier"] == "high"

    critical = _create_score(client, org["org_headers"], vendor["id"], likelihood="very_high", impact="very_high")
    assert critical["risk_level"] == "critical"

    after_critical = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=org["org_headers"])
    assert after_critical.status_code == 200
    assert after_critical.json()["risk_tier"] == "critical"

    latest = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores/latest", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["risk_level"] == after_critical.json()["risk_tier"]

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    tier_updates = [row for row in logs.json() if row["action"] == "vendor.risk_tier.updated"]
    assert any(row["after_json"]["risk_tier"] == "critical" for row in tier_updates)
    assert any(row["after_json"].get("vendor_risk_score_id") == critical["id"] for row in tier_updates)


def test_phase95_score_history_newest_first_and_latest_endpoint(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-history")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p95-history-owner@example.com", "admin")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="History Vendor")

    first = _create_score(client, org["org_headers"], vendor["id"], likelihood="low", impact="low", notes="first")
    second = _create_score(client, org["org_headers"], vendor["id"], likelihood="high", impact="very_high", notes="second")

    listed = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores", headers=org["org_headers"])
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 2
    assert rows[0]["id"] == second["id"]
    assert rows[1]["id"] == first["id"]

    latest = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores/latest", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == second["id"]

    detail = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores/{first['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == first["id"]


def test_phase95_control_link_duplicate_tenant_and_archived_blocking(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p95-link-a")
    org2 = bootstrap_org_user(client, email_prefix="p95-link-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p95-link-owner1@example.com", "admin")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "p95-link-owner2@example.com", "admin")

    vendor1 = _create_vendor(client, org1["org_headers"], owner_user_id=str(owner1.id), name="Link Vendor 1")
    control1 = _create_control(client, org1["org_headers"], title="Control Org1")
    control2 = _create_control(client, org2["org_headers"], title="Control Org2")

    linked = client.post(
        f"{VENDORS_BASE}/{vendor1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control1["id"], "link_reason": "map"},
    )
    assert linked.status_code == 201

    duplicate = client.post(
        f"{VENDORS_BASE}/{vendor1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control1["id"], "link_reason": "dup"},
    )
    assert duplicate.status_code == 400

    cross_org_control = client.post(
        f"{VENDORS_BASE}/{vendor1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control2["id"], "link_reason": "cross"},
    )
    assert cross_org_control.status_code == 404

    cross_org_list = client.get(f"{VENDORS_BASE}/{vendor1['id']}/links/controls", headers=org2["org_headers"])
    assert cross_org_list.status_code == 404

    _archive_vendor(client, org1["org_headers"], vendor1["id"])
    blocked = client.post(
        f"{VENDORS_BASE}/{vendor1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control1["id"], "link_reason": "blocked"},
    )
    assert blocked.status_code == 400

    _ = owner2


def test_phase95_unlink_non_destructive_summary_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-unlink")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p95-unlink-owner@example.com", "admin")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Unlink Vendor")
    control_a = _create_control(client, org["org_headers"], title="Unlink Control A")
    control_b = _create_control(client, org["org_headers"], title="Unlink Control B")

    _ = _create_score(client, org["org_headers"], vendor["id"], likelihood="medium", impact="high")

    link_a = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_a["id"], "link_reason": "a"},
    )
    assert link_a.status_code == 201
    link_b = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_b["id"], "link_reason": "b"},
    )
    assert link_b.status_code == 201

    missing_reason = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/links/controls/{link_b.json()['id']}/unlink",
        headers=org["org_headers"],
        json={},
    )
    assert missing_reason.status_code == 422

    unlinked = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/links/controls/{link_b.json()['id']}/unlink",
        headers=org["org_headers"],
        json={"unlink_reason": "cleanup"},
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["status"] == "unlinked"

    active_links = client.get(f"{VENDORS_BASE}/{vendor['id']}/links/controls", headers=org["org_headers"])
    assert active_links.status_code == 200
    assert len(active_links.json()) == 1

    all_links = client.get(f"{VENDORS_BASE}/{vendor['id']}/links/controls?include_unlinked=true", headers=org["org_headers"])
    assert all_links.status_code == 200
    assert len(all_links.json()) == 2

    summary = client.get(f"{VENDORS_BASE}/{vendor['id']}/links/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_control_links"] == 1
    assert body["unlinked_control_links"] == 1
    assert body["total_active_links"] == 1
    assert body["total_unlinked_links"] == 1

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "vendor_risk_score.created" in actions
    assert "vendor.control_linked" in actions
    assert "vendor.control_unlinked" in actions


def test_phase95_risk_score_flags_stale_after_newer_score_supersedes_it(client, db_session):
    """A prior VendorRiskScore must be flagged recalculated_since_update once a newer
    score changes the vendor's cached risk_tier, and the freshly-created score itself
    must NOT be flagged stale immediately after creation."""
    org = bootstrap_org_user(client, email_prefix="p95-stale")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Stale Signal Vendor")

    first = _create_score(client, org["org_headers"], vendor["id"], likelihood="low", impact="low")
    assert first["recalculated_since_update"] is False

    second = _create_score(client, org["org_headers"], vendor["id"], likelihood="very_high", impact="very_high")
    assert second["recalculated_since_update"] is False

    history = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores", headers=org["org_headers"])
    assert history.status_code == 200
    by_id = {row["id"]: row for row in history.json()}
    assert by_id[first["id"]]["recalculated_since_update"] is True
    assert by_id[first["id"]]["stale_reason"] is not None
    assert by_id[second["id"]]["recalculated_since_update"] is False

    latest = client.get(f"{VENDORS_BASE}/{vendor['id']}/risk-scores/latest", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == second["id"]
    assert latest.json()["recalculated_since_update"] is False


def test_phase95_risk_score_flags_stale_after_nth_party_signal_update(client, db_session):
    """If the vendor's nth-party risk flag is raised AFTER a risk score was computed,
    that score must be surfaced as stale even though its own risk_level still matches
    the vendor's last manually-set tier at creation time."""
    org = bootstrap_org_user(client, email_prefix="p95-nth")
    parent = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Nth Parent Vendor")
    child = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Nth Child Vendor")

    score = _create_score(client, org["org_headers"], parent["id"], likelihood="low", impact="low")
    assert score["recalculated_since_update"] is False

    link_resp = client.post(
        f"/api/v1/vendors/{parent['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": child["id"], "relationship_type": "supplier"},
    )
    assert link_resp.status_code == 201, link_resp.text

    # Drive the nth-party propagation directly via the service (there is no public
    # "fire an arbitrary signal" endpoint; real callers are satellites like sanctions
    # screening or KYB checks that call this same method).
    from app.services.vendor_supply_chain_service import VendorSupplyChainService

    VendorSupplyChainService(db_session).propagate_vendor_signal(
        organization_id=uuid.UUID(org["organization_id"]),
        triggering_vendor_id=uuid.UUID(child["id"]),
        signal_type="sanctions_hit",
        severity="critical",
        explanation="test signal",
        actor_user_id=uuid.UUID(org["user_id"]),
    )
    db_session.commit()

    fetched = client.get(f"{VENDORS_BASE}/{parent['id']}/risk-scores/{score['id']}", headers=org["org_headers"])
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["recalculated_since_update"] is True
    assert "nth-party" in body["stale_reason"]


def test_phase95_list_vendors_supports_pagination(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p95-page")
    for i in range(5):
        _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name=f"Page Vendor {i}")

    page1 = client.get(f"{VENDORS_BASE}?limit=2&skip=0", headers=org["org_headers"])
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get(f"{VENDORS_BASE}?limit=2&skip=2", headers=org["org_headers"])
    assert page2.status_code == 200
    assert len(page2.json()) == 2
    assert {row["id"] for row in page1.json()}.isdisjoint({row["id"] for row in page2.json()})


def test_phase95_creating_critical_vendor_refreshes_tracked_concentration_detection(client, db_session):
    """A newly-created vendor that starts out critical/active is itself one of T1-6's
    direct HHI inputs; an org that already opted into concentration tracking must see
    it reflected immediately, not just after the next unrelated vendor change."""
    org = bootstrap_org_user(client, email_prefix="p95-conc")
    _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Existing Critical Vendor")

    opt_in = client.post("/api/v1/vendor-concentration-risk/recompute", headers=org["org_headers"], json={})
    assert opt_in.status_code == 200
    before_count = opt_in.json()["detection"]["critical_vendor_count"]

    new_vendor_resp = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": "Freshly Created Critical Vendor",
            "vendor_type": "software",
            "owner_user_id": org["user_id"],
            "risk_tier": "critical",
            "status": "active",
        },
    )
    assert new_vendor_resp.status_code == 201

    detection = client.get("/api/v1/vendor-concentration-risk", headers=org["org_headers"])
    assert detection.status_code == 200
    assert detection.json()["critical_vendor_count"] == before_count + 1


def test_phase95_manual_risk_score_escalation_refreshes_tracked_concentration_detection(client, db_session):
    """A manual likelihood x impact score that escalates a vendor to critical is a
    direct T1-6 HHI input just like a sanctions-driven escalation; a tracked org's
    detection must reflect it without a separate manual recompute call."""
    org = bootstrap_org_user(client, email_prefix="p95-conc2")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Escalation Candidate Vendor")

    opt_in = client.post("/api/v1/vendor-concentration-risk/recompute", headers=org["org_headers"], json={})
    assert opt_in.status_code == 200
    before_count = opt_in.json()["detection"]["critical_vendor_count"]

    _create_score(client, org["org_headers"], vendor["id"], likelihood="very_high", impact="very_high")

    detection = client.get("/api/v1/vendor-concentration-risk", headers=org["org_headers"])
    assert detection.status_code == 200
    assert detection.json()["critical_vendor_count"] == before_count + 1

    from app.models.audit_log import AuditLog
    from sqlalchemy import select as sa_select

    audits = db_session.execute(
        sa_select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "vendor_concentration_risk.recomputed",
        )
    ).scalars().all()
    assert any(row.metadata_json["source"] == "vendor_risk_score.created" for row in audits)
