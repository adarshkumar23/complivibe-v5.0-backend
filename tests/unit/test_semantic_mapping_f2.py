from __future__ import annotations

import uuid

from sqlalchemy import inspect, select

from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation
from tests.helpers.auth_org import bootstrap_org_user


def _create_framework(db_session, *, code: str, name: str) -> Framework:
    row = Framework(
        code=code,
        name=name,
        description=f"{name} framework",
        category="Security",
        jurisdiction="global",
        authority="CompliVibe",
        version="1.0",
        status="active",
        coverage_level="starter",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _create_obligation(
    db_session,
    *,
    framework_id: uuid.UUID,
    ref: str,
    title: str,
    description: str,
) -> Obligation:
    row = Obligation(
        framework_id=framework_id,
        framework_section_id=None,
        reference_code=ref,
        title=title,
        description=description,
        plain_language_summary=title,
        obligation_type="security",
        jurisdiction="global",
        source_url=None,
        version="1.0",
        ig_level=None,
        control_family=None,
        baseline=None,
        status="active",
        effective_date=None,
        parent_obligation_id=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_semantic_mapping_columns_exist(db_session):
    inspector = inspect(db_session.bind)
    cols = {c["name"] for c in inspector.get_columns("cross_framework_obligation_mappings")}
    assert "semantic_similarity_score" in cols
    assert "mapping_method" in cols


def test_semantic_mapping_migration_contains_manual_backfill():
    path = "alembic/versions/0171_semantic_mapping.py"
    content = open(path, "r", encoding="utf-8").read()
    assert "semantic_similarity_score" in content
    assert "mapping_method" in content
    assert "SET mapping_method = 'manual'" in content


def test_semantic_endpoints_and_fallback_search(client, db_session):
    org = bootstrap_org_user(client, email_prefix="semantic-f2")

    fw_source = _create_framework(db_session, code="SEM_SRC", name="Semantic Source")
    fw_target = _create_framework(db_session, code="SEM_TGT", name="Semantic Target")

    src = _create_obligation(
        db_session,
        framework_id=fw_source.id,
        ref="SRC-001",
        title="Encrypt customer personal data at rest and in transit",
        description="Implement encryption controls for customer personal data at rest and in transit.",
    )
    _create_obligation(
        db_session,
        framework_id=fw_source.id,
        ref="SRC-002",
        title="Encrypt customer personal data at rest and in transit",
        description="Same-framework similar row that should be excluded by default.",
    )
    _create_obligation(
        db_session,
        framework_id=fw_target.id,
        ref="TGT-001",
        title="Encrypt personal customer data at rest and in transit",
        description="Apply encryption controls for personal customer data in transit and at rest.",
    )
    _create_obligation(
        db_session,
        framework_id=fw_target.id,
        ref="TGT-002",
        title="Restrict privileged access and monitor administrator actions",
        description="Least privilege and monitoring controls for administrators.",
    )
    db_session.commit()

    similar = client.get(
        f"/api/v1/compliance/obligations/{src.id}/semantic-similar",
        headers=org["org_headers"],
        params={"top_k": 3, "min_score": 0.2},
    )
    assert similar.status_code == 200, similar.text
    rows = similar.json()
    assert len(rows) <= 3
    assert rows

    for row in rows:
        assert "framework_name" in row
        assert 0.0 <= float(row["similarity_score"]) <= 1.0
        matched = db_session.get(Obligation, uuid.UUID(row["obligation_id"]))
        assert matched is not None
        assert matched.framework_id != fw_source.id

    top_1 = client.get(
        f"/api/v1/compliance/obligations/{src.id}/semantic-similar",
        headers=org["org_headers"],
        params={"top_k": 1, "min_score": 0.2},
    )
    assert top_1.status_code == 200
    assert len(top_1.json()) <= 1

    discover = client.post(
        f"/api/v1/compliance/frameworks/{fw_source.id}/discover-mappings",
        headers=org["org_headers"],
        json={"target_framework_id": str(fw_target.id), "min_score": 0.2},
    )
    assert discover.status_code == 200, discover.text
    discover_payload = discover.json()
    assert "mappings_created" in discover_payload

    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    if mappings:
        assert all(m.mapping_method in {"semantic", "manual", "rule_based", None} for m in mappings)

    status_resp = client.get("/api/v1/compliance/semantic/status", headers=org["org_headers"])
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert isinstance(status_body["pgvector_available"], bool)
    assert "total_obligations" in status_body
    assert "coverage_pct" in status_body

    embed = client.post(
        f"/api/v1/compliance/frameworks/{fw_source.id}/embed",
        headers=org["org_headers"],
        json={},
    )
    assert embed.status_code == 200
    embed_body = embed.json()
    assert "embedded" in embed_body
    assert "skipped" in embed_body
    if not status_body["pgvector_available"]:
        assert embed_body["embedded"] == 0
        assert "reason" in embed_body
