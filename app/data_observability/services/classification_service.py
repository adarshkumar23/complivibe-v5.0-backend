from app.data_observability.services.presidio_loader import get_presidio

CLASSIFICATION_RULES = {
    "personal_data": {
        "keywords": [
            "email",
            "phone",
            "address",
            "name",
            "customer",
            "user",
            "person",
            "contact",
            "dob",
            "date_of_birth",
            "ssn",
            "passport",
            "national_id",
            "aadhaar",
            "aadhar",
            "uidai",
            "mobile",
            "firstname",
            "lastname",
            "surname",
            "gender",
            "pii",
        ],
        "sensitivity_tier": "confidential",
        "base_confidence": 0.70,
    },
    "sensitive_personal_data": {
        "keywords": [
            "health",
            "medical",
            "diagnosis",
            "race",
            "ethnicity",
            "religion",
            "biometric",
            "fingerprint",
            "retina",
            "genetic",
            "sexual_orientation",
            "disability",
            "mental_health",
            "political",
            "union",
            "criminal",
            "conviction",
            "refugee",
        ],
        "sensitivity_tier": "restricted",
        "base_confidence": 0.80,
    },
    "financial_data": {
        "keywords": [
            "credit_card",
            "card_number",
            "iban",
            "account_number",
            "bank",
            "transaction",
            "payment",
            "salary",
            "revenue",
            "invoice",
            "balance",
            "credit",
            "debit",
            "routing",
            "swift",
            "pan",
            "pan_number",
            "pan_card",
            "cvv",
            "financial",
        ],
        "sensitivity_tier": "restricted",
        "base_confidence": 0.75,
    },
    "health_data": {
        "keywords": [
            "patient",
            "diagnosis",
            "prescription",
            "medication",
            "clinical",
            "lab_result",
            "ehr",
            "emr",
            "hipaa",
            "health_record",
            "icd",
            "procedure",
            "treatment",
            "symptom",
        ],
        "sensitivity_tier": "restricted",
        "base_confidence": 0.80,
    },
    "intellectual_property": {
        "keywords": [
            "proprietary",
            "confidential",
            "trade_secret",
            "patent",
            "source_code",
            "algorithm",
            "model_weights",
            "training_data",
            "research",
            "invention",
            "copyright",
            "internal_only",
        ],
        "sensitivity_tier": "confidential",
        "base_confidence": 0.65,
    },
    "operational_data": {
        "keywords": [
            "log",
            "metric",
            "telemetry",
            "event",
            "audit",
            "trace",
            "monitoring",
            "operational",
            "system",
            "infrastructure",
            "config",
        ],
        "sensitivity_tier": "internal",
        "base_confidence": 0.60,
    },
}


def classify_metadata(name: str, description: str | None, column_names: list[str] | None) -> dict:
    combined_text = " ".join(
        filter(
            None,
            [
                name.lower(),
                (description or "").lower(),
                " ".join(col.lower() for col in (column_names or [])),
            ],
        )
    )

    best_match = None
    best_score = 0.0

    for class_type, rule in CLASSIFICATION_RULES.items():
        hits = sum(1 for keyword in rule["keywords"] if keyword in combined_text)
        if hits == 0:
            continue

        score = rule["base_confidence"] + (min(hits, 5) * 0.04)
        score = min(score, 0.99)
        if score > best_score:
            best_score = score
            best_match = {
                "classification_type": class_type,
                "sensitivity_tier": rule["sensitivity_tier"],
                "confidence": round(score, 2),
                "source": "metadata_rules",
                "keyword_hits": hits,
            }

    if best_match is None:
        return {
            "classification_type": "unclassified",
            "sensitivity_tier": None,
            "confidence": 0.0,
            "source": "metadata_rules",
            "keyword_hits": 0,
        }
    return best_match


def _map_entities_to_class(entity_types: list[str]) -> str:
    if any(entity in entity_types for entity in ["MEDICAL_LICENSE", "US_HEALTHCARE_NPI"]):
        return "health_data"
    if any(entity in entity_types for entity in ["CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER", "US_ITIN", "IN_PAN"]):
        return "financial_data"
    if any(
        entity in entity_types
        for entity in [
            "PERSON",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "US_SSN",
            "US_PASSPORT",
            "IP_ADDRESS",
            "DATE_TIME",
            "LOCATION",
            "NRP",
            "IN_AADHAAR",
            "IN_PHONE_NUMBER",
        ]
    ):
        return "personal_data"
    return "unclassified"


def _map_class_to_tier(class_type: str) -> str | None:
    return {
        "health_data": "restricted",
        "financial_data": "restricted",
        "personal_data": "confidential",
        "sensitive_personal_data": "restricted",
    }.get(class_type)


def classify_sample(sample_text: str, language: str = "en") -> dict:
    engine = get_presidio()
    if engine is None:
        return {
            "status": "unavailable",
            "message": "Presidio analyzer not available.",
            "entities": [],
        }

    results = engine.analyze(text=sample_text, language=language)

    entities = []
    for result in results:
        entities.append(
            {
                "entity_type": result.entity_type,
                "score": round(result.score, 3),
                "start": result.start,
                "end": result.end,
            }
        )

    classification_type = _map_entities_to_class([item["entity_type"] for item in entities])
    max_score = max((item["score"] for item in entities), default=0.0)

    return {
        "status": "success",
        "entities": entities,
        "suggested_classification": classification_type,
        "suggested_sensitivity_tier": _map_class_to_tier(classification_type),
        "confidence": round(max_score, 3),
        "source": "presidio_sample",
        "warning": (
            "This result is based on a submitted text sample. "
            "Human review and confirmation is required before classification is applied."
        ),
    }
