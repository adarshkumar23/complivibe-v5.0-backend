"""add reports:share and grant it to the egress-capable system roles

POST /reports/share was gated on ``compliance:read``. Minting a share link is not a
read -- it produces a tokenized URL that serves report contents to whoever holds it,
entirely outside the application's authentication. Every system role holds
compliance:read, so ``auditor`` and ``readonly`` -- roles whose defining property is
that they cannot change or export anything -- could mint one.

The seed catalog now carries a dedicated ``reports:share`` permission granted to
owner, admin and compliance_manager. Seeding is add-only, so this migration brings
EXISTING orgs in line: it creates the permission row if absent and grants it to those
three system roles per org.

Roles deliberately NOT granted, and why:
  * readonly / auditor -- read-only postures by definition; egress is out of scope.
  * reviewer -- de-scoped in 0316/0306 from exactly this class of Bucket-B write.
    A reviewer keeps reports:read and reports:generate (in-app, authenticated) but
    not the ability to publish report contents to an unauthenticated URL.

Reversibility: ``downgrade`` revokes the grants and drops the permission row, which
restores the pre-migration state exactly (the endpoint's gate reverts with the code).

Revision ID: 0319_reports_share_permission
Revises: 0318_export_signature_validity_window
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0319_reports_share_permission"
down_revision: str | None = "0318_export_signature_validity_window"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "reports:share"
PERMISSION_DESCRIPTION = "Mint externally-reachable tokenized share links for compliance reports"
TARGET_ROLE_NAMES: tuple[str, ...] = ("owner", "admin", "compliance_manager")


def _permission_id(bind):
    return bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION_KEY}
    ).scalar()


def _target_role_ids(bind) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text(
                "SELECT id FROM roles WHERE is_system_role = TRUE AND name IN :names"
            ).bindparams(sa.bindparam("names", expanding=True)),
            {"names": list(TARGET_ROLE_NAMES)},
        ).scalars().all()
    )


def upgrade() -> None:
    """Create the permission (if absent) and grant it to the three system roles.

    Idempotent throughout: both the permission row and each grant are inserted only
    when not already present, mirroring the add-only backfill pattern of 0307/0309.
    """
    bind = op.get_bind()

    permission_id = _permission_id(bind)
    if permission_id is None:
        permission_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, key, description) "
                "VALUES (:id, :key, :description)"
            ),
            {"id": permission_id, "key": PERMISSION_KEY, "description": PERMISSION_DESCRIPTION},
        )

    for role_id in _target_role_ids(bind):
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :pid"
            ),
            {"role_id": role_id, "pid": permission_id},
        ).scalar()
        if exists is None:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, role_id, permission_id) "
                    "VALUES (:id, :role_id, :pid)"
                ),
                {"id": str(uuid.uuid4()), "role_id": role_id, "pid": permission_id},
            )


def downgrade() -> None:
    """Revoke every grant of reports:share and drop the permission itself."""
    bind = op.get_bind()
    permission_id = _permission_id(bind)
    if permission_id is None:
        return
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": permission_id}
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": permission_id})
