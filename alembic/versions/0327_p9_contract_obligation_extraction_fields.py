"""p9 contract obligation extraction fields on customer_commitments

Adds the FIVE columns the P9 contract-extraction pipeline needs that core's
existing ``customer_commitments`` table does not already have.

It creates NO new table. Per standing rule 5 this satellite ADDS a population
pipeline to an EXISTING production feature; the obligation data belongs on the
commitment record itself, not in a parallel table that would then need joining,
backfilling, and keeping consistent.

Verified against real core (not the satellite's stale docstring) before writing:

  already present, reused as-is, NOT duplicated
    commitment_type          <- P9's coarse type, CHECK-constrained to 8 values
    triggering_incident_type <- P9's "trigger_event" concept (migration 0191)
    sla_hours                <- P9's normalised deadline in hours
    linked_contract_ref      <- P9's document provenance reference

  added here
    obligation_type          the precise P9 type, which commitment_type's
                             8-value CHECK list cannot always express
    extracted_params         the Stage 3 parameters, as JSONB
    confidence_score         the Stage 3 deterministic score
    requires_human_review    below-threshold flag
    source_clause_text       the originating clause, for audit

All five are safe for existing rows: four are NULLABLE, and
``requires_human_review`` is NOT NULL with a ``false`` server default, so every
row that predates P9 -- which is every row today -- backfills to "not a
machine-extracted obligation awaiting review". The migration is reversible.

WHY THIS IS 0327 AND NOT 0200
=============================
The upstream satellite patch numbered this 0200 and set down_revision to
``0199_audit_engagement_source_schedule_link``. That revision DOES NOT EXIST in
core's chain -- it survives only as stale docstring prose inside
``0200_risk_appetite_category_ai_governance.py``, whose real parent is
``a6947935ab21``. The satellite read a docstring rather than the code, exactly as
the P4 patch did. Applied as shipped, ``alembic upgrade head`` would abort with
"Can't locate revision identified by '0199_...'". Slot 0200 was also already
taken, so even a real 0199 would have forked the chain into two heads.

This revision therefore chains off the real head at the time of writing,
``0326_patent_scoped_key_p4_ingest``.

Identifier lengths (all well under the 63-byte limit):
  ck_customer_commitments_obligation_type (39)
  ck_customer_commitments_confidence_score (40)
  ix_customer_commitments_org_review (34)

Revision ID: 0327_p9_contract_obligation_extraction_fields
Revises: 0326_patent_scoped_key_p4_ingest
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0327_p9_contract_obligation_extraction_fields"
down_revision: str | None = "0326_patent_scoped_key_p4_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The six types P9 classifies. Kept as a CHECK rather than a native enum so
#: adding a seventh type later is a one-line constraint change, matching how
#: core already constrains commitment_type -- and because native ENUM is
#: disallowed by the locked schema rules.
P9_OBLIGATION_TYPES = (
    "breach_notification_sla",
    "audit_right",
    "data_deletion_timeline",
    "subprocessor_restriction",
    "data_residency_requirement",
    "sla_commitment",
)


def upgrade() -> None:
    op.add_column(
        "customer_commitments",
        sa.Column("obligation_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "customer_commitments",
        sa.Column(
            "extracted_params",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "customer_commitments",
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.add_column(
        "customer_commitments",
        sa.Column(
            "requires_human_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "customer_commitments",
        sa.Column("source_clause_text", sa.Text(), nullable=True),
    )

    op.create_check_constraint(
        "ck_customer_commitments_obligation_type",
        "customer_commitments",
        "obligation_type IS NULL OR obligation_type IN ("
        + ", ".join(f"'{t}'" for t in P9_OBLIGATION_TYPES)
        + ")",
    )
    op.create_check_constraint(
        "ck_customer_commitments_confidence_score",
        "customer_commitments",
        "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
    )

    # Supports the compliance reviewer's primary query: "what is waiting for
    # my review in this organization?"
    op.create_index(
        "ix_customer_commitments_org_review",
        "customer_commitments",
        ["organization_id", "requires_human_review"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customer_commitments_org_review", table_name="customer_commitments")
    op.drop_constraint(
        "ck_customer_commitments_confidence_score", "customer_commitments",
        type_="check",
    )
    op.drop_constraint(
        "ck_customer_commitments_obligation_type", "customer_commitments",
        type_="check",
    )
    op.drop_column("customer_commitments", "source_clause_text")
    op.drop_column("customer_commitments", "requires_human_review")
    op.drop_column("customer_commitments", "confidence_score")
    op.drop_column("customer_commitments", "extracted_params")
    op.drop_column("customer_commitments", "obligation_type")
