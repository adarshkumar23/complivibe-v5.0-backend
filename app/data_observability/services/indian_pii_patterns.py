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


# Confidence scores mirror the Presidio PatternRecognizer scores below, so a caller sees
# comparable confidences whether detection came from Presidio or this built-in path.
_AADHAAR_SCORE = 0.5
_PAN_SCORE = 0.6
_PHONE_SCORE = 0.4


def detect_indian_pii_entities(text: str) -> list[dict]:
    """Presidio-free detection of Indian PII (Aadhaar, PAN, Indian mobile) in a text sample.

    Reuses the SAME regexes and the SAME Verhoeff / PAN validators as the Presidio custom
    recognizers in ``get_custom_recognizers`` — this is the always-available fallback used
    when ``presidio_analyzer`` is not installed, so Indian PII detection degrades gracefully
    to a real result instead of returning nothing.

    Returns a list of ``{"entity_type", "score", "start", "end"}`` dicts (the same shape the
    Presidio path emits). An Aadhaar candidate is only emitted when its Verhoeff check digit
    validates — matching ``AadhaarRecognizer.validate_result`` — so a merely 12-digit string
    is not a false positive. Overlapping matches are de-duplicated preferring the longer span,
    so a 10-digit phone substring inside a 12-digit Aadhaar is not double-counted.
    """
    candidates: list[dict] = []

    for match in re.finditer(AADHAAR_REGEX, text):
        if verhoeff_checksum_valid(match.group()):
            candidates.append(
                {"entity_type": IN_AADHAAR, "score": _AADHAAR_SCORE, "start": match.start(), "end": match.end()}
            )

    for match in re.finditer(PAN_REGEX, text):
        candidates.append({"entity_type": IN_PAN, "score": _PAN_SCORE, "start": match.start(), "end": match.end()})

    for match in re.finditer(INDIAN_PHONE_REGEX, text):
        candidates.append(
            {"entity_type": IN_PHONE_NUMBER, "score": _PHONE_SCORE, "start": match.start(), "end": match.end()}
        )

    # Prefer the earliest-starting, then longest, span; drop any candidate fully contained
    # within an already-accepted span (e.g. a phone match inside an Aadhaar number).
    candidates.sort(key=lambda c: (c["start"], -(c["end"] - c["start"])))
    accepted: list[dict] = []
    for cand in candidates:
        if any(cand["start"] >= acc["start"] and cand["end"] <= acc["end"] for acc in accepted):
            continue
        accepted.append(cand)
    return accepted


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
