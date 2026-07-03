"""dora tables and seed

Revision ID: 0149_dora_tables_and_seed
Revises: 0148_iso_27701_seed_and_cross_mappings
Create Date: 2026-06-27 15:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0149_dora_tables_and_seed"
down_revision: str | None = "0148_iso_27701_seed_and_cross_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DORA_SECTIONS: list[tuple[str, str, int]] = [
    ("DORA-II", "ICT Risk Management", 1),
    ("DORA-III", "ICT Incident Management", 2),
    ("DORA-IV", "Digital Operational Resilience Testing", 3),
    ("DORA-V", "ICT Third-Party Risk Management", 4),
    ("DORA-VI", "Information Sharing Arrangements", 5),
]

DORA_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "DORA-5.1",
        "Governance and organisation of ICT risk management",
        "Financial entities shall have in place an internal governance and control framework that ensures effective and prudent management of ICT risk.",
        "DORA-II",
        ["ict_risk_policy", "governance_documentation", "board_approval"],
    ),
    (
        "DORA-6.1",
        "ICT risk management framework",
        "Financial entities shall have a sound, comprehensive and well-documented ICT risk management framework as part of their overall risk management system.",
        "DORA-II",
        ["ict_risk_framework", "risk_register", "annual_review_evidence"],
    ),
    (
        "DORA-7.1",
        "ICT systems, protocols and tools",
        "Financial entities shall use and maintain updated ICT systems, protocols and tools that are appropriate to the magnitude of operations.",
        "DORA-II",
        [],
    ),
    (
        "DORA-8.1",
        "Identification of ICT risks",
        "Financial entities shall implement processes to identify all sources of ICT risk including risks from third-party ICT service providers.",
        "DORA-II",
        [],
    ),
    (
        "DORA-9.1",
        "Protection and prevention controls",
        "Financial entities shall have in place appropriate ICT security policies, procedures and controls to ensure the resilience and continuity of ICT systems.",
        "DORA-II",
        [],
    ),
    (
        "DORA-10.1",
        "Detection of anomalous activities",
        "Financial entities shall have in place mechanisms to promptly detect anomalous activities including ICT network performance issues and ICT-related incidents.",
        "DORA-II",
        [],
    ),
    (
        "DORA-11.1",
        "Business continuity policy",
        "Financial entities shall put in place a comprehensive ICT business continuity policy as part of their overall business continuity management.",
        "DORA-II",
        [],
    ),
    (
        "DORA-12.1",
        "Backup policies and recovery procedures",
        "Financial entities shall implement backup policies and procedures to ensure that all critical data can be recovered within defined time objectives.",
        "DORA-II",
        [],
    ),
    (
        "DORA-13.1",
        "Learning and evolving",
        "Financial entities shall have in place capabilities and staff to gather intelligence on the latest cyber threats and vulnerabilities.",
        "DORA-II",
        [],
    ),
    (
        "DORA-14.1",
        "Communication",
        "Financial entities shall have in place crisis communication plans enabling a responsible disclosure of ICT-related incidents to clients and counterparts.",
        "DORA-II",
        [],
    ),
    (
        "DORA-15.1",
        "ICT risk management for payment systems",
        "Financial entities that are payment institutions shall additionally comply with sector-specific ICT requirements for payment services.",
        "DORA-II",
        [],
    ),
    (
        "DORA-16.1",
        "Simplified ICT risk management framework",
        "Smaller financial entities may apply a simplified ICT risk management framework proportionate to their size, overall risk profile and complexity.",
        "DORA-II",
        [],
    ),
    (
        "DORA-17.1",
        "ICT-related incident management process",
        "Financial entities shall define, establish and implement an ICT-related incident management process to detect, manage and notify ICT-related incidents.",
        "DORA-III",
        [],
    ),
    (
        "DORA-18.1",
        "ICT-related incident classification",
        "Financial entities shall classify ICT-related incidents and determine their impact based on criteria including number of clients affected, duration, geographic spread, and data losses.",
        "DORA-III",
        [],
    ),
    (
        "DORA-19.1",
        "Major ICT incident reporting",
        "Financial entities shall report major ICT-related incidents to the relevant competent authority. Initial notification within 4 hours. Intermediate report within 72 hours. Final report within 1 month.",
        "DORA-III",
        [],
    ),
    (
        "DORA-20.1",
        "Harmonised reporting",
        "Competent authorities shall use standardised reporting templates for ICT incident reporting. EBA/ESMA/EIOPA to develop regulatory technical standards.",
        "DORA-III",
        [],
    ),
    (
        "DORA-21.1",
        "Voluntary notification of cyber threats",
        "Financial entities may voluntarily notify significant cyber threats to the relevant competent authority.",
        "DORA-III",
        [],
    ),
    (
        "DORA-24.1",
        "General digital operational resilience testing",
        "Financial entities shall establish, maintain and review a sound and comprehensive digital operational resilience testing programme.",
        "DORA-IV",
        [],
    ),
    (
        "DORA-25.1",
        "Testing of ICT tools and systems",
        "Financial entities shall test ICT tools, systems and processes at least annually including vulnerability assessments and scans.",
        "DORA-IV",
        [],
    ),
    (
        "DORA-26.1",
        "Advanced testing — TLPT",
        "Financial entities identified by competent authorities shall conduct advanced testing using threat-led penetration testing (TLPT) at least every 3 years.",
        "DORA-IV",
        [],
    ),
    (
        "DORA-28.1",
        "Key principles for ICT TPRM",
        "Financial entities shall manage ICT third-party risk as an integral component of their ICT risk management framework.",
        "DORA-V",
        [],
    ),
    (
        "DORA-28.2",
        "Register of information",
        "Financial entities shall maintain and update a register of information for all contractual arrangements on the use of ICT services.",
        "DORA-V",
        [],
    ),
    (
        "DORA-29.1",
        "Preliminary assessment of ICT third-party risk",
        "Financial entities shall carry out a preliminary risk assessment before entering into contractual arrangements with ICT third-party service providers.",
        "DORA-V",
        [],
    ),
    (
        "DORA-30.1",
        "Key contractual provisions",
        "Financial entities shall ensure contractual arrangements with ICT third-party service providers include provisions on access, audit rights, exit strategies, and service levels.",
        "DORA-V",
        [],
    ),
    (
        "DORA-31.1",
        "Critical or important functions",
        "Financial entities shall identify ICT services supporting critical or important functions and ensure enhanced oversight of relevant providers.",
        "DORA-V",
        [],
    ),
]

DORA_QUESTIONS: list[dict[str, object]] = [
    {
        "question_key": "eu_financial_entity",
        "question_text": "Is your organization a financial entity operating in the EU (bank, investment firm, insurance, payment institution, CASP)?",
        "help_text": "DORA applies to financial entities as defined in Article 2: credit institutions, payment institutions, e-money institutions, investment firms, crypto-asset service providers, insurance undertakings, and others.",
        "triggers_scope": "all",
        "order_index": 1,
    },
    {
        "question_key": "is_microenterprise",
        "question_text": "Is your organization a microenterprise (fewer than 10 employees and turnover < EUR 2M)?",
        "help_text": "Microenterprises qualify for the simplified ICT risk management framework under Art. 16.",
        "triggers_scope": "partial",
        "order_index": 2,
    },
]


def _ensure_dora_ict_register_table() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("dora_ict_register"):
        return

    op.create_table(
        "dora_ict_register",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("counterparty_name", sa.String(length=255), nullable=False),
        sa.Column("service_description", sa.Text(), nullable=False),
        sa.Column("is_critical_function", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sub_outsourcing_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("data_location", sa.String(length=200), nullable=True),
        sa.Column("data_location_countries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("contract_start_date", sa.Date(), nullable=True),
        sa.Column("contract_end_date", sa.Date(), nullable=True),
        sa.Column("exit_strategy_documented", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("exit_strategy_notes", sa.Text(), nullable=True),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_frequency", sa.String(length=20), nullable=True),
        sa.Column("dora_article", sa.String(length=20), nullable=False, server_default=sa.text("'Art.28'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "assessment_frequency IN ('annual', 'biannual', 'quarterly', 'continuous') OR assessment_frequency IS NULL",
            name="ck_dora_ict_register_assessment_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'under_review', 'terminated')",
            name="ck_dora_ict_register_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dora_ict_register_org_critical", "dora_ict_register", ["organization_id", "is_critical_function"], unique=False)
    op.create_index("ix_dora_ict_register_org_status", "dora_ict_register", ["organization_id", "status"], unique=False)
    op.create_index("ix_dora_ict_register_org_vendor", "dora_ict_register", ["organization_id", "vendor_id"], unique=False)


def _seed_dora(bind: sa.Connection) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "DORA")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="DORA",
                name="DORA",
                description=(
                    "EU Digital Operational Resilience Act (Regulation EU 2022/2554). Mandatory for financial sector entities in the EU "
                    "from January 2025. Covers ICT risk management, incident classification and reporting, digital operational resilience "
                    "testing, and ICT third-party risk management."
                ),
                category="Operational Resilience",
                jurisdiction="EU",
                authority="European Union",
                version="2022/2554",
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
    for code, title, order_idx in DORA_SECTIONS:
        if code in section_by_code:
            bind.execute(
                sections.update()
                .where(sections.c.id == section_by_code[code])
                .values(title=title, description=title, sort_order=order_idx, status="active")
            )
            continue
        sec_id = uuid.uuid4()
        section_by_code[code] = sec_id
        bind.execute(
            sections.insert().values(
                id=sec_id,
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

    existing = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id))
    }
    for ref_code, title, description, section_code, evidence_hints in DORA_OBLIGATIONS:
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_by_code.get(section_code),
            "reference_code": ref_code,
            "title": title,
            "description": description,
            "plain_language_summary": f"Implement and evidence {title.lower()}. Evidence hints: {', '.join(evidence_hints)}" if evidence_hints else f"Implement and evidence {title.lower()}.",
            "obligation_type": "resilience",
            "jurisdiction": "EU",
            "source_url": None,
            "version": "2022/2554",
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
        for item in DORA_QUESTIONS:
            values = {
                "organization_id": None,
                "framework_id": framework_id,
                "obligation_id": None,
                "question_key": str(item["question_key"]),
                "question_text": str(item["question_text"]),
                "help_text": str(item["help_text"]),
                "answer_type": "boolean",
                "required": True,
                "sort_order": int(item["order_index"]),
                "status": "active",
                "metadata_json": {"triggers_scope": str(item["triggers_scope"]), "choices": []},
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
    _ensure_dora_ict_register_table()
    _seed_dora(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()

    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    dora_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "DORA")).scalar_one_or_none()
    if dora_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == dora_id))

    inspector = sa.inspect(bind)
    if inspector.has_table("dora_ict_register"):
        op.drop_index("ix_dora_ict_register_org_vendor", table_name="dora_ict_register")
        op.drop_index("ix_dora_ict_register_org_status", table_name="dora_ict_register")
        op.drop_index("ix_dora_ict_register_org_critical", table_name="dora_ict_register")
        op.drop_table("dora_ict_register")
