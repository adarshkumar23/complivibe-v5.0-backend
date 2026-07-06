from __future__ import annotations

# Sources verified July 2026 (official publishers):
# - RBI IT governance/risk/control directions:
#   https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12562
# - RBI outsourcing of IT services directions (cloud/outsourcing control baseline):
#   https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12486
# - SEBI CSCRF:
#   https://www.sebi.gov.in/legal/circulars/aug-2024/cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_85964.html
# - SEBI cloud framework:
#   https://www.sebi.gov.in/legal/circulars/mar-2023/framework-for-adoption-of-cloud-services-by-sebi-regulated-entities-res-_68740.html
# - IRDAI cyber guidelines:
#   https://irdai.gov.in/documents/37343/366029/IRDAI%2BCS%2BGuidelines%2B2023.pdf/81730785-1f51-977b-5a92-d9cfd7eb2cd6?download=true&t=1682401978542&version=1.0
# - CERT-In directions + FAQ:
#   https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf
#   https://www.cert-in.org.in/PDF/FAQs_on_CyberSecurityDirections_May2022.pdf
# - IT Act + amendment text:
#   https://www.indiacode.nic.in/handle/123456789/1999
#   https://www.meity.gov.in/static/uploads/2024/03/IT_amendment_act2008-1_0.pdf
# - MCA compliance timing is statutorily derived from Companies Act sections:
#   https://www.indiacode.nic.in/show-data?actid=AC_CEN_22_29_00008_201318_1517807327856&orderno=99&sectionId=1287&sectionno=96
#   https://www.indiacode.nic.in/show-data?actid=AC_CEN_22_29_00008_201318_1517807327856&orderno=95&sectionId=1283&sectionno=92
#   https://www.indiacode.nic.in/show-data?actid=AC_CEN_22_29_00008_201318_1517807327856&orderno=141
# - DPIIT Startup India requirements:
#   https://www.dpiit.gov.in/static/uploads/2026/02/119e52e2a36f652215a32c3ccc5f9c66.pdf
#   https://www.startupindia.gov.in/content/sih/en/startupgov/startup_recognition_page.html

INDIA_PACK_SECTIONS: dict[str, list[dict[str, int | str]]] = {
    "RBI_IT_GOV": [
        {"code": "RBI-ITGRC-GOV", "title": "IT Governance and Board Oversight", "order": 1},
        {"code": "RBI-ITGRC-CTRL", "title": "Controls and Assurance", "order": 2},
    ],
    "RBI_CLOUD_OUTSOURCING": [
        {"code": "RBI-OUTSCOPE", "title": "Outsourcing Scope and Risk", "order": 1},
        {"code": "RBI-OUTMON", "title": "Monitoring and Exit", "order": 2},
    ],
    "SEBI_CSCRF": [
        {"code": "SEBI-CSCRF-GOV", "title": "Cyber Governance", "order": 1},
        {"code": "SEBI-CSCRF-RES", "title": "Resilience and Monitoring", "order": 2},
    ],
    "SEBI_CLOUD": [
        {"code": "SEBI-CLOUD-RISK", "title": "Cloud Risk and Due Diligence", "order": 1},
        {"code": "SEBI-CLOUD-OPS", "title": "Operations and Control Assurance", "order": 2},
    ],
    "IRDAI_CYBER_2023": [
        {"code": "IRDAI-GOV", "title": "Security Governance", "order": 1},
        {"code": "IRDAI-IR", "title": "Incident Response and Assurance", "order": 2},
    ],
    "CERT_IN_2022": [
        {"code": "CERT-REPORT", "title": "Incident Reporting", "order": 1},
        {"code": "CERT-RETENTION", "title": "Logs and Time Sync", "order": 2},
    ],
    "INDIA_IT_ACT": [
        {"code": "ITA-SEC43A", "title": "Reasonable Security Practices", "order": 1},
        {"code": "ITA-SEC70B", "title": "CERT-In and Incident Coordination", "order": 2},
    ],
    "MCA_COMPLIANCE_CAL": [
        {"code": "MCA-ANNUAL", "title": "Annual Statutory Filing Timeline", "order": 1},
    ],
    "DPIIT_STARTUP": [
        {"code": "DPIIT-ELIG", "title": "Recognition Eligibility", "order": 1},
        {"code": "DPIIT-COMPLIANCE", "title": "Recognition Continuity and Disclosures", "order": 2},
    ],
}

# (reference_code, title, description, section_code, evidence_hints)
INDIA_PACK_OBLIGATIONS: dict[str, list[tuple[str, str, str, str, list[str]]]] = {
    "RBI_IT_GOV": [
        (
            "RBI-ITGRC-01",
            "Board-approved IT and cyber governance framework",
            "Maintain board-approved IT governance, risk management, control, and assurance practices with clear accountability.",
            "RBI-ITGRC-GOV",
            ["board_minutes", "it_governance_policy", "risk_committee_charter"],
        ),
        (
            "RBI-ITGRC-02",
            "Independent assurance over critical IT controls",
            "Run periodic independent assurance over material IT and cyber controls and track remediation to closure.",
            "RBI-ITGRC-CTRL",
            ["internal_audit_reports", "control_test_results", "remediation_tracker"],
        ),
    ],
    "RBI_CLOUD_OUTSOURCING": [
        (
            "RBI-OUT-01",
            "Risk-based due diligence before outsourcing critical IT services",
            "Perform documented due diligence, contract controls, and risk assessment before onboarding outsourced IT or cloud service providers.",
            "RBI-OUTSCOPE",
            ["third_party_risk_assessment", "outsourcing_contracts", "vendor_due_diligence_pack"],
        ),
        (
            "RBI-OUT-02",
            "Ongoing monitoring and exit readiness",
            "Maintain continuous monitoring, concentration risk oversight, and tested exit strategy for critical outsourced services.",
            "RBI-OUTMON",
            ["vendor_monitoring_reports", "exit_strategy", "resilience_test_evidence"],
        ),
    ],
    "SEBI_CSCRF": [
        (
            "SEBI-CSCRF-01",
            "Documented cyber resilience governance",
            "Implement governance, roles, and board-level oversight for cybersecurity and cyber resilience under CSCRF.",
            "SEBI-CSCRF-GOV",
            ["cscrf_policy", "governance_structure", "board_reporting_pack"],
        ),
        (
            "SEBI-CSCRF-02",
            "Continuous detection, response, and recovery capability",
            "Operate threat detection, incident response, and recovery controls with periodic testing and evidence retention.",
            "SEBI-CSCRF-RES",
            ["soc_alert_logs", "incident_response_playbooks", "dr_test_reports"],
        ),
    ],
    "SEBI_CLOUD": [
        (
            "SEBI-CLOUD-01",
            "Cloud adoption risk and legal control baseline",
            "Classify workloads and maintain due diligence, contractual, and data protection controls before cloud adoption.",
            "SEBI-CLOUD-RISK",
            ["cloud_risk_register", "cloud_contract_controls", "data_classification_register"],
        ),
        (
            "SEBI-CLOUD-02",
            "Cloud operations monitoring and auditability",
            "Retain auditability and monitoring for cloud deployments, including security event observability and governance reviews.",
            "SEBI-CLOUD-OPS",
            ["cloud_audit_logs", "cloud_security_monitoring", "periodic_cloud_reviews"],
        ),
    ],
    "IRDAI_CYBER_2023": [
        (
            "IRDAI-CS-01",
            "Insurer and intermediary cyber governance program",
            "Maintain information and cybersecurity governance covering policy, ownership, risk assessment, and control implementation.",
            "IRDAI-GOV",
            ["security_policy", "cyber_risk_assessment", "control_inventory"],
        ),
        (
            "IRDAI-CS-02",
            "Incident management and regulator-aligned reporting",
            "Operate cyber incident response, reporting, and assurance procedures aligned with IRDAI obligations.",
            "IRDAI-IR",
            ["incident_records", "reporting_workflow", "security_audit_reports"],
        ),
    ],
    "CERT_IN_2022": [
        (
            "CERTIN-01",
            "Report cyber incidents within six hours",
            "Report specified cyber incidents to CERT-In within six hours of noticing the incident or being brought to notice.",
            "CERT-REPORT",
            ["incident_reporting_runbook", "certin_submission_records", "incident_timestamps"],
        ),
        (
            "CERTIN-02",
            "Preserve and time-synchronize security logs",
            "Enable synchronized system clocks and retain specified ICT logs for the prescribed retention period.",
            "CERT-RETENTION",
            ["ntp_sync_config", "log_retention_policy", "siem_retention_evidence"],
        ),
    ],
    "INDIA_IT_ACT": [
        (
            "ITACT-01",
            "Implement reasonable security practices for personal data",
            "Apply reasonable security practices and procedures to protect sensitive personal data and information.",
            "ITA-SEC43A",
            ["security_program_docs", "privacy_controls", "risk_treatment_plan"],
        ),
        (
            "ITACT-02",
            "Support lawful CERT-In incident coordination",
            "Maintain incident handling and cooperation controls to support lawful cybersecurity coordination requirements.",
            "ITA-SEC70B",
            ["certin_coordination_records", "incident_communication_log", "legal_notice_handling_sop"],
        ),
    ],
    "MCA_COMPLIANCE_CAL": [
        (
            "MCA-CAL-01",
            "Annual filing calendar based on AGM and statutory windows",
            "Maintain a compliance calendar that captures AGM timeline, annual return filing window, and financial statement filing window.",
            "MCA-ANNUAL",
            ["agm_calendar", "annual_return_filing_tracker", "financial_statement_filing_tracker"],
        ),
    ],
    "DPIIT_STARTUP": [
        (
            "DPIIT-01",
            "Startup recognition eligibility and documentation",
            "Maintain evidence that entity form, age, innovation criteria, and turnover thresholds meet DPIIT recognition requirements.",
            "DPIIT-ELIG",
            ["incorporation_documents", "recognition_application", "innovation_statement"],
        ),
        (
            "DPIIT-02",
            "Ongoing eligibility and disclosure maintenance",
            "Track continuing eligibility and supporting records required to retain startup recognition status.",
            "DPIIT-COMPLIANCE",
            ["annual_eligibility_review", "supporting_disclosures", "recognition_status_tracker"],
        ),
    ],
}

INDIA_PACK_QUESTIONS: dict[str, list[dict[str, int | str]]] = {
    "RBI_IT_GOV": [
        {
            "question_key": "regulated_by_rbi",
            "question_text": "Is your organization a regulated entity under RBI supervision?",
            "help_text": "Use this when banking or NBFC regulatory obligations apply.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "SEBI_CSCRF": [
        {
            "question_key": "regulated_by_sebi",
            "question_text": "Is your organization regulated by SEBI for market operations?",
            "help_text": "CSCRF applies to SEBI-regulated entities.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "IRDAI_CYBER_2023": [
        {
            "question_key": "regulated_by_irdai",
            "question_text": "Is your organization an insurer or intermediary regulated by IRDAI?",
            "help_text": "IRDAI cyber guidelines primarily target regulated insurance entities.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "CERT_IN_2022": [
        {
            "question_key": "operates_digital_systems_in_india",
            "question_text": "Do you operate digital systems or services in India subject to CERT-In directions?",
            "help_text": "Applicable when systems are in scope of CERT-In direction reporting requirements.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "INDIA_IT_ACT": [
        {
            "question_key": "handles_spdi_in_india",
            "question_text": "Do you process sensitive personal data or information in India?",
            "help_text": "This drives IT Act reasonable security practice obligations.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "MCA_COMPLIANCE_CAL": [
        {
            "question_key": "registered_company_india",
            "question_text": "Is the organization incorporated in India under the Companies Act?",
            "help_text": "Used to activate annual statutory filing calendar obligations.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
    "DPIIT_STARTUP": [
        {
            "question_key": "seeking_dpiit_recognition",
            "question_text": "Is the organization applying for or maintaining DPIIT Startup recognition?",
            "help_text": "Used for Startup India eligibility and evidence requirements.",
            "triggers_scope": "all",
            "order_index": 1,
            "answer_type": "boolean",
        },
    ],
}
