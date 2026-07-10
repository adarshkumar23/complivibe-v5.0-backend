from __future__ import annotations

from dataclasses import dataclass

from app.data_observability.services import classification_service
from app.data_observability.services.classification_service import classify_metadata, classify_sample
from app.data_observability.services.indian_pii_patterns import (
    pan_format_valid,
    verhoeff_checksum_valid,
)


@dataclass
class _MockResult:
    entity_type: str
    score: float
    start: int
    end: int


class _MockIndianPIIEngine:
    def __init__(self, entity_type: str) -> None:
        self._entity_type = entity_type

    def analyze(self, text: str, language: str = "en"):
        _ = (text, language)
        return [_MockResult(entity_type=self._entity_type, score=0.9, start=0, end=len(text))]


def test_verhoeff_checksum_matches_reference_wikipedia_example():
    # "2363" is the standard worked example for the Verhoeff algorithm (Wikipedia:
    # Verhoeff algorithm) — "236" with correct check digit "3" passes, "2362" does not.
    assert verhoeff_checksum_valid("2363") is False  # wrong length for our 12-digit Aadhaar check
    assert verhoeff_checksum_valid("123456789012") is False
    assert verhoeff_checksum_valid("not-a-number") is False
    assert verhoeff_checksum_valid("12345") is False
    # A 12-digit number with its correct trailing Verhoeff check digit passes; changing
    # the check digit fails, proving the checksum is actually being enforced (not a stub).
    assert verhoeff_checksum_valid("499118665401") is True
    assert verhoeff_checksum_valid("499118665402") is False


def test_pan_format_valid_matches_standard_pan_shape():
    assert pan_format_valid("ABCDE1234F") is True
    assert pan_format_valid("abcde1234f") is True
    assert pan_format_valid("ABCDE1234") is False
    assert pan_format_valid("1BCDE1234F") is False


def test_classify_metadata_tier1_detects_aadhaar_and_pan_keywords():
    aadhaar_result = classify_metadata("customer_kyc_table", "stores aadhaar and uidai reference", ["aadhaar_number"])
    assert aadhaar_result["classification_type"] == "personal_data"

    pan_result = classify_metadata("tax_records", "stores pan_number for filing", ["pan_number"])
    assert pan_result["classification_type"] == "financial_data"


def test_classify_sample_tier2_maps_indian_entity_types(monkeypatch):
    monkeypatch.setattr(classification_service, "get_presidio", lambda: _MockIndianPIIEngine("IN_AADHAAR"))
    aadhaar_sample = classify_sample("1234 5678 9012")
    assert aadhaar_sample["suggested_classification"] == "personal_data"

    monkeypatch.setattr(classification_service, "get_presidio", lambda: _MockIndianPIIEngine("IN_PAN"))
    pan_sample = classify_sample("ABCDE1234F")
    assert pan_sample["suggested_classification"] == "financial_data"

    monkeypatch.setattr(classification_service, "get_presidio", lambda: _MockIndianPIIEngine("IN_PHONE_NUMBER"))
    phone_sample = classify_sample("9876543210")
    assert phone_sample["suggested_classification"] == "personal_data"
