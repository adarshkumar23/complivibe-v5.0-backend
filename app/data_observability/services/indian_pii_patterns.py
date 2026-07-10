"""Indian PII detectors: Aadhaar (UIDAI 12-digit identity number), PAN (Income Tax
Department 10-character Permanent Account Number), and Indian mobile phone numbers.

These are additive detectors for app.data_observability.services.classification_service's
Tier 2 (Presidio sample) classifier — they do not replace or modify the existing
region-matching/residency logic in app.core.geo, per that logic already having been fixed
in an earlier pass.
"""

import re

AADHAAR_REGEX = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
PAN_REGEX = r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
INDIAN_PHONE_REGEX = r"(?:\+91[\s-]?|0)?[6-9]\d{9}\b"

IN_AADHAAR = "IN_AADHAAR"
IN_PAN = "IN_PAN"
IN_PHONE_NUMBER = "IN_PHONE_NUMBER"


def verhoeff_checksum_valid(number: str) -> bool:
    """Validate a 12-digit Aadhaar number using the Verhoeff checksum algorithm, which
    UIDAI uses for its check digit. Reduces false positives from generic 12-digit strings
    (e.g. arbitrary numeric IDs) matching the Aadhaar format."""
    digits = re.sub(r"[\s-]", "", number)
    if not digits.isdigit() or len(digits) != 12:
        return False

    multiplication_table = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
        (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
        (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
        (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
        (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
        (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
        (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
        (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
        (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    )
    permutation_table = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
        (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
        (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
        (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
        (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
        (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
        (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
    )

    check = 0
    reversed_digits = [int(d) for d in reversed(digits)]
    for i, digit in enumerate(reversed_digits):
        check = multiplication_table[check][permutation_table[i % 8][digit]]
    return check == 0


def pan_format_valid(candidate: str) -> bool:
    return bool(re.fullmatch(PAN_REGEX, candidate.strip().upper()))


def get_custom_recognizers() -> list:
    """Build Presidio PatternRecognizers for Aadhaar/PAN/Indian phone. Returns an empty
    list if presidio_analyzer is not installed, mirroring presidio_loader's own
    optional-dependency fallback."""
    try:
        from presidio_analyzer import Pattern, PatternRecognizer
    except Exception:  # pragma: no cover - optional dependency fallback
        return []

    class AadhaarRecognizer(PatternRecognizer):
        def __init__(self) -> None:
            super().__init__(
                supported_entity=IN_AADHAAR,
                patterns=[Pattern(name="aadhaar_12_digit", regex=AADHAAR_REGEX, score=0.5)],
                context=["aadhaar", "uidai", "aadhar"],
            )

        def validate_result(self, pattern_text: str) -> bool | None:
            return verhoeff_checksum_valid(pattern_text)

    pan_recognizer = PatternRecognizer(
        supported_entity=IN_PAN,
        patterns=[Pattern(name="pan_10_char", regex=PAN_REGEX, score=0.6)],
        context=["pan", "permanent account number", "income tax"],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity=IN_PHONE_NUMBER,
        patterns=[Pattern(name="in_mobile_10_digit", regex=INDIAN_PHONE_REGEX, score=0.4)],
        context=["mobile", "phone", "contact"],
    )

    return [AadhaarRecognizer(), pan_recognizer, phone_recognizer]
