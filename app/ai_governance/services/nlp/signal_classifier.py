from app.ai_governance.services.nlp.nlp_loader import get_sm

RISK_KEYWORDS = {
    "critical": [
        "production",
        "public",
        "external",
        "health",
        "financial",
        "biometric",
        "gdpr",
    ],
    "high": [
        "staging",
        "internal",
        "employees",
        "customers",
        "personal data",
        "sensitive",
    ],
    "medium": [
        "development",
        "test",
        "demo",
        "pilot",
    ],
}


def classify_signal_severity(description: str) -> str:
    nlp = get_sm()
    doc = nlp(description.lower())
    for severity, keywords in RISK_KEYWORDS.items():
        if any(keyword in doc.text for keyword in keywords):
            return severity
    return "low"
