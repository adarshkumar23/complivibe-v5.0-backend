"""backfill legacy pbc_requests into pbc_items

Revision ID: 0301_pbc_requests_backfill_into_pbc_items
Revises: 0300_obligation_embedding_json_always_present
Create Date: 2026-07-14 00:00:00.000000

Two parallel PBC (Provided-By-Client) models have existed side by side:
`pbc_items` (table created in 0104, the original audit-planning build) and
`pbc_requests` (table created later in 0188, tagged "pbc_requests_v2" in the
feature inventory). Both are still live today -- both have their own router,
service, and daily overdue-sweep scheduler job -- but only `pbc_items` has a
`/summary` dashboard endpoint, soft-delete, and an acceptance-override-reason
field (0293), and the frontend's Audit Pack dashboard already reads
exclusively from `pbc_items`. Any PBC request created via the `pbc_requests`
API was therefore invisible on the dashboard even though it's real,
organization-scoped data -- the exact "two disconnected data stores silently
disagreeing" bug pattern this project has hit before (see the fixed
common-controls/obligations split and the fixed policy-issue-links v1/v2
split, both noted in prior audits).

This migration makes `pbc_items` the sole source of truth going forward:
1. Backfills every existing `pbc_requests` row into `pbc_items` (preserving
   original timestamps and status), so no real data is lost.
2. `pbc_requests` rows are left in place afterward (not deleted) purely as a
   historical record of what was backfilled -- the API endpoints reading and
   writing to that table are separately deprecated with 410 Gone in
   app/compliance/routers/pbc_requests.py, so nothing can write to it again
   and cause a second silent divergence.

Field mapping:
- audit_id -> audit_engagement_id (same referenced table, audit_engagements)
- item_description -> title (truncated to 255 chars, the pbc_items.title
  limit) + full text preserved in description
- created_by -> requester_id (pbc_items.requester_id is NOT NULL; pbc_requests
  already guarantees created_by is NOT NULL, so this always maps cleanly)
- assigned_to -> assignee_id
- status: 'open' -> 'pending' (pbc_items' equivalent initial state), every
  other status value ('submitted' | 'accepted' | 'rejected' | 'overdue') is
  spelled identically in both check constraints and maps unchanged
- due_date: pbc_requests.due_date is nullable, pbc_items.due_date is NOT
  NULL. Where null, falls back to the linked audit engagement's end_date,
  then to created_at + 30 days if the engagement itself has no end_date --
  the same 30-day default used for real user-created pbc_items elsewhere.
- evidence_id, submitted_at, accepted_at, rejected_at, rejection_reason,
  created_at, updated_at all map to identically-named columns unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0301_pbc_requests_backfill_into_pbc_items"
down_revision: str | None = "0300_obligation_embedding_json_always_present"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (inspector.has_table("pbc_requests") and inspector.has_table("pbc_items")):
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO pbc_items (
                id, organization_id, audit_engagement_id, title, description,
                requester_id, assignee_id, due_date, status, evidence_id,
                submitted_at, accepted_at, rejected_at, rejection_reason,
                acceptance_override_reason, deleted_at, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                r.organization_id,
                r.audit_id,
                left(r.item_description, 255),
                r.item_description,
                r.created_by,
                r.assigned_to,
                COALESCE(r.due_date, ae.end_date, (r.created_at + interval '30 days')::date),
                CASE WHEN r.status = 'open' THEN 'pending' ELSE r.status END,
                r.evidence_id,
                r.submitted_at,
                r.accepted_at,
                r.rejected_at,
                r.rejection_reason,
                NULL,
                NULL,
                r.created_at,
                r.updated_at
            FROM pbc_requests r
            LEFT JOIN audit_engagements ae ON ae.id = r.audit_id
            """
        )
    )


def downgrade() -> None:
    # Intentionally a no-op: the backfilled pbc_items rows are indistinguishable
    # from rows a real user could have created directly against /pbc-items in
    # the meantime, so there's no safe way to identify and remove exactly (and
    # only) the ones this migration inserted.
    pass
