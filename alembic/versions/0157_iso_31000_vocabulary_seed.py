"""iso 31000 vocabulary + seed

Revision ID: 0157_iso_31000_vocabulary_seed
Revises: 0156_india_dpdp_complete
Create Date: 2026-06-28 00:20:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a6 import ISO_31000_OBLIGATIONS, ISO_31000_QUESTIONS, ISO_31000_SECTIONS

revision: str = "0157_iso_31000_vocabulary_seed"
down_revision: str | None = "0156_india_dpdp_complete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ISO_31000_NAME = "ISO 31000"


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def _seed_iso_31000(bind: sa.Connection) -> None:
    frameworks = sa.table(
        "frameworks",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("jurisdiction", sa.String()),
        sa.column("authority", sa.String()),
        sa.column("version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("coverage_level", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("effective_date", sa.Date()),
    )
    sections = sa.table(
        "framework_sections",
        sa.column("id", sa.Uuid()),
        sa.column("framework_id", sa.Uuid()),
        sa.column("framework_version_id", sa.Uuid()),
        sa.column("parent_section_id", sa.Uuid()),
        sa.column("section_code", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("sort_order", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )
    obligations = sa.table(
        "obligations",
        sa.column("id", sa.Uuid()),
        sa.column("framework_id", sa.Uuid()),
        sa.column("framework_section_id", sa.Uuid()),
        sa.column("reference_code", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("plain_language_summary", sa.Text()),
        sa.column("obligation_type", sa.String()),
        sa.column("jurisdiction", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("version", sa.String()),
        sa.column("ig_level", sa.String()),
        sa.column("control_family", sa.String()),
        sa.column("baseline", sa.String()),
        sa.column("status", sa.String()),
        sa.column("effective_date", sa.Date()),
        sa.column("parent_obligation_id", sa.Uuid()),
    )
    questions = sa.table(
        "obligation_applicability_questions",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("framework_id", sa.Uuid()),
        sa.column("obligation_id", sa.Uuid()),
        sa.column("question_key", sa.String()),
        sa.column("question_text", sa.Text()),
        sa.column("help_text", sa.Text()),
        sa.column("answer_type", sa.String()),
        sa.column("required", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == ISO_31000_NAME)).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="ISO_31000",
                name=ISO_31000_NAME,
                description=(
                    "ISO 31000:2018 — Risk Management Guidelines. International standard for risk management "
                    "principles and guidelines applicable to any organization regardless of size, sector, or "
                    "activity. Provides vocabulary and process model for risk management."
                ),
                category="Risk Management",
                jurisdiction="global",
                authority="ISO",
                version="2018",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
        )

    section_map = {
        row.section_code: row.id
        for row in bind.execute(sa.select(sections.c.id, sections.c.section_code).where(sections.c.framework_id == framework_id))
    }
    for item in ISO_31000_SECTIONS:
        code = str(item["code"])
        title = str(item["title"])
        order_idx = int(item["order"])
        row_id = section_map.get(code)
        if row_id is None:
            row_id = uuid.uuid4()
            section_map[code] = row_id
            bind.execute(
                sections.insert().values(
                    id=row_id,
                    framework_id=framework_id,
                    framework_version_id=None,
                    parent_section_id=None,
                    section_code=code,
                    title=title,
                    description=title,
                    sort_order=order_idx,
                    status="active",
                    metadata_json=None,
                )
            )
        else:
            bind.execute(
                sections.update().where(sections.c.id == row_id).values(title=title, description=title, sort_order=order_idx, status="active")
            )

    existing = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id))
    }
    for ref_code, title, description, section_code, evidence_hints in ISO_31000_OBLIGATIONS:
        plain = f"Implement and evidence {title.lower()}."
        if evidence_hints:
            plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_map.get(section_code),
            "reference_code": ref_code,
            "title": title,
            "description": description,
            "plain_language_summary": plain,
            "obligation_type": "risk_management",
            "jurisdiction": "global",
            "source_url": None,
            "version": "2018",
            "ig_level": None,
            "control_family": None,
            "baseline": None,
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        row_id = existing.get(ref_code)
        if row_id is None:
            bind.execute(obligations.insert().values(id=uuid.uuid4(), **values))
        else:
            bind.execute(obligations.update().where(obligations.c.id == row_id).values(**values))

    if sa.inspect(bind).has_table("obligation_applicability_questions"):
        existing_keys = {
            row.question_key
            for row in bind.execute(
                sa.select(questions.c.question_key).where(
                    questions.c.framework_id == framework_id,
                    questions.c.organization_id.is_(None),
                    questions.c.obligation_id.is_(None),
                )
            )
        }
        for item in ISO_31000_QUESTIONS:
            values = {
                "organization_id": None,
                "framework_id": framework_id,
                "obligation_id": None,
                "question_key": str(item["question_key"]),
                "question_text": str(item["question_text"]),
                "help_text": str(item["help_text"]),
                "answer_type": str(item.get("answer_type", "boolean")),
                "required": True,
                "sort_order": int(item["order_index"]),
                "status": "active",
                "metadata_json": {"triggers_scope": str(item["triggers_scope"])},
            }
            if str(item["question_key"]) in existing_keys:
                bind.execute(
                    questions.update()
                    .where(
                        questions.c.framework_id == framework_id,
                        questions.c.organization_id.is_(None),
                        questions.c.obligation_id.is_(None),
                        questions.c.question_key == str(item["question_key"]),
                    )
                    .values(**values)
                )
            else:
                bind.execute(questions.insert().values(id=uuid.uuid4(), **values))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "risks", "treatment_option"):
        op.add_column("risks", sa.Column("treatment_option", sa.VARCHAR(length=20), nullable=True))
    if not _has_column(inspector, "risks", "risk_context_internal"):
        op.add_column("risks", sa.Column("risk_context_internal", sa.Text(), nullable=True))
    if not _has_column(inspector, "risks", "risk_context_external"):
        op.add_column("risks", sa.Column("risk_context_external", sa.Text(), nullable=True))
    if not _has_column(inspector, "risks", "residual_risk_acceptable"):
        op.add_column("risks", sa.Column("residual_risk_acceptable", sa.Boolean(), nullable=True))
    if not _has_column(inspector, "risks", "risk_communication_plan"):
        op.add_column("risks", sa.Column("risk_communication_plan", sa.Text(), nullable=True))

    inspector = sa.inspect(bind)
    ck_name = "ck_risks_treatment_option"
    if _has_constraint(inspector, "risks", ck_name):
        op.drop_constraint(ck_name, "risks", type_="check")
    op.create_check_constraint(
        ck_name,
        "risks",
        "treatment_option IS NULL OR treatment_option IN ('avoid', 'reduce', 'share', 'retain')",
    )

    _seed_iso_31000(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == ISO_31000_NAME)).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))

    ck_name = "ck_risks_treatment_option"
    if _has_constraint(inspector, "risks", ck_name):
        op.drop_constraint(ck_name, "risks", type_="check")

    if _has_column(inspector, "risks", "risk_communication_plan"):
        op.drop_column("risks", "risk_communication_plan")
    if _has_column(inspector, "risks", "residual_risk_acceptable"):
        op.drop_column("risks", "residual_risk_acceptable")
    if _has_column(inspector, "risks", "risk_context_external"):
        op.drop_column("risks", "risk_context_external")
    if _has_column(inspector, "risks", "risk_context_internal"):
        op.drop_column("risks", "risk_context_internal")
    if _has_column(inspector, "risks", "treatment_option"):
        op.drop_column("risks", "treatment_option")
