"""control-exception four-eyes: decided_by column + distinct exceptions:override perm

Closes the approval-chain collapse where a single identity could clear an entire
multi-step control-exception chain.

Two changes, one logical fix:

1. control_exception_approvals.decided_by_user_id -- the identity that actually
   recorded a step's decision, distinct from approver_user_id (the *assigned*
   approver). Distinct-identity (four-eyes) enforcement keys on this column so an
   override-approved step still counts against its decider. Nullable: existing
   decided rows predate the column and are left NULL.

2. A new, distinct permission exceptions:override, granted to owner + admin only.
   Previously the approve endpoint required exceptions:approve AND the service
   derived "override authority" from that same permission -- so it was true for
   every caller and the per-step / distinct-identity guards were dead. The endpoint
   now gates on org membership and override is this separate, rarely-granted code,
   leaving exceptions:approve holders (e.g. reviewer) as ordinary approvers bound
   by the chain. Self-sufficient (inserts the permission row if absent) and
   idempotent, mirroring 0311/0313/0315.

Reversibility: downgrade drops the column and removes the permission row (its
grants cascade).

Revision ID: 0316_control_exception_four_eyes
Revises: 0315_backfill_shadow_ai_signature_perms
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0316_control_exception_four_eyes"
down_revision: str | None = "0315_backfill_shadow_ai_signature_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OVERRIDE_KEY = "exceptions:override"
_OVERRIDE_DESCRIPTION = (
    "Override the control-exception approval chain (approve out of assigned order, "
    "as a non-assigned approver, or without a chain)"
)
_OVERRIDE_ROLES: tuple[str, ...] = ("owner", "admin")


def _permission_id_by_key(bind, key: str):
    return bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()


def _role_ids(bind, names: tuple[str, ...]) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text("SELECT id FROM roles WHERE is_system_role = TRUE AND name IN :names").bindparams(
                sa.bindparam("names", expanding=True)
            ),
            {"names": list(names)},
        ).scalars().all()
    )


def upgrade() -> None:
    op.add_column(
        "control_exception_approvals",
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_control_exception_approvals_decided_by_user_id_users",
        "control_exception_approvals",
        "users",
        ["decided_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    bind = op.get_bind()
    permission_id = _permission_id_by_key(bind, _OVERRIDE_KEY)
    if permission_id is None:
        permission_id = str(uuid.uuid4())
        bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
            {"id": permission_id, "key": _OVERRIDE_KEY, "description": _OVERRIDE_DESCRIPTION},
        )
    for role_id in _role_ids(bind, _OVERRIDE_ROLES):
        exists = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :pid"),
            {"role_id": role_id, "pid": permission_id},
        ).scalar()
        if exists is None:
            bind.execute(
                sa.text("INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role_id, :pid)"),
                {"id": str(uuid.uuid4()), "role_id": role_id, "pid": permission_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = _permission_id_by_key(bind, _OVERRIDE_KEY)
    if permission_id is not None:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": permission_id})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": permission_id})

    op.drop_constraint(
        "fk_control_exception_approvals_decided_by_user_id_users",
        "control_exception_approvals",
        type_="foreignkey",
    )
    op.drop_column("control_exception_approvals", "decided_by_user_id")
