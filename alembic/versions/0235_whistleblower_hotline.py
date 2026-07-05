"""add whistleblower hotline reports and messages

Reporter anonymity is a hard invariant of this migration: the
whistleblower_reports table has no created_by/submitter user FK, no IP
address column, and no session reference. The only reporter credential is
a high-entropy tracking code, stored here only as its sha256 hash
(tracking_code_hash) -- the raw code is never persisted.

Revision ID: 0235_whistleblower_hotline
Revises: 0234_dora_resilience_testing
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0235_whistleblower_hotline"
down_revision: str | None = "0234_dora_resilience_testing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Only owner/admin/compliance_manager may investigate whistleblower reports.
# This is intentionally NOT granted to reviewer/auditor/readonly by default
# given the sensitivity of this data; revisit if a read-only "auditor can
# view whistleblower cases" need emerges later.
PERMISSIONS = [
    (
        "whistleblower:investigate",
        "Investigate and respond to whistleblower hotline reports",
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
        "whistleblower_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("anonymous_id", sa.String(length=64), nullable=False),
        sa.Column("tracking_code_hash", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="submitted"),
        sa.Column("assigned_investigator_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "category IN ('fraud', 'corruption', 'harassment', 'safety_violation', 'data_privacy', "
            "'financial_misconduct', 'discrimination', 'retaliation', 'other')",
            name="ck_whistleblower_reports_category",
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'under_review', 'investigating', 'resolved', 'closed', 'dismissed')",
            name="ck_whistleblower_reports_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_investigator_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anonymous_id", name="uq_whistleblower_reports_anonymous_id"),
        sa.UniqueConstraint("tracking_code_hash", name="uq_whistleblower_reports_tracking_code_hash"),
    )
    op.create_index(
        "ix_whistleblower_reports_org_status",
        "whistleblower_reports",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "whistleblower_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "sender_type IN ('reporter', 'investigator')",
            name="ck_whistleblower_messages_sender_type",
        ),
        sa.ForeignKeyConstraint(["report_id"], ["whistleblower_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_whistleblower_messages_report_created",
        "whistleblower_messages",
        ["report_id", "created_at"],
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

    op.drop_index("ix_whistleblower_messages_report_created", table_name="whistleblower_messages")
    op.drop_table("whistleblower_messages")
    op.drop_index("ix_whistleblower_reports_org_status", table_name="whistleblower_reports")
    op.drop_table("whistleblower_reports")
