"""backfill entity_graph/compound_insights/score_attribution reads to existing orgs

Three read permissions -- ``entity_graph:read``, ``compound_insights:read`` and
``score_attribution:read`` -- were added to the seed ``PERMISSIONS`` catalog and
granted to every system role (owner, admin, compliance_manager, auditor, readonly,
reviewer) when the entity-graph / compound-insight / score-attribution features
shipped. But seeding is add-only, so those grants only reached orgs created AFTER
each feature landed. Pre-existing orgs' roles never received them, leaving the
graph-traverse / compound-insights / score-explain read endpoints 403 for every
role on those older orgs.

This migration brings live data in line with the corrected seed by granting all
three read permissions to every EXISTING org's six system roles. It is purely
additive (idempotent INSERT where the row is not already present) and mirrors the
add-only backfill pattern of 0307 (compliance_manager KRI/appetite writes).

Reversibility: ``downgrade`` removes the three reads from the six system roles --
the same tradeoff as 0307's downgrade (an org that had the grant via post-feature
seeding also loses it on downgrade; the pre-migration intent is restored).

Revision ID: 0309_backfill_read_perm_grants
Revises: 0308_evidence_ai_assessments
Create Date: 2026-07-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0309_backfill_read_perm_grants"
down_revision: str | None = "0308_evidence_ai_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The three read permissions and the six system roles that hold them per the seed
# ROLE_PERMISSION_MAP. Keeping both lists explicit (rather than reading the seed at
# runtime) makes the migration a fixed, auditable historical record.
GRANTED_KEYS: tuple[str, ...] = (
    "entity_graph:read",
    "compound_insights:read",
    "score_attribution:read",
)
TARGET_ROLE_NAMES: tuple[str, ...] = (
    "owner",
    "admin",
    "compliance_manager",
    "auditor",
    "readonly",
    "reviewer",
)

_ROLE_FILTER = "name IN :names AND is_system_role = TRUE"


def _target_role_ids(bind) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text(
                "SELECT id FROM roles WHERE is_system_role = TRUE "
                "AND name IN :names"
            ).bindparams(sa.bindparam("names", expanding=True)),
            {"names": list(TARGET_ROLE_NAMES)},
        ).scalars().all()
    )


def _permission_id_by_key(bind, key: str):
    return bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}
    ).scalar()


def upgrade() -> None:
    """Grant the three read permissions to every existing system role.

    Idempotent: a grant is only inserted where the permission exists and the
    role_permissions row is not already present.
    """
    bind = op.get_bind()
    role_ids = _target_role_ids(bind)
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
    """Revoke the three read permissions from every existing system role."""
    bind = op.get_bind()
    role_ids = _target_role_ids(bind)
    if not role_ids:
        return
    for key in GRANTED_KEYS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id = :pid AND role_id IN :role_ids"
            ).bindparams(sa.bindparam("role_ids", expanding=True)),
            {"pid": permission_id, "role_ids": role_ids},
        )
