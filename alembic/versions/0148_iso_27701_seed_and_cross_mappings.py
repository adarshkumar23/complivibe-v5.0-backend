"""iso 27701 seed and cross-framework mappings

Revision ID: 0148_iso_27701_seed_and_cross_mappings
Revises: 0147_cis_controls_v8_seed
Create Date: 2026-06-27 14:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a2 import (
    ISO_27701_GDPR_MAPPINGS,
    ISO_27701_OBLIGATIONS,
    ISO_27701_QUESTIONS,
    ISO_27701_SECTIONS,
)

revision: str = "0148_iso_27701_seed_and_cross_mappings"
down_revision: str | None = "0147_cis_controls_v8_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ensure_cross_mapping_table() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("cross_framework_obligation_mappings"):
        return
    op.create_table(
        "cross_framework_obligation_mappings",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("source_obligation_id", sa.Uuid(), nullable=False),
        sa.Column("target_obligation_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_type", sa.String(length=30), nullable=False, server_default=sa.text("'equivalent'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("mapping_type IN ('equivalent', 'partial', 'related')", name="ck_cross_framework_mapping_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_obligation_id", "target_obligation_id", name="uq_cross_framework_source_target"),
    )
    op.create_index(
        "ix_cross_framework_source_obligation_id",
        "cross_framework_obligation_mappings",
        ["source_obligation_id"],
        unique=False,
    )
    op.create_index(
        "ix_cross_framework_target_obligation_id",
        "cross_framework_obligation_mappings",
        ["target_obligation_id"],
        unique=False,
    )


def _seed_iso_27701(bind: sa.Connection) -> None:
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
        sa.column("section_code", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("sort_order", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("framework_version_id", sa.Uuid()),
        sa.column("parent_section_id", sa.Uuid()),
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "ISO 27701")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="ISO_27701",
                name="ISO 27701",
                description=(
                    "ISO/IEC 27701:2019 — Privacy Information Management System. Extension to ISO 27001 "
                    "and ISO 27002 for managing privacy controls."
                ),
                category="Privacy",
                jurisdiction="global",
                authority="ISO/IEC",
                version="2019",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
        )

    section_by_code = {
        row.section_code: row.id
        for row in bind.execute(sa.select(sections.c.id, sections.c.section_code).where(sections.c.framework_id == framework_id))
    }
    for item in ISO_27701_SECTIONS:
        code = str(item["code"])
        if code in section_by_code:
            bind.execute(
                sections.update()
                .where(sections.c.id == section_by_code[code])
                .values(title=str(item["title"]), description=str(item["title"]), sort_order=int(item["order"]), status="active")
            )
            continue
        sec_id = uuid.uuid4()
        section_by_code[code] = sec_id
        bind.execute(
            sections.insert().values(
                id=sec_id,
                framework_id=framework_id,
                section_code=code,
                title=str(item["title"]),
                description=str(item["title"]),
                sort_order=int(item["order"]),
                status="active",
                framework_version_id=None,
                parent_section_id=None,
                metadata_json=None,
            )
        )

    existing = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id))
    }
    for ref_code, title, section_code in ISO_27701_OBLIGATIONS:
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_by_code.get(section_code),
            "reference_code": ref_code,
            "title": title,
            "description": f"{title}. Implement this ISO 27701 privacy control and retain supporting evidence.",
            "plain_language_summary": f"Implement and evidence {title.lower()}.",
            "obligation_type": "privacy",
            "jurisdiction": "global",
            "source_url": None,
            "version": "2019",
            "ig_level": None,
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        row_id = existing.get(ref_code)
        if row_id is None:
            bind.execute(obligations.insert().values(id=uuid.uuid4(), **values))
        else:
            bind.execute(obligations.update().where(obligations.c.id == row_id).values(**values))

    existing_questions = {
        row.question_key
        for row in bind.execute(
            sa.select(questions.c.question_key).where(
                questions.c.framework_id == framework_id,
                questions.c.organization_id.is_(None),
                questions.c.obligation_id.is_(None),
            )
        )
    }
    for item in ISO_27701_QUESTIONS:
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
            "metadata_json": {
                "triggers_scope": str(item["triggers_scope"]),
                "choices": list(item.get("choices", [])),
            },
        }
        if str(item["question_key"]) in existing_questions:
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


def _seed_cross_mappings(bind: sa.Connection) -> None:
    frameworks = sa.table(
        "frameworks",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
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
        sa.column("status", sa.String()),
        sa.column("effective_date", sa.Date()),
        sa.column("parent_obligation_id", sa.Uuid()),
    )
    mappings = sa.table(
        "cross_framework_obligation_mappings",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("source_obligation_id", sa.Uuid()),
        sa.column("target_obligation_id", sa.Uuid()),
        sa.column("mapping_type", sa.String()),
        sa.column("notes", sa.Text()),
    )

    gdpr_framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "GDPR")).scalar_one_or_none()
    if gdpr_framework_id is not None:
        gdpr_targets = {
            "GDPR-OBL-02": "Document lawful basis per processing purpose",
            "GDPR-OBL-03": "Provide transparent privacy notices",
            "GDPR-OBL-04": "Support right of access and portability workflows",
            "GDPR-OBL-05": "Support rectification and erasure rights",
            "GDPR-OBL-07": "Maintain records of processing activities",
            "GDPR-OBL-09": "Execute data processing agreements",
            "GDPR-OBL-10": "Perform DPIAs for high-risk processing",
        }
        existing_gdpr_refs = {
            row.reference_code
            for row in bind.execute(
                sa.select(obligations.c.reference_code).where(obligations.c.framework_id == gdpr_framework_id)
            )
        }
        for ref_code, title in gdpr_targets.items():
            if ref_code in existing_gdpr_refs:
                continue
            bind.execute(
                obligations.insert().values(
                    id=uuid.uuid4(),
                    framework_id=gdpr_framework_id,
                    framework_section_id=None,
                    reference_code=ref_code,
                    title=title,
                    description=f"{title}.",
                    plain_language_summary=title,
                    obligation_type="privacy",
                    jurisdiction="European Union",
                    source_url=None,
                    version="2018",
                    ig_level=None,
                    status="active",
                    effective_date=None,
                    parent_obligation_id=None,
                )
            )

    by_ref = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code))
    }
    existing = {
        (row.source_obligation_id, row.target_obligation_id): row.id
        for row in bind.execute(sa.select(mappings.c.id, mappings.c.source_obligation_id, mappings.c.target_obligation_id))
    }
    for source_ref, target_ref, mapping_type in ISO_27701_GDPR_MAPPINGS:
        source_id = by_ref.get(source_ref)
        target_id = by_ref.get(target_ref)
        if source_id is None or target_id is None:
            continue
        key = (source_id, target_id)
        values = {
            "organization_id": None,
            "source_obligation_id": source_id,
            "target_obligation_id": target_id,
            "mapping_type": mapping_type,
            "notes": f"Seeded mapping: {source_ref} -> {target_ref}",
        }
        if key in existing:
            bind.execute(mappings.update().where(mappings.c.id == existing[key]).values(**values))
        else:
            bind.execute(mappings.insert().values(id=uuid.uuid4(), **values))


def upgrade() -> None:
    _ensure_cross_mapping_table()
    bind = op.get_bind()
    _seed_iso_27701(bind)
    _seed_cross_mappings(bind)


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    iso_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "ISO_27701")).scalar_one_or_none()
    if iso_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == iso_id))
