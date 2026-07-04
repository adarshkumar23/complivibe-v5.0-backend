import uuid
from app.models.compliance_policy_version import CompliancePolicyVersion
from tests.helpers.auth_org import bootstrap_org_user

BASE_TEMPLATES = "/api/v1/compliance/policy-templates"


def test_verify_template_apply_creates_real_policy_version(client, db_session):
    org = bootstrap_org_user(client, email_prefix="partD-tmplapply")

    templates = client.get(BASE_TEMPLATES, headers=org["org_headers"])
    assert templates.status_code == 200
    assert templates.json(), "expected at least one system template to exist"
    template_id = templates.json()[0]["id"]

    applied = client.post(
        f"{BASE_TEMPLATES}/{template_id}/apply",
        headers=org["org_headers"],
        json={},
    )
    print("APPLIED:", applied.status_code, applied.json())
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert "policy_version_id" in body, "BUG: template apply does not create a real policy version"

    version = db_session.get(CompliancePolicyVersion, uuid.UUID(body["policy_version_id"]))
    assert version is not None
    assert version.policy_id == uuid.UUID(body["policy_id"])
    assert version.content_snapshot_json["source"] == "policy_template"
    assert version.content_snapshot_json["content"], "BUG: template content not persisted into the real version"

    api_versions = client.get(
        f"/api/v1/compliance/policies/{body['policy_id']}/versions",
        headers=org["org_headers"],
    )
    assert api_versions.status_code == 200
    version_list = api_versions.json()
    assert len(version_list) >= 1, "BUG: GET policy versions is empty for a template-created policy"
    matched = next((v for v in version_list if v["id"] == body["policy_version_id"]), None)
    assert matched is not None, "BUG: template-created version not returned by GET policy versions"
    assert matched["content_snapshot_json"]["source"] == "policy_template"
    assert matched["content_snapshot_json"]["content"] == version.content_snapshot_json["content"]
