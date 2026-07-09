"""add status_notes_json to data_incidents for queryable investigate/contain notes

Revision ID: 0280_data_incident_status_notes
Revises: 0279_bia_last_reviewed_at_nullable
Create Date: 2026-07-09 00:00:00.000000

The investigate/contain (and dismiss) endpoints accepted no request body at all, so any
free-text investigation/containment note a caller sent was silently discarded by FastAPI
(no matching parameter) -- never persisted, never queryable. resolve's notes were stored
by overwriting a single evidence_json["status_note"] key, which also clobbered any prior
note from an earlier transition. This adds an append-only status_notes_json column so
every transition's note is preserved and independently queryable via
GET /data-observability/incidents/{id}.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0280_data_incident_status_notes"
down_revision: str | None = "0279_bia_last_reviewed_at_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_incidents",
        sa.Column("status_notes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("data_incidents", "status_notes_json", server_default=None)


def downgrade() -> None:
    op.drop_column("data_incidents", "status_notes_json")
