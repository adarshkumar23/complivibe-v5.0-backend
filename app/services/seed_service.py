import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.models.framework import Framework
from app.models.framework_version import FrameworkVersion
from app.models.obligation import Obligation
from app.models.permission import Permission
from app.models.policy_template import PolicyTemplate
from app.models.issue_sla_policy import IssueSLAPolicy
from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.questionnaire_template_section import QuestionnaireTemplateSection
from app.models.eu_act_annex_mapping import EUActAnnexMapping
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.data_access_anomaly_rule import DataAccessAnomalyRule

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
    "audit:read": "Read audit engagements and PBC evidence request lists",
    "audit:write": "Create and manage audit engagements and PBC evidence request lists",
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
    "vendor:read": "Read vendor questionnaire templates, responses, and scoring rules",
    "vendor:write": "Create and manage vendor questionnaire templates, responses, and scoring rules",
    "monitoring:read": "Read control monitoring definitions and results",
    "monitoring:write": "Create and manage control monitoring definitions and results",
    "compliance_deadlines:read": "Read compliance deadlines and calendar events",
    "compliance_deadlines:write": "Create and manage compliance deadlines and calendar events",
    "risk_appetite:read": "Read risk appetite thresholds and breach summaries",
    "risk_appetite:write": "Create and manage risk appetite thresholds",
    "risk_indicators:read": "Read key risk indicators",
    "risk_indicators:write": "Create and manage key risk indicators",
    "issues:read": "Read formal issue log records and dashboards",
    "issues:write": "Create and manage formal issue log records",
    "issues:admin": "Manage organization-level issue module settings",
    "escalations:read": "Read escalation policies and escalation events",
    "escalations:write": "Create and manage escalation policies",
    "ai_governance:read": "Read AI governance dashboard summary",
    "ai_governance:write": "Create and update AI governance reviews and classifications",
    "ai_governance:approve": "Approve or reject AI governance reviews and conditional approvals",
    "integrations:read": "Read MLOps integrations and sync logs",
    "integrations:write": "Create and manage MLOps integrations and sync operations",
    "data:read": "Read data observability assets and classification summaries",
    "data:write": "Create and manage data observability assets and classifications",
    "privacy:read": "Read privacy processing activities and Article 30 RoPA reports",
    "privacy:write": "Create and manage privacy processing activities and RoPA links",
    "privacy:approve": "Approve and reject privacy governance workflows such as DPIAs",
    "scheduler:admin": "Read scheduler jobs and execution run logs",
    "drafts:use": "Create, review, and apply AI-assisted drafting outputs",
    "webhooks:read": "Read outbound webhook endpoints and delivery history",
    "webhooks:write": "Create and manage outbound webhook endpoints and test emissions",
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
        "audit:read",
        "audit:write",
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
        "vendor:read",
        "vendor:write",
        "monitoring:read",
        "monitoring:write",
        "compliance_deadlines:read",
        "compliance_deadlines:write",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "issues:write",
        "escalations:read",
        "escalations:write",
        "ai_governance:read",
        "ai_governance:write",
        "integrations:read",
        "integrations:write",
        "data:read",
        "data:write",
        "privacy:read",
        "privacy:write",
        "drafts:use",
        "webhooks:read",
        "webhooks:write",
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
        "audit:read",
        "governance_override:read",
        "governance_override:approve",
        "governance_override_template:read",
        "framework_content:review",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "escalations:read",
        "ai_governance:read",
        "integrations:read",
        "data:read",
        "privacy:read",
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
        "audit:read",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "escalations:read",
        "ai_governance:read",
        "integrations:read",
        "data:read",
        "privacy:read",
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
        "audit:read",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "vendors:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "escalations:read",
        "integrations:read",
        "data:read",
        "privacy:read",
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
    "vendor_questionnaires": (
        "questionnaire_template.created",
        "questionnaire_template.cloned",
        "questionnaire_template.deleted",
        "questionnaire_response.created",
        "questionnaire_response.answer_submitted",
        "questionnaire_response.bulk_answers_submitted",
        "questionnaire_response.status_transitioned",
        "questionnaire_response.score_computed",
        "scoring_rule.created",
        "scoring_rule.updated",
        "scoring_rule.deactivated",
    ),
    "inbound_questionnaires": (
        "inbound_questionnaire.session_created",
        "inbound_questionnaire.item_added",
        "inbound_questionnaire.items_bulk_added",
        "inbound_questionnaire.item_drafted",
        "inbound_questionnaire.all_drafted",
        "inbound_questionnaire.item_approved",
        "inbound_questionnaire.item_edited",
        "inbound_questionnaire.item_rejected",
        "inbound_questionnaire.item_sent",
        "inbound_questionnaire.session_completed",
    ),
    "subprocessors": (
        "subprocessor.created",
        "subprocessor.updated",
        "subprocessor.dpa_status_updated",
        "subprocessor.reviewed",
        "subprocessor.deleted",
        "subprocessor.transfer_added",
        "subprocessor.dpa_expiry_swept",
    ),
    "customer_commitments": (
        "customer_commitment.created",
        "customer_commitment.updated",
        "customer_commitment.triggered",
        "customer_commitment.fulfilled",
        "customer_commitment.waived",
        "customer_commitment.deleted",
        "customer_commitment.sweep_processed",
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
    "issues": (
        "issue.created",
        "issue.updated",
        "issue.assigned",
        "issue.transitioned",
        "issue.promoted_from_alert",
        "issue.promoted_from_finding",
        "issue.deleted",
        "issue_settings.updated",
        "rca.created",
        "rca.updated",
        "rca.reviewed",
        "sla_policy.updated",
        "sla.response_breached",
        "sla.resolution_breached",
    ),
    "escalations": (
        "escalation_policy.created",
        "escalation_policy.updated",
        "escalation_policy.deactivated",
        "escalation.fired",
    ),
    "breach_notifications": (
        "breach_notification.created",
        "breach_notification.regulator_notified",
        "breach_notification.subjects_notified",
        "breach_notification.closed",
        "breach_notification.deadline_warned",
    ),
    "webhooks": (
        "webhook_endpoint.created",
        "webhook_endpoint.updated",
        "webhook_endpoint.deactivated",
        "webhook_endpoint.deleted",
        "webhook.emitted",
    ),
    "offboarding": (
        "offboarding.validated",
        "offboarding.executed",
        "offboarding.risks_reassigned",
        "offboarding.controls_reassigned",
        "offboarding.tasks_reassigned",
        "offboarding.policies_reassigned",
        "offboarding.vendors_reassigned",
        "offboarding.audit_engagements_reassigned",
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
    "audit_engagements": (
        "audit_engagement.created",
        "audit_engagement.updated",
        "audit_engagement.status_transitioned",
        "audit_engagement.deleted",
    ),
    "pbc_items": (
        "pbc_item.created",
        "pbc_item.submitted",
        "pbc_item.accepted",
        "pbc_item.rejected",
        "pbc_item.overdue_marked",
        "pbc_item.deleted",
    ),
    "auditor_portal": (
        "auditor_portal.invitation_created",
        "auditor_portal.invitation_revoked",
        "auditor_portal.access",
    ),
    "audit_findings": (
        "audit_finding.created",
        "audit_finding.updated",
        "audit_finding.status_transitioned",
        "audit_finding.risk_linked",
        "audit_finding.bulk_transitioned",
        "audit_finding.deleted",
    ),
    "audit_schedules": (
        "audit_schedule.created",
        "audit_schedule.updated",
        "audit_schedule.status_changed",
        "audit_schedule.engagement_linked",
        "audit_schedule.reminder_processed",
    ),
    "evidence_packages": (
        "evidence_package.created",
        "evidence_package.item_added",
        "evidence_package.item_removed",
        "evidence_package.assembled",
        "evidence_package.exported",
        "evidence_package.archived",
        "evidence_package.deleted",
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
        "coverage_level": "starter",
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

DATA_ACCESS_DEFAULT_RULES: list[dict] = [
    {
        "rule_type": "access_count_spike",
        "rule_config": {"count": 100, "window_minutes": 10},
    },
    {
        "rule_type": "after_hours_access",
        "rule_config": {"business_start": "09:00", "business_end": "18:00", "timezone": "UTC"},
    },
    {
        "rule_type": "mass_download",
        "rule_config": {"bytes": 5368709120},
    },
    {
        "rule_type": "failed_access_spike",
        "rule_config": {"count": 20, "window_minutes": 5},
    },
]

ISO42001_OBLIGATIONS: list[tuple[str, str]] = [
    ("4.1", "Understanding the organization and its context for AI"),
    ("4.2", "Understanding the needs and expectations of interested parties for AI"),
    ("4.3", "Determining the scope of the AI management system"),
    ("4.4", "AI management system establishment and maintenance"),
    ("5.1", "Leadership commitment to AI management system"),
    ("5.2", "AI policy establishment and communication"),
    ("5.3", "Organizational roles, responsibilities and authorities for AI"),
    ("6.1", "Actions to address risks and opportunities in AI"),
    ("6.1.2", "AI impact assessment process"),
    ("6.2", "AI objectives and planning to achieve them"),
    ("7.1", "Resources for AI management system"),
    ("7.2", "AI-specific competence requirements"),
    ("7.3", "Awareness of AI policies and objectives"),
    ("7.4", "Communication regarding AI management"),
    ("7.5", "Documented information management for AI"),
    ("8.1", "Operational planning and control for AI systems"),
    ("8.2", "AI risk assessment process"),
    ("8.3", "AI risk treatment process"),
    ("8.4", "AI system impact assessment"),
    ("8.5", "Data management for AI systems"),
    ("8.6", "Responsible AI development practices"),
    ("8.7", "AI system verification and validation"),
    ("8.8", "AI system documentation"),
    ("8.9", "AI system deployment controls"),
    ("9.1", "Monitoring, measurement, analysis and evaluation of AI"),
    ("9.2", "Internal audit of AI management system"),
    ("9.3", "Management review of AI management system"),
    ("10.1", "Continual improvement of AI management system"),
    ("10.2", "Nonconformity and corrective action for AI"),
    ("10.3", "Innovation and learning in AI management"),
]

NIST_AI_RMF_SUBCATEGORIES: dict[str, list[tuple[str, str]]] = {
    "GOVERN": [
        ("GOVERN-1.1", "Policies, processes, procedures, and practices for AI risk management"),
        ("GOVERN-1.2", "AI risk tolerance and appetite"),
        ("GOVERN-1.3", "Organizational roles and responsibilities for AI risk"),
        ("GOVERN-1.4", "AI risk management integration into enterprise risk"),
        ("GOVERN-1.5", "Processes for ongoing AI risk identification and management"),
        ("GOVERN-1.6", "Organizational teams are committed to AI risk management"),
        ("GOVERN-1.7", "AI risk processes across the AI lifecycle"),
        ("GOVERN-2.1", "Scientific knowledge about AI risk and impacts"),
        ("GOVERN-2.2", "AI risk accountability and organizational practices"),
        ("GOVERN-4.1", "Organizational teams understand their roles in AI risk"),
        ("GOVERN-4.2", "Risk awareness and information sharing practices"),
        ("GOVERN-5.1", "Policies for engagement with AI community"),
        ("GOVERN-5.2", "Mechanisms to incorporate affected groups' feedback"),
        ("GOVERN-6.1", "Policies for AI risk in supply chain"),
        ("GOVERN-6.2", "AI risk tracking in procurement and partnerships"),
    ],
    "MAP": [
        ("MAP-1.1", "Intended purpose and context documented"),
        ("MAP-1.2", "AI classification applicable to use case"),
        ("MAP-1.3", "Scientific findings on AI risks"),
        ("MAP-1.4", "Risks and benefits to stakeholders"),
        ("MAP-1.5", "Organizational risk tolerance applied"),
        ("MAP-1.6", "Practices for involving affected groups"),
        ("MAP-2.1", "Scientific disciplines relevant to the AI system"),
        ("MAP-2.2", "Scientific output and basis for decisions"),
        ("MAP-2.3", "AI system benefits and limitations documented"),
        ("MAP-3.1", "AI context established and documented"),
        ("MAP-3.2", "AI benefits and limitations communicated"),
        ("MAP-3.5", "Risks to affected groups identified"),
        ("MAP-5.1", "Likelihood and magnitude of AI risks identified"),
        ("MAP-5.2", "Practices for risk prioritization"),
    ],
    "MEASURE": [
        ("MEASURE-1.1", "AI risk measurement methods identified"),
        ("MEASURE-1.3", "Internal AI risk experts and methods"),
        ("MEASURE-2.1", "Test sets developed for evaluating AI risks"),
        ("MEASURE-2.2", "AI system metrics established"),
        ("MEASURE-2.3", "AI system testing and evaluation documented"),
        ("MEASURE-2.5", "AI system performance evaluated"),
        ("MEASURE-2.6", "Evaluations are documented and interpretable"),
        ("MEASURE-2.7", "AI system security and resilience tested"),
        ("MEASURE-2.8", "Fairness and bias evaluations performed"),
        ("MEASURE-2.9", "Privacy risks evaluated"),
        ("MEASURE-2.10", "AI system privacy tested"),
        ("MEASURE-2.11", "Fairness and bias evaluation documented"),
        ("MEASURE-3.1", "Risk tracking mechanisms established"),
        ("MEASURE-3.3", "Feedback mechanisms established"),
    ],
    "MANAGE": [
        ("MANAGE-1.1", "Risks managed and prioritized"),
        ("MANAGE-1.2", "Treatment plans developed for high risks"),
        ("MANAGE-1.3", "Responses to identified AI risks"),
        ("MANAGE-2.1", "Resources allocated for AI risk management"),
        ("MANAGE-2.2", "AI risk treatment plans maintained"),
        ("MANAGE-2.4", "Mechanisms for timely response to AI risks"),
        ("MANAGE-3.1", "AI incident response plans established"),
        ("MANAGE-3.2", "Affected parties informed of incidents"),
        ("MANAGE-4.1", "Post-deployment AI risks monitored"),
        ("MANAGE-4.2", "Feedback mechanisms for post-deployment"),
    ],
}

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
    *[
        {
            "framework_code": "ISO_42001",
            "reference_code": reference_code,
            "title": title,
            "description": title,
            "plain_language_summary": title,
            "obligation_type": "governance",
            "jurisdiction": "International",
            "source_url": None,
            "version": "2023",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        for reference_code, title in ISO42001_OBLIGATIONS
    ],
    *[
        {
            "framework_code": "NIST_AI_RMF",
            "reference_code": reference_code,
            "title": title,
            "description": title,
            "plain_language_summary": title,
            "obligation_type": function_name.lower(),
            "jurisdiction": "United States",
            "source_url": None,
            "version": "1.0",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        for function_name, subcategories in NIST_AI_RMF_SUBCATEGORIES.items()
        for reference_code, title in subcategories
    ],
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

QUESTIONNAIRE_TEMPLATE_SEEDS: list[dict] = [
    {
        "template_type": "sig_lite",
        "name": "SIG Lite",
        "version": "2023",
        "description": "Standardized Information Gathering Lite questionnaire for vendor security assessments.",
        "sections": [
            {
                "title": "Risk Management",
                "order_index": 0,
                "questions": [
                    {
                        "question_text": "Does the organization have a formally documented risk management program?",
                        "question_type": "yes_no",
                        "category_tag": "risk_management",
                        "framework_ref": "SOC2 CC3.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is a formal risk assessment conducted at least annually or when significant changes occur?",
                        "question_type": "yes_no",
                        "category_tag": "risk_assessment",
                        "framework_ref": "ISO27001 A.8.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Security Policy",
                "order_index": 1,
                "questions": [
                    {
                        "question_text": "Is there a documented and board-approved information security policy?",
                        "question_type": "yes_no",
                        "category_tag": "security_policy",
                        "framework_ref": "ISO27001 A.5.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is the security policy reviewed and updated at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "security_policy_review",
                        "framework_ref": "SOC2 CC2.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Access Control",
                "order_index": 2,
                "questions": [
                    {
                        "question_text": "Is multi-factor authentication (MFA) enforced for all privileged and remote access?",
                        "question_type": "yes_no",
                        "category_tag": "access_control_mfa",
                        "framework_ref": "SOC2 CC6.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is access reviewed and recertified at least semi-annually?",
                        "question_type": "yes_no",
                        "category_tag": "access_review",
                        "framework_ref": "ISO27001 A.9.2.5",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is role-based access control (RBAC) implemented across all critical systems?",
                        "question_type": "yes_no",
                        "category_tag": "rbac",
                        "framework_ref": "SOC2 CC6.3",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Vulnerability Management",
                "order_index": 3,
                "questions": [
                    {
                        "question_text": "Is automated vulnerability scanning conducted at least monthly on all production systems?",
                        "question_type": "yes_no",
                        "category_tag": "vulnerability_management",
                        "framework_ref": "SOC2 CC7.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is penetration testing conducted at least annually by an independent third party?",
                        "question_type": "yes_no",
                        "category_tag": "penetration_testing",
                        "framework_ref": "SOC2 CC4.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are critical security patches applied within 30 days of release?",
                        "question_type": "yes_no",
                        "category_tag": "patch_management",
                        "framework_ref": "ISO27001 A.12.6.1",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Data Protection",
                "order_index": 4,
                "questions": [
                    {
                        "question_text": "Is sensitive and customer data encrypted at rest using AES-256 or equivalent?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_at_rest",
                        "framework_ref": "SOC2 CC6.7",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is data in transit protected using TLS 1.2 or higher?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_in_transit",
                        "framework_ref": "SOC2 CC6.7",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is there a formal data retention and disposal policy?",
                        "question_type": "yes_no",
                        "category_tag": "data_retention",
                        "framework_ref": "ISO27001 A.8.3",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Incident Management",
                "order_index": 5,
                "questions": [
                    {
                        "question_text": "Is there a documented and tested incident response plan?",
                        "question_type": "yes_no",
                        "category_tag": "incident_response",
                        "framework_ref": "SOC2 CC7.3",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Can security incidents affecting customer data be notified within 72 hours?",
                        "question_type": "yes_no",
                        "category_tag": "breach_notification",
                        "framework_ref": "GDPR Art. 33",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Business Continuity",
                "order_index": 6,
                "questions": [
                    {
                        "question_text": "Is there a documented business continuity plan (BCP) tested at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "business_continuity",
                        "framework_ref": "ISO27001 A.17.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are defined Recovery Time Objectives (RTOs) and Recovery Point Objectives (RPOs) documented?",
                        "question_type": "yes_no",
                        "category_tag": "rto_rpo",
                        "framework_ref": "SOC2 A1.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Network Security",
                "order_index": 7,
                "questions": [
                    {
                        "question_text": "Is network segmentation implemented to isolate sensitive and production systems?",
                        "question_type": "yes_no",
                        "category_tag": "network_segmentation",
                        "framework_ref": "SOC2 CC6.6",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Privacy",
                "order_index": 8,
                "questions": [
                    {
                        "question_text": "Is there a formal privacy policy covering data subject rights and GDPR obligations?",
                        "question_type": "yes_no",
                        "category_tag": "privacy_policy",
                        "framework_ref": "GDPR Art. 13",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is a Data Protection Officer (DPO) or privacy lead designated for privacy program oversight?",
                        "question_type": "yes_no",
                        "category_tag": "privacy_governance",
                        "framework_ref": "GDPR Art. 37",
                        "expected_answer": "Yes",
                    },
                ],
            },
        ],
    },
    {
        "template_type": "caiq",
        "name": "CAIQ v4",
        "version": "4.0",
        "description": "Cloud Security Alliance Consensus Assessment Initiative Questionnaire for cloud vendor risk assessment.",
        "sections": [
            {
                "title": "Governance, Risk & Compliance",
                "order_index": 0,
                "questions": [
                    {
                        "question_text": "Do you have a documented information security management system (ISMS)?",
                        "question_type": "yes_no",
                        "category_tag": "information_security_program",
                        "framework_ref": "ISO27001 A.5.1",
                        "help_text": "CAIQ GRC-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you perform formal risk assessments that include cloud-specific risks at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "risk_assessment",
                        "framework_ref": "ISO27001 A.8.2",
                        "help_text": "CAIQ GRC-06",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Identity & Access Management",
                "order_index": 1,
                "questions": [
                    {
                        "question_text": "Do you enforce MFA for all user and administrative access to cloud services?",
                        "question_type": "yes_no",
                        "category_tag": "access_control_mfa",
                        "framework_ref": "SOC2 CC6.1",
                        "help_text": "CAIQ IAM-02",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you implement least privilege and RBAC for all cloud resources and APIs?",
                        "question_type": "yes_no",
                        "category_tag": "rbac",
                        "framework_ref": "SOC2 CC6.3",
                        "help_text": "CAIQ IAM-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Data Security & Privacy",
                "order_index": 2,
                "questions": [
                    {
                        "question_text": "Do you encrypt all customer data at rest within cloud storage services?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_at_rest",
                        "framework_ref": "SOC2 CC6.7",
                        "help_text": "CAIQ DSP-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you have a formal data classification and handling policy?",
                        "question_type": "yes_no",
                        "category_tag": "data_classification",
                        "framework_ref": "ISO27001 A.8.2",
                        "help_text": "CAIQ DSP-07",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are data processing agreements (DPAs) in place with all subprocessors?",
                        "question_type": "yes_no",
                        "category_tag": "subprocessor_dpa",
                        "framework_ref": "GDPR Art. 28",
                        "help_text": "CAIQ DSP-17",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Cryptography & Key Management",
                "order_index": 3,
                "questions": [
                    {
                        "question_text": "Do you use AES-256 or equivalent approved encryption algorithms for all data protection?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_algorithms",
                        "framework_ref": "NIST SP 800-57",
                        "help_text": "CAIQ CEK-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are cryptographic keys rotated at least annually or upon suspected compromise?",
                        "question_type": "yes_no",
                        "category_tag": "key_management",
                        "framework_ref": "SOC2 CC6.7",
                        "help_text": "CAIQ CEK-03",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Logging & Monitoring",
                "order_index": 4,
                "questions": [
                    {
                        "question_text": "Do you maintain comprehensive audit logs for all privileged user actions?",
                        "question_type": "yes_no",
                        "category_tag": "audit_logging",
                        "framework_ref": "SOC2 CC7.2",
                        "help_text": "CAIQ LOG-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are security logs retained for a minimum of 12 months?",
                        "question_type": "yes_no",
                        "category_tag": "log_retention",
                        "framework_ref": "ISO27001 A.12.4.1",
                        "help_text": "CAIQ LOG-05",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Human Resources Security",
                "order_index": 5,
                "questions": [
                    {
                        "question_text": "Do you conduct background verification checks on all employees with access to customer data?",
                        "question_type": "yes_no",
                        "category_tag": "background_checks",
                        "framework_ref": "ISO27001 A.7.1",
                        "help_text": "CAIQ HRS-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is annual security awareness training mandatory for all personnel?",
                        "question_type": "yes_no",
                        "category_tag": "security_training",
                        "framework_ref": "ISO27001 A.7.2.2",
                        "help_text": "CAIQ HRS-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Threat & Vulnerability Management",
                "order_index": 6,
                "questions": [
                    {
                        "question_text": "Do you conduct automated vulnerability scanning at least monthly?",
                        "question_type": "yes_no",
                        "category_tag": "vulnerability_management",
                        "framework_ref": "SOC2 CC7.1",
                        "help_text": "CAIQ TVM-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you conduct annual penetration testing by a qualified independent third party?",
                        "question_type": "yes_no",
                        "category_tag": "penetration_testing",
                        "framework_ref": "SOC2 CC4.1",
                        "help_text": "CAIQ TVM-07",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Application Security",
                "order_index": 7,
                "questions": [
                    {
                        "question_text": "Do you perform automated static code analysis (SAST) on all production code releases?",
                        "question_type": "yes_no",
                        "category_tag": "code_review",
                        "framework_ref": "SOC2 CC8.1",
                        "help_text": "CAIQ AIS-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you apply OWASP Top 10 mitigations in your software development process?",
                        "question_type": "yes_no",
                        "category_tag": "owasp",
                        "framework_ref": "ISO27001 A.14.2.1",
                        "help_text": "CAIQ AIS-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Business Continuity",
                "order_index": 8,
                "questions": [
                    {
                        "question_text": "Is a documented and tested BCP in place covering cloud service disruption scenarios?",
                        "question_type": "yes_no",
                        "category_tag": "business_continuity",
                        "framework_ref": "ISO27001 A.17.1",
                        "help_text": "CAIQ BCR-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are RTOs and RPOs defined and tested for all critical cloud services?",
                        "question_type": "yes_no",
                        "category_tag": "rto_rpo",
                        "framework_ref": "SOC2 A1.2",
                        "help_text": "CAIQ BCR-09",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Incident Management",
                "order_index": 9,
                "questions": [
                    {
                        "question_text": "Can you notify affected customers of security incidents within 72 hours?",
                        "question_type": "yes_no",
                        "category_tag": "breach_notification",
                        "framework_ref": "GDPR Art. 33",
                        "help_text": "CAIQ SEF-05",
                        "expected_answer": "Yes",
                    },
                ],
            },
        ],
    },
]

QUESTIONNAIRE_HIGH_IMPACT_RULES: dict[str, dict[str, str | int]] = {
    "penetration_testing": {
        "score_delta": 20,
        "rule_name": "Missing annual pen test",
        "rationale": "Lack of annual penetration testing leaves undetected vulnerabilities unaddressed.",
    },
    "encryption_at_rest": {
        "score_delta": 25,
        "rule_name": "No encryption at rest",
        "rationale": "Customer data unencrypted at rest represents a critical data exposure risk.",
    },
    "access_control_mfa": {
        "score_delta": 20,
        "rule_name": "No MFA enforced",
        "rationale": "Absence of MFA significantly increases risk of unauthorized account access.",
    },
    "incident_response": {
        "score_delta": 15,
        "rule_name": "No incident response plan",
        "rationale": "Absence of an IRP increases dwell time and breach impact.",
    },
    "breach_notification": {
        "score_delta": 20,
        "rule_name": "Cannot notify within 72hrs",
        "rationale": "Failure to notify within 72 hours violates GDPR Article 33.",
    },
    "information_security_program": {
        "score_delta": 15,
        "rule_name": "No security program",
        "rationale": "Lack of a formal security program weakens governance and control oversight.",
    },
    "security_policy": {
        "score_delta": 15,
        "rule_name": "No security program",
        "rationale": "Lack of a formal security program weakens governance and control oversight.",
    },
}

ANNEX_III_SECTORS: list[dict[str, object]] = [
    {
        "ref": "III.1",
        "type": "annex_iii",
        "sector": "Biometric identification and categorisation",
        "description": "AI systems intended for biometric identification or categorisation of natural persons, including facial recognition.",
        "articles": ["Art. 6", "Art. 10", "Art. 13"],
    },
    {
        "ref": "III.2",
        "type": "annex_iii",
        "sector": "Critical infrastructure management",
        "description": "AI systems as safety components in management and operation of critical infrastructure (road traffic, water, gas, heating, electricity).",
        "articles": ["Art. 6", "Art. 9"],
    },
    {
        "ref": "III.3",
        "type": "annex_iii",
        "sector": "Education and vocational training",
        "description": "AI systems determining access to educational institutions, evaluating learning outcomes, monitoring student behaviour.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
    {
        "ref": "III.4",
        "type": "annex_iii",
        "sector": "Employment and workers management",
        "description": "AI systems for recruitment, promotion, termination, task allocation and monitoring of employees.",
        "articles": ["Art. 6", "Art. 9", "Art. 14"],
    },
    {
        "ref": "III.5",
        "type": "annex_iii",
        "sector": "Access to essential services",
        "description": "AI systems evaluating eligibility for essential public services including healthcare, housing, creditworthiness.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
    {
        "ref": "III.6",
        "type": "annex_iii",
        "sector": "Law enforcement",
        "description": "AI systems for risk assessment, polygraphs, evaluation of evidence reliability, crime prediction, profiling.",
        "articles": ["Art. 6", "Art. 10"],
    },
    {
        "ref": "III.7",
        "type": "annex_iii",
        "sector": "Migration, asylum and border control",
        "description": "AI systems for risk assessment, lie detection, examination of applications, monitoring for illegal border crossings.",
        "articles": ["Art. 6", "Art. 9"],
    },
    {
        "ref": "III.8",
        "type": "annex_iii",
        "sector": "Administration of justice",
        "description": "AI systems assisting courts in researching, interpreting facts/law, applying law to concrete sets of facts.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
]


class SeedService:
    ISSUE_SLA_DEFAULTS: tuple[tuple[str, int, int], ...] = (
        ("critical", 1, 24),
        ("high", 4, 72),
        ("medium", 24, 168),
        ("low", 72, 720),
    )

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
    def ensure_default_data_access_anomaly_rules(db: Session, organization_id: uuid.UUID, created_by: uuid.UUID) -> list[DataAccessAnomalyRule]:
        rows: list[DataAccessAnomalyRule] = []
        existing = {
            row.rule_type: row
            for row in db.execute(
                select(DataAccessAnomalyRule).where(
                    DataAccessAnomalyRule.organization_id == organization_id,
                    DataAccessAnomalyRule.data_asset_id.is_(None),
                    DataAccessAnomalyRule.deleted_at.is_(None),
                )
            ).scalars().all()
        }
        for payload in DATA_ACCESS_DEFAULT_RULES:
            if payload["rule_type"] in existing:
                rows.append(existing[payload["rule_type"]])
                continue
            now = datetime.now(UTC)
            row = DataAccessAnomalyRule(
                organization_id=organization_id,
                data_asset_id=None,
                rule_type=payload["rule_type"],
                rule_config=payload["rule_config"],
                is_active=True,
                created_by=created_by,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            db.add(row)
            db.flush()
            rows.append(row)
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

    @staticmethod
    def ensure_questionnaire_templates(db: Session) -> list[QuestionnaireTemplate]:
        existing_templates = {
            row.template_type: row
            for row in db.execute(
                select(QuestionnaireTemplate).where(
                    QuestionnaireTemplate.organization_id.is_(None),
                    QuestionnaireTemplate.is_system_template.is_(True),
                )
            ).scalars().all()
        }
        seeded: list[QuestionnaireTemplate] = []

        for template_seed in QUESTIONNAIRE_TEMPLATE_SEEDS:
            row = existing_templates.get(template_seed["template_type"])
            if row is None:
                row = QuestionnaireTemplate(
                    organization_id=None,
                    template_type=template_seed["template_type"],
                    name=template_seed["name"],
                    version=template_seed["version"],
                    description=template_seed["description"],
                    is_system_template=True,
                    is_active=True,
                    created_by=None,
                )
                db.add(row)
                db.flush()
                existing_templates[template_seed["template_type"]] = row
            else:
                row.name = template_seed["name"]
                row.version = template_seed["version"]
                row.description = template_seed["description"]
                row.is_system_template = True
                row.is_active = True

            section_map = {
                (section.title, section.order_index): section
                for section in db.execute(
                    select(QuestionnaireTemplateSection).where(
                        QuestionnaireTemplateSection.template_id == row.id,
                    )
                ).scalars().all()
            }
            for section_seed in template_seed["sections"]:
                section_key = (section_seed["title"], int(section_seed["order_index"]))
                section = section_map.get(section_key)
                if section is None:
                    section = QuestionnaireTemplateSection(
                        template_id=row.id,
                        title=section_seed["title"],
                        description=section_seed.get("description"),
                        order_index=int(section_seed["order_index"]),
                    )
                    db.add(section)
                    db.flush()
                    section_map[section_key] = section

                question_map = {
                    (question.question_text, question.order_index): question
                    for question in db.execute(
                        select(QuestionnaireTemplateQuestion).where(
                            QuestionnaireTemplateQuestion.template_id == row.id,
                            QuestionnaireTemplateQuestion.section_id == section.id,
                        )
                    ).scalars().all()
                }
                for q_idx, question_seed in enumerate(section_seed["questions"]):
                    question_key = (question_seed["question_text"], q_idx)
                    question = question_map.get(question_key)
                    if question is None:
                        question = QuestionnaireTemplateQuestion(
                            template_id=row.id,
                            section_id=section.id,
                            question_text=question_seed["question_text"],
                            question_type=question_seed["question_type"],
                            category_tag=question_seed["category_tag"],
                            framework_ref=question_seed.get("framework_ref"),
                            allowed_values=question_seed.get("allowed_values"),
                            expected_answer=question_seed.get("expected_answer"),
                            is_required=bool(question_seed.get("is_required", True)),
                            order_index=q_idx,
                            help_text=question_seed.get("help_text"),
                        )
                        db.add(question)
                        db.flush()
                    else:
                        question.question_type = question_seed["question_type"]
                        question.category_tag = question_seed["category_tag"]
                        question.framework_ref = question_seed.get("framework_ref")
                        question.allowed_values = question_seed.get("allowed_values")
                        question.expected_answer = question_seed.get("expected_answer")
                        question.is_required = bool(question_seed.get("is_required", True))
                        question.help_text = question_seed.get("help_text")
                        question.order_index = q_idx
                        question.section_id = section.id

            seeded.append(row)

        db.flush()
        return seeded

    @staticmethod
    def ensure_questionnaire_scoring_rules(db: Session) -> list[QuestionnaireScoringRule]:
        templates = SeedService.ensure_questionnaire_templates(db)
        template_ids = [row.id for row in templates]
        if not template_ids:
            return []

        questions = db.execute(
            select(QuestionnaireTemplateQuestion).where(QuestionnaireTemplateQuestion.template_id.in_(template_ids))
        ).scalars().all()
        existing_rules = {
            (row.organization_id, row.question_id, row.condition_operator, row.condition_value): row
            for row in db.execute(
                select(QuestionnaireScoringRule).where(QuestionnaireScoringRule.organization_id.is_(None))
            ).scalars().all()
        }
        seeded: list[QuestionnaireScoringRule] = []

        for question in questions:
            if question.question_type != "yes_no":
                continue
            if (question.expected_answer or "").strip().lower() != "yes":
                continue

            no_override = QUESTIONNAIRE_HIGH_IMPACT_RULES.get(question.category_tag)
            no_rule_name = "Control expectation not met"
            no_rationale = "The answer indicates the expected control is not in place."
            no_delta = 15
            if no_override is not None:
                no_rule_name = str(no_override["rule_name"])
                no_rationale = str(no_override["rationale"])
                no_delta = int(no_override["score_delta"])

            rule_specs = [
                ("eq", "No", no_delta, no_rule_name, no_rationale),
                (
                    "eq",
                    "Yes",
                    -5,
                    "Control expectation met",
                    "The answer indicates expected control coverage is in place.",
                ),
            ]
            for operator, value, delta, name, rationale in rule_specs:
                key = (None, question.id, operator, value)
                row = existing_rules.get(key)
                if row is None:
                    row = QuestionnaireScoringRule(
                        organization_id=None,
                        template_id=question.template_id,
                        question_id=question.id,
                        rule_name=name,
                        condition_operator=operator,
                        condition_value=value,
                        score_delta=delta,
                        rationale=rationale,
                        is_active=True,
                    )
                    db.add(row)
                    db.flush()
                    existing_rules[key] = row
                else:
                    row.template_id = question.template_id
                    row.rule_name = name
                    row.score_delta = delta
                    row.rationale = rationale
                    row.is_active = True
                seeded.append(row)

        db.flush()
        return seeded

    @staticmethod
    def ensure_issue_sla_policies(db: Session, organization_id: uuid.UUID) -> list[IssueSLAPolicy]:
        existing = {
            row.severity: row
            for row in db.execute(
                select(IssueSLAPolicy).where(IssueSLAPolicy.organization_id == organization_id)
            ).scalars().all()
        }
        seeded: list[IssueSLAPolicy] = []
        for severity, response_hours, resolution_hours in SeedService.ISSUE_SLA_DEFAULTS:
            row = existing.get(severity)
            if row is None:
                row = IssueSLAPolicy(
                    organization_id=organization_id,
                    severity=severity,
                    response_sla_hours=response_hours,
                    resolution_sla_hours=resolution_hours,
                )
                db.add(row)
                db.flush()
            seeded.append(row)
        db.flush()
        return seeded

    @staticmethod
    def ensure_eu_act_annex_mappings(db: Session) -> list[EUActAnnexMapping]:
        existing = {
            row.annex_ref: row
            for row in db.execute(select(EUActAnnexMapping)).scalars().all()
        }
        seeded: list[EUActAnnexMapping] = []
        for item in ANNEX_III_SECTORS:
            ref = str(item["ref"])
            row = existing.get(ref)
            if row is None:
                row = EUActAnnexMapping(
                    annex_ref=ref,
                    annex_type=str(item["type"]),
                    sector=str(item["sector"]),
                    description=str(item["description"]),
                    article_refs=list(item["articles"]),
                    is_active=True,
                )
                db.add(row)
                db.flush()
            else:
                row.annex_type = str(item["type"])
                row.sector = str(item["sector"])
                row.description = str(item["description"])
                row.article_refs = list(item["articles"])
                row.is_active = True
            seeded.append(row)
        db.flush()
        return seeded
