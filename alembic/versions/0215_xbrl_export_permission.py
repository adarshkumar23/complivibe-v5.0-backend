"""add xbrl export permission

Revision ID: 0215_xbrl_export_permission
Revises: 0214_esg_disclosure_templates
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0215_xbrl_export_permission"
down_revision: str | None = "0214_esg_disclosure_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "reports:xbrl_export"
PERMISSION_DESCRIPTION = "Generate ESG XBRL exports for compliance reports"


def upgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION_KEY}).scalar()
    if permission_id is None:
        permission_id = bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, key, description)
                VALUES (:id, :key, :description)
                RETURNING id
                """
            ),
            {"id": str(__import__("uuid").uuid4()), "key": PERMISSION_KEY, "description": PERMISSION_DESCRIPTION},
        ).scalar_one()

    role_ids = bind.execute(
        sa.text(
            """
            SELECT id
            FROM roles
            WHERE name IN ('owner', 'admin', 'compliance_manager')
              AND is_active = TRUE
            """
        )
    ).scalars().all()
    for role_id in role_ids:
        exists = bind.execute(
            sa.text(
                """
                SELECT 1
                FROM role_permissions
                WHERE role_id = :role_id AND permission_id = :permission_id
                """
            ),
            {"role_id": role_id, "permission_id": permission_id},
        ).scalar()
        if exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    VALUES (:id, :role_id, :permission_id)
                    """
                ),
                {"id": str(__import__("uuid").uuid4()), "role_id": role_id, "permission_id": permission_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION_KEY}).scalar()
    if permission_id is not None:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
