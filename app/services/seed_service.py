import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.models.framework import Framework
from app.models.framework_version import FrameworkVersion
from app.models.obligation import Obligation
from app.models.permission import Permission
from app.models.policy_template import PolicyTemplate
from app.models.role import Role
from app.models.role_permission import RolePermission

PERMISSIONS: dict[str, str] = {
    "org:read": "Read organization details",
    "org:update": "Update organization details",
    "users:read": "Read users",
    "users:invite": "Invite users",
    "users:update_role": "Update user role",
    "frameworks:read": "Read frameworks",
    "frameworks:activate": "Activate frameworks",
    "controls:read": "Read controls",
    "controls:write": "Write controls",
    "exceptions:approve": "Approve or reject control exception requests",
    "technical_controls:manage": "Register technical agents and manage technical control rules",
    "technical_controls:view": "Read technical control test results and summaries",
    "evidence:read": "Read evidence metadata",
    "evidence:write": "Write evidence metadata",
    "risks:read": "Read risks",
    "risks:write": "Write risks",
    "tasks:read": "Read tasks",
    "tasks:write": "Write tasks",
    "audit_logs:read": "Read audit logs",
    "dashboard:read": "Read dashboard",
    "email:read": "Read email templates and outbox",
    "email:write": "Create email templates and queue/cancel emails",
    "email:send": "Mark emails sent/failed for internal testing",
    "email:admin": "Administer organization email templates",
    "automation:read": "Read automation rules and execution history",
    "automation:write": "Create and manage automation rules",
    "automation:execute": "Execute automation scans and rules",
    "recertification:read": "Read recertification policies and runs",
    "recertification:write": "Create and manage recertification policies",
    "recertification:execute": "Execute recertification and reassessment runs",
    "reports:read": "Read compliance reports",
    "reports:write": "Manage compliance reports",
    "reports:generate": "Generate compliance reports",
    "exports:read": "Read export jobs and export packages",
    "exports:write": "Create and manage export jobs",
    "exports:run": "Run export jobs",
    "exports:verify": "Verify export integrity",
    "retention:read": "Read retention governance data",
    "retention:write": "Manage retention policies and legal holds",
    "attestations:read": "Read export attestations",
    "attestations:write": "Create export attestations",
    "attestations:revoke": "Revoke export attestations",
    "attestations:manage": "Create and manage employee attestation campaigns and exemptions",
    "attestations:submit": "Submit employee policy attestations",
    "attestations:view": "Read employee attestation campaigns and records",
    "policy_exceptions:submit": "Submit and withdraw own policy exception requests",
    "policy_exceptions:manage": "Approve, reject, and manage all policy exception requests",
    "policy_exceptions:view": "Read policy exception requests and dashboards",
    "policy_risks:manage": "Create, update, and delete policy-to-risk mappings",
    "policy_risks:view": "Read policy-to-risk mappings and coverage summaries",
    "policy_issues:manage": "Create, update, and delete policy-to-issue links",
    "policy_issues:view": "Read policy-to-issue links and effectiveness summaries",
    "governance_override:read": "Read governance override requests",
    "governance_override:create": "Create governance override requests",
    "governance_override:approve": "Approve or reject governance override requests",
    "governance_override:execute": "Execute approved governance override requests",
    "governance_override:cancel": "Cancel governance override requests",
    "governance_override_template:read": "Read governance override templates",
    "governance_override_template:write": "Create and manage governance override templates",
    "framework_content:review": "Review framework content packs and review history",
    "framework_content:promote": "Create and execute framework coverage promotions",
    "framework_review_capacity:read": "Read reviewer capacity policies, workload, and assignment suggestions",
    "framework_review_capacity:write": "Manage reviewer capacity policies",
    "ai_systems:read": "Read AI system inventory records",
    "ai_systems:write": "Create and update AI system inventory records",
    "ai_systems:admin": "Archive and administer AI system inventory records",
    "compliance_policies:read": "Read compliance policies",
    "compliance_policies:write": "Create and update compliance policies",
    "compliance_policies:approve": "Approve compliance policies",
    "vendors:read": "Read vendor and third-party inventory",
    "vendors:write": "Create and update vendor inventory records",
    "vendors:admin": "Archive and administer vendor inventory records",
    "monitoring:read": "Read control monitoring definitions and results",
    "monitoring:write": "Create and manage control monitoring definitions and results",
    "compliance_deadlines:read": "Read compliance deadlines and calendar events",
    "compliance_deadlines:write": "Create and manage compliance deadlines and calendar events",
    "risk_appetite:read": "Read risk appetite thresholds and breach summaries",
    "risk_appetite:write": "Create and manage risk appetite thresholds",
    "risk_indicators:read": "Read key risk indicators",
    "risk_indicators:write": "Create and manage key risk indicators",
}

ROLE_PERMISSION_MAP: dict[str, set[str]] = {
    "owner": set(PERMISSIONS.keys()),
    "admin": set(PERMISSIONS.keys()),
    "compliance_manager": {
        "frameworks:read",
        "frameworks:activate",
        "controls:read",
        "controls:write",
        "evidence:read",
        "evidence:write",
        "risks:read",
        "risks:write",
        "tasks:read",
        "tasks:write",
        "dashboard:read",
        "org:read",
        "users:read",
        "email:read",
        "email:write",
        "email:send",
        "automation:read",
        "automation:write",
        "automation:execute",
        "recertification:read",
        "recertification:write",
        "recertification:execute",
        "reports:read",
        "reports:write",
        "reports:generate",
        "exports:read",
        "exports:write",
        "exports:run",
        "exports:verify",
        "retention:read",
        "retention:write",
        "attestations:read",
        "attestations:write",
        "attestations:revoke",
        "attestations:submit",
        "attestations:view",
        "policy_exceptions:manage",
        "policy_exceptions:submit",
        "policy_exceptions:view",
        "policy_risks:manage",
        "policy_risks:view",
        "policy_issues:manage",
        "policy_issues:view",
        "governance_override:read",
        "governance_override:create",
        "governance_override:approve",
        "governance_override:execute",
        "governance_override:cancel",
        "governance_override_template:read",
        "governance_override_template:write",
        "framework_content:review",
        "framework_content:promote",
        "framework_review_capacity:read",
        "framework_review_capacity:write",
        "ai_systems:read",
        "ai_systems:write",
        "ai_systems:admin",
        "compliance_policies:read",
        "compliance_policies:write",
        "compliance_policies:approve",
        "vendors:read",
        "vendors:write",
        "vendors:admin",
        "monitoring:read",
        "monitoring:write",
        "compliance_deadlines:read",
        "compliance_deadlines:write",
        "risk_appetite:read",
        "risk_indicators:read",
        "technical_controls:manage",
        "technical_controls:view",
    },
    "reviewer": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "evidence:write",
        "risks:read",
        "tasks:read",
        "tasks:write",
        "dashboard:read",
        "email:read",
        "automation:read",
        "recertification:read",
        "recertification:execute",
        "reports:read",
        "reports:generate",
        "exports:read",
        "exports:run",
        "retention:read",
        "attestations:read",
        "attestations:write",
        "attestations:manage",
        "attestations:submit",
        "attestations:view",
        "policy_exceptions:submit",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "governance_override:read",
        "governance_override:approve",
        "governance_override_template:read",
        "framework_content:review",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "technical_controls:manage",
        "technical_controls:view",
    },
    "auditor": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "risks:read",
        "audit_logs:read",
        "dashboard:read",
        "tasks:read",
        "org:read",
        "email:read",
        "automation:read",
        "recertification:read",
        "reports:read",
        "exports:read",
        "exports:verify",
        "retention:read",
        "attestations:read",
        "attestations:view",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "technical_controls:view",
    },
    "readonly": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "risks:read",
        "tasks:read",
        "dashboard:read",
        "org:read",
        "reports:read",
        "exports:read",
        "retention:read",
        "attestations:read",
        "attestations:view",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "technical_controls:view",
    },
}

PILLAR1_AUDIT_ACTION_REGISTRY: dict[str, tuple[str, ...]] = {
    "compliance_policies": (
        "compliance_policy.created",
        "compliance_policy.updated",
        "compliance_policy.archived",
    ),
    "compliance_policy_versions": (
        "compliance_policy_version.created",
        "compliance_policy_version.submitted",
    ),
    "compliance_policy_approval_requests": (
        "compliance_policy_approval.requested",
        "compliance_policy_approval.approved",
        "compliance_policy_approval.rejected",
        "compliance_policy_approval.cancelled",
    ),
    "compliance_policy_control_links": (
        "compliance_policy.control_linked",
        "compliance_policy.control_unlinked",
    ),
    "vendors": (
        "vendor.created",
        "vendor.updated",
        "vendor.archived",
    ),
    "vendor_assessments": (
        "vendor_assessment.created",
        "vendor_assessment.started",
        "vendor_assessment.completed",
        "vendor_assessment.cancelled",
        "vendor_assessment_question.answered",
    ),
    "vendor_risk_scores": (
        "vendor_risk_score.created",
    ),
    "vendor_control_links": (
        "vendor.control_linked",
        "vendor.control_unlinked",
    ),
    "risk_indicators": (
        "risk_indicator.created",
        "risk_indicator.updated",
        "risk_indicator.recalculated",
        "risk_indicator.archived",
    ),
    "risk_appetite": (
        "risk_appetite.created",
        "risk_appetite.updated",
        "risk_appetite.deactivated",
        "risk_appetite.breach_detected",
    ),
    "control_monitoring_definitions": (
        "control_monitoring_definition.created",
        "control_monitoring_definition.updated",
        "control_monitoring_definition.archived",
        "control_monitoring_result.recorded",
    ),
    "control_monitoring_rules": (
        "control_monitoring_rule.created",
        "control_monitoring_rule.updated",
        "control_monitoring_rule.archived",
        "control_monitoring_rule.evaluated",
    ),
    "control_monitoring_alerts": (
        "control_monitoring_alert.created",
        "control_monitoring_alert.acknowledged",
        "control_monitoring_alert.resolved",
        "control_monitoring_alert.dismissed",
        "control_monitoring_alert.assigned",
    ),
    "control_exceptions": (
        "control_exception.created",
        "control_exception.approved",
        "control_exception.rejected",
        "control_exception.revoked",
        "control_exception.expired",
        "control_exception.approval_step_completed",
    ),
    "common_controls": (
        "common_control.mapping_created",
        "common_control.mapping_updated",
        "common_control.mapping_deactivated",
        "common_control.evidence_coverage_added",
    ),
    "oscal_exports": (
        "oscal_export.job_created",
        "oscal_export.job_completed",
        "oscal_export.job_failed",
    ),
    "technical_controls": (
        "technical_control.agent_registered",
        "technical_control.agent_deregistered",
        "technical_control.rule_created",
        "technical_control.rule_updated",
        "technical_control.rule_deactivated",
        "technical_control.result_ingested",
        "technical_control.result_failed",
    ),
    "employee_attestations": (
        "attestation.campaign_created",
        "attestation.campaign_updated",
        "attestation.campaign_cancelled",
        "attestation.submitted",
        "attestation.user_exempted",
        "attestation.reminder_sent",
        "attestation.bulk_reminder_sent",
        "attestation.expired",
    ),
    "policy_exceptions": (
        "policy_exception.created",
        "policy_exception.updated",
        "policy_exception.withdrawn",
        "policy_exception.approved",
        "policy_exception.rejected",
        "policy_exception.expired",
    ),
    "policy_templates": (
        "policy_template.cloned",
    ),
    "policy_risk_mappings": (
        "policy_risk_mapping.created",
        "policy_risk_mapping.updated",
        "policy_risk_mapping.deleted",
    ),
    "policy_issue_links": (
        "policy_issue_link.created",
        "policy_issue_link.updated",
        "policy_issue_link.deleted",
    ),
    "compliance_deadlines": (
        "compliance_deadline.created",
        "compliance_deadline.updated",
        "compliance_deadline.completed",
        "compliance_deadline.waived",
        "compliance_deadline.cancelled",
        "compliance_deadline.evaluated",
    ),
}

EMAIL_TEMPLATE_SEEDS: list[dict] = [
    {
        "template_key": "invited_user_activation",
        "name": "Invited User Activation",
        "description": "Activation instructions for invited users.",
        "subject_template": "Activate your CompliVibe account",
        "body_text_template": "Hello {{ user_name }},\n\nUse this activation link to set your password: {{ activation_link }}\n\nThis link expires soon.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "activation_link"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "task_assigned",
        "name": "Task Assigned",
        "description": "Notification when a task is assigned.",
        "subject_template": "New task assigned: {{ task_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nA task has been assigned to you: {{ task_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "task_title"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "evidence_requested",
        "name": "Evidence Requested",
        "description": "Request for evidence submission.",
        "subject_template": "Evidence requested: {{ request_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nEvidence is requested for: {{ request_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "request_title"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "control_owner_reminder",
        "name": "Control Owner Reminder",
        "description": "Reminder for control owners.",
        "subject_template": "Reminder: review control {{ control_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nPlease review control: {{ control_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "control_title"],
        "status": "active",
        "version": 1,
    },
]

FRAMEWORK_SEEDS: list[dict] = [
    {
        "code": "EU_AI_ACT",
        "name": "EU AI Act",
        "description": "European Union AI regulation metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "European Union",
        "authority": "European Parliament and Council",
        "version": "2024",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "INDIA_DPDP",
        "name": "India DPDP",
        "description": "India Digital Personal Data Protection Act metadata entry.",
        "category": "Privacy",
        "jurisdiction": "India",
        "authority": "Government of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "SOC2",
        "name": "SOC 2",
        "description": "AICPA SOC 2 trust services criteria metadata entry.",
        "category": "Security Assurance",
        "jurisdiction": "United States",
        "authority": "AICPA",
        "version": "2017",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_27001",
        "name": "ISO 27001",
        "description": "ISO/IEC 27001 information security standard metadata entry.",
        "category": "Security",
        "jurisdiction": "International",
        "authority": "ISO/IEC",
        "version": "2022",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_42001",
        "name": "ISO 42001",
        "description": "ISO/IEC 42001 AI management system standard metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "International",
        "authority": "ISO/IEC",
        "version": "2023",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "NIST_AI_RMF",
        "name": "NIST AI RMF",
        "description": "NIST AI Risk Management Framework metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "United States",
        "authority": "NIST",
        "version": "1.0",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "COLORADO_AI_ACT",
        "name": "Colorado AI Act",
        "description": "Colorado AI Act metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "Colorado, United States",
        "authority": "State of Colorado",
        "version": "2024",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": date(2026, 2, 1),
    },
    {
        "code": "GDPR",
        "name": "GDPR",
        "description": "EU General Data Protection Regulation metadata entry.",
        "category": "Privacy",
        "jurisdiction": "European Union",
        "authority": "European Union",
        "version": "2018",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": date(2018, 5, 25),
    },
]

FRAMEWORK_VERSION_SEEDS: list[dict] = [
    {"framework_code": "EU_AI_ACT", "version_label": "2024", "status": "active", "coverage_level": "metadata_only"},
    {"framework_code": "INDIA_DPDP", "version_label": "2023", "status": "active", "coverage_level": "metadata_only"},
    {"framework_code": "ISO_42001", "version_label": "2023", "status": "active", "coverage_level": "starter"},
    {"framework_code": "NIST_AI_RMF", "version_label": "1.0", "status": "active", "coverage_level": "starter"},
    {"framework_code": "SOC2", "version_label": "2017", "status": "active", "coverage_level": "starter"},
    {"framework_code": "ISO_27001", "version_label": "2022", "status": "active", "coverage_level": "starter"},
    {"framework_code": "COLORADO_AI_ACT", "version_label": "2024", "status": "active", "coverage_level": "metadata_only"},
    {"framework_code": "GDPR", "version_label": "2018", "status": "active", "coverage_level": "starter"},
]

OBLIGATION_SEEDS: list[dict] = [
    {
        "framework_code": "NIST_AI_RMF",
        "reference_code": "GOV-1",
        "title": "Establish AI risk governance roles",
        "description": "Define accountability for AI risk management activities.",
        "plain_language_summary": "Assign people to own AI risk governance.",
        "obligation_type": "governance",
        "jurisdiction": "United States",
        "source_url": None,
        "version": "1.0",
        "status": "active",
        "effective_date": None,
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-ART5",
        "title": "Process personal data lawfully and transparently",
        "description": "Personal data processing must follow lawfulness, fairness, and transparency principles.",
        "plain_language_summary": "Use personal data only on a lawful basis and explain processing clearly.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
]


def _policy_template_content(
    *,
    purpose: str,
    scope: str,
    statement: str,
    responsibilities: str,
    enforcement: str,
    review_cycle: str,
) -> str:
    return (
        "## Purpose\n"
        f"{purpose}\n\n"
        "## Scope\n"
        f"{scope}\n\n"
        "## Policy Statement\n"
        f"{statement}\n\n"
        "## Responsibilities\n"
        f"{responsibilities}\n\n"
        "## Enforcement\n"
        f"{enforcement}\n\n"
        "## Review Cycle\n"
        f"{review_cycle}\n"
    )


POLICY_TEMPLATE_SEEDS: list[dict] = [
    {
        "slug": "acceptable-use",
        "name": "Acceptable Use Policy",
        "description": "Defines acceptable handling of company systems, data, and internet resources.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST"],
        "content": _policy_template_content(
            purpose="Establish clear expectations for safe and lawful use of organizational technology assets.",
            scope="Applies to all employees, contractors, and third parties using organization-managed devices, applications, or networks.",
            statement="Users must access only authorized systems, protect credentials, avoid unapproved software, and use company resources for business purposes unless explicitly permitted.",
            responsibilities="Users protect account secrets and report suspected misuse. Managers ensure team compliance. Security maintains technical safeguards and periodic awareness guidance.",
            enforcement="Violations may result in access revocation, disciplinary action, contract termination, and, where applicable, legal referral.",
            review_cycle="Reviewed at least annually and after major changes to threat landscape, technology stack, or regulatory obligations.",
        ),
        "version": "1.0",
    },
    {
        "slug": "data-retention",
        "name": "Data Retention Policy",
        "description": "Defines retention periods, archival controls, and disposal standards for records.",
        "category": "Privacy",
        "framework_tags": ["GDPR", "HIPAA", "SOC2"],
        "content": _policy_template_content(
            purpose="Ensure records are retained only as long as operational, legal, and contractual obligations require.",
            scope="Covers production databases, backups, file repositories, logs, collaboration content, and vendor-hosted data stores.",
            statement="Data classes must have documented retention durations and disposal methods. Personal data beyond required retention periods must be deleted or anonymized.",
            responsibilities="Data owners define retention schedules. Engineering implements deletion controls. Compliance verifies schedules and exceptions.",
            enforcement="Failure to apply retention or disposal controls may trigger remediation plans, restricted access, and audit findings.",
            review_cycle="Reviewed every 12 months and when legal or contractual retention obligations change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "incident-response",
        "name": "Incident Response Policy",
        "description": "Defines incident classification, triage, containment, and post-incident review requirements.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Provide a repeatable process for identifying, containing, eradicating, and recovering from security incidents.",
            scope="Applies to incidents affecting systems, data, users, third-party services, and business operations.",
            statement="Incidents must be promptly reported, severity-rated, assigned to an incident commander, and tracked through closure with documented timelines and evidence.",
            responsibilities="Security leads response execution. Engineering and IT perform containment and remediation. Legal and leadership coordinate communications when required.",
            enforcement="Unreported incidents or delayed containment actions are treated as control failures and escalated to management.",
            review_cycle="Reviewed after significant incidents and at least annually with tabletop validation.",
        ),
        "version": "1.0",
    },
    {
        "slug": "access-control",
        "name": "Access Control Policy",
        "description": "Defines account lifecycle, least privilege, and privileged access controls.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "HIPAA"],
        "content": _policy_template_content(
            purpose="Prevent unauthorized access and ensure access rights match business need.",
            scope="Applies to identity providers, cloud platforms, SaaS systems, endpoints, and administrative interfaces.",
            statement="Access is granted through approved requests, follows least privilege, requires MFA where supported, and is removed promptly at role change or termination.",
            responsibilities="Managers approve role-based access. IT/Security provision and deprovision accounts. Control owners perform periodic access reviews.",
            enforcement="Non-compliant access grants or stale privileges must be remediated within defined SLA windows.",
            review_cycle="Reviewed quarterly for privileged access controls and annually for full policy maintenance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "change-management",
        "name": "Change Management Policy",
        "description": "Defines risk-based planning, testing, approval, and rollback for production changes.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "ITIL"],
        "content": _policy_template_content(
            purpose="Reduce service disruption and security risk by applying disciplined change governance.",
            scope="Applies to application releases, infrastructure updates, configuration changes, and database migrations.",
            statement="All production changes require documented scope, peer review, test evidence, approval, implementation plan, and rollback plan commensurate with risk.",
            responsibilities="Requesters prepare change records. Approvers verify risk controls. Operators execute and document outcomes.",
            enforcement="Emergency changes require retrospective review; repeated non-compliant changes trigger managerial escalation.",
            review_cycle="Reviewed annually and after major incidents tied to release or configuration processes.",
        ),
        "version": "1.0",
    },
    {
        "slug": "business-continuity",
        "name": "Business Continuity Policy",
        "description": "Defines continuity planning, recovery targets, and crisis response responsibilities.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "NIST"],
        "content": _policy_template_content(
            purpose="Maintain critical operations during disruptive events and recover services within defined targets.",
            scope="Applies to critical systems, workforce continuity, vendor dependencies, and communication workflows.",
            statement="Business continuity plans must define RTO/RPO objectives, alternate procedures, and prioritized recovery order for critical functions.",
            responsibilities="Leadership approves continuity priorities. Technical teams maintain recovery procedures. Owners run periodic exercises and track findings.",
            enforcement="Unaddressed continuity gaps require corrective plans with executive oversight.",
            review_cycle="Reviewed annually and after continuity exercises, major outages, or organizational restructuring.",
        ),
        "version": "1.0",
    },
    {
        "slug": "vendor-management",
        "name": "Vendor Management Policy",
        "description": "Defines lifecycle controls for vendor due diligence, contracting, and monitoring.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "GDPR"],
        "content": _policy_template_content(
            purpose="Manage third-party risk through consistent due diligence, contractual safeguards, and ongoing oversight.",
            scope="Covers software vendors, service providers, contractors, and sub-processors handling company data or operations.",
            statement="Vendors must be risk-classified, assessed before onboarding, and monitored through periodic review of controls, incidents, and contractual commitments.",
            responsibilities="Procurement and business owners coordinate onboarding. Security and privacy teams conduct control assessments. Legal manages contractual clauses.",
            enforcement="High-risk vendors without required controls cannot be onboarded or must have approved remediation exceptions.",
            review_cycle="Reviewed annually and when procurement, legal, or security requirements materially change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "ai-acceptable-use",
        "name": "AI Acceptable Use Policy",
        "description": "Defines approved AI use cases, restrictions, and human oversight requirements.",
        "category": "AI Governance",
        "framework_tags": ["ISO42001", "NIST-AI", "EU-AI-Act"],
        "content": _policy_template_content(
            purpose="Enable responsible AI adoption while managing privacy, security, fairness, and regulatory risk.",
            scope="Applies to internal and external use of generative and predictive AI tools, models, and AI-enabled workflows.",
            statement="AI systems may be used only for approved use cases, with prohibited handling of sensitive data unless controls and legal basis are documented.",
            responsibilities="Users validate outputs and maintain human accountability. Governance owners approve high-impact uses. Security reviews model and data controls.",
            enforcement="Unauthorized AI usage or unsafe data submission can result in immediate access restriction and corrective action requirements.",
            review_cycle="Reviewed every six months due to rapidly changing model capabilities and regulatory guidance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "data-classification",
        "name": "Data Classification Policy",
        "description": "Defines sensitivity classes and required handling controls for each class.",
        "category": "Privacy",
        "framework_tags": ["SOC2", "ISO27001", "GDPR", "HIPAA"],
        "content": _policy_template_content(
            purpose="Apply proportional safeguards based on data sensitivity and impact of unauthorized disclosure or misuse.",
            scope="Applies to structured and unstructured data at rest, in transit, and in use across all business systems.",
            statement="Data must be labeled according to classification tiers with required controls for encryption, sharing, retention, and access management.",
            responsibilities="Data owners classify assets. Engineering enforces controls. Users handle data according to labeling standards.",
            enforcement="Mislabeled or improperly handled data requires immediate remediation and may trigger incident response.",
            review_cycle="Reviewed annually and whenever classification definitions or legal data categories change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "password-management",
        "name": "Password Management Policy",
        "description": "Defines password creation, storage, rotation, and reset controls.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Reduce credential compromise risk through strong authentication hygiene and secure secret handling.",
            scope="Applies to workforce identities, service accounts, administrative accounts, and integrated third-party systems.",
            statement="Passwords must meet complexity and reuse controls, be stored only in approved secret managers, and never be shared through insecure channels.",
            responsibilities="Users maintain secure credentials. IT configures identity controls. Security monitors weak-password and reuse indicators.",
            enforcement="Credential policy violations can result in forced resets, temporary account lockout, and security training requirements.",
            review_cycle="Reviewed at least annually and after changes to identity provider capabilities or relevant standards.",
        ),
        "version": "1.0",
    },
    {
        "slug": "remote-work",
        "name": "Remote Work Security Policy",
        "description": "Defines minimum security controls for remote access and offsite work environments.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001"],
        "content": _policy_template_content(
            purpose="Protect company systems and information when accessed from remote or hybrid work locations.",
            scope="Applies to employees and contractors connecting from home, travel, coworking locations, or other offsite environments.",
            statement="Remote access requires managed devices, secure network practices, MFA, and adherence to physical security and privacy safeguards.",
            responsibilities="Users maintain secure work environments and report suspicious activity. IT enforces endpoint standards and remote access controls.",
            enforcement="Non-compliant remote practices may lead to network access revocation until corrective actions are completed.",
            review_cycle="Reviewed annually and after major changes in remote access tooling or workforce model.",
        ),
        "version": "1.0",
    },
    {
        "slug": "vulnerability-management",
        "name": "Vulnerability Management Policy",
        "description": "Defines scanning cadence, prioritization, remediation SLAs, and exception governance.",
        "category": "Security",
        "framework_tags": ["SOC2", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Identify and remediate vulnerabilities before they can be exploited in production environments.",
            scope="Applies to infrastructure, applications, containers, dependencies, and internet-facing assets.",
            statement="Assets must be scanned on defined cadences, findings triaged by severity and exploitability, and remediation tracked to SLA completion.",
            responsibilities="Security operates vulnerability workflows. Engineering and IT remediate assigned findings. Leadership monitors overdue risk.",
            enforcement="Repeated SLA breaches require escalation and risk acceptance approval by designated authorities.",
            review_cycle="Reviewed semi-annually and after significant vulnerabilities affecting core technology stacks.",
        ),
        "version": "1.0",
    },
    {
        "slug": "privacy-notice",
        "name": "Privacy Notice Policy",
        "description": "Defines disclosure standards for data collection, usage, sharing, and rights handling.",
        "category": "Privacy",
        "framework_tags": ["GDPR", "CCPA", "HIPAA"],
        "content": _policy_template_content(
            purpose="Provide transparent communication of privacy practices to customers, users, and workforce members.",
            scope="Applies to all channels where personal data is collected, processed, transferred, or retained.",
            statement="Privacy notices must accurately describe data categories, purposes, legal bases, sharing practices, retention periods, and rights request channels.",
            responsibilities="Privacy and legal teams maintain notice language. Product owners ensure notices align with implemented data practices.",
            enforcement="Material processing changes require notice updates before launch; non-compliance is escalated to legal and compliance leadership.",
            review_cycle="Reviewed at least annually and before release of new data uses or jurisdiction-specific processing changes.",
        ),
        "version": "1.0",
    },
    {
        "slug": "third-party-risk",
        "name": "Third-Party Risk Management Policy",
        "description": "Defines governance for assessing and monitoring third-party control risk over time.",
        "category": "Compliance",
        "framework_tags": ["SOC2", "ISO27001", "GDPR"],
        "content": _policy_template_content(
            purpose="Maintain ongoing visibility and mitigation of risk introduced by external providers and partners.",
            scope="Applies to all third parties with access to systems, sensitive data, or critical operational processes.",
            statement="Third-party engagements require risk profiling, control evidence review, contractual safeguards, and periodic reassessment aligned to risk tier.",
            responsibilities="Business owners sponsor vendors. Security/compliance perform assessments. Legal enforces contractual requirements and remediation terms.",
            enforcement="Third parties failing critical control requirements may be offboarded or restricted until risk treatment is approved.",
            review_cycle="Reviewed annually and after significant incidents, audit findings, or regulatory updates affecting third-party governance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "secure-development",
        "name": "Secure Development Lifecycle Policy",
        "description": "Defines security activities integrated across design, build, test, and release workflows.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Embed security controls into the software lifecycle to prevent defects and reduce production exposure.",
            scope="Applies to internally developed software, infrastructure-as-code, and release pipelines for production systems.",
            statement="Development must include threat-informed design, secure coding standards, peer review, dependency scanning, and pre-release security validation.",
            responsibilities="Engineering teams execute secure SDLC controls. Security provides standards and tooling. Release owners ensure gating requirements are met.",
            enforcement="Releases that bypass mandatory security gates require documented exception approval and immediate follow-up remediation.",
            review_cycle="Reviewed every 12 months and after significant architecture, tooling, or regulatory changes affecting software assurance.",
        ),
        "version": "1.0",
    },
]


class SeedService:
    @staticmethod
    def ensure_permissions(db: Session) -> dict[str, Permission]:
        existing = {p.key: p for p in db.execute(select(Permission)).scalars().all()}

        for code, description in PERMISSIONS.items():
            if code not in existing:
                permission = Permission(key=code, description=description)
                db.add(permission)
                db.flush()
                existing[code] = permission
        return existing

    @staticmethod
    def ensure_roles_for_organization(db: Session, organization_id: uuid.UUID) -> dict[str, Role]:
        permission_map = SeedService.ensure_permissions(db)

        existing_roles = {
            r.name: r
            for r in db.execute(select(Role).where(Role.organization_id == organization_id)).scalars().all()
        }

        for role_name in ROLE_PERMISSION_MAP:
            if role_name not in existing_roles:
                role = Role(
                    organization_id=organization_id,
                    name=role_name,
                    description=f"{role_name} default role",
                    is_system=True,
                )
                db.add(role)
                db.flush()
                existing_roles[role_name] = role

        for role_name, permission_codes in ROLE_PERMISSION_MAP.items():
            role = existing_roles[role_name]
            current_permission_ids = set(
                db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).scalars().all()
            )
            for code in permission_codes:
                permission = permission_map[code]
                if permission.id not in current_permission_ids:
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        db.flush()
        return existing_roles

    @staticmethod
    def ensure_framework_catalog(db: Session) -> dict[str, Framework]:
        existing_by_code = {f.code: f for f in db.execute(select(Framework)).scalars().all()}

        for payload in FRAMEWORK_SEEDS:
            framework = existing_by_code.get(payload["code"])
            if framework is None:
                framework = Framework(**payload)
                db.add(framework)
                db.flush()
                existing_by_code[payload["code"]] = framework
            else:
                for field, value in payload.items():
                    setattr(framework, field, value)

        db.flush()
        return existing_by_code

    @staticmethod
    def ensure_starter_obligations(db: Session) -> list[Obligation]:
        frameworks = SeedService.ensure_framework_catalog(db)
        existing_keys = {
            (o.framework_id, o.reference_code): o
            for o in db.execute(select(Obligation)).scalars().all()
        }

        created_or_updated: list[Obligation] = []
        for payload in OBLIGATION_SEEDS:
            framework = frameworks[payload["framework_code"]]
            key = (framework.id, payload["reference_code"])
            body = {k: v for k, v in payload.items() if k != "framework_code"}
            body["framework_id"] = framework.id

            obligation = existing_keys.get(key)
            if obligation is None:
                obligation = Obligation(**body)
                db.add(obligation)
                db.flush()
            else:
                for field, value in body.items():
                    setattr(obligation, field, value)

            created_or_updated.append(obligation)

        db.flush()
        return created_or_updated

    @staticmethod
    def ensure_framework_versions(db: Session) -> list[FrameworkVersion]:
        frameworks = SeedService.ensure_framework_catalog(db)
        existing = {
            (row.framework_id, row.version_label): row
            for row in db.execute(select(FrameworkVersion)).scalars().all()
        }
        rows: list[FrameworkVersion] = []
        for payload in FRAMEWORK_VERSION_SEEDS:
            framework = frameworks[payload["framework_code"]]
            key = (framework.id, payload["version_label"])
            row = existing.get(key)
            body = {
                "framework_id": framework.id,
                "version_label": payload["version_label"],
                "status": payload["status"],
                "coverage_level": payload["coverage_level"],
                "source_url": framework.source_url,
                "source_reference": framework.authority,
                "effective_from": framework.effective_date,
                "effective_until": None,
                "notes": "Seeded starter/metadata content pack baseline.",
            }
            if row is None:
                row = FrameworkVersion(**body)
                db.add(row)
                db.flush()
            else:
                for field, value in body.items():
                    setattr(row, field, value)
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_global_email_templates(db: Session) -> list[EmailTemplate]:
        existing = {
            (tpl.organization_id, tpl.template_key, tpl.version): tpl
            for tpl in db.execute(select(EmailTemplate)).scalars().all()
        }
        results: list[EmailTemplate] = []
        for payload in EMAIL_TEMPLATE_SEEDS:
            key = (None, payload["template_key"], payload["version"])
            template = existing.get(key)
            if template is None:
                template = EmailTemplate(
                    organization_id=None,
                    created_by_user_id=None,
                    **payload,
                )
                db.add(template)
                db.flush()
            else:
                for field, value in payload.items():
                    setattr(template, field, value)
            results.append(template)

        db.flush()
        return results

    @staticmethod
    def ensure_policy_templates(db: Session) -> list[PolicyTemplate]:
        existing_by_slug = {row.slug: row for row in db.execute(select(PolicyTemplate)).scalars().all()}
        created: list[PolicyTemplate] = []
        for payload in POLICY_TEMPLATE_SEEDS:
            if payload["slug"] in existing_by_slug:
                created.append(existing_by_slug[payload["slug"]])
                continue

            row = PolicyTemplate(
                slug=payload["slug"],
                name=payload["name"],
                description=payload["description"],
                category=payload["category"],
                framework_tags=list(payload["framework_tags"]),
                content=payload["content"],
                version=payload["version"],
                is_active=True,
            )
            db.add(row)
            db.flush()
            existing_by_slug[row.slug] = row
            created.append(row)

        db.flush()
        return created
