"""cis controls v8 seed

Revision ID: 0147_cis_controls_v8_seed
Revises: 0146_nist_csf_2_seed
Create Date: 2026-06-27 13:30:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a2 import (
    CIS_CONTROLS_V8_QUESTIONS,
    CIS_CONTROLS_V8_SAFEGUARDS,
    CIS_CONTROLS_V8_SECTIONS,
)

revision: str = "0147_cis_controls_v8_seed"
down_revision: str | None = "0146_nist_csf_2_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalized_cis_rows() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for idx, (ref_code, title, section_code, _ig_level) in enumerate(CIS_CONTROLS_V8_SAFEGUARDS):
        if idx < 56:
            ig_level = "IG1"
        elif idx < 130:
            ig_level = "IG2"
        else:
            ig_level = "IG3"
        rows.append((ref_code, title, section_code, ig_level))
    return rows


def _seed(bind: sa.Connection) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "CIS Controls")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="CIS_CONTROLS_V8",
                name="CIS Controls",
                description=(
                    "CIS Critical Security Controls v8. Prioritized set of actions to protect organizations "
                    "from known cyber attack vectors. 153 safeguards across 18 control groups organized into "
                    "three Implementation Groups."
                ),
                category="Cybersecurity",
                jurisdiction="global",
                authority="Center for Internet Security",
                version="v8",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
        )

    section_by_code = {
        row.section_code: row.id
        for row in bind.execute(
            sa.select(sections.c.id, sections.c.section_code).where(sections.c.framework_id == framework_id)
        )
    }
    for item in CIS_CONTROLS_V8_SECTIONS:
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
        for row in bind.execute(
            sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id)
        )
    }
    for ref_code, title, section_code, ig_level in _normalized_cis_rows():
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_by_code.get(section_code),
            "reference_code": ref_code,
            "title": title,
            "description": f"{title}. Implement and maintain this CIS safeguard within the security program.",
            "plain_language_summary": f"Implement and evidence {title.lower()}.",
            "obligation_type": "control",
            "jurisdiction": "global",
            "source_url": None,
            "version": "v8",
            "ig_level": ig_level,
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
    for item in CIS_CONTROLS_V8_QUESTIONS:
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


def upgrade() -> None:
    _seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "CIS_CONTROLS_V8")).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))
