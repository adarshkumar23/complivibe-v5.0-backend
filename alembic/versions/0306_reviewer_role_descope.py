"""revoke drifted write/approve/manage grants from the reviewer role

The seeded ``reviewer`` role had accumulated broad write/manage grants
(indistinguishable from ``compliance_manager``) plus blanket ``*:approve``
grants that contradict the per-request assignment authorization the approval
endpoints were designed around. Seeding is add-only, so simply fixing
``ROLE_PERMISSION_MAP`` in ``seed_service.py`` only affects newly-created
orgs -- existing orgs keep the drifted ``role_permissions`` rows. This
migration revokes those grants from every existing org's system ``reviewer``
role, bringing live data in line with the corrected seed (read-only across
the platform + a curated set of genuinely review-related actions).

Reviewers retain approval authority ONLY via per-request assignment
(``approval_request.approver_user_id``), which is enforced independently of
the blanket ``*:approve`` permission -- so this does not break legitimate
assigned-reviewer approvals.

Revision ID: 0306_reviewer_role_descope
Revises: 0305_autopilot_graph_reasoning
Create Date: 2026-07-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0306_reviewer_role_descope"
down_revision: str | None = "0305_autopilot_graph_reasoning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Drifted permission keys to strip from the reviewer role on every existing org.
# 26 are (or were) present in the seed's reviewer set; vendor_criticality:manage
# was never in the seed but was granted to reviewer in the DB by migration 0228
# via its `if key.endswith(":manage")` role tuple, and (seeding being add-only)
# was never pruned -- so it is a live drift and is revoked here too.
REVOKED_KEYS: tuple[str, ...] = (
    # Bucket B -- general domain write/manage, unrelated to reviewing
    "risks:write",
    "risk_indicators:write",
    "risk_appetite:write",
    "evidence:write",
    "tasks:write",
    "technical_controls:manage",
    "identity_governance:manage",
    "sod:manage",
    "legal_matters:write",
    "ip_assets:manage",
    "content_provenance:manage",
    "training_data_rights:manage",
    "synthetic_data:manage",
    "geopolitical_risk:manage",
    "ot_ics_assets:manage",
    "vendor_supply_chain:manage",
    "vendor_concentration_risk:manage",
    "vendor_criticality:manage",
    "ai_usage_policy:write",
    "training_analytics:write",
    # Blanket approve grant that duplicates an assignment-based path: the
    # compliance-policy approval endpoint routes authority through per-request
    # assignment (approver_user_id), so an assigned reviewer can still approve a
    # specific policy without this org-wide grant. NOTE: governance_override:approve,
    # ai_governance:approve, and exceptions:approve are deliberately NOT revoked --
    # those endpoints are role/quorum gated with no per-assignment fallback, so the
    # grant is the intended approval mechanism, not blanket drift.
    "compliance_policies:approve",
    # Attestation / policy-exception broader-control verbs (submit is the reviewer verb)
    "attestations:manage",
    "attestations:write",
    "policy_exceptions:manage",
)

_REVIEWER_ROLE_FILTER = "name = 'reviewer' AND is_system_role = TRUE"


def _reviewer_role_ids(bind) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text(f"SELECT id FROM roles WHERE {_REVIEWER_ROLE_FILTER}")
        ).scalars().all()
    )


def _permission_id_by_key(bind, key: str):
    return bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    role_ids = _reviewer_role_ids(bind)
    if not role_ids:
        return
    for key in REVOKED_KEYS:
        permission_id = _permission_id_by_key(bind, key)
        if permission_id is None:
            continue
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id = :pid "
                "AND role_id IN (SELECT id FROM roles WHERE "
                + _REVIEWER_ROLE_FILTER
                + ")"
            ),
            {"pid": permission_id},
        )


def downgrade() -> None:
    """Re-grant the revoked permissions to every system reviewer role.

    This restores the pre-migration (drifted) state for reversibility. It is
    idempotent: a grant is only inserted where the permission exists and the
    row is not already present.
    """
    bind = op.get_bind()
    role_ids = _reviewer_role_ids(bind)
    if not role_ids:
        return
    for key in REVOKED_KEYS:
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
