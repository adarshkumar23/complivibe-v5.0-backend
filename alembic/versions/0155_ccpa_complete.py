"""ccpa complete

Revision ID: 0155_ccpa_complete
Revises: 0154_hipaa_obligation_pack_seed
Create Date: 2026-06-27 18:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a5 import CCPA_OBLIGATIONS, CCPA_QUESTIONS, CCPA_SECTIONS

revision: str = "0155_ccpa_complete"
down_revision: str | None = "0154_hipaa_obligation_pack_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def _seed_ccpa(bind: sa.Connection) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "CCPA/CPRA")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="CCPA_CPRA",
                name="CCPA/CPRA",
                description=(
                    "California Consumer Privacy Act (CCPA) as amended by the California Privacy Rights Act "
                    "(CPRA). Applies to for-profit businesses that collect personal information of California "
                    "residents and meet thresholds. Grants consumers rights to know, delete, opt-out of sale, "
                    "correct, and limit use of sensitive personal information."
                ),
                category="Privacy",
                jurisdiction="US-CA",
                authority="State of California",
                version="2023",
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
    for item in CCPA_SECTIONS:
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
    for ref_code, title, description, section_code, evidence_hints in CCPA_OBLIGATIONS:
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
            "obligation_type": "privacy",
            "jurisdiction": "US-CA",
            "source_url": None,
            "version": "2023",
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
        for item in CCPA_QUESTIONS:
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

    req_ck = "ck_data_subject_requests_request_type"
    if _has_constraint(inspector, "data_subject_requests", req_ck):
        op.drop_constraint(req_ck, "data_subject_requests", type_="check")
    op.create_check_constraint(
        req_ck,
        "data_subject_requests",
        "request_type IN ('access', 'erasure', 'portability', 'rectification', 'restriction', 'objection', 'opt_out_of_sale', 'limit_sensitive', 'know', 'correct')",
    )

    inspector = sa.inspect(bind)
    consent_ck = "ck_consent_records_mechanism"
    if _has_constraint(inspector, "consent_records", consent_ck):
        op.drop_constraint(consent_ck, "consent_records", type_="check")
    op.create_check_constraint(
        consent_ck,
        "consent_records",
        "consent_mechanism IN ('explicit_checkbox', 'cookie_banner', 'written_form', 'verbal_recorded', 'api_consent', 'implied', 'ccpa_opt_out')",
    )

    _seed_ccpa(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "CCPA/CPRA")).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))

    req_ck = "ck_data_subject_requests_request_type"
    if _has_constraint(inspector, "data_subject_requests", req_ck):
        op.drop_constraint(req_ck, "data_subject_requests", type_="check")
    op.create_check_constraint(
        req_ck,
        "data_subject_requests",
        "request_type IN ('access', 'erasure', 'portability', 'rectification', 'restriction', 'objection')",
    )

    inspector = sa.inspect(bind)
    consent_ck = "ck_consent_records_mechanism"
    if _has_constraint(inspector, "consent_records", consent_ck):
        op.drop_constraint(consent_ck, "consent_records", type_="check")
    op.create_check_constraint(
        consent_ck,
        "consent_records",
        "consent_mechanism IN ('explicit_checkbox', 'cookie_banner', 'written_form', 'verbal_recorded', 'api_consent', 'implied')",
    )
