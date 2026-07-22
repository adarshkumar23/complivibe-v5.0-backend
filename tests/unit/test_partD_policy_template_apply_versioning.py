import uuid
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user

BASE_TEMPLATES = "/api/v1/compliance/policy-templates"
BASE_POLICIES = "/api/v1/compliance/policies"


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


def test_g6_direct_create_accepts_every_policy_type_a_template_can_apply(client, db_session):
    """Regression test for the G6 bug: CompliancePolicyCreate.policy_type used a
    Pydantic pattern that only allowed 7 values (acceptable_use, data_retention,
    incident_response, access_control, change_management, business_continuity,
    other), while SeedService.ensure_policy_templates's slug_policy_type_map stores
    5 additional values via template-apply (data_privacy, vendor_management,
    information_security, ai_governance, third_party_risk) with no schema
    validation at all. Applying an "ai-governance" template produced a
    CompliancePolicy with policy_type="ai_governance" that POST /compliance/policies
    would then itself reject with 422 for the exact same value.

    This applies the real "ai-governance" system template end to end, confirms
    the resulting policy's policy_type is "ai_governance", and then asserts
    POST /compliance/policies with policy_type="ai_governance" (and the other
    template-only values) now succeeds instead of 422.
    """
    org = bootstrap_org_user(client, email_prefix="partD-g6-policytype")
    # This test exercises policy_type acceptance (template-apply + 5 direct
    # creates = 6 policies), not the Free-tier 5-record cap. Run it on an
    # uncapped plan so the cap doesn't mask the schema behaviour under test.
    _g6_org = db_session.get(Organization, uuid.UUID(org["organization_id"]))
    _g6_org.subscription_plan = "enterprise"
    _g6_org.subscription_status = "active"
    db_session.commit()

    templates = client.get(BASE_TEMPLATES, headers=org["org_headers"])
    assert templates.status_code == 200
    ai_gov_template = next((t for t in templates.json() if t.get("slug") == "ai-governance"), None)
    assert ai_gov_template is not None, "expected the system 'ai-governance' policy template to exist"

    applied = client.post(
        f"{BASE_TEMPLATES}/{ai_gov_template['id']}/apply",
        headers=org["org_headers"],
        json={},
    )
    assert applied.status_code == 200, applied.text
    applied_policy_id = applied.json()["policy_id"]

    from app.models.compliance_policy import CompliancePolicy

    applied_policy = db_session.get(CompliancePolicy, uuid.UUID(applied_policy_id))
    assert applied_policy is not None
    assert applied_policy.policy_type == "ai_governance"

    # The exact same value that template-apply just stored, attempted via direct
    # create, must not be rejected.
    for policy_type in (
        "ai_governance",
        "third_party_risk",
        "information_security",
        "vendor_management",
        "data_privacy",
    ):
        direct_create = client.post(
            BASE_POLICIES,
            headers=org["org_headers"],
            json={
                "title": f"Direct-create {policy_type} policy",
                "policy_type": policy_type,
                "owner_user_id": org["user_id"],
            },
        )
        assert direct_create.status_code == 201, (
            f"policy_type={policy_type!r} rejected by direct-create schema: {direct_create.text}"
        )
        assert direct_create.json()["policy_type"] == policy_type
