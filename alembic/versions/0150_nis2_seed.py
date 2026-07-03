"""nis2 seed

Revision ID: 0150_nis2_seed
Revises: 0149_dora_tables_and_seed
Create Date: 2026-06-27 15:20:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0150_nis2_seed"
down_revision: str | None = "0149_dora_tables_and_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NIS2_SECTIONS: list[tuple[str, str, int]] = [
    ("NIS2-ART21", "Cybersecurity Risk Management Measures", 1),
    ("NIS2-ART23", "Reporting Obligations", 2),
    ("NIS2-ART24", "Use of European Cybersecurity Schemes", 3),
]

NIS2_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "NIS2-21.1",
        "Policies on risk analysis and information system security",
        "Essential and important entities shall adopt documented policies on risk analysis and information system security.",
        "NIS2-ART21",
        ["risk_policy", "isms_documentation", "board_approval_evidence"],
    ),
    (
        "NIS2-21.2",
        "Incident handling",
        "Entities shall have documented procedures for incident detection, analysis, containment, eradication, and recovery.",
        "NIS2-ART21",
        ["incident_response_plan", "tabletop_exercise_record", "post_incident_review"],
    ),
    (
        "NIS2-21.3",
        "Business continuity and backup",
        "Entities shall implement backup management and crisis management measures to maintain availability during incidents.",
        "NIS2-ART21",
        ["bcp_document", "backup_test_results", "rto_rpo_documentation"],
    ),
    (
        "NIS2-21.4",
        "Supply chain security",
        "Entities shall address cybersecurity in relationships with direct suppliers and service providers including security assessment criteria.",
        "NIS2-ART21",
        ["supplier_security_policy", "vendor_assessment_records", "contract_security_clauses"],
    ),
    (
        "NIS2-21.5",
        "Security in network acquisition and development",
        "Entities shall implement security measures in the acquisition, development, and maintenance of network and information systems.",
        "NIS2-ART21",
        ["sdlc_security_policy", "code_review_evidence", "security_testing_results"],
    ),
    (
        "NIS2-21.6",
        "Policies and procedures for cryptography and encryption",
        "Entities shall implement policies and procedures on the use of cryptography and encryption to protect data at rest and in transit.",
        "NIS2-ART21",
        ["crypto_policy", "tls_config", "key_management_procedure"],
    ),
    (
        "NIS2-21.7",
        "Human resources security and access control",
        "Entities shall implement personnel security measures including background checks where permitted and access management controls.",
        "NIS2-ART21",
        ["access_control_policy", "hr_security_procedure", "mfa_implementation_evidence"],
    ),
    (
        "NIS2-21.8",
        "Use of multi-factor authentication",
        "Entities shall use multi-factor authentication or continuous authentication solutions for privileged and remote access.",
        "NIS2-ART21",
        ["mfa_configuration_screenshot", "privileged_access_policy", "mfa_coverage_report"],
    ),
    (
        "NIS2-21.9",
        "Securing communications and emergency communications",
        "Entities shall use secure voice, video and text communications and secured emergency communication systems where appropriate.",
        "NIS2-ART21",
        ["secure_comms_policy", "encrypted_communication_tools", "incident_comms_procedure"],
    ),
    (
        "NIS2-21.10",
        "Awareness training",
        "Entities shall ensure basic cybersecurity hygiene practices and cybersecurity training for all personnel.",
        "NIS2-ART21",
        ["training_completion_records", "awareness_program_materials", "phishing_simulation_results"],
    ),
    (
        "NIS2-23.1",
        "Significant incident — early warning (24h)",
        "Entities shall submit an early warning to the competent authority within 24 hours of becoming aware of a significant incident.",
        "NIS2-ART23",
        ["early_warning_submission", "incident_timeline_record"],
    ),
    (
        "NIS2-23.2",
        "Significant incident — notification (72h)",
        "Entities shall submit an incident notification within 72 hours of becoming aware, providing an initial assessment of the incident.",
        "NIS2-ART23",
        ["incident_notification_record", "72h_submission_evidence"],
    ),
    (
        "NIS2-23.3",
        "Significant incident — final report (1 month)",
        "Entities shall submit a final report within one month, including a description of the incident, its severity, impact, and the cross-border impact where applicable.",
        "NIS2-ART23",
        ["final_report_submission", "post_incident_review"],
    ),
    (
        "NIS2-23.4",
        "Intermediate report if requested",
        "At the request of the competent authority, an intermediate report on relevant status updates shall be submitted.",
        "NIS2-ART23",
        [],
    ),
    (
        "NIS2-24.1",
        "Use of certified ICT products and services",
        "Where required by implementing acts, entities shall use ICT products, services and processes certified under European cybersecurity certification schemes.",
        "NIS2-ART24",
        [],
    ),
]

NIS2_QUESTIONS: list[dict[str, object]] = [
    {
        "question_key": "eu_entity",
        "question_text": "Does your organization operate in the European Union or provide services to EU residents?",
        "help_text": "",
        "triggers_scope": "all",
        "order_index": 1,
    },
    {
        "question_key": "entity_type",
        "question_text": "Is your organization classified as an Essential Entity (EE) or Important Entity (IE) under NIS2?",
        "help_text": "Essential Entities (larger organizations in critical sectors) face more stringent supervisory requirements than Important Entities but both must comply with Art. 21.",
        "triggers_scope": "partial",
        "order_index": 2,
    },
    {
        "question_key": "sector",
        "question_text": "Which NIS2 sector applies to your organization?",
        "help_text": "Annex I (Essential): Energy, transport, banking, financial markets, health, drinking water, wastewater, digital infrastructure, ICT managed services, public administration, space. Annex II (Important): Postal, waste, chemicals, food, manufacturing, digital providers, research.",
        "triggers_scope": "partial",
        "order_index": 3,
    },
]

DORA_NIS2_MAPPINGS: list[tuple[str, str, str]] = [
    ("DORA-17.1", "NIS2-21.2", "related"),
    ("DORA-11.1", "NIS2-21.3", "related"),
    ("DORA-28.1", "NIS2-21.4", "related"),
    ("DORA-19.1", "NIS2-23.2", "related"),
]

DORA_ISO27001_MAPPINGS: list[tuple[str, str, str]] = [
    ("DORA-6.1", "ISO27001 A.6.1.1", "related"),
    ("DORA-10.1", "ISO27001 A.12.4.1", "related"),
    ("DORA-12.1", "ISO27001 A.12.3.1", "related"),
]


def _seed_nis2(bind: sa.Connection) -> None:
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "NIS2")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="NIS2",
                name="NIS2",
                description=(
                    "EU Network and Information Security Directive 2 (Directive EU 2022/2555). Replaces NIS1. Mandatory for essential and "
                    "important entities in critical sectors across the EU from October 2024. Covers cybersecurity risk management, incident "
                    "reporting obligations, and supply chain security."
                ),
                category="Cybersecurity",
                jurisdiction="EU",
                authority="European Union",
                version="2022/2555",
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
    for code, title, order_idx in NIS2_SECTIONS:
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
    for ref_code, title, description, section_code, evidence_hints in NIS2_OBLIGATIONS:
        values = {
            "framework_id": framework_id,
            "framework_section_id": section_by_code.get(section_code),
            "reference_code": ref_code,
            "title": title,
            "description": description,
            "plain_language_summary": f"Implement and evidence {title.lower()}. Evidence hints: {', '.join(evidence_hints)}" if evidence_hints else f"Implement and evidence {title.lower()}.",
            "obligation_type": "cybersecurity",
            "jurisdiction": "EU",
            "source_url": None,
            "version": "2022/2555",
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
        for item in NIS2_QUESTIONS:
            answer_type = "single_select" if item["question_key"] == "sector" else "boolean"
            values = {
                "organization_id": None,
                "framework_id": framework_id,
                "obligation_id": None,
                "question_key": str(item["question_key"]),
                "question_text": str(item["question_text"]),
                "help_text": str(item["help_text"]),
                "answer_type": answer_type,
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


def _seed_cross_mappings(bind: sa.Connection) -> None:
    obligations = sa.table(
        "obligations",
        sa.column("id", sa.Uuid()),
        sa.column("framework_id", sa.Uuid()),
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

    obligation_by_ref = {
        row.reference_code: row.id
        for row in bind.execute(sa.select(obligations.c.id, obligations.c.reference_code))
    }
    existing = {
        (row.source_obligation_id, row.target_obligation_id): row.id
        for row in bind.execute(sa.select(mappings.c.id, mappings.c.source_obligation_id, mappings.c.target_obligation_id))
    }

    for source_ref, target_ref, mapping_type in [*DORA_NIS2_MAPPINGS, *DORA_ISO27001_MAPPINGS]:
        source_id = obligation_by_ref.get(source_ref)
        target_id = obligation_by_ref.get(target_ref)
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
    bind = op.get_bind()
    _seed_nis2(bind)
    _seed_cross_mappings(bind)


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    nis2_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "NIS2")).scalar_one_or_none()
    if nis2_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == nis2_id))
