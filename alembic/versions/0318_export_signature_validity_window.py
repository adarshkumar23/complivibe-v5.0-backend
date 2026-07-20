"""signed-export validity window: valid_from / not_after on export_jobs + export_attestations

Adds a signature validity window to the HMAC-signed export/attestation artifacts. Both
columns are embedded in the signed payload (see ExportService.compute_integrity_signature
/ AttestationService.signature), so the window itself is tamper-evident, and verify_job
enforces `not_after` (expired) and attestation revocation.

Nullable: rows signed before this window existed keep verifying under the legacy
window-less signature, so a historical export is not invalidated by this change.

New identifiers (Postgres 63-byte limit): columns valid_from (10) and not_after (9) on
export_jobs (11) and export_attestations (19). All well under 63. No new indexes or
constraints.

Revision ID: 0318_export_signature_validity_window
Revises: 0317_subsystem_ingest_keys
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0318_export_signature_validity_window"
down_revision: str | None = "0317_subsystem_ingest_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_jobs", sa.Column("not_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_attestations", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_attestations", sa.Column("not_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("export_attestations", "not_after")
    op.drop_column("export_attestations", "valid_from")
    op.drop_column("export_jobs", "not_after")
    op.drop_column("export_jobs", "valid_from")
