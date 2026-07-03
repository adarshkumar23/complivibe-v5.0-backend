"""nist sp 800-53 rev 5 schema + low baseline seed

Revision ID: 0152_nist_800_53_seed
Revises: 0151_nis2_dora_sla_wiring
Create Date: 2026-06-27 16:10:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.services.framework_seed_data_stream_a4 import (
    NIST_800_53_LOW_CONTROLS,
    NIST_800_53_QUESTIONS,
    NIST_800_53_SECTIONS,
    nist_description,
    nist_evidence_hints,
)

revision: str = "0152_nist_800_53_seed"
down_revision: str | None = "0151_nis2_dora_sla_wiring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NIST_FRAMEWORK_NAME = "NIST SP 800-53"
NIST_VERSION = "Rev 5"


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def _seed_nist(bind: sa.Connection) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == NIST_FRAMEWORK_NAME)).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="NIST_800_53",
                name=NIST_FRAMEWORK_NAME,
                description=(
                    "NIST Special Publication 800-53 Rev 5 — Security and Privacy Controls for Information "
                    "Systems and Organizations. Baseline: LOW (125 controls). Required for US federal "
                    "systems. Foundation for FedRAMP."
                ),
                category="Cybersecurity",
                jurisdiction="US",
                authority="NIST",
                version=NIST_VERSION,
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
        )
    else:
        bind.execute(
            frameworks.update()
            .where(frameworks.c.id == framework_id)
            .values(
                code="NIST_800_53",
                version=NIST_VERSION,
                status="active",
                coverage_level="starter",
                jurisdiction="US",
                authority="NIST",
                category="Cybersecurity",
            )
        )

    section_map = {
        row.section_code: row.id
        for row in bind.execute(sa.select(sections.c.id, sections.c.section_code).where(sections.c.framework_id == framework_id))
    }
    for item in NIST_800_53_SECTIONS:
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
                sections.update()
                .where(sections.c.id == row_id)
                .values(title=title, description=title, sort_order=order_idx, status="active")
            )

    existing = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id))
    }
    desired_refs: set[str] = set()
    for ref_code, title, family in NIST_800_53_LOW_CONTROLS:
        desired_refs.add(ref_code)
        hints = nist_evidence_hints(family)
        plain = f"Implement and evidence {title.lower()}."
        if hints:
            plain = f"{plain} Evidence hints: {', '.join(hints)}"
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_map.get(family),
            "reference_code": ref_code,
            "title": title,
            "description": nist_description(ref_code, title, family),
            "plain_language_summary": plain,
            "obligation_type": "control",
            "jurisdiction": "US",
            "source_url": None,
            "version": NIST_VERSION,
            "ig_level": None,
            "control_family": family,
            "baseline": "LOW",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        row_id = existing.get(ref_code)
        if row_id is None:
            bind.execute(obligations.insert().values(id=uuid.uuid4(), **values))
        else:
            bind.execute(obligations.update().where(obligations.c.id == row_id).values(**values))

    for ref_code, row_id in existing.items():
        if ref_code in desired_refs:
            continue
        bind.execute(
            obligations.update()
            .where(obligations.c.id == row_id)
            .values(status="inactive", baseline=None, control_family=None)
        )

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
        for item in NIST_800_53_QUESTIONS:
            metadata = {"triggers_scope": str(item["triggers_scope"])}
            if "choices" in item:
                metadata["choices"] = list(item["choices"])  # type: ignore[index]
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
                "metadata_json": metadata,
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


def _verify_nist_count(bind: sa.Connection) -> None:
    obligations = sa.table(
        "obligations",
        sa.column("framework_id", sa.Uuid()),
        sa.column("baseline", sa.String()),
        sa.column("status", sa.String()),
        sa.column("id", sa.Uuid()),
    )
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == NIST_FRAMEWORK_NAME)).scalar_one_or_none()
    if framework_id is None:
        return
    count = int(
        bind.execute(
            sa.select(sa.func.count(obligations.c.id)).where(
                obligations.c.framework_id == framework_id,
                obligations.c.status == "active",
                obligations.c.baseline == "LOW",
            )
        ).scalar_one()
        or 0
    )
    if count != 125:
        raise RuntimeError(f"Expected 125 LOW baseline controls for {NIST_FRAMEWORK_NAME}, found {count}")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "obligations", "control_family"):
        op.add_column("obligations", sa.Column("control_family", sa.VARCHAR(length=10), nullable=True))
    if not _has_column(inspector, "obligations", "baseline"):
        op.add_column("obligations", sa.Column("baseline", sa.VARCHAR(length=20), nullable=True))

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "obligations", "ck_obligations_control_family"):
        op.drop_constraint("ck_obligations_control_family", "obligations", type_="check")
    op.create_check_constraint(
        "ck_obligations_control_family",
        "obligations",
        "control_family IS NULL OR control_family IN ('AC','AT','AU','CA','CM','CP','IA','IR','MA','MP','PE','PL','PM','PS','PT','RA','SA','SC','SI','SR')",
    )

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "obligations", "ck_obligations_baseline"):
        op.drop_constraint("ck_obligations_baseline", "obligations", type_="check")
    op.create_check_constraint(
        "ck_obligations_baseline",
        "obligations",
        "baseline IS NULL OR baseline IN ('LOW','MODERATE','HIGH')",
    )

    _seed_nist(bind)
    _verify_nist_count(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == NIST_FRAMEWORK_NAME)).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "obligations", "ck_obligations_baseline"):
        op.drop_constraint("ck_obligations_baseline", "obligations", type_="check")
    if _has_constraint(inspector, "obligations", "ck_obligations_control_family"):
        op.drop_constraint("ck_obligations_control_family", "obligations", type_="check")

    inspector = sa.inspect(bind)
    if _has_column(inspector, "obligations", "baseline"):
        op.drop_column("obligations", "baseline")
    if _has_column(inspector, "obligations", "control_family"):
        op.drop_column("obligations", "control_family")
