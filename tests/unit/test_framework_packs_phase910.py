import json
from pathlib import Path

from app.services.framework_content_pack_service import FrameworkContentPackService

PACK_MIN_COUNTS = {
    "soc2_starter": 10,
    "iso_27001_starter": 10,
    "gdpr_starter": 15,
    "nist_ai_rmf_starter": 15,
    "eu_ai_act_starter": 10,
    "india_dpdp_starter": 10,
}

REQUIRED_CAVEAT = (
    "This is a starter content pack for scoping purposes only. "
    "It does not constitute legal advice or a complete compliance determination."
)


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def test_phase910_framework_pack_files_validate_counts_and_required_fields(client):
    pack_root = Path(FrameworkContentPackService.PACK_ROOT)

    for pack_key, min_count in PACK_MIN_COUNTS.items():
        path = pack_root / f"{pack_key}.json"
        assert path.exists(), f"Missing content pack file: {path}"
        payload = json.loads(path.read_text())

        assert payload["coverage_level"] == "starter"
        assert payload["coverage_level"] != "full_verified"
        assert payload.get("version") == "1.0"
        assert REQUIRED_CAVEAT in payload.get("caveat", "")

        obligations = payload.get("obligations", [])
        assert len(obligations) >= min_count, f"{pack_key} has {len(obligations)} obligations, expected >= {min_count}"

        ref_codes = set()
        for item in obligations:
            for required_field in [
                "section_code",
                "obligation_code",
                "title",
                "description",
                "obligation_type",
                "applicability_notes",
                "reference_code",
            ]:
                assert item.get(required_field), f"{pack_key} obligation missing {required_field}"

            assert item["obligation_type"] in {"control", "documentation", "process", "assessment"}
            assert item["reference_code"] not in ref_codes, f"Duplicate reference_code in {pack_key}: {item['reference_code']}"
            ref_codes.add(item["reference_code"])


def test_phase910_loader_validate_and_apply_dry_run_for_all_updated_packs(client):
    owner = _register(client, "p910-owner@example.com", "Pass1234!@", "P910 Org")
    org_id = _org_id(client, owner)

    for pack_key, min_count in PACK_MIN_COUNTS.items():
        validate = client.post(
            f"/api/v1/framework-content/packs/{pack_key}/validate",
            headers=_headers(owner, org_id),
        )
        assert validate.status_code == 200
        body = validate.json()
        assert body["valid"] is True, f"Validation failed for {pack_key}: {body.get('validation_errors')}"
        assert body["coverage_level"] == "starter"
        assert body["counts"]["obligations"] >= min_count

        dry_run_apply = client.post(
            f"/api/v1/framework-content/packs/{pack_key}/apply",
            headers=_headers(owner, org_id),
            json={"dry_run": True, "force_update": False},
        )
        assert dry_run_apply.status_code == 200
        apply_body = dry_run_apply.json()
        assert apply_body["valid"] is True, f"Dry-run apply failed for {pack_key}: {apply_body.get('validation_errors')}"
        assert apply_body["persisted"] is False
        assert apply_body["counts"]["obligations"] >= min_count
