"""shadow AI signature detection (patent graft: shadow-ai-discovery-engine)

Adds the signature-scored shadow-AI discovery subsystem ALONGSIDE core's
existing shadow-AI feature. Core's ``shadow_ai_detections`` table is not
touched, renamed, migrated or dropped by this migration -- the upstream repo's
colliding table is created here as ``shadow_ai_signature_detections``.

Every table is namespaced ``shadow_ai_*`` so ownership is unambiguous.

Revision ID: 0314_shadow_ai_signature_detection
Revises: 0313_backfill_governance_graph_perms
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0314_shadow_ai_signature_detection"
down_revision: str | None = "0313_backfill_governance_graph_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('shadow_ai_signature_registry',
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('provider_name', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('endpoint_patterns', sa.Text(), nullable=False),
    sa.Column('keyword_patterns', sa.Text(), nullable=False),
    sa.Column('oauth_app_patterns', sa.Text(), nullable=False),
    sa.Column('data_egress_indicators', sa.Text(), nullable=True),
    sa.Column('confidence_weights', sa.Text(), nullable=False),
    sa.Column('risk_level', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name='ck_shadow_ai_sig_registry_risk_level'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('shadow_ai_federated_observations',
    sa.Column('hostname_hash', sa.String(length=64), nullable=False),
    sa.Column('hostname', sa.String(length=500), nullable=False),
    sa.Column('observation_count', sa.Integer(), nullable=False),
    sa.Column('first_observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('behavioral_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('promoted_signature_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('observed', 'candidate', 'promoted', 'rejected')", name='ck_shadow_ai_federated_status'),
    sa.ForeignKeyConstraint(['promoted_signature_id'], ['shadow_ai_signature_registry.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hostname_hash', name='uq_shadow_ai_federated_hostname_hash')
    )
    op.create_table('shadow_ai_federated_submissions',
    sa.Column('hostname_hash', sa.String(length=64), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('behavioral_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('was_duplicate', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'hostname_hash', name='uq_shadow_ai_federated_sub_org_hash')
    )
    op.create_table('shadow_ai_idp_connections',
    sa.Column('idp_provider', sa.String(length=30), nullable=False),
    sa.Column('access_token_enc', sa.Text(), nullable=False),
    sa.Column('refresh_token_enc', sa.Text(), nullable=True),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('idp_domain', sa.String(length=255), nullable=True),
    sa.Column('scopes_granted', sa.Text(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_status', sa.String(length=20), nullable=False),
    sa.Column('sync_error', sa.Text(), nullable=True),
    sa.Column('sync_window_hours', sa.Integer(), nullable=False),
    sa.Column('total_syncs', sa.Integer(), nullable=False),
    sa.Column('total_signals', sa.Integer(), nullable=False),
    sa.Column('connected_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("idp_provider IN ('okta', 'azure_ad', 'google_workspace')", name='ck_shadow_ai_idp_provider'),
    sa.CheckConstraint("sync_status IN ('pending', 'syncing', 'ok', 'error')", name='ck_shadow_ai_idp_sync_status'),
    sa.ForeignKeyConstraint(['connected_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shadow_ai_suppressed_detections',
    sa.Column('signature_id', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('suppressed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['signature_id'], ['shadow_ai_signature_registry.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['suppressed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'signature_id', name='uq_shadow_ai_suppressed_org_signature')
    )
    op.create_table('shadow_ai_telemetry_events',
    sa.Column('tier', sa.SmallInteger(), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('source_system_label', sa.String(length=255), nullable=True),
    sa.Column('matched_signature_id', sa.Uuid(), nullable=True),
    sa.Column('raw_signal_json', sa.Text(), nullable=False),
    sa.Column('signal_hash', sa.String(length=64), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('tier IN (1, 2, 3)', name='ck_shadow_ai_telemetry_tier'),
    sa.ForeignKeyConstraint(['matched_signature_id'], ['shadow_ai_signature_registry.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'signal_hash', name='uq_shadow_ai_telemetry_org_hash')
    )
    op.create_table('shadow_ai_idp_sync_logs',
    sa.Column('connection_id', sa.Uuid(), nullable=False),
    sa.Column('idp_provider', sa.String(length=30), nullable=False),
    sa.Column('events_fetched', sa.Integer(), nullable=False),
    sa.Column('events_matched', sa.Integer(), nullable=False),
    sa.Column('signals_created', sa.Integer(), nullable=False),
    sa.Column('signals_duplicate', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['shadow_ai_idp_connections.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shadow_ai_signature_detections',
    sa.Column('signature_id', sa.Uuid(), nullable=False),
    sa.Column('provider_name', sa.String(length=255), nullable=False),
    sa.Column('confidence_score', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('confidence_band', sa.String(length=10), nullable=False),
    sa.Column('detection_basis_json', sa.Text(), nullable=False),
    sa.Column('event_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dismissal_reason', sa.Text(), nullable=True),
    sa.Column('registered_ai_system_id', sa.Uuid(), nullable=True),
    sa.Column('base_confidence_score', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('decay_lambda', sa.Numeric(precision=6, scale=5), nullable=True),
    sa.Column('decayed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_stale', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("confidence_band IN ('high', 'medium')", name='ck_shadow_ai_sig_detections_band'),
    sa.CheckConstraint("status IN ('new', 'under_review', 'confirmed', 'dismissed', 'escalated', 'registered')", name='ck_shadow_ai_sig_detections_status'),
    sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='ck_shadow_ai_sig_detections_score_range'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['registered_ai_system_id'], ['ai_systems.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['signature_id'], ['shadow_ai_signature_registry.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'signature_id', name='uq_shadow_ai_sig_detections_org_signature')
    )

    op.create_index('ix_shadow_ai_sig_registry_active', 'shadow_ai_signature_registry', ['is_active'], unique=False)
    op.create_index('ix_shadow_ai_federated_status', 'shadow_ai_federated_observations', ['status'], unique=False)
    op.create_index(op.f('ix_shadow_ai_federated_submissions_organization_id'), 'shadow_ai_federated_submissions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_shadow_ai_idp_connections_organization_id'), 'shadow_ai_idp_connections', ['organization_id'], unique=False)
    op.create_index('ix_shadow_ai_idp_org_provider', 'shadow_ai_idp_connections', ['organization_id', 'idp_provider'], unique=False)
    op.create_index(op.f('ix_shadow_ai_suppressed_detections_organization_id'), 'shadow_ai_suppressed_detections', ['organization_id'], unique=False)
    op.create_index(op.f('ix_shadow_ai_telemetry_events_organization_id'), 'shadow_ai_telemetry_events', ['organization_id'], unique=False)
    op.create_index('ix_shadow_ai_telemetry_observed_at', 'shadow_ai_telemetry_events', ['observed_at'], unique=False)
    op.create_index('ix_shadow_ai_telemetry_org_signature', 'shadow_ai_telemetry_events', ['organization_id', 'matched_signature_id'], unique=False)
    op.create_index('ix_shadow_ai_idp_sync_logs_connection', 'shadow_ai_idp_sync_logs', ['connection_id'], unique=False)
    op.create_index(op.f('ix_shadow_ai_idp_sync_logs_organization_id'), 'shadow_ai_idp_sync_logs', ['organization_id'], unique=False)
    op.create_index('ix_shadow_ai_sig_detections_org_status', 'shadow_ai_signature_detections', ['organization_id', 'status'], unique=False)
    op.create_index('ix_shadow_ai_sig_detections_stale', 'shadow_ai_signature_detections', ['organization_id', 'is_stale'], unique=False)
    op.create_index(op.f('ix_shadow_ai_signature_detections_organization_id'), 'shadow_ai_signature_detections', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table("shadow_ai_signature_detections")
    op.drop_table("shadow_ai_idp_sync_logs")
    op.drop_table("shadow_ai_telemetry_events")
    op.drop_table("shadow_ai_suppressed_detections")
    op.drop_table("shadow_ai_idp_connections")
    op.drop_table("shadow_ai_federated_submissions")
    op.drop_table("shadow_ai_federated_observations")
    op.drop_table("shadow_ai_signature_registry")
