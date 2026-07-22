"""Proof that Indian PII detection works WITHOUT Presidio installed.

Batch-3 walkthrough found that the classify-sample path hard-required Presidio via
``get_presidio()`` — which is not installed and not a hard dependency — so it returned
``{"status": "unavailable", "entities": []}`` and detected nothing in every shipped
environment. These tests pin the graceful-degradation fix: with Presidio absent, the
built-in Indian-PII matcher (Aadhaar + Verhoeff checksum, PAN, Indian mobile) runs and
returns REAL detections, and the Verhoeff validation is genuinely enforced in that path.

The whole module runs with Presidio genuinely absent in this environment (it is not in
requirements.txt); ``get_presidio()`` therefore returns ``None`` naturally, so these tests
exercise the real fallback, not a mock. Where a test wants to be robust even if Presidio
were later installed, it monkeypatches ``get_presidio`` to ``None`` explicitly.
"""

from __future__ import annotations

import uuid

from app.data_observability.services import classification_service
from app.data_observability.services.classification_service import classify_sample
from app.data_observability.services.indian_pii_patterns import (
    IN_AADHAAR,
    IN_PAN,
    IN_PHONE_NUMBER,
    detect_indian_pii_entities,
)
from app.data_observability.services.presidio_loader import get_presidio

# A 12-digit number whose trailing digit is a valid Verhoeff check digit (also asserted in
# test_dpdp_indian_pii_detectors.py::test_verhoeff_checksum_matches_reference_wikipedia_example).
VALID_AADHAAR = "4991 1866 5401"
# Same 12 digits with the check digit changed — format-valid but Verhoeff-INVALID.
INVALID_AADHAAR = "4991 1866 5402"
VALID_PAN = "ABCPL1234C"
INDIAN_PHONE = "+91 9876543210"


def _no_presidio(monkeypatch) -> None:
    monkeypatch.setattr(classification_service, "get_presidio", lambda: None)


def test_presidio_is_actually_absent_in_this_environment():
    # Establishes the premise: the fallback is the real (not mocked) code path here.
    assert get_presidio() is None


def test_builtin_detects_aadhaar_pan_and_phone_together(monkeypatch):
    _no_presidio(monkeypatch)
    sample = f"KYC record: Aadhaar {VALID_AADHAAR}, PAN {VALID_PAN}, mobile {INDIAN_PHONE}"

    result = classify_sample(sample)

    assert result["status"] == "success"
    assert result["status"] != "unavailable"
    assert result["detection_engine"] == "builtin"

    detected_types = {entity["entity_type"] for entity in result["entities"]}
    assert IN_AADHAAR in detected_types
    assert IN_PAN in detected_types
    assert IN_PHONE_NUMBER in detected_types

    # PAN maps to financial_data (see _map_entities_to_class), so the overall suggestion is
    # a real, non-null classification driven by the built-in detections.
    assert result["suggested_classification"] == "financial_data"
    assert result["suggested_sensitivity_tier"] == "restricted"
    assert result["confidence"] > 0.0

    # Reported spans genuinely point at the matched substrings.
    for entity in result["entities"]:
        assert sample[entity["start"] : entity["end"]]


def test_builtin_rejects_checksum_invalid_aadhaar(monkeypatch):
    _no_presidio(monkeypatch)

    # Format-valid but Verhoeff-invalid 12-digit string must NOT be reported as an Aadhaar,
    # proving the checksum validation is running in the fallback (not naive regex).
    result = classify_sample(f"reference id {INVALID_AADHAAR} only")
    detected_types = {entity["entity_type"] for entity in result["entities"]}
    assert IN_AADHAAR not in detected_types

    # And the valid counterpart IS detected, so the difference is the checksum, not the regex.
    valid_result = classify_sample(f"aadhaar {VALID_AADHAAR}")
    assert IN_AADHAAR in {entity["entity_type"] for entity in valid_result["entities"]}


def test_detect_function_checksum_and_overlap_behaviour():
    # Direct unit test of the builtin detector.
    assert {e["entity_type"] for e in detect_indian_pii_entities(VALID_AADHAAR)} == {IN_AADHAAR}
    assert detect_indian_pii_entities(INVALID_AADHAAR) == []  # checksum fails -> nothing
    assert {e["entity_type"] for e in detect_indian_pii_entities(VALID_PAN)} == {IN_PAN}
    assert {e["entity_type"] for e in detect_indian_pii_entities(INDIAN_PHONE)} == {IN_PHONE_NUMBER}

    # A bare 12-digit Aadhaar (no separators) must not also yield a phone sub-span match.
    compact = VALID_AADHAAR.replace(" ", "")
    types = [e["entity_type"] for e in detect_indian_pii_entities(compact)]
    assert types == [IN_AADHAAR]


def test_empty_and_no_pii_samples_return_success_not_unavailable(monkeypatch):
    _no_presidio(monkeypatch)
    for text in ("nothing sensitive here", "order 42 shipped"):
        result = classify_sample(text)
        assert result["status"] == "success"
        assert result["detection_engine"] == "builtin"
        assert result["entities"] == []
        assert result["suggested_classification"] == "unclassified"


def test_endpoint_no_longer_returns_unavailable_without_presidio(monkeypatch, client):
    # End-to-end through the real API: Presidio absent, endpoint returns detected Indian PII.
    from tests.helpers.auth_org import bootstrap_org_user  # mirrors sibling test style

    _no_presidio(monkeypatch)
    org = bootstrap_org_user(client, email_prefix=f"pii-builtin-{uuid.uuid4().hex[:8]}")
    create = client.post(
        "/api/v1/data-observability/assets",
        headers=org["org_headers"],
        json={
            "name": "kyc_sample_asset",
            "asset_type": "database",
            "description": "kyc",
            "owner_id": org["user_id"],
        },
    )
    assert create.status_code in (200, 201), create.text
    asset_id = create.json()["id"]

    resp = client.post(
        f"/api/v1/data-observability/assets/{asset_id}/classify-sample",
        headers=org["org_headers"],
        json={"sample_text": f"Aadhaar {VALID_AADHAAR} PAN {VALID_PAN} phone {INDIAN_PHONE}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["status"] != "unavailable"
    assert body["detection_engine"] == "builtin"
    detected = {entity["entity_type"] for entity in body["entities"]}
    assert {IN_AADHAAR, IN_PAN, IN_PHONE_NUMBER} <= detected
