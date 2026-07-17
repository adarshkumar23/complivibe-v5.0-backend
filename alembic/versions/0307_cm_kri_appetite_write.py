"""grant risk_indicators:write and risk_appetite:write to compliance_manager

The reviewer de-scope (migration 0306) revoked ``risk_indicators:write`` and
``risk_appetite:write`` from the ``reviewer`` role. After that change no
non-owner/admin role held those write grants, leaving KRI creation/edit and
risk-appetite updates owner/admin-only -- an unintended side effect, since the
``compliance_manager`` role is the intended day-to-day holder of those actions.

The seed fix (adding both keys to ``compliance_manager`` in
``ROLE_PERMISSION_MAP``) only affects newly-created orgs, because seeding is
add-only. This migration grants both permissions to every EXISTING org's system
``compliance_manager`` role, bringing live data in line with the corrected seed.

This is purely additive and touches only the ``compliance_manager`` role; no
other role's ``role_permissions`` rows are modified. It is the additive mirror
of 0306's revocation.

Revision ID: 0307_cm_kri_appetite_write
Revises: 0306_reviewer_role_descope
Create Date: 2026-07-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0307_cm_kri_appetite_write"
down_revision: str | None = "0306_reviewer_role_descope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Write permissions to grant to the compliance_manager role on every existing
# org. These were left owner/admin-only after 0306 stripped them from reviewer.
GRANTED_KEYS: tuple[str, ...] = (
    "risk_indicators:write",
    "risk_appetite:write",
)

_CM_ROLE_FILTER = "name = 'compliance_manager' AND is_system_role = TRUE"


def _cm_role_ids(bind) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text(f"SELECT id FROM roles WHERE {_CM_ROLE_FILTER}")
        ).scalars().all()
    )


def _permission_id_by_key(bind, key: str):
    return bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}
    ).scalar()


def upgrade() -> None:
    """Grant the write permissions to every system compliance_manager role.

    Idempotent: a grant is only inserted where the permission exists and the
    role_permissions row is not already present.
    """
    bind = op.get_bind()
    role_ids = _cm_role_ids(bind)
    if not role_ids:
        return
    for key in GRANTED_KEYS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        for role_id in role_ids:
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions "
                    "WHERE role_id = :role_id AND permission_id = :pid"
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
    """Revoke the granted permissions from every system compliance_manager role.

    Restores the pre-migration state for reversibility.
    """
    bind = op.get_bind()
    role_ids = _cm_role_ids(bind)
    if not role_ids:
        return
    for key in GRANTED_KEYS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id = :pid "
                "AND role_id IN (SELECT id FROM roles WHERE "
                + _CM_ROLE_FILTER
                + ")"
            ),
            {"pid": permission_id},
        )
