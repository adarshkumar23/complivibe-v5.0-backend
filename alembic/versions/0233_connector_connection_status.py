"""add connector connection status tracking and real vendor catalog entries

Revision ID: 0233_connector_status
Revises: 0232_synth_risk_metric
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0233_connector_status"
down_revision: str | None = "0232_synth_risk_metric"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Renames applied to the connector catalog rows seeded by 0217_connector_marketplace so the
# marketplace lists real, recognizable third-party systems (its actual purpose) instead of
# generic placeholder names. Matched by the original seeded name.
RENAMES = {
    "Data catalog metadata ingest": (
        "OpenMetadata",
        "data_governance",
        "Data catalog and lineage metadata sync via OpenMetadata's REST API.",
        {
            "type": "object",
            "required": ["base_url", "jwt_token"],
            "properties": {"base_url": {"type": "string"}, "jwt_token": {"type": "string"}},
        },
    ),
    "Access review evidence import": (
        "Okta",
        "identity_governance",
        "Identity provider sync for access review and segregation-of-duties evidence via Okta's API.",
        {
            "type": "object",
            "required": ["org_url", "api_token"],
            "properties": {"org_url": {"type": "string"}, "api_token": {"type": "string"}},
        },
    ),
}

NEW_CONNECTORS = [
    (
        "Salesforce",
        "crm",
        "Customer relationship data sync for third-party risk and customer compliance context.",
        {
            "type": "object",
            "required": ["instance_url", "client_id", "client_secret"],
            "properties": {
                "instance_url": {"type": "string"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
            },
        },
    ),
    (
        "Workday",
        "hr",
        "Human capital management sync for employee lifecycle and access review evidence.",
        {
            "type": "object",
            "required": ["tenant_url", "client_id", "client_secret"],
            "properties": {
                "tenant_url": {"type": "string"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
            },
        },
    ),
    (
        "ServiceNow",
        "itsm",
        "IT service management sync for compliance issue and incident tracking.",
        {
            "type": "object",
            "required": ["instance_url", "username", "password"],
            "properties": {
                "instance_url": {"type": "string"},
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
        },
    ),
]


def upgrade() -> None:
    op.add_column(
        "connector_org_enablements",
        sa.Column("connection_status", sa.String(length=20), nullable=False, server_default="unconfigured"),
    )
    op.add_column("connector_org_enablements", sa.Column("connection_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("connector_org_enablements", sa.Column("connection_error", sa.Text(), nullable=True))

    bind = op.get_bind()
    catalog = sa.table(
        "connector_catalog_entries",
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("config_schema", sa.JSON()),
    )
    for old_name, (new_name, category, description, config_schema) in RENAMES.items():
        bind.execute(
            catalog.update()
            .where(catalog.c.name == old_name)
            .values(name=new_name, category=category, description=description, config_schema=config_schema)
        )

    catalog_full = sa.table(
        "connector_catalog_entries",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("config_schema", sa.JSON()),
        sa.column("enabled", sa.Boolean()),
    )
    for name, category, description, config_schema in NEW_CONNECTORS:
        exists = bind.execute(sa.text("SELECT 1 FROM connector_catalog_entries WHERE name = :name"), {"name": name}).scalar()
        if exists is None:
            op.bulk_insert(
                catalog_full,
                [
                    {
                        "id": uuid.uuid4(),
                        "name": name,
                        "category": category,
                        "description": description,
                        "config_schema": config_schema,
                        "enabled": True,
                    }
                ],
            )


def downgrade() -> None:
    op.drop_column("connector_org_enablements", "connection_error")
    op.drop_column("connector_org_enablements", "connection_checked_at")
    op.drop_column("connector_org_enablements", "connection_status")
