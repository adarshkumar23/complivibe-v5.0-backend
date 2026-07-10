from __future__ import annotations

CCPA_SECTIONS: list[dict[str, int | str]] = [
    {"code": "CCPA-RIGHTS", "title": "Consumer Rights", "order": 1},
    {"code": "CCPA-BUSINESS", "title": "Business Obligations", "order": 2},
    {"code": "CCPA-SENSITIVE", "title": "Sensitive Personal Information", "order": 3},
]

# (reference_code, title, description, section_code, evidence_hints)
CCPA_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "CCPA-1798.100",
        "Right to Know",
        "Consumers have the right to know what personal information a business collects, uses, and discloses, and businesses must respond within 45 days.",
        "CCPA-RIGHTS",
        ["privacy_policy", "dsar_response_records", "data_inventory"],
    ),
    (
        "CCPA-1798.105",
        "Right to Delete",
        "Consumers can request deletion of personal information collected from them, subject to statutory exceptions, and businesses must respond within 45 days.",
        "CCPA-RIGHTS",
        ["deletion_procedure", "deletion_confirmation_records", "exception_documentation"],
    ),
    (
        "CCPA-1798.106",
        "Right to Correct",
        "Consumers may request correction of inaccurate personal information and businesses must use commercially reasonable efforts.",
        "CCPA-RIGHTS",
        ["correction_procedure", "correction_response_records"],
    ),
    (
        "CCPA-1798.110",
        "Right to Know — Categories",
        "Consumers may request categories of personal information collected, sources, purposes, and categories sold or disclosed.",
        "CCPA-RIGHTS",
        ["privacy_notice", "data_category_mapping"],
    ),
    (
        "CCPA-1798.115",
        "Right to Know — Sale/Disclosure",
        "Consumers may request disclosure of categories of personal information sold or disclosed for business purposes and recipient categories.",
        "CCPA-RIGHTS",
        ["third_party_disclosure_register", "sale_disclosure_log"],
    ),
    (
        "CCPA-1798.120",
        "Right to Opt-Out of Sale",
        "Consumers have the right to opt out of sale or sharing of personal information and businesses should process opt-out requests promptly.",
        "CCPA-RIGHTS",
        ["do_not_sell_page", "opt_out_mechanism", "opt_out_records"],
    ),
    (
        "CCPA-1798.121",
        "Right to Limit Sensitive PI Use",
        "Consumers may limit use and disclosure of sensitive personal information to necessary service purposes.",
        "CCPA-RIGHTS",
        ["sensitive_pi_use_policy", "limit_request_records"],
    ),
    (
        "CCPA-1798.125",
        "Non-Discrimination",
        "Businesses must not discriminate against consumers for exercising CCPA rights.",
        "CCPA-RIGHTS",
        ["non_discrimination_policy", "consumer_rights_training"],
    ),
    (
        "CCPA-1798.100-b",
        "Privacy Policy Disclosures",
        "Businesses must maintain and publish disclosures about categories, purposes, rights, and request channels.",
        "CCPA-BUSINESS",
        ["published_privacy_policy", "policy_review_records", "policy_update_log"],
    ),
    (
        "CCPA-1798.130",
        "Methods for Submitting Requests",
        "Businesses must provide designated request submission methods, such as web forms and telephone mechanisms where applicable.",
        "CCPA-BUSINESS",
        ["consumer_request_methods", "website_request_form"],
    ),
    (
        "CCPA-1798.135",
        "Do Not Sell/Share Links",
        "Businesses that sell or share PI must provide a clear and conspicuous opt-out link.",
        "CCPA-BUSINESS",
        ["homepage_opt_out_link", "link_placement_screenshot"],
    ),
    (
        "CCPA-1798.150",
        "Data Security",
        "Businesses must implement and maintain reasonable security procedures appropriate to the nature of personal information.",
        "CCPA-BUSINESS",
        ["security_policy", "security_assessment_records", "encryption_evidence"],
    ),
    (
        "CCPA-SPI-1",
        "Sensitive PI Categories Defined",
        "Sensitive PI categories include identifiers and protected characteristics such as precise geolocation, health data, and biometric data used for identification.",
        "CCPA-SENSITIVE",
        ["data_inventory", "sensitive_pi_classification"],
    ),
    (
        "CCPA-SPI-2",
        "Sensitive PI Processing Limits",
        "Sensitive PI use must be limited to reasonably necessary purposes unless additional use is authorized.",
        "CCPA-SENSITIVE",
        ["sensitive_pi_use_policy", "purpose_limitation_controls"],
    ),
    (
        "CCPA-SPI-3",
        "Sensitive PI Disclosure to Third Parties",
        "Businesses must disclose sensitive PI sharing and provide mechanisms to limit such sharing.",
        "CCPA-SENSITIVE",
        ["third_party_disclosure_notice", "sensitive_pi_sharing_controls"],
    ),
]

CCPA_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "california_business",
        "question_text": "Does your organization collect personal information of California residents?",
        "help_text": "",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "meets_threshold",
        "question_text": "Does your organization meet at least one CCPA threshold?",
        "help_text": (
            "CCPA applies if: (1) annual gross revenue > $25M, OR (2) annually buys/sells/shares personal "
            "information of 100,000+ consumers or households, OR (3) derives 50%+ of annual revenue from "
            "selling/sharing personal information."
        ),
        "triggers_scope": "all",
        "order_index": 2,
        "answer_type": "boolean",
    },
    {
        "question_key": "sells_shares_pi",
        "question_text": "Does your organization sell or share personal information with third parties?",
        "help_text": "If yes, opt-out mechanism and 'Do Not Sell' link are required.",
        "triggers_scope": "partial",
        "order_index": 3,
        "answer_type": "boolean",
    },
]

DPDP_SECTIONS: list[dict[str, int | str]] = [
    {"code": "DPDP-DF", "title": "Data Fiduciary Obligations", "order": 1},
    {"code": "DPDP-DP", "title": "Data Principal Rights", "order": 2},
    {"code": "DPDP-SDF", "title": "Significant Data Fiduciary", "order": 3},
    {"code": "DPDP-XBDR", "title": "Cross-Border Data Restrictions", "order": 4},
]


# NOTE: DPDP_OBLIGATIONS is retained only because historical migration
# alembic/versions/0156_india_dpdp_complete.py imports it to replay its one-time data
# seed byte-for-byte. The live/idempotent seeder (SeedService.ensure_dpdp_framework)
# no longer uses this list — it uses the consolidated, more current DPDP_2025_RULES_OBLIGATIONS
# in app/services/framework_seed_data_phase1.py instead. Do not add new callers of this list;
# do not delete it without first rewriting migration 0156 to inline its own snapshot of this data.
DPDP_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "DPDP-S4",
        "Grounds for processing digital personal data",
        "Data Principals' personal data may be processed for lawful purposes with valid consent or recognized legitimate uses.",
        "DPDP-DF",
        ["consent_records", "legitimate_use_documentation", "processing_purpose_register"],
    ),
    (
        "DPDP-S5",
        "Notice to Data Principal",
        "Before obtaining consent, Data Fiduciaries must provide clear notice of data sought, purpose, rights, and grievance channels.",
        "DPDP-DF",
        ["consent_notice", "privacy_policy", "complaint_mechanism"],
    ),
    (
        "DPDP-S6",
        "Consent requirements",
        "Consent must be free, specific, informed, unconditional, and unambiguous, with a clear affirmative action and withdrawal option.",
        "DPDP-DF",
        ["consent_records", "withdrawal_mechanism", "consent_audit_trail"],
    ),
    (
        "DPDP-S8-1",
        "Data Principal rights — access",
        "Data Fiduciaries must provide summaries of personal data processing upon valid request.",
        "DPDP-DF",
        ["data_access_procedure", "access_response_records"],
    ),
    (
        "DPDP-S8-2",
        "Data Principal rights — correction and erasure",
        "Data Principals can request correction, completion, updating, and erasure when no longer necessary for purpose.",
        "DPDP-DF",
        ["correction_erasure_procedure", "dsrrecords"],
    ),
    (
        "DPDP-S8-4",
        "Data Principal rights — grievance redressal",
        "Data Fiduciaries must establish and operate grievance redressal mechanisms within prescribed timelines.",
        "DPDP-DF",
        ["grievance_mechanism", "complaint_response_records"],
    ),
    (
        "DPDP-S8-7",
        "Data Principal rights — nominate",
        "Data Principals may nominate another person to exercise rights in events such as death or incapacity.",
        "DPDP-DF",
        ["nomination_process", "nomination_records"],
    ),
    (
        "DPDP-S9",
        "Processing of children's data",
        "For children, Data Fiduciaries must obtain verifiable parental or lawful guardian consent.",
        "DPDP-DF",
        ["parental_consent_procedure", "age_verification_evidence"],
    ),
    (
        "DPDP-S10",
        "Processing of data of persons with disability",
        "Consent for certain persons with disability may be provided through lawful guardians per applicable law.",
        "DPDP-DF",
        ["guardian_consent_process", "guardian_authorization_records"],
    ),
    (
        "DPDP-S11",
        "Duties of Data Fiduciaries",
        "Data Fiduciaries must ensure data accuracy, apply security safeguards, and notify relevant authorities and affected individuals of breaches.",
        "DPDP-DF",
        ["data_quality_procedure", "security_safeguards_documentation", "breach_notification_records"],
    ),
    (
        "DPDP-S12",
        "Retention",
        "Personal data should not be retained beyond necessary purpose or legal requirements and should be erased thereafter.",
        "DPDP-DF",
        ["retention_policy", "data_erasure_records"],
    ),
    (
        "DPDP-DP-1",
        "Right to information about processing",
        "Data Principals can obtain information about processing of their personal data.",
        "DPDP-DP",
        ["information_request_process", "dp_information_responses"],
    ),
    (
        "DPDP-DP-2",
        "Right to correction and erasure",
        "Data Principals may request correction, completion, updating, and erasure of personal data.",
        "DPDP-DP",
        ["correction_erasure_requests", "request_resolution_logs"],
    ),
    (
        "DPDP-DP-3",
        "Right to grievance redressal",
        "Data Principals are entitled to grievance redressal by Data Fiduciaries within required timelines.",
        "DPDP-DP",
        ["grievance_register", "resolution_timelines"],
    ),
    (
        "DPDP-DP-4",
        "Right to nominate",
        "Data Principals may nominate another individual to act on their behalf where legally permitted.",
        "DPDP-DP",
        ["nominee_records", "rights_delegation_procedure"],
    ),
    (
        "DPDP-SDF-1",
        "Data Protection Officer",
        "Significant Data Fiduciaries must appoint a DPO based in India to represent the fiduciary and handle grievances.",
        "DPDP-SDF",
        ["dpo_appointment_letter", "dpo_contact_information"],
    ),
    (
        "DPDP-SDF-2",
        "Data Auditor",
        "Significant Data Fiduciaries must undergo periodic independent data audits.",
        "DPDP-SDF",
        ["data_audit_report", "auditor_appointment"],
    ),
    (
        "DPDP-SDF-3",
        "Algorithmic accountability",
        "SDFs using algorithmic systems should perform periodic impact assessments for potential harms to Data Principals.",
        "DPDP-SDF",
        ["ai_impact_assessment", "algorithmic_review_records"],
    ),
    (
        "DPDP-S16-1",
        "Restriction on transfer of data outside India",
        "Cross-border transfers may be restricted to approved countries or territories notified by the government.",
        "DPDP-XBDR",
        ["transfer_mapping", "permitted_country_list", "transfer_safeguard_documentation"],
    ),
    (
        "DPDP-S16-2",
        "Data localization for sensitive categories",
        "Certain sensitive categories may require storage or processing localization within India.",
        "DPDP-XBDR",
        ["data_localization_evidence", "storage_location_documentation"],
    ),
]

DPDP_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "processes_indian_data",
        "question_text": "Does your organization process digital personal data of Indian residents?",
        "help_text": "",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "is_sdf",
        "question_text": "Has your organization been designated as a Significant Data Fiduciary by the Central Government of India?",
        "help_text": (
            "Significant Data Fiduciaries have additional obligations including appointing a DPO based in India, "
            "annual data audits, and algorithmic accountability assessments."
        ),
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

DPDP_GDPR_MAPPINGS: list[tuple[str, str, str]] = [
    ("DPDP-S4", "GDPR-OBL-02", "equivalent"),
    ("DPDP-S5-R3", "GDPR-OBL-03", "equivalent"),
    ("DPDP-S6-R4", "GDPR-OBL-10", "related"),
    ("DPDP-S11", "GDPR-OBL-04", "equivalent"),
    ("DPDP-S12-R13", "GDPR-OBL-05", "equivalent"),
    ("DPDP-S11", "GDPR-OBL-07", "equivalent"),
    ("DPDP-RULE-PROCESSOR", "GDPR-OBL-09", "related"),
]
