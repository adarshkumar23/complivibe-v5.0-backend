from __future__ import annotations

from app.models.issue import Issue

REMEDIATION_TEMPLATES: dict[tuple[str, str | None], list[str]] = {
    ("security_incident", "access_control"): [
        "Immediately revoke access credentials for all accounts potentially affected by this incident.",
        "Enable MFA on all privileged accounts and review access logs for unauthorized activity.",
        "Conduct an access review and recertify all user permissions within 72 hours.",
    ],
    ("security_incident", "network_security"): [
        "Isolate affected network segments and block suspicious IP ranges at the firewall.",
        "Review network access logs for lateral movement and document findings in the incident record.",
    ],
    ("security_incident", "vulnerability_management"): [
        "Apply emergency patches to the affected systems and validate patch success before reconnecting.",
        "Run a targeted vulnerability scan on affected systems and document all findings.",
    ],
    ("security_incident", None): [
        "Document all actions taken and preserve logs for forensic review.",
        "Notify relevant stakeholders per the incident response plan.",
        "Update the incident record with timeline and findings within 24 hours.",
    ],
    ("data_loss", "encryption_at_rest"): [
        "Immediately assess what data was exposed and determine if encryption was bypassed or absent.",
        "Enable encryption at rest on all affected storage systems and rotate encryption keys.",
    ],
    ("data_loss", None): [
        "Assess the scope and classify data types affected (personal, financial, health, confidential).",
        "Preserve all relevant logs and backups to support recovery and regulatory reporting.",
        "Notify the privacy/legal team within 2 hours of confirming data loss.",
    ],
    ("compliance_violation", "security_policy"): [
        "Update the security policy to close the gap that led to this violation and communicate changes.",
        "Schedule a policy awareness session for affected teams within 30 days.",
    ],
    ("compliance_violation", None): [
        "Document the specific control or policy that was violated and the circumstances.",
        "Perform a gap assessment to identify other potential violations of the same type.",
    ],
    ("unauthorized_access", "access_control"): [
        "Terminate all active sessions for the affected account and reset credentials immediately.",
        "Review IAM policies and remove excessive permissions discovered during investigation.",
    ],
    ("unauthorized_access", None): [
        "Preserve access logs and timeline for forensic review before making any changes.",
        "Alert the security team and escalate to issues:admin if the access was privileged.",
    ],
    ("policy_violation", None): [
        "Identify the employee and provide immediate coaching on the violated policy.",
        "Review whether the policy requires clarification or additional training materials.",
    ],
    ("vendor_failure", None): [
        "Notify the vendor immediately and document the failure in the vendor risk register.",
        "Assess contract SLA breach and initiate the vendor mitigation workflow.",
    ],
    ("operational_failure", None): [
        "Activate the business continuity plan if the failure impacts critical operations.",
        "Document the failure timeline and root cause in the issue record.",
    ],
    ("custom", None): [
        "Review this issue with the relevant team lead and define remediation steps within 48 hours.",
    ],
}

GENERIC_SUGGESTIONS: list[str] = [
    "Document all facts known about this issue, assign an owner, and set a resolution target date.",
    "Review similar past issues for applicable remediation patterns.",
]


class RemediationEngine:
    @staticmethod
    def _control_category(control) -> str | None:
        # controls table currently has no category field; use None fallback.
        for field_name in ("category", "control_category", "category_tag"):
            if hasattr(control, field_name):
                value = getattr(control, field_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @classmethod
    def resolve_source_key(cls, issue: Issue, linked_controls: list[object]) -> str:
        control_category = cls._control_category(linked_controls[0]) if linked_controls else None
        if (issue.issue_type, control_category) in REMEDIATION_TEMPLATES:
            return f"{issue.issue_type}:{control_category}"
        if (issue.issue_type, None) in REMEDIATION_TEMPLATES:
            return f"{issue.issue_type}:generic"
        return "generic"

    @classmethod
    def generate(cls, issue: Issue, linked_controls: list[object], db=None) -> list[str]:  # noqa: ARG003
        control_category = cls._control_category(linked_controls[0]) if linked_controls else None
        suggestions = REMEDIATION_TEMPLATES.get((issue.issue_type, control_category))
        if suggestions is None:
            suggestions = REMEDIATION_TEMPLATES.get((issue.issue_type, None))
        if suggestions is None:
            suggestions = GENERIC_SUGGESTIONS
        return list(dict.fromkeys(suggestions))
