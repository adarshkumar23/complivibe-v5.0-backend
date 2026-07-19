"""backfill shadow_ai_signature:* permissions + grants to existing orgs

Adds the four signature-scored shadow-AI permission codes to existing orgs:
  * shadow_ai_signature:read   -> every system role
  * shadow_ai_signature:write  -> owner, admin, compliance_manager
  * shadow_ai_signature:review -> owner, admin, compliance_manager
  * shadow_ai_signature:admin  -> owner, admin, compliance_manager

These are deliberately distinct from core's existing ai_systems:* codes, which
govern the separate, untouched shadow-AI feature. Self-sufficient (inserts the
permission rows if absent) and idempotent, mirroring 0311/0313.

Reversibility: downgrade removes the four permission rows (cascading grants).

Revision ID: 0315_backfill_shadow_ai_signature_perms
Revises: 0314_shadow_ai_signature_detection
Create Date: 2026-07-19 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0315_backfill_shadow_ai_signature_perms"
down_revision: str | None = "0314_shadow_ai_signature_detection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALL_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager", "auditor", "readonly", "reviewer")
_WRITE_ROLES: tuple[str, ...] = ("owner", "admin", "compliance_manager")

PERMISSION_GRANTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "shadow_ai_signature:read": (
        "Read signature-scored shadow-AI detections, signatures and federated candidates",
        _ALL_ROLES,
    ),
    "shadow_ai_signature:write": (
        "Ingest shadow-AI telemetry and trigger signature rescans",
        _WRITE_ROLES,
    ),
    "shadow_ai_signature:review": (
        "Triage signature-scored shadow-AI detections (confirm, dismiss, escalate, suppress)",
        _WRITE_ROLES,
    ),
    "shadow_ai_signature:admin": (
        "Manage shadow-AI signature registry, IdP connections and federated promotion",
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
