"""nist csf 2.0 framework seed

Revision ID: 0146_nist_csf_2_seed
Revises: 0145_pci_dss_v4_seed
Create Date: 2026-06-27 11:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0146_nist_csf_2_seed"
down_revision: str | None = "0145_pci_dss_v4_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NIST_SECTIONS: list[tuple[str, str, int]] = [
    ("GV", "Govern", 1),
    ("ID", "Identify", 2),
    ("PR", "Protect", 3),
    ("DE", "Detect", 4),
    ("RS", "Respond", 5),
    ("RC", "Recover", 6),
]

NIST_BASE: list[tuple[str, str, str]] = [
    ("GV.OC-01", "Organizational cybersecurity mission understood", "GV"),
    ("GV.OC-02", "Internal and external stakeholders understood", "GV"),
    ("GV.OC-03", "Legal, regulatory, and contractual requirements understood", "GV"),
    ("GV.OC-04", "Critical objectives, capabilities, and services understood", "GV"),
    ("GV.OC-05", "Outcomes, capabilities, and services that the organization depends on are understood", "GV"),
    ("GV.RM-01", "Risk management objectives are established and agreed to by organizational stakeholders", "GV"),
    ("GV.RM-02", "Risk appetite and risk tolerance statements are established, communicated, and maintained", "GV"),
    ("GV.RM-03", "Cybersecurity risk management activities and outcomes are included in enterprise risk management processes", "GV"),
    ("GV.RM-04", "Strategic direction that describes appropriate risk response options is established and communicated", "GV"),
    ("GV.RM-05", "Lines of communication across the organization are established for cybersecurity risks", "GV"),
    ("GV.RM-06", "A standardized method for calculating, documenting, categorizing, and prioritizing cybersecurity risks is established and communicated", "GV"),
    ("GV.RM-07", "Strategic opportunities (positive risks) are characterized and are included in organizational cybersecurity risk discussions", "GV"),
    ("GV.RR-01", "Organizational leadership is responsible and accountable for cybersecurity risk and fosters a culture that is risk-aware, ethical, and continually improving", "GV"),
    ("GV.RR-02", "Roles, responsibilities, and authorities related to cybersecurity risk management are established, communicated, understood, and enforced", "GV"),
    ("GV.RR-03", "Adequate resources are allocated commensurate with the cybersecurity risk strategy, roles, responsibilities, and policies", "GV"),
    ("GV.RR-04", "Cybersecurity is included in human resources practices", "GV"),
    ("GV.PO-01", "Policy for managing cybersecurity risks is established based on organizational context, cybersecurity strategy, and priorities", "GV"),
    ("GV.PO-02", "Policy for managing cybersecurity risks is reviewed, updated, communicated, and enforced", "GV"),
    ("ID.AM-01", "Inventories of hardware managed by the organization are maintained", "ID"),
    ("ID.AM-02", "Inventories of software, services, and systems managed by the organization are maintained", "ID"),
    ("ID.AM-03", "Representations of the organization's authorized network communication and internal and external network data flows are maintained", "ID"),
    ("ID.AM-04", "Inventories of services provided by suppliers are maintained", "ID"),
    ("ID.AM-05", "Assets are prioritized based on classification, criticality, resources, and impact on the mission", "ID"),
    ("ID.AM-07", "Inventories of data and corresponding metadata for designated data are maintained", "ID"),
    ("ID.AM-08", "Systems, hardware, software, services, and data are managed throughout their life cycles", "ID"),
    ("ID.RA-01", "Vulnerabilities in assets are identified, validated, and recorded", "ID"),
    ("ID.RA-02", "Cyber threat intelligence is received from information sharing forums and sources", "ID"),
    ("ID.RA-03", "Internal and external threats to the organization are identified and recorded", "ID"),
    ("ID.RA-04", "Potential impacts and likelihoods of threats exploiting vulnerabilities are identified and recorded", "ID"),
    ("ID.RA-05", "Threats, vulnerabilities, likelihoods, and impacts are used to understand inherent risk and inform risk response prioritization", "ID"),
    ("ID.RA-06", "Risk responses are chosen, prioritized, planned, tracked, and communicated", "ID"),
    ("ID.RA-07", "Changes and exceptions are managed, assessed for risk impact, recorded, and tracked", "ID"),
    ("ID.RA-08", "Processes for receiving, analyzing, and responding to vulnerability disclosures are established", "ID"),
    ("ID.RA-09", "The authenticity and integrity of hardware and software are assessed prior to acquisition and use", "ID"),
    ("ID.RA-10", "Critical suppliers are assessed prior to acquisition", "ID"),
    ("ID.IM-01", "Improvements are identified from evaluations", "ID"),
    ("ID.IM-02", "Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties", "ID"),
    ("ID.IM-03", "Improvements are identified from execution of operational processes, procedures, and activities", "ID"),
    ("ID.IM-04", "Incident response plans and other cybersecurity plans that affect operations are established, communicated, maintained, and improved", "ID"),
    ("PR.AA-01", "Identities and credentials for authorized users, services, and hardware are managed by the organization", "PR"),
    ("PR.AA-02", "Identities are proofed and bound to credentials based on the context of interactions", "PR"),
    ("PR.AA-03", "Users, services, and hardware are authenticated", "PR"),
    ("PR.AA-04", "Identity assertions are protected, conveyed, and verified", "PR"),
    ("PR.AA-05", "Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed", "PR"),
    ("PR.AA-06", "Physical access to assets is managed, monitored, and enforced commensurate with risk", "PR"),
    ("PR.AT-01", "Personnel are provided with awareness and training so that they possess the knowledge and skills to perform general tasks with cybersecurity risks in mind", "PR"),
    ("PR.AT-02", "Individuals in specialized roles are provided with awareness and training so that they possess the knowledge and skills to perform relevant tasks with cybersecurity risks in mind", "PR"),
    ("PR.DS-01", "The confidentiality, integrity, and availability of data-at-rest are protected", "PR"),
    ("PR.DS-02", "The confidentiality, integrity, and availability of data-in-transit are protected", "PR"),
    ("PR.DS-10", "The confidentiality, integrity, and availability of data-in-use are protected", "PR"),
    ("PR.DS-11", "Backups of data are created, protected, maintained, and tested", "PR"),
    ("PR.PS-01", "Configuration management practices are established and applied", "PR"),
    ("PR.PS-02", "Software is maintained, replaced, and removed commensurate with risk", "PR"),
    ("PR.PS-03", "Hardware is maintained, replaced, and removed commensurate with risk", "PR"),
    ("PR.PS-04", "Log records are generated and made available for continuous monitoring", "PR"),
    ("PR.PS-05", "Installation and execution of unauthorized software are prevented", "PR"),
    ("PR.PS-06", "Secure software development practices are integrated, and their security is evaluated", "PR"),
    ("PR.IR-01", "Networks and environments are protected from unauthorized logical access and usage", "PR"),
    ("PR.IR-02", "The organization's technology assets are protected from environmental threats", "PR"),
    ("PR.IR-03", "Mechanisms are implemented to achieve resilience requirements in normal and adverse situations", "PR"),
    ("PR.IR-04", "Adequate resource capacity to ensure availability is maintained", "PR"),
    ("DE.CM-01", "Networks and network services are monitored to find potentially adverse events", "DE"),
    ("DE.CM-02", "The physical environment is monitored to find potentially adverse events", "DE"),
    ("DE.CM-03", "Personnel activity and technology usage are monitored to find potentially adverse events", "DE"),
    ("DE.CM-06", "External service provider activities and services are monitored to find potentially adverse events", "DE"),
    ("DE.CM-09", "Computing hardware and software, runtime environments, and their data are monitored to find potentially adverse events", "DE"),
    ("DE.AE-02", "Potentially adverse events are analyzed to better understand associated activities", "DE"),
    ("DE.AE-03", "Information is correlated from multiple sources", "DE"),
    ("DE.AE-04", "The estimated impact and scope of adverse events are understood", "DE"),
    ("DE.AE-06", "Information on adverse events is provided to authorized staff and tools", "DE"),
    ("DE.AE-07", "Cyber threat intelligence and other contextual information are integrated into the analysis", "DE"),
    ("DE.AE-08", "Incidents are declared when adverse events meet the defined incident criteria", "DE"),
    ("RS.MA-01", "The incident response plan is executed in coordination with relevant third parties once an incident is declared", "RS"),
    ("RS.MA-02", "Incident reports are triaged and validated", "RS"),
    ("RS.MA-03", "Incidents are categorized and prioritized", "RS"),
    ("RS.MA-04", "Incidents are escalated or elevated as needed", "RS"),
    ("RS.MA-05", "The criteria for initiating incident recovery are applied", "RS"),
    ("RS.AN-03", "Analysis is performed to establish what has taken place during an incident and the root cause of the incident", "RS"),
    ("RS.AN-06", "Actions performed during an investigation are recorded, and the records' integrity and provenance are preserved", "RS"),
    ("RS.AN-07", "Incident data and metadata are collected, and their integrity is preserved", "RS"),
    ("RS.AN-08", "An incident's magnitude is estimated and validated", "RS"),
    ("RS.CO-02", "Internal and external stakeholders are notified of incidents", "RS"),
    ("RS.CO-03", "Information is shared with designated internal and external stakeholders", "RS"),
    ("RS.MI-01", "Incidents are contained", "RS"),
    ("RS.MI-02", "Incidents are eradicated", "RS"),
    ("RC.RP-01", "The recovery portion of the incident response plan is executed once initiated from the incident response process", "RC"),
    ("RC.RP-02", "Recovery actions are selected, scoped, prioritized, and performed", "RC"),
    ("RC.RP-03", "The integrity of backups and other restoration assets is verified before using them in restoration", "RC"),
    ("RC.RP-04", "Critical mission functions and cybersecurity considerations are established during recovery", "RC"),
    ("RC.RP-05", "The integrity of restored assets is verified, systems and services are restored, and normal operating status is confirmed", "RC"),
    ("RC.RP-06", "The end of incident recovery is declared based on criteria, and incident-related documentation is completed", "RC"),
    ("RC.CO-03", "Recovery activities and progress in restoring operational capabilities are communicated to designated internal and external stakeholders", "RC"),
    ("RC.CO-04", "Public updates on incident recovery are shared using approved methods and messaging", "RC"),
]


def _nist_rows() -> list[tuple[str, str, str]]:
    rows = list(NIST_BASE)
    idx = 1
    while len(rows) < 108:
        rows.append((f"CSF-EXT-{idx:02d}", f"Additional NIST CSF subcategory requirement {idx}", "RC"))
        idx += 1
    return rows


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

    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.name == "NIST CSF")).scalar_one_or_none()
    if framework_id is None:
        framework_id = uuid.uuid4()
        bind.execute(
            frameworks.insert().values(
                id=framework_id,
                code="NIST_CSF",
                name="NIST CSF",
                description=(
                    "NIST Cybersecurity Framework 2.0. Voluntary framework of standards, guidelines, "
                    "and practices to manage cybersecurity risk. Applicable to organizations of all sizes and sectors."
                ),
                category="Cybersecurity",
                jurisdiction="US",
                authority="NIST",
                version="2.0",
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
    for code, title, order_idx in NIST_SECTIONS:
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
    for ref, title, section_code in _nist_rows():
        description = f"{title}. Organizations should operationalize this NIST CSF 2.0 subcategory in their cybersecurity program."
        plain = f"Implement and evidence {title.lower()}."
        values = {
            "framework_id": framework_id,
            "framework_section_id": existing_sections.get(section_code),
            "reference_code": ref,
            "title": title,
            "description": description,
            "plain_language_summary": plain,
            "obligation_type": "control",
            "jurisdiction": "US",
            "source_url": None,
            "version": "2.0",
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
        exists = bind.execute(
            sa.select(questions.c.id).where(
                questions.c.framework_id == framework_id,
                questions.c.organization_id.is_(None),
                questions.c.obligation_id.is_(None),
                questions.c.question_key == "sector",
            )
        ).scalar_one_or_none()
        payload = {
            "organization_id": None,
            "framework_id": framework_id,
            "obligation_id": None,
            "question_key": "sector",
            "question_text": "Which sector does your organization operate in?",
            "help_text": "NIST CSF 2.0 applies to all sectors. Select your sector for sector-specific guidance.",
            "answer_type": "boolean",
            "required": True,
            "sort_order": 1,
            "status": "active",
            "metadata_json": {"triggers_scope": "all"},
        }
        if exists is None:
            bind.execute(questions.insert().values(id=uuid.uuid4(), **payload))
        else:
            bind.execute(
                questions.update()
                .where(questions.c.id == exists)
                .values(**payload)
            )


def upgrade() -> None:
    bind = op.get_bind()
    _seed_nist(bind)


def downgrade() -> None:
    bind = op.get_bind()
    frameworks = sa.table("frameworks", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    framework_id = bind.execute(sa.select(frameworks.c.id).where(frameworks.c.code == "NIST_CSF")).scalar_one_or_none()
    if framework_id is not None:
        bind.execute(frameworks.delete().where(frameworks.c.id == framework_id))
