"""backfill governance_graph:* permissions + grants to existing orgs (patent P2)

Adds the two P2 knowledge-graph permission codes to existing orgs:
  * governance_graph:read  -> every system role
  * governance_graph:write -> owner, admin, compliance_manager

Self-sufficient (inserts the permission rows if absent) and idempotent, mirroring
0311. (The scoped satellite keys patent_export:p2:read / patent_ingest:p2:write
are NOT human RBAC permissions -- they live in the patent_scoped_keys table, not
here.)

Reversibility: downgrade removes the two permission rows (cascading grants).

Revision ID: 0313_backfill_governance_graph_perms
Revises: 0312_governance_graph_p2
Create Date: 2026-07-19 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0313_backfill_governance_graph_perms"
down_revision: str | None = "0312_governance_graph_p2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALL_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager", "auditor", "readonly", "reviewer")
_WRITE_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager")

PERMISSION_GRANTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "governance_graph:read": (
        "Read the AI-governance knowledge graph and derived obligations",
        _ALL_ROLES,
    ),
    "governance_graph:write": (
        "Add manual edges and trigger syncs on the AI-governance knowledge graph",
        _WRITE_ROLES,
    ),
}


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
    bind = op.get_bind()
    for key, (description, role_names) in PERMISSION_GRANTS.items():
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            permission_id = str(uuid.uuid4())
            bind.execute(
                sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
                {"id": permission_id, "key": key, "description": description},
            )
        for role_id in _role_ids(bind, role_names):
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
    for key in PERMISSION_GRANTS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": permission_id})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": permission_id})
