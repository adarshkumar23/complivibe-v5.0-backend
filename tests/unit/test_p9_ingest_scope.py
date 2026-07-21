"""The P9 satellite's own scoped-key type.

P9 gets 'p9_ingest' rather than borrowing P2's 'ingest' or P4's 'p4_ingest',
for the same reason migration 0317 split six subsystems off one shared
OpenMetadata key: a key leaked from any one satellite must not authenticate the
others. These tests pin the isolation at the service layer, where it is
actually enforced (resolve_org_by_key filters on key_type); the matching HTTP
403 is proved against the live route in test_p9_ingest_route.py.
"""

from __future__ import annotations

import uuid

import pytest

from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
from app.models.organization import Organization


@pytest.fixture()
def two_orgs(db_session):
    a = Organization(id=uuid.uuid4(), name="P9 Scope Org A")
    b = Organization(id=uuid.uuid4(), name="P9 Scope Org B")
    db_session.add_all([a, b])
    db_session.flush()
    return a, b


def test_p9_ingest_is_a_provisionable_key_type(db_session, two_orgs):
    org, _ = two_orgs
    raw = PatentScopedKeyService(db_session).provision_key(org.id, "p9_ingest", None)
    assert raw

    resolved = PatentScopedKeyService(db_session).resolve_org_by_key(raw, "p9_ingest")
    assert resolved == org.id


@pytest.mark.parametrize("other_type", ["ingest", "p4_ingest", "export"])
def test_another_satellites_key_cannot_resolve_as_p9(db_session, two_orgs, other_type):
    """The whole reason P9 gets its own key type: no cross-satellite reuse."""
    org, _ = two_orgs
    service = PatentScopedKeyService(db_session)
    foreign_key = service.provision_key(org.id, other_type, None)

    assert service.resolve_org_by_key(foreign_key, "p9_ingest") is None, (
        f"a '{other_type}' key resolved as p9_ingest"
    )


def test_a_p9_key_cannot_resolve_as_another_satellites_scope(db_session, two_orgs):
    """Isolation runs both ways -- a leaked P9 key must not reach P2 or P4."""
    org, _ = two_orgs
    service = PatentScopedKeyService(db_session)
    p9_key = service.provision_key(org.id, "p9_ingest", None)

    for other_type in ("ingest", "p4_ingest", "export"):
        assert service.resolve_org_by_key(p9_key, other_type) is None, (
            f"a p9_ingest key resolved as {other_type}"
        )


def test_a_p9_key_only_ever_resolves_its_own_org(db_session, two_orgs):
    """Org is derived from the key, so one org's key can never name another."""
    org_a, org_b = two_orgs
    service = PatentScopedKeyService(db_session)
    key_a = service.provision_key(org_a.id, "p9_ingest", None)
    service.provision_key(org_b.id, "p9_ingest", None)

    assert service.resolve_org_by_key(key_a, "p9_ingest") == org_a.id


def test_require_p9_ingest_scope_dependency_exists():
    from app.ai_governance.services.governance_graph import scope_deps

    assert hasattr(scope_deps, "require_p9_ingest_scope")
