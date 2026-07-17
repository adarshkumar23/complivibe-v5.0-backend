"""Additional coverage for the crisis-management router (app/api/v1/crisis_management.py).

The existing suite (test_crisis_management_t2_3.py) exercises the create/
activate/resolve happy path, cross-referencing of processes/risks, and the
schema/validation 422s plus the resolve/activate state-machine 400s -- all as
the org owner. It never asserts the require_permission gate nor the not-found
(404) paths nor org-scoping. This file adds:

  * permission enforcement -- crisis_management:manage is denied to a read-only
    role (403 on create/activate/resolve) while crisis_management:read still
    lets that role list (2xx); a bespoke zero-permission role is denied read.
  * not-found edges -- get / activate an unknown playbook, resolve an unknown
    activation.
  * org-scoping -- org B cannot read, activate, or list org A's playbook.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

PLAYBOOKS = "/api/v1/crisis/playbooks"
ACTIVE = "/api/v1/crisis/active"


def _playbook_payload(**overrides) -> dict:
    payload = {
        "name": "Cyber Incident Response Playbook",
        "scenario_type": "cyber_incident",
        "steps_json": [{"step": "Contain the incident"}, {"step": "Notify stakeholders"}],
        "owner_team": "Security",
    }
    payload.update(overrides)
    return payload


def _create_playbook(client, headers, **overrides) -> str:
    resp = client.post(PLAYBOOKS, headers=headers, json=_playbook_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A member on a custom role that holds NO permissions.

    Every seeded role holds crisis_management:read, so a bespoke empty role is
    the only way to exercise the read (403) path.
    """
    from app.models.role import Role

    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"zero-perms-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


# --------------------------------------------------------------------------
# Permission enforcement
# --------------------------------------------------------------------------
def test_create_playbook_requires_crisis_manage(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-manage-perm")
    # readonly holds crisis_management:read but NOT crisis_management:manage.
    ro = add_org_member(db_session, client, org["organization_id"], "cmc-ro@example.com", role_name="readonly")
    resp = client.post(PLAYBOOKS, headers=ro, json=_playbook_payload())
    assert resp.status_code == 403, resp.text


def test_activate_and_resolve_require_crisis_manage(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-mutate-perm")
    owner = org["org_headers"]
    playbook_id = _create_playbook(client, owner)
    activation = client.post(f"{PLAYBOOKS}/{playbook_id}/activate", headers=owner)
    assert activation.status_code == 201, activation.text
    activation_id = activation.json()["id"]

    ro = add_org_member(db_session, client, org["organization_id"], "cmc-ro2@example.com", role_name="readonly")
    activate_denied = client.post(f"{PLAYBOOKS}/{playbook_id}/activate", headers=ro)
    assert activate_denied.status_code == 403, activate_denied.text

    resolve_denied = client.post(
        f"/api/v1/crisis/activations/{activation_id}/resolve", headers=ro, json={"resolution_notes": "x"}
    )
    assert resolve_denied.status_code == 403, resolve_denied.text


def test_readonly_role_can_read_but_not_manage(client, db_session):
    """The read-only member that is refused manage is still allowed read, proving
    the 403 is the manage-permission gate and not a blanket auth failure."""
    org = bootstrap_org_user(client, email_prefix="cmc-read-2xx")
    playbook_id = _create_playbook(client, org["org_headers"])

    ro = add_org_member(db_session, client, org["organization_id"], "cmc-ro3@example.com", role_name="readonly")
    listed = client.get(PLAYBOOKS, headers=ro)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == playbook_id for row in listed.json())

    active = client.get(ACTIVE, headers=ro)
    assert active.status_code == 200, active.text


def test_list_playbooks_requires_crisis_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-read-perm")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "cmc-noperm@example.com")
    resp = client.get(PLAYBOOKS, headers=no_perms)
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------
# Not-found edges
# --------------------------------------------------------------------------
def test_get_unknown_playbook_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-404-get")
    resp = client.get(f"{PLAYBOOKS}/{uuid.uuid4()}", headers=org["org_headers"])
    assert resp.status_code == 404, resp.text


def test_activate_unknown_playbook_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-404-activate")
    resp = client.post(f"{PLAYBOOKS}/{uuid.uuid4()}/activate", headers=org["org_headers"])
    assert resp.status_code == 404, resp.text


def test_resolve_unknown_activation_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cmc-404-resolve")
    resp = client.post(
        f"/api/v1/crisis/activations/{uuid.uuid4()}/resolve", headers=org["org_headers"], json={}
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------
# Org-scoping
# --------------------------------------------------------------------------
def test_playbook_is_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="cmc-org-a")
    org_b = bootstrap_org_user(client, email_prefix="cmc-org-b")
    playbook_id = _create_playbook(client, org_a["org_headers"])

    # Org B cannot read org A's playbook.
    get_b = client.get(f"{PLAYBOOKS}/{playbook_id}", headers=org_b["org_headers"])
    assert get_b.status_code == 404, get_b.text

    # Org B cannot activate org A's playbook.
    activate_b = client.post(f"{PLAYBOOKS}/{playbook_id}/activate", headers=org_b["org_headers"])
    assert activate_b.status_code == 404, activate_b.text

    # Org B's playbook list does not leak org A's playbook.
    list_b = client.get(PLAYBOOKS, headers=org_b["org_headers"])
    assert list_b.status_code == 200, list_b.text
    assert all(row["id"] != playbook_id for row in list_b.json())
