"""openscap rule mappings

Revision ID: 0165_openscap_rule_mappings
Revises: 0164_security_scan_jobs_table
Create Date: 2026-06-28 19:10:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "0165_openscap_rule_mappings"
down_revision: str | None = "0164_security_scan_jobs_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MAPPINGS: list[tuple[str, str, str, str]] = [
    (
        "xccdf_org.ssgproject.content_rule_accounts_",
        "AC",
        "access_control",
        "Account and identity access control rules.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_audit_",
        "AU",
        "audit_logging",
        "Audit logging and traceability rules.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_sshd_",
        "SC",
        "network_security",
        "SSH and secure communications hardening rules.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_sudo_",
        "AC",
        "privileged_access",
        "Privileged command execution controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_password_",
        "IA",
        "authentication",
        "Password and credential policy controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_firewall_",
        "SC",
        "network_security",
        "Firewall enforcement controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_selinux_",
        "AC",
        "access_control",
        "Mandatory access control policy checks.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_crypto_",
        "SC",
        "encryption",
        "Cryptographic configuration checks.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_file_",
        "CM",
        "configuration_management",
        "File-level configuration integrity checks.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_login_",
        "IA",
        "authentication",
        "Login and authentication flow checks.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_kernel_",
        "CM",
        "configuration_management",
        "Kernel hardening and baseline controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_network_",
        "SC",
        "network_security",
        "Network boundary and protocol controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_service_",
        "CM",
        "configuration_management",
        "Service configuration and startup controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_logging_",
        "AU",
        "audit_logging",
        "Logging configuration and retention controls.",
    ),
    (
        "xccdf_org.ssgproject.content_rule_mount_",
        "CM",
        "configuration_management",
        "Mount options and storage hardening controls.",
    ),
]


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "openscap_rule_mappings"):
        op.create_table(
            "openscap_rule_mappings",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("rule_prefix", sa.VARCHAR(length=100), nullable=False),
            sa.Column("control_family", sa.VARCHAR(length=10), nullable=False),
            sa.Column("control_type", sa.VARCHAR(length=50), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("rule_prefix", name="uq_openscap_rule_mappings_rule_prefix"),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "openscap_rule_mappings", "ix_openscap_rule_mappings_rule_prefix"):
        op.create_index("ix_openscap_rule_mappings_rule_prefix", "openscap_rule_mappings", ["rule_prefix"], unique=False)
    if not _has_index(inspector, "openscap_rule_mappings", "ix_openscap_rule_mappings_control_family"):
        op.create_index(
            "ix_openscap_rule_mappings_control_family",
            "openscap_rule_mappings",
            ["control_family"],
            unique=False,
        )

    table = sa.table(
        "openscap_rule_mappings",
        sa.column("id", sa.Uuid()),
        sa.column("rule_prefix", sa.String()),
        sa.column("control_family", sa.String()),
        sa.column("control_type", sa.String()),
        sa.column("description", sa.Text()),
    )

    for rule_prefix, control_family, control_type, description in MAPPINGS:
        stmt = insert(table).values(
            id=uuid.uuid4(),
            rule_prefix=rule_prefix,
            control_family=control_family,
            control_type=control_type,
            description=description,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["rule_prefix"])
        bind.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "openscap_rule_mappings", "ix_openscap_rule_mappings_control_family"):
        op.drop_index("ix_openscap_rule_mappings_control_family", table_name="openscap_rule_mappings")
    if _has_index(inspector, "openscap_rule_mappings", "ix_openscap_rule_mappings_rule_prefix"):
        op.drop_index("ix_openscap_rule_mappings_rule_prefix", table_name="openscap_rule_mappings")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "openscap_rule_mappings"):
        op.drop_table("openscap_rule_mappings")
