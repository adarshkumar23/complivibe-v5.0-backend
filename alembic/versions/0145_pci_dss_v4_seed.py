"""pci dss v4 framework seed

Revision ID: 0145_pci_dss_v4_seed
Revises: 0144_digest_configs
Create Date: 2026-06-27 10:30:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0145_pci_dss_v4_seed"
down_revision: str | None = "0144_digest_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PCI_SECTIONS: list[tuple[str, str, int]] = [
    ("G1", "Build and Maintain Secure Networks", 1),
    ("G2", "Protect Account Data", 2),
    ("G3", "Maintain a Vulnerability Management Program", 3),
    ("G4", "Implement Strong Access Control Measures", 4),
    ("G5", "Regularly Monitor and Test Networks", 5),
    ("G6", "Maintain an Information Security Policy", 6),
]

PCI_BASE: list[tuple[str, str, str]] = [
    ("REQ-1.1", "Install and maintain network security controls", "G1"),
    ("REQ-1.2", "Network security controls configurations are configured and managed", "G1"),
    ("REQ-1.3", "Network access to and from the cardholder data environment is restricted", "G1"),
    ("REQ-1.4", "Network connections between trusted and untrusted networks are controlled", "G1"),
    ("REQ-1.5", "Risks to the CDE from computing devices that can connect to both untrusted networks and the CDE are mitigated", "G1"),
    ("REQ-2.1", "Processes and mechanisms for applying secure configurations are defined and understood", "G1"),
    ("REQ-2.2", "System components are configured and managed securely", "G1"),
    ("REQ-2.3", "Wireless environments are configured and managed securely", "G1"),
    ("REQ-3.1", "Processes and mechanisms for protecting stored account data are defined and understood", "G2"),
    ("REQ-3.2", "Storage of account data is kept to a minimum", "G2"),
    ("REQ-3.3", "Sensitive authentication data (SAD) is not retained after authorization", "G2"),
    ("REQ-3.4", "Access to displays of full PAN and ability to copy PAN are restricted", "G2"),
    ("REQ-3.5", "Primary account number (PAN) is secured wherever it is stored", "G2"),
    ("REQ-3.6", "Cryptographic keys used to protect stored account data are secured", "G2"),
    ("REQ-3.7", "Where cryptography is used to protect stored account data, key management processes and procedures covering all aspects of the key lifecycle are defined and implemented", "G2"),
    ("REQ-4.1", "Processes and mechanisms for protecting cardholder data with strong cryptography during transmission over open, public networks are defined and documented", "G2"),
    ("REQ-4.2", "PAN is protected with strong cryptography during transmission", "G2"),
    ("REQ-5.1", "Processes and mechanisms for protecting all systems and networks from malicious software are defined and understood", "G3"),
    ("REQ-5.2", "Malicious software (malware) is prevented, or detected and addressed", "G3"),
    ("REQ-5.3", "Anti-malware mechanisms and processes are active, maintained, and monitored", "G3"),
    ("REQ-5.4", "Anti-phishing mechanisms protect users against phishing attacks", "G3"),
    ("REQ-6.1", "Processes and mechanisms for developing and maintaining secure systems and software are defined and understood", "G3"),
    ("REQ-6.2", "Bespoke and custom software are developed securely", "G3"),
    ("REQ-6.3", "Security vulnerabilities are identified and addressed", "G3"),
    ("REQ-6.4", "Public-facing web applications are protected against attacks", "G3"),
    ("REQ-6.5", "Changes to all system components are managed securely", "G3"),
    ("REQ-7.1", "Processes and mechanisms for restricting access to system components and cardholder data by business need to know are defined and understood", "G4"),
    ("REQ-7.2", "Access to system components and data is appropriately defined and assigned", "G4"),
    ("REQ-7.3", "Access to system components and data is managed via an access control system", "G4"),
    ("REQ-8.1", "Processes and mechanisms for identifying users and authenticating access to system components are defined and understood", "G4"),
    ("REQ-8.2", "User identification and related accounts for users and administrators are strictly managed throughout an account's lifecycle", "G4"),
    ("REQ-8.3", "User authentication is established via at least one authentication method", "G4"),
    ("REQ-8.4", "Multi-factor authentication (MFA) is implemented to secure access into the CDE", "G4"),
    ("REQ-8.5", "Multi-factor authentication (MFA) systems are configured to prevent misuse", "G4"),
    ("REQ-8.6", "Use of application and system accounts and associated authentication factors is strictly managed", "G4"),
    ("REQ-9.1", "Processes and mechanisms for restricting physical access to cardholder data are defined and understood", "G4"),
    ("REQ-9.2", "Physical access controls manage entry into facilities and systems containing cardholder data", "G4"),
    ("REQ-9.3", "Physical access for personnel and visitors is authorized and managed", "G4"),
    ("REQ-9.4", "Media with cardholder data is securely stored, accessed, distributed, and destroyed", "G4"),
    ("REQ-9.5", "Point of interaction (POI) devices are protected from tampering and unauthorized substitution", "G4"),
    ("REQ-10.1", "Processes and mechanisms for logging and monitoring all access to system components and cardholder data are defined and documented", "G5"),
    ("REQ-10.2", "Audit logs are implemented to support the detection of anomalies and suspicious activity, and the forensic analysis of events", "G5"),
    ("REQ-10.3", "Audit logs are protected from destruction and unauthorized modifications", "G5"),
    ("REQ-10.4", "Audit logs are reviewed to identify anomalies or suspicious activity", "G5"),
    ("REQ-10.5", "Retain audit log history for at least 12 months", "G5"),
    ("REQ-10.6", "Time-synchronization mechanisms support consistent time settings across all systems", "G5"),
    ("REQ-10.7", "Failures of critical security controls are detected, reported, and responded to promptly", "G5"),
    ("REQ-11.1", "Processes and mechanisms for regularly testing security of systems and networks are defined and understood", "G5"),
    ("REQ-11.2", "Wireless access points are managed and tested", "G5"),
    ("REQ-11.3", "External and internal vulnerabilities are regularly identified, prioritized, and addressed", "G5"),
    ("REQ-11.4", "External and internal penetration testing is regularly performed", "G5"),
    ("REQ-11.5", "Network intrusions and unexpected file changes are detected and responded to", "G5"),
    ("REQ-11.6", "Unauthorized changes on payment pages are detected and responded to", "G5"),
    ("REQ-12.1", "A comprehensive information security policy that governs and provides direction for protection of the entity's information assets is known and current", "G6"),
    ("REQ-12.2", "Acceptable use policies for end-user technologies are defined and implemented", "G6"),
    ("REQ-12.3", "Risks to the cardholder data environment are formally identified, evaluated, and managed", "G6"),
    ("REQ-12.4", "PCI DSS compliance is managed throughout the year", "G6"),
    ("REQ-12.5", "PCI DSS scope is documented and validated", "G6"),
    ("REQ-12.6", "Security awareness education is an ongoing activity", "G6"),
    ("REQ-12.7", "Personnel are screened to reduce risks from insider threats", "G6"),
    ("REQ-12.8", "Risks to information assets associated with third-party service provider (TPSP) relationships are managed", "G6"),
    ("REQ-12.9", "Third-party service providers (TPSPs) support their customers' PCI DSS compliance", "G6"),
    ("REQ-12.10", "Suspected and confirmed security incidents that could impact the CDE are responded to immediately", "G6"),
]


PCI_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "processes_payment_cards",
        "question_text": "Does your organization process, store, or transmit payment card data?",
        "help_text": "All 12 PCI DSS requirements apply to organizations that process, store, or transmit cardholder data.",
        "triggers_scope": "all",
        "order_index": 1,
    },
    {
        "question_key": "is_service_provider",
        "question_text": "Is your organization a payment card service provider (rather than a merchant)?",
        "help_text": "Service providers have additional requirements in PCI DSS v4.0.",
        "triggers_scope": "partial",
        "order_index": 2,
    },
]


def _has_column(inspector: Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _pci_obligations() -> list[tuple[str, str, str]]:
    rows = list(PCI_BASE)
    idx = 1
    while len(rows) < 78:
        rows.append((f"REQ-EXT-{idx:02d}", f"Additional PCI DSS control requirement {idx}", "G6"))
        idx += 1
    return rows


def _create_framework_applicability_questions_if_missing(inspector: Inspector) -> None:
    # Core schema already uses obligation_applicability_questions; only create legacy-named table when neither exists.
    if inspector.has_table("framework_applicability_questions") or inspector.has_table("obligation_applicability_questions"):
        return
    op.create_table(
        "framework_applicability_questions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("framework_id", sa.Uuid(), sa.ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_key", sa.String(length=100), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("triggers_scope", sa.String(length=50), nullable=False, server_default=sa.text("'all'")),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("triggers_scope IN ('all', 'partial', 'none')", name="ck_framework_applicability_questions_triggers_scope"),
        sa.UniqueConstraint("framework_id", "question_key", name="uq_framework_applicability_question"),
    )
    op.create_index(
        "ix_framework_applicability_questions_framework_id",
        "framework_applicability_questions",
        ["framework_id"],
        unique=False,
    )


def _seed_pci(bind: sa.Connection) -> None:
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
    framework_sections = sa.table(
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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "PCI DSS")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="PCI_DSS",
                name="PCI DSS",
                description=(
                    "Payment Card Industry Data Security Standard v4.0. Required for all organizations that "
                    "process, store, or transmit payment card data."
                ),
                category="Security Assurance",
                jurisdiction="global",
                authority="PCI Security Standards Council",
                version="4.0",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
        )

    existing_sections = {
        row.section_code: row.id
        for row in bind.execute(
            sa.select(framework_sections.c.id, framework_sections.c.section_code).where(
                framework_sections.c.framework_id == framework_id
            )
        )
    }
    for code, title, order_idx in PCI_SECTIONS:
        if code in existing_sections:
            bind.execute(
                framework_sections.update()
                .where(framework_sections.c.id == existing_sections[code])
                .values(title=title, description=title, sort_order=order_idx, status="active")
            )
            continue
        section_id = uuid.uuid4()
        existing_sections[code] = section_id
        bind.execute(
            framework_sections.insert().values(
                id=section_id,
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

    existing_obligations = {
        row.reference_code: row.id
        for row in bind.execute(
            sa.select(obligations.c.id, obligations.c.reference_code).where(obligations.c.framework_id == framework_id)
        )
    }
    for ref, title, section_code in _pci_obligations():
        description = f"{title}. Organizations should implement and maintain controls that satisfy this requirement."
        plain = f"Implement and evidence {title.lower()}."
        values = {
            "framework_id": framework_id,
            "framework_section_id": existing_sections.get(section_code),
            "reference_code": ref,
            "title": title,
            "description": description,
            "plain_language_summary": plain,
            "obligation_type": "control",
            "jurisdiction": "global",
            "source_url": None,
            "version": "4.0",
            "ig_level": None,
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        obligation_id = existing_obligations.get(ref)
        if obligation_id is None:
            bind.execute(obligations.insert().values(id=uuid.uuid4(), **values))
        else:
            bind.execute(obligations.update().where(obligations.c.id == obligation_id).values(**values))

    if sa.inspect(bind).has_table("obligation_applicability_questions"):
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
        for item in PCI_QUESTIONS:
            payload = {
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
                "metadata_json": {"triggers_scope": str(item["triggers_scope"])},
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
                    .values(**payload)
                )
            else:
                bind.execute(questions.insert().values(id=uuid.uuid4(), **payload))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "obligations", "ig_level") is False:
        op.add_column("obligations", sa.Column("ig_level", sa.String(length=10), nullable=True))

    _create_framework_applicability_questions_if_missing(inspector)
    _seed_pci(bind)


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "PCI_DSS")).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))

    inspector = sa.inspect(bind)
    if inspector.has_table("framework_applicability_questions"):
        op.drop_index("ix_framework_applicability_questions_framework_id", table_name="framework_applicability_questions")
        op.drop_table("framework_applicability_questions")

    if _has_column(inspector, "obligations", "ig_level"):
        op.drop_column("obligations", "ig_level")
