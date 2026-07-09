"""add trust_center_slug_confirmed_at to organizations

Revision ID: 0284_trust_center_slug_confirmed_at
Revises: 0283_data_incident_status_notes
Create Date: 2026-07-09 00:00:00.000000

Fixes a regression introduced by the G4 trust-center slug confirmation guard: it gated
the confirm=true requirement on `organizations.slug` being non-null, but every org already
has a slug auto-generated from its name at registration (used for SSO routing) -- so the
guard demanded confirm=true on every org's *first* real trust-center customization too,
not just genuine re-customizations. This adds a dedicated timestamp set only when the
trust-center slug endpoint is explicitly used, so the guard can tell "auto-generated at
signup" apart from "deliberately set as a public trust-center link" and only require
confirmation for the latter.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0284_trust_center_slug_confirmed_at"
down_revision: str | None = "0283_data_incident_status_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("trust_center_slug_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "trust_center_slug_confirmed_at")
