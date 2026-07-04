WHERE_WE_STAND = (
    "Your organization currently meets {coverage_pct}%"
    " of its {framework_name} obligations. The overall"
    " compliance score is {score}%{delta_clause}."
)

NEEDS_ATTENTION = (
    "{open_risk_count} risk(s) remain open, the most"
    " critical being: {top_risk_title} (severity:"
    " {top_risk_severity}). {critical_issue_count}"
    " critical issue(s) require immediate attention."
)

ACHIEVEMENTS = (
    "This quarter, {certifications_gained} new"
    " certification(s) were obtained and"
    " {risks_closed} risk(s) were closed."
)

UPCOMING = (
    "{deadline_count} compliance deadline(s) are"
    " due within the next 90 days. The nearest is:"
    " {nearest_deadline_title} on {nearest_due_date}."
)

CAVEAT = (
    "This report is generated from CompliVibe"
    " compliance data as of {report_date}. It is"
    " not legal advice and should not be relied upon"
    " as a substitute for professional legal or"
    " compliance counsel."
)

NO_OPEN_RISKS = "No high-severity risks currently open."

ISSUES_ONLY_ATTENTION = (
    "No open risks currently, but {high_severity_issue_count}"
    " high-severity issue(s) require attention, the most"
    " urgent being: {top_issue_title} (severity: {top_issue_severity})."
)
NO_ACHIEVEMENTS = "No new certifications or risk closures recorded this quarter."
NO_DEADLINES = "No compliance deadlines due within the next 90 days."
