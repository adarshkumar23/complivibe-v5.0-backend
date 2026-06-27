import os
from datetime import UTC, datetime

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "templates",
    "email",
)

_env: Environment | None = None


def get_jinja_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=True,
        )
    return _env


class EmailTemplateService:
    def render(
        self,
        template_name: str,
        context: dict,
        org_name: str = "Your Organization",
    ) -> tuple[str, str]:
        env = get_jinja_env()
        ctx = {
            "org_name": org_name,
            "current_year": datetime.now(UTC).year,
            **(context or {}),
        }
        template = env.get_template(template_name)
        html_body = template.render(**ctx)
        subject = str(ctx.get("subject") or "CompliVibe Notification")
        return subject, html_body

    def render_task_assigned(self, task_title, due_date, assigned_by, description, org_name, cta_link=None) -> tuple[str, str]:
        return self.render(
            "task_assigned.html",
            {
                "subject": f"Action Required: {task_title}",
                "task_title": task_title,
                "due_date": due_date,
                "assigned_by": assigned_by,
                "description": description,
                "cta_link": cta_link,
            },
            org_name,
        )

    def render_evidence_expiring(self, evidence_title, expiry_date, control_name, days_remaining, org_name) -> tuple[str, str]:
        return self.render(
            "evidence_expiring.html",
            {
                "subject": f"Evidence Expiring Soon: {evidence_title}",
                "evidence_title": evidence_title,
                "expiry_date": expiry_date,
                "control_name": control_name,
                "days_remaining": days_remaining,
            },
            org_name,
        )

    def render_deadline_approaching(self, deadline_title, due_date, framework_name, days_remaining, org_name) -> tuple[str, str]:
        return self.render(
            "deadline_approaching.html",
            {
                "subject": f"Upcoming Deadline: {deadline_title}",
                "deadline_title": deadline_title,
                "due_date": due_date,
                "framework_name": framework_name,
                "days_remaining": days_remaining,
            },
            org_name,
        )

    def render_audit_finding_raised(self, finding_ref, severity, title, description, target_remediation_date, engagement_title, org_name) -> tuple[str, str]:
        return self.render(
            "audit_finding_raised.html",
            {
                "subject": f"New Audit Finding: {finding_ref}",
                "finding_ref": finding_ref,
                "severity": severity,
                "title": title,
                "description": description,
                "target_remediation_date": target_remediation_date,
                "engagement_title": engagement_title,
            },
            org_name,
        )

    def render_new_obligation_activated(self, obligation_title, framework_name, due_date, owner, org_name) -> tuple[str, str]:
        return self.render(
            "new_obligation_activated.html",
            {
                "subject": f"New Obligation: {obligation_title}",
                "obligation_title": obligation_title,
                "framework_name": framework_name,
                "due_date": due_date,
                "owner": owner,
            },
            org_name,
        )

    def render_sla_breach(self, entity_type, entity_ref, deadline, hours_overdue, owner, org_name) -> tuple[str, str]:
        return self.render(
            "sla_breach.html",
            {
                "subject": f"SLA Breach Alert: {entity_type} {entity_ref}",
                "entity_type": entity_type,
                "entity_ref": entity_ref,
                "deadline": deadline,
                "hours_overdue": hours_overdue,
                "owner": owner,
            },
            org_name,
        )

    def render_dsr_received(self, request_ref, request_type, subject_name, response_deadline, regulatory_framework, org_name) -> tuple[str, str]:
        return self.render(
            "dsr_received.html",
            {
                "subject": f"New Data Subject Request: {request_ref}",
                "request_ref": request_ref,
                "request_type": request_type,
                "subject_name": subject_name,
                "response_deadline": response_deadline,
                "regulatory_framework": regulatory_framework,
            },
            org_name,
        )

    def render_consent_withdrawn(self, activity_name, withdrawal_reason, data_asset_names, org_name) -> tuple[str, str]:
        return self.render(
            "consent_withdrawn.html",
            {
                "subject": f"Consent Withdrawn: {activity_name}",
                "activity_name": activity_name,
                "withdrawal_reason": withdrawal_reason,
                "data_asset_names": data_asset_names,
            },
            org_name,
        )

    def render_risk_escalated(self, risk_title, severity, escalated_by, escalation_reason, org_name) -> tuple[str, str]:
        return self.render(
            "risk_escalated.html",
            {
                "subject": f"Risk Escalated: {risk_title}",
                "risk_title": risk_title,
                "severity": severity,
                "escalated_by": escalated_by,
                "escalation_reason": escalation_reason,
            },
            org_name,
        )

    def render_breach_notification_due(self, breach_type, supervisory_authority, deadline, hours_remaining, org_name) -> tuple[str, str]:
        return self.render(
            "breach_notification_due.html",
            {
                "subject": f"URGENT: Breach Notification Due in {hours_remaining}h",
                "breach_type": breach_type,
                "supervisory_authority": supervisory_authority,
                "deadline": deadline,
                "hours_remaining": hours_remaining,
                "urgent": hours_remaining < 6,
            },
            org_name,
        )
