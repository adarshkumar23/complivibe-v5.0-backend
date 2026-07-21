"""The five P9 contract-extraction columns on customer_commitments.

The upstream satellite patch shipped a migration for these five columns but no
ORM or Pydantic change to go with it. That combination fails in the worst
possible way: the columns exist in the database, so nothing errors loudly, but
every write through the ORM silently discards them and every read returns
nothing. These tests pin the round trip -- write five values, read five values
back -- so the schema and the code that reads it cannot drift apart again.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.customer_commitment import CustomerCommitment
from app.models.organization import Organization
from app.models.user import User
from app.schemas.customer_commitment import CustomerCommitmentRead

P9_FIELDS = (
    "obligation_type",
    "extracted_params",
    "confidence_score",
    "requires_human_review",
    "source_clause_text",
)


@pytest.fixture()
def org_and_user(db_session):
    org = Organization(id=uuid.uuid4(), name="P9 Fields Org")
    user = User(
        id=uuid.uuid4(),
        email=f"p9-fields-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add_all([org, user])
    db_session.flush()
    return org, user


def _commitment(org, user, **overrides) -> CustomerCommitment:
    now = datetime.now(UTC)
    row = CustomerCommitment(
        id=uuid.uuid4(),
        organization_id=org.id,
        customer_name="Acme Corp",
        commitment_type="breach_notification",
        title="Notify Acme within 72 hours",
        description="Contractual breach-notification obligation.",
        trigger_condition="A data breach affecting Acme's data",
        assigned_owner_id=user.id,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_all_five_p9_fields_exist_on_the_orm_model():
    """Fails loudly if the migration lands without the mapped attributes."""
    missing = [f for f in P9_FIELDS if not hasattr(CustomerCommitment, f)]
    assert missing == [], f"migration-only columns, not mapped on the ORM: {missing}"


def test_all_five_p9_fields_persist_and_read_back(db_session, org_and_user):
    """The regression the upstream patch would have shipped: silent field loss."""
    org, user = org_and_user
    row = _commitment(
        org,
        user,
        obligation_type="breach_notification_sla",
        extracted_params={"deadline_hours": 72, "recipient": "customer"},
        confidence_score=Decimal("0.9250"),
        requires_human_review=False,
        source_clause_text="Supplier shall notify Customer within 72 hours.",
    )
    db_session.add(row)
    db_session.flush()
    db_session.expunge_all()

    stored = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == row.id)
    ).scalar_one()

    assert stored.obligation_type == "breach_notification_sla"
    assert stored.extracted_params == {"deadline_hours": 72, "recipient": "customer"}
    assert Decimal(str(stored.confidence_score)) == Decimal("0.9250")
    assert stored.requires_human_review is False
    assert stored.source_clause_text == "Supplier shall notify Customer within 72 hours."


def test_p9_fields_round_trip_through_the_read_schema(db_session, org_and_user):
    """A field that persists but is absent from CustomerCommitmentRead is still
    invisible to every API consumer, so the schema is part of the contract."""
    org, user = org_and_user
    row = _commitment(
        org,
        user,
        obligation_type="audit_right",
        extracted_params={"frequency_per_year": 1},
        confidence_score=Decimal("0.8100"),
        requires_human_review=True,
        source_clause_text="Customer may audit Supplier once per year.",
    )
    db_session.add(row)
    db_session.flush()

    read = CustomerCommitmentRead.model_validate(row, from_attributes=True)

    assert read.obligation_type == "audit_right"
    assert read.extracted_params == {"frequency_per_year": 1}
    assert float(read.confidence_score) == pytest.approx(0.81)
    assert read.requires_human_review is True
    assert read.source_clause_text == "Customer may audit Supplier once per year."


def test_p9_fields_default_safely_for_a_human_created_commitment(db_session, org_and_user):
    """Every commitment a human creates predates P9 and sets none of these.

    They must all be optional, and requires_human_review must default to False
    rather than NULL -- it is NOT NULL in the migration.
    """
    org, user = org_and_user
    row = _commitment(org, user)
    db_session.add(row)
    db_session.flush()
    db_session.expunge_all()

    stored = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == row.id)
    ).scalar_one()

    assert stored.obligation_type is None
    assert stored.extracted_params is None
    assert stored.confidence_score is None
    assert stored.source_clause_text is None
    assert stored.requires_human_review is False

    read = CustomerCommitmentRead.model_validate(stored, from_attributes=True)
    assert read.obligation_type is None
    assert read.requires_human_review is False
