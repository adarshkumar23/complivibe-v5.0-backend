"""oecd ai principles + ieee 7000 seed

Revision ID: 0158_oecd_ieee_seed
Revises: 0157_iso_31000_vocabulary_seed
Create Date: 2026-06-28 00:30:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a6 import (
    IEEE_7000_OBLIGATIONS,
    IEEE_7000_QUESTIONS,
    IEEE_7000_SECTIONS,
    IEEE_EUAI_MAPPINGS,
    OECD_AI_OBLIGATIONS,
    OECD_AI_QUESTIONS,
    OECD_AI_SECTIONS,
    OECD_EUAI_MAPPINGS,
)

revision: str = "0158_oecd_ieee_seed"
down_revision: str | None = "0157_iso_31000_vocabulary_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _seed_framework(
    bind: sa.Connection,
    *,
    framework_code: str,
    framework_name: str,
    description: str,
    category: str,
    jurisdiction: str,
    authority: str,
    version: str,
    sections_seed: list[dict[str, int | str]],
    obligations_seed: list[tuple[str, str, str, str, list[str]]],
    questions_seed: list[dict[str, int | str]],
) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == framework_name)).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code=framework_code,
                name=framework_name,
                description=description,
                category=category,
                jurisdiction=jurisdiction,
                authority=authority,
                version=version,
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
    for item in sections_seed:
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
    for ref_code, title, description, section_code, evidence_hints in obligations_seed:
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
            "obligation_type": "ai_governance",
            "jurisdiction": jurisdiction,
            "source_url": None,
            "version": version,
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
        for item in questions_seed:
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


def _seed_mappings(bind: sa.Connection, mapping_rows: list[tuple[str, str, str]]) -> None:
    obligations = sa.table(
        "obligations",
        sa.column("id", sa.Uuid()),
        sa.column("reference_code", sa.String()),
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

    obligation_by_ref = {row.reference_code: row.id for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code))}
    existing = {
        (row.source_obligation_id, row.target_obligation_id): row.id
        for row in bind.execute(sa.select(mappings.c.id, mappings.c.source_obligation_id, mappings.c.target_obligation_id))
    }

    for source_ref, target_ref, mapping_type in mapping_rows:
        source_id = obligation_by_ref.get(source_ref)
        target_id = obligation_by_ref.get(target_ref)
        if source_id is None or target_id is None:
            continue
        values = {
            "organization_id": None,
            "source_obligation_id": source_id,
            "target_obligation_id": target_id,
            "mapping_type": mapping_type,
            "notes": f"Seeded mapping: {source_ref} -> {target_ref}",
        }
        row_id = existing.get((source_id, target_id))
        if row_id is None:
            bind.execute(mappings.insert().values(id=uuid.uuid4(), **values))
        else:
            bind.execute(mappings.update().where(mappings.c.id == row_id).values(**values))


def upgrade() -> None:
    bind = op.get_bind()

    _seed_framework(
        bind,
        framework_code="OECD_AI_PRINCIPLES",
        framework_name="OECD AI Principles",
        description=(
            "OECD Principles on Artificial Intelligence (updated 2024). International standard for trustworthy "
            "AI adopted by 46+ countries. Five principles and five recommendations for governments."
        ),
        category="AI Governance",
        jurisdiction="global",
        authority="OECD",
        version="2024",
        sections_seed=OECD_AI_SECTIONS,
        obligations_seed=OECD_AI_OBLIGATIONS,
        questions_seed=OECD_AI_QUESTIONS,
    )

    _seed_framework(
        bind,
        framework_code="IEEE_7000_SERIES",
        framework_name="IEEE 7000 Series",
        description=(
            "IEEE Standards for Ethically Aligned Design. IEEE 7000-2021: Model Process for Addressing "
            "Ethical Concerns in System Design. IEEE 7001-2021: Transparency of Autonomous Systems. "
            "IEEE 7009-2022: Fail-Safe Design."
        ),
        category="AI Governance",
        jurisdiction="global",
        authority="IEEE",
        version="2021-2022",
        sections_seed=IEEE_7000_SECTIONS,
        obligations_seed=IEEE_7000_OBLIGATIONS,
        questions_seed=IEEE_7000_QUESTIONS,
    )

    if sa.inspect(bind).has_table("cross_framework_obligation_mappings"):
        _seed_mappings(bind, OECD_EUAI_MAPPINGS)
        _seed_mappings(bind, IEEE_EUAI_MAPPINGS)


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))

    for name in ["IEEE 7000 Series", "OECD AI Principles"]:
        framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == name)).scalar_one_or_none()
        if framework_id is not None:
            bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))
