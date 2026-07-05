"""add anti-bribery & corruption risk assessments (T4-7)

Grounded methodology: UK Bribery Act 2010 s.7 "adequate procedures" defense
(gov.uk MoJ guidance -- six principles including risk assessment and
monitoring/review), and FCPA-aligned third-party risk factors per the
DOJ/SEC FCPA Resource Guide (jurisdiction corruption risk via Transparency
International CPI, PEP exposure, gifts/hospitality, industry risk). The
scoring implementation lives in
app/satellites/tprm_intelligence/bribery_risk_scoring.py and is an
illustrative, documented weighting scaffold -- not a regulator-prescribed
formula.

Revision ID: 0236_bribery_risk_assessment
Revises: 0235_whistleblower_hotline
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0236_bribery_risk_assessment"
down_revision: str | None = "0235_whistleblower_hotline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# T4-7 is scoped as its own dedicated permission family (not a reuse of
# vendors:read/vendors:write) since it introduces a new first-class
# assessed-risk resource hanging off the vendor, per phase instructions.
PERMISSIONS = [
    (
        "anti_bribery:read",
        "Read anti-bribery and corruption risk assessments for vendors/third parties",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "anti_bribery:manage",
        "Create and compute anti-bribery and corruption risk assessments",
        ("owner", "admin", "compliance_manager"),
    ),
]


def _ensure_permissions() -> None:
    bind = op.get_bind()
    for key, description, roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is None:
            permission_id = bind.execute(
                sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description) RETURNING id"),
                {"id": str(uuid.uuid4()), "key": key, "description": description},
            ).scalar_one()
        role_ids = bind.execute(
            sa.text(f"SELECT id FROM roles WHERE name IN ({','.join(':r' + str(i) for i in range(len(roles)))}) AND is_active = TRUE"),
            {f"r{i}": name for i, name in enumerate(roles)},
        ).scalars().all()
        for role_id in role_ids:
            exists = bind.execute(
                sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"),
                {"role_id": role_id, "permission_id": permission_id},
            ).scalar()
            if exists is None:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role_id, :permission_id)"),
                    {"id": str(uuid.uuid4()), "role_id": role_id, "permission_id": permission_id},
                )


def upgrade() -> None:
    op.create_table(
        "bribery_risk_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction_cpi_score", sa.Integer(), nullable=True),
        sa.Column("pep_exposure", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("gift_hospitality_log_json", sa.JSON(), nullable=True),
        sa.Column("industry_category", sa.String(length=100), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=20), nullable=False),
        sa.Column("scoring_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("computed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "jurisdiction_cpi_score IS NULL OR (jurisdiction_cpi_score >= 0 AND jurisdiction_cpi_score <= 100)",
            name="ck_bribery_risk_assessments_cpi_range",
        ),
        sa.CheckConstraint(
            "pep_exposure IN ('none', 'indirect', 'direct')",
            name="ck_bribery_risk_assessments_pep_exposure",
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1",
            name="ck_bribery_risk_assessments_risk_score_range",
        ),
        sa.CheckConstraint(
            "risk_tier IN ('low', 'medium', 'high')",
            name="ck_bribery_risk_assessments_risk_tier",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bribery_risk_assessments_org_vendor_computed",
        "bribery_risk_assessments",
        ["organization_id", "vendor_id", "computed_at"],
        unique=False,
    )

    _ensure_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})

    op.drop_index("ix_bribery_risk_assessments_org_vendor_computed", table_name="bribery_risk_assessments")
    op.drop_table("bribery_risk_assessments")
