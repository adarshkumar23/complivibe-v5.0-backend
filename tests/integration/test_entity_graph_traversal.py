from __future__ import annotations

"""
Entity-graph recursive-CTE traversal -- Postgres integration test (manual/CI gate).

Exercises the Step-2 read layer (app/compliance/services/entity_graph_traversal_service.py)
against a REAL PostgreSQL 14+ instance -- the CYCLE clause is Postgres-only, so this
cannot run on SQLite.

STANDING RULE (see tests/integration/test_postgres_migration_smoke.py): Postgres-touching
tests use the dedicated `complivibe_test_user` role, NEVER `complivibe_user`. Run:

    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://complivibe_test_user:complivibe_test_local_only@localhost:5432/complivibe_entity_graph_test \
    PYTHONPATH=. .venv/bin/pytest tests/integration/test_entity_graph_traversal.py -m postgres_smoke -v

The traversal is a pure (entity_type, entity_id) reachability layer that never reads the
node tables (risks/controls/...), only the edge tables. So we isolate the graph logic by
building the real schema, DROPPING all FK constraints in the throwaway test DB, and
inserting edge rows with synthetic node UUIDs. This validates the registry + CTE against
the ACTUAL edge-table columns while decoupling the test from unrelated node-table schemas.
"""

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.compliance.services.entity_graph_registry import (
    EDGE_REGISTRY,
    SeamStatus,
    validate_registry,
)
from app.compliance.services.entity_graph_traversal_service import (
    EntityGraphTraversalService,
)
from app.db.base import Base
import app.models  # noqa: F401  -- register all mappers

# ---- Fixed UUIDs for a hand-readable graph --------------------------------
ORG_A = uuid.UUID("0a000000-0000-0000-0000-000000000001")
ORG_B = uuid.UUID("0b000000-0000-0000-0000-000000000001")
USER = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

# Shared across BOTH orgs -- the cross-tenant leak hazard.
V = uuid.UUID("11111111-0000-0000-0000-000000000001")

# Org-A nodes
C1 = uuid.UUID("a1000000-0000-0000-0000-0000000000c1")
R1 = uuid.UUID("a1000000-0000-0000-0000-0000000000d1")
R2 = uuid.UUID("a1000000-0000-0000-0000-0000000000d2")
R3 = uuid.UUID("a1000000-0000-0000-0000-0000000000d3")
O1 = uuid.UUID("a1000000-0000-0000-0000-0000000000e1")
O2 = uuid.UUID("a1000000-0000-0000-0000-0000000000e2")
O3 = uuid.UUID("a1000000-0000-0000-0000-0000000000e3")
P1 = uuid.UUID("a1000000-0000-0000-0000-0000000000f1")
C9 = uuid.UUID("a1000000-0000-0000-0000-0000000000c9")
FRAMEWORK = uuid.UUID("a1000000-0000-0000-0000-00000000ffff")

# Org-B nodes (must never be reached from an Org-A anchor)
C_B = uuid.UUID("b1000000-0000-0000-0000-000000000001")
R_B = uuid.UUID("b1000000-0000-0000-0000-000000000002")
P_B = uuid.UUID("b1000000-0000-0000-0000-000000000003")


def _db_name(url: URL) -> str:
    return (url.database or "").strip()


def _assert_safe_test_db(url: URL) -> None:
    db_name = _db_name(url)
    if not db_name:
        raise AssertionError("POSTGRES_TEST_DATABASE_URL must include a database name")
    if db_name == "complivibe":
        raise AssertionError("Refusing to run against production database name 'complivibe'")
    if "test" not in db_name and "smoke" not in db_name:
        raise AssertionError(f"Must point to a dedicated test/smoke database (got '{db_name}')")
    if (url.username or "") == "complivibe_user":
        raise AssertionError("Refusing to run as live role complivibe_user; use complivibe_test_user")


def _recreate_db(target: URL) -> None:
    admin = sa.create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = _db_name(target)
    with admin.connect() as conn:
        conn.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": name},
        )
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def _create_edge_tables(engine: sa.Engine) -> None:
    """Create ONLY the registry's edge tables, as faithful FK-stripped copies.

    The traversal reads exactly these tables and never the node tables, so we
    avoid building the full schema (which pulls pgvector-typed node tables that
    need a superuser CREATE EXTENSION). FKs are stripped so synthetic node UUIDs
    are valid endpoints; real column names/types/defaults/checks are preserved,
    so the ORM inserts and the CTE run against the actual edge-table shape.
    """
    sub = sa.MetaData()
    table_names = sorted({spec.table for spec in EDGE_REGISTRY})
    for name in table_names:
        src = Base.metadata.tables[name]
        cols = [
            sa.Column(
                c.name,
                c.type,
                primary_key=c.primary_key,
                nullable=c.nullable,
                server_default=c.server_default,
            )
            for c in src.columns
        ]
        sa.Table(name, sub, *cols)  # no FKs/checks/uniques -> synthetic UUIDs are valid
    sub.create_all(engine)


@pytest.fixture(scope="module")
def graph_session():
    db_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; skipping entity-graph PG test")
    target = make_url(db_url)
    if not target.drivername.startswith("postgresql"):
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not PostgreSQL; skipping")
    _assert_safe_test_db(target)

    _recreate_db(target)
    engine = sa.create_engine(target)
    try:
        _create_edge_tables(engine)
        with Session(engine) as session:
            _seed(session)
            session.commit()
            yield session
    finally:
        engine.dispose()
        # Leave the DB for post-run inspection is unnecessary; drop it.
        admin = sa.create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
        name = _db_name(target)
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _seed(db: Session) -> None:
    from app.models.common_control_mapping import CommonControlMapping
    from app.models.control_obligation_mapping import ControlObligationMapping
    from app.models.policy_risk_link import PolicyRiskLink
    from app.models.policy_risk_mapping import PolicyRiskMapping
    from app.models.risk_control_link import RiskControlLink
    from app.models.risk_dependency import RiskDependency
    from app.models.vendor_control_link import VendorControlLink

    # ----- Org A subgraph (anchor = vendor V) -----
    # V --provides--> C1                                  (undirected assoc, depth 1)
    db.add(VendorControlLink(organization_id=ORG_A, vendor_id=V, control_id=C1,
                             status="active", linked_by_user_id=USER))
    # C1 --mitigated_by--> R1                             (depth 2)
    db.add(RiskControlLink(organization_id=ORG_A, risk_id=R1, control_id=C1, status="active"))
    # C1 --satisfies--> O1  (CANONICAL control_obligation_mappings)   (depth 2)
    db.add(ControlObligationMapping(organization_id=ORG_A, control_id=C1, obligation_id=O1,
                                    status="active", created_by_user_id=USER))
    # C1 --satisfies--> O2  (DEPRECATED common_control_mappings)      (depth 2)
    db.add(CommonControlMapping(organization_id=ORG_A, control_id=C1, framework_id=FRAMEWORK,
                                obligation_id=O2, status="active", created_by_user_id=USER))
    # P1 --addresses--> R1  (CANONICAL policy_risk_links)            (P1 at depth 3 from R1)
    db.add(PolicyRiskLink(organization_id=ORG_A, policy_id=P1, risk_id=R1,
                          status="active", created_by=USER))
    # P1 --addresses--> R2  (DEPRECATED policy_risk_mappings)        (R2 at depth 4 from P1)
    db.add(PolicyRiskMapping(organization_id=ORG_A, policy_id=P1, risk_id=R2))
    # R1 --cascades_to--> R3  and  R3 --cascades_to--> R1  => CYCLE  (R3 depth 3)
    db.add(RiskDependency(organization_id=ORG_A, upstream_risk_id=R1, downstream_risk_id=R3,
                          relationship_type="cascades_to"))
    db.add(RiskDependency(organization_id=ORG_A, upstream_risk_id=R3, downstream_risk_id=R1,
                          relationship_type="cascades_to"))
    # Beyond-depth-4 bait: R2 (depth 4) --mitigated_by--> C9  => C9 would be depth 5, must NOT appear.
    db.add(RiskControlLink(organization_id=ORG_A, risk_id=R2, control_id=C9, status="active"))
    # And O3 hangs off R2 too via a control -- also beyond depth, must NOT appear.
    db.add(ControlObligationMapping(organization_id=ORG_A, control_id=C9, obligation_id=O3,
                                    status="active", created_by_user_id=USER))

    # ----- Org B subgraph, sharing vendor V (the adversarial leak path) -----
    db.add(VendorControlLink(organization_id=ORG_B, vendor_id=V, control_id=C_B,
                             status="active", linked_by_user_id=USER))
    db.add(RiskControlLink(organization_id=ORG_B, risk_id=R_B, control_id=C_B, status="active"))
    db.add(PolicyRiskLink(organization_id=ORG_B, policy_id=P_B, risk_id=R_B,
                          status="active", created_by=USER))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.postgres_smoke
def test_registry_validates_against_schema():
    validate_registry()  # raises if any table/column drifted


@pytest.mark.postgres_smoke
def test_multi_hop_traversal_depth_and_cycle(graph_session):
    svc = EntityGraphTraversalService(graph_session)
    res = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_A, max_depth=4)

    reached = {(n.entity_type, n.entity_id): n for n in res.nodes}

    # Expected reachable set within depth 4, org A only.
    assert ("control", C1) in reached and reached[("control", C1)].depth == 1
    assert ("risk", R1) in reached and reached[("risk", R1)].depth == 2
    assert ("obligation", O1) in reached and reached[("obligation", O1)].depth == 2
    assert ("obligation", O2) in reached and reached[("obligation", O2)].depth == 2  # via DEPRECATED table
    assert ("policy", P1) in reached and reached[("policy", P1)].depth == 3
    assert ("risk", R3) in reached and reached[("risk", R3)].depth == 3
    assert ("risk", R2) in reached and reached[("risk", R2)].depth == 4  # via DEPRECATED table, at the ceiling

    # Depth ceiling: C9 (depth 5 off R2) and O3 (depth 6) must be excluded.
    assert ("control", C9) not in reached
    assert ("obligation", O3) not in reached
    assert res.depth_reached == 4
    assert res.truncated is False

    # Cycle R1<->R3 must be detected, not looped.
    assert res.cycle_detected is True

    # Edge-type provenance surfaced.
    assert "vendor_provides_control" in reached[("control", C1)].via_edge_types
    assert "risk_cascades_to" in reached[("risk", R3)].via_edge_types


@pytest.mark.postgres_smoke
def test_tenant_isolation_shared_vendor_does_not_bridge(graph_session):
    """CRITICAL: an Org-A anchor must NOT reach Org-B data via the shared vendor V."""
    svc = EntityGraphTraversalService(graph_session)
    res = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_A, max_depth=4)
    reached_ids = {n.entity_id for n in res.nodes}

    assert C_B not in reached_ids, "LEAK: Org-B control reached from Org-A anchor via shared vendor"
    assert R_B not in reached_ids, "LEAK: Org-B risk reached from Org-A anchor"
    assert P_B not in reached_ids, "LEAK: Org-B policy reached from Org-A anchor"

    # Symmetric check: Org-B anchor sees ONLY its own subgraph.
    res_b = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_B, max_depth=4)
    reached_b = {n.entity_id for n in res_b.nodes}
    assert reached_b == {C_B, R_B, P_B}
    assert C1 not in reached_b and R1 not in reached_b


@pytest.mark.postgres_smoke
def test_deprecated_seam_edges_are_not_dropped_but_can_be_excluded(graph_session):
    svc = EntityGraphTraversalService(graph_session)

    # With deprecated tables (default): O2 (common_control_mappings) and R2
    # (policy_risk_mappings) are reachable.
    incl = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_A, max_depth=4)
    incl_ids = {n.entity_id for n in incl.nodes}
    assert O2 in incl_ids
    assert R2 in incl_ids

    # Excluding deprecated tables drops exactly those edges (canonical-only view).
    excl = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_A,
                        max_depth=4, include_deprecated=False)
    excl_ids = {n.entity_id for n in excl.nodes}
    assert O2 not in excl_ids  # only came via deprecated common_control_mappings
    assert R2 not in excl_ids  # only came via deprecated policy_risk_mappings
    assert O1 in excl_ids      # canonical control_obligation_mappings still present
    assert P1 in excl_ids      # canonical policy_risk_links still present


@pytest.mark.postgres_smoke
def test_depth_ceiling_shrinks_reachable_set(graph_session):
    svc = EntityGraphTraversalService(graph_session)
    d2 = svc.traverse(anchor_type="vendor", anchor_id=V, organization_id=ORG_A, max_depth=2)
    d2_ids = {n.entity_id for n in d2.nodes}
    # At depth 2 we reach C1, R1, O1, O2 but not P1/R3 (depth 3) or R2 (depth 4).
    assert {C1, R1, O1, O2} <= d2_ids
    assert P1 not in d2_ids and R3 not in d2_ids and R2 not in d2_ids
    assert d2.depth_reached == 2


@pytest.mark.postgres_smoke
def test_truncation_flag_and_node_cap(graph_session):
    """Build a wide star and confirm max_nodes truncates with an explicit flag."""
    from app.models.risk_control_link import RiskControlLink

    hub_risk = uuid.UUID("cc000000-0000-0000-0000-000000000000")
    org_c = uuid.UUID("0c000000-0000-0000-0000-000000000001")
    for i in range(20):
        cid = uuid.UUID(f"cc000000-0000-0000-0000-0000000{i:05d}")
        graph_session.add(
            RiskControlLink(organization_id=org_c, risk_id=hub_risk, control_id=cid, status="active")
        )
    graph_session.commit()

    svc = EntityGraphTraversalService(graph_session)
    capped = svc.traverse(anchor_type="risk", anchor_id=hub_risk, organization_id=org_c,
                          max_depth=2, max_nodes=5)
    assert capped.truncated is True
    assert len(capped.nodes) == 5

    full = svc.traverse(anchor_type="risk", anchor_id=hub_risk, organization_id=org_c,
                        max_depth=2, max_nodes=1000)
    assert full.truncated is False
    assert len(full.nodes) == 20
