CLASSIFICATION_RULES: dict[tuple[str, str], dict[str, object]] = {
    ("data_loss", "critical"): {
        "category": "privacy_violation",
        "sub_category": "critical data loss",
        "regulatory_implications": ["gdpr_72hr", "dpdp_72hr"],
    },
    ("data_loss", "high"): {
        "category": "privacy_violation",
        "sub_category": "significant data loss",
        "regulatory_implications": ["gdpr_72hr", "dpdp_72hr"],
    },
    ("data_loss", "medium"): {
        "category": "data_corruption",
        "sub_category": "partial data loss",
        "regulatory_implications": [],
    },
    ("unauthorized_access", "critical"): {
        "category": "security_breach",
        "sub_category": "privileged account compromise",
        "regulatory_implications": ["gdpr_72hr", "pci_dss_incident", "dpdp_72hr"],
    },
    ("unauthorized_access", "high"): {
        "category": "unauthorized_access",
        "sub_category": "account compromise",
        "regulatory_implications": ["gdpr_72hr"],
    },
    ("unauthorized_access", "medium"): {
        "category": "unauthorized_access",
        "sub_category": "unauthorized system access",
        "regulatory_implications": [],
    },
    ("security_incident", "critical"): {
        "category": "security_breach",
        "sub_category": "critical security incident",
        "regulatory_implications": ["gdpr_72hr", "pci_dss_incident"],
    },
    ("security_incident", "high"): {
        "category": "security_breach",
        "sub_category": "security incident",
        "regulatory_implications": ["gdpr_72hr"],
    },
    ("security_incident", "medium"): {
        "category": "service_disruption",
        "sub_category": "security-related disruption",
        "regulatory_implications": [],
    },
    ("compliance_violation", "critical"): {
        "category": "regulatory_event",
        "sub_category": "critical compliance failure",
        "regulatory_implications": ["gdpr_72hr"],
    },
    ("compliance_violation", "high"): {
        "category": "regulatory_event",
        "sub_category": "compliance violation",
        "regulatory_implications": [],
    },
    ("vendor_failure", "critical"): {
        "category": "third_party_failure",
        "sub_category": "critical vendor failure",
        "regulatory_implications": ["pci_dss_incident"],
    },
    ("vendor_failure", "high"): {
        "category": "third_party_failure",
        "sub_category": "vendor service failure",
        "regulatory_implications": [],
    },
    ("policy_violation", "critical"): {
        "category": "insider_threat",
        "sub_category": "critical policy breach",
        "regulatory_implications": [],
    },
    ("policy_violation", "high"): {
        "category": "insider_threat",
        "sub_category": "policy violation",
        "regulatory_implications": [],
    },
}

FALLBACK_CLASSIFICATION = {
    "category": "service_disruption",
    "sub_category": "unclassified incident",
    "regulatory_implications": [],
}


class ClassificationEngine:
    @staticmethod
    def classify(issue_type: str, severity: str) -> dict[str, object]:
        return dict(CLASSIFICATION_RULES.get((issue_type, severity), FALLBACK_CLASSIFICATION))
