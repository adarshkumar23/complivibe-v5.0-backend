"""backfill ai_guardrail:* permissions + grants to existing orgs (patent P3)

The agentic policy-derivation feature (patent P3) adds four permission codes to
the seed ``PERMISSIONS`` catalog:

  * ``ai_guardrail:read``      -> every system role
  * ``ai_guardrail:create``    -> owner, admin, compliance_manager
  * ``ai_guardrail:recompile`` -> owner, admin, compliance_manager
  * ``ai_guardrail:check``     -> owner, admin, compliance_manager

Seeding is add-only, so a fresh boot creates these rows/grants only for NEW
orgs. This migration brings existing orgs in line: it inserts the four
permission rows if absent (unlike 0309 it is self-sufficient -- it does not rely
on the seed having run) and grants each to its target system roles. Purely
additive and idempotent (INSERT only where the row is not already present).

Reversibility: ``downgrade`` removes the four permission rows (cascading their
role_permissions grants), restoring the pre-migration state.

Revision ID: 0311_backfill_ai_guardrail_perms
Revises: 0310_ai_derived_guardrails
Create Date: 2026-07-18 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0311_backfill_ai_guardrail_perms"
down_revision: str | None = "0310_ai_derived_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALL_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager", "auditor", "readonly", "reviewer")
_WRITE_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager")

# permission key -> (description, target system role names)
PERMISSION_GRANTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ai_guardrail:read": (
        "Read AI derived policy guardrails, check events, and signed receipt chains",
        _ALL_ROLES,
    ),
    "ai_guardrail:create": (
        "Derive and compile AI policy guardrails from regulatory obligations",
        _WRITE_ROLES,
    ),
    "ai_guardrail:recompile": (
        "Recompile a derived AI policy guardrail from its source obligations",
        _WRITE_ROLES,
    ),
    "ai_guardrail:check": (
        "Run agent-action guardrail checks and record guardrail check events",
        _WRITE_ROLES,
    ),
}


def _permission_id_by_key(bind, key: str):
    return bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}
    ).scalar()


def _role_ids(bind, names: tuple[str, ...]) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text(
                "SELECT id FROM roles WHERE is_system_role = TRUE AND name IN :names"
            ).bindparams(sa.bindparam("names", expanding=True)),
            {"names": list(names)},
        ).scalars().all()
    )


def upgrade() -> None:
    bind = op.get_bind()
    for key, (description, role_names) in PERMISSION_GRANTS.items():
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            permission_id = str(uuid.uuid4())
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (id, key, description) "
                    "VALUES (:id, :key, :description)"
                ),
                {"id": permission_id, "key": key, "description": description},
            )
        for role_id in _role_ids(bind, role_names):
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
    bind = op.get_bind()
    for key in PERMISSION_GRANTS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        # Remove grants first, then the permission row (explicit even though the
        # role_permissions FK is ON DELETE CASCADE).
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"),
            {"pid": permission_id},
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE id = :pid"),
            {"pid": permission_id},
        )
