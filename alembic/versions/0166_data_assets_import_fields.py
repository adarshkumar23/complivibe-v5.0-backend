"""data asset import fields

Revision ID: 0166_data_assets_import_fields
Revises: 0165_openscap_rule_mappings
Create Date: 2026-06-28 19:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0166_data_assets_import_fields"
down_revision: str | None = "0165_openscap_rule_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "data_assets", "import_source") is False:
        op.add_column("data_assets", sa.Column("import_source", sa.VARCHAR(length=30), nullable=True))
    if _has_column(inspector, "data_assets", "import_key") is False:
        op.add_column("data_assets", sa.Column("import_key", sa.VARCHAR(length=500), nullable=True))

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "data_assets", "ck_data_assets_import_source"):
        op.drop_constraint("ck_data_assets_import_source", "data_assets", type_="check")
    op.create_check_constraint(
        "ck_data_assets_import_source",
        "data_assets",
        "import_source IS NULL OR import_source IN ('manual', 'fides', 'openmetadata', 'mlflow')",
    )

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "data_assets", "ck_data_assets_classification_source"):
        op.drop_constraint("ck_data_assets_classification_source", "data_assets", type_="check")
    op.create_check_constraint(
        "ck_data_assets_classification_source",
        "data_assets",
        "classification_source IS NULL OR classification_source IN ('metadata_rules', 'presidio_sample', 'manual', 'fides', 'openmetadata', 'mlflow')",
    )

    inspector = sa.inspect(bind)
    if _has_index(inspector, "data_assets", "uix_data_assets_import") is False:
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uix_data_assets_import
            ON data_assets(organization_id, import_source, import_key)
            WHERE import_key IS NOT NULL;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "data_assets", "uix_data_assets_import"):
        op.drop_index("uix_data_assets_import", table_name="data_assets")

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "data_assets", "ck_data_assets_import_source"):
        op.drop_constraint("ck_data_assets_import_source", "data_assets", type_="check")

    if _has_constraint(inspector, "data_assets", "ck_data_assets_classification_source"):
        op.drop_constraint("ck_data_assets_classification_source", "data_assets", type_="check")
    op.create_check_constraint(
        "ck_data_assets_classification_source",
        "data_assets",
        "classification_source IS NULL OR classification_source IN ('metadata_rules', 'presidio_sample', 'manual')",
    )

    inspector = sa.inspect(bind)
    if _has_column(inspector, "data_assets", "import_key"):
        op.drop_column("data_assets", "import_key")
    if _has_column(inspector, "data_assets", "import_source"):
        op.drop_column("data_assets", "import_source")
