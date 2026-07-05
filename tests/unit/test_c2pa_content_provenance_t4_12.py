import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.content_provenance_record import ContentProvenanceRecord
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

VERIFY_URL = "/api/v1/content-provenance/verify"


def _valid_manifest() -> dict:
    return {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-1.2",
        "assertions": [
            {"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.created"}]}},
            {"label": "c2pa.hash.data", "data": {"hash": "abc123"}},
        ],
        "signature_info": {
            "algorithm": "es256",
            "signature": "deadbeefcafebabe",
        },
    }


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def test_t4_12_valid_manifest_verifies_ok(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-valid")

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-001", "manifest": _valid_manifest()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "valid"
    assert body["invalid_reason"] is None
    assert body["spec_version_detected"] == "c2pa-1.2"
    assert body["claim_generator"] == "AcmeCam/1.0"
    assert body["assertion_count"] == 2

    stored = db_session.query(ContentProvenanceRecord).filter_by(id=uuid.UUID(body["id"])).one()
    assert stored.verification_status == "valid"
    assert stored.invalid_reason is None


def test_t4_12_empty_manifest_is_malformed_claim(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-empty")

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-002", "manifest": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "malformed_claim"
    assert body["spec_version_detected"] is None
    assert body["claim_generator"] is None
    assert body["assertion_count"] is None


def test_t4_12_missing_signature_block(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-nosig")

    manifest = {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-1.2",
        "assertions": [{"label": "c2pa.actions", "data": {"actions": []}}],
    }

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-003", "manifest": manifest},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "missing_signature"
    assert body["spec_version_detected"] == "c2pa-1.2"
    assert body["claim_generator"] == "AcmeCam/1.0"
    assert body["assertion_count"] == 1


def test_t4_12_signature_block_missing_algorithm_is_tampered(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-tampered")

    manifest = {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-1.2",
        "assertions": [{"label": "c2pa.actions", "data": {"actions": []}}],
        "signature_info": {
            "signature": "deadbeefcafebabe",
        },
    }

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-004", "manifest": manifest},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "tampered_signature"


def test_t4_12_signature_block_empty_algorithm_is_tampered(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-tampered2")

    manifest = {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-1.2",
        "assertions": [{"label": "c2pa.actions", "data": {"actions": []}}],
        "signature_info": {
            "algorithm": "   ",
            "signature": "deadbeefcafebabe",
        },
    }

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-004b", "manifest": manifest},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "tampered_signature"


def test_t4_12_unsupported_spec_version(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-badver")

    manifest = {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-9.9",
        "assertions": [{"label": "c2pa.actions", "data": {"actions": []}}],
        "signature_info": {
            "algorithm": "es256",
            "signature": "deadbeefcafebabe",
        },
    }

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-005", "manifest": manifest},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "unsupported_version"
    assert body["spec_version_detected"] == "c2pa-9.9"
    assert body["claim_generator"] == "AcmeCam/1.0"


def test_t4_12_empty_assertions_list_is_malformed_claim_no_crash(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-emptyassert")

    manifest = {
        "claim_generator": "AcmeCam/1.0",
        "spec_version": "c2pa-1.2",
        "assertions": [],
        "signature_info": {
            "algorithm": "es256",
            "signature": "deadbeefcafebabe",
        },
    }

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-006", "manifest": manifest},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "malformed_claim"
    assert body["assertion_count"] == 0


def test_t4_12_get_record_and_cross_org_404(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="c2pa-get-a")
    org2 = bootstrap_org_user(client, email_prefix="c2pa-get-b")

    created = client.post(
        VERIFY_URL,
        headers=org1["org_headers"],
        json={"content_identifier": "asset-007", "manifest": _valid_manifest()},
    )
    assert created.status_code == 200
    record_id = created.json()["id"]

    fetched = client.get(f"/api/v1/content-provenance/{record_id}", headers=org1["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == record_id
    assert fetched.json()["content_identifier"] == "asset-007"

    cross_org = client.get(f"/api/v1/content-provenance/{record_id}", headers=org2["org_headers"])
    assert cross_org.status_code == 404


def test_t4_12_audit_log_recorded_for_verification(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-audit")

    response = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-008", "manifest": _valid_manifest()},
    )
    assert response.status_code == 200
    record_id = response.json()["id"]

    audit_row = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "content_provenance.manifest_verified",
            AuditLog.entity_id == uuid.UUID(record_id),
        )
        .one_or_none()
    )
    assert audit_row is not None
    assert audit_row.after_json["verification_status"] == "valid"
    assert audit_row.metadata_json["verification_status"] == "valid"


def test_t4_12_user_without_permission_forbidden(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2pa-perm")

    auditor_email = "c2pa-auditor@example.com"
    _create_active_user_with_role(db_session, org["organization_id"], auditor_email, "auditor")
    auditor_token = login_user(client, auditor_email)
    auditor_headers = org_headers(auditor_token, org["organization_id"])

    response = client.post(
        VERIFY_URL,
        headers=auditor_headers,
        json={"content_identifier": "asset-009", "manifest": _valid_manifest()},
    )
    assert response.status_code == 403


def test_t4_12_no_third_party_c2pa_library_reference():
    import inspect

    from app.services import content_provenance_service as svc_module

    source = inspect.getsource(svc_module)
    lowered = source.lower()

    # The comment block is allowed to mention "c2pa" as the spec name itself,
    # but no third-party binding/package names (e.g. the "libc2pa" native
    # binding, or a "c2pa-python" style package) should be referenced or
    # imported anywhere in the service module.
    banned_fragments = ("lib" + "c2pa", "c2pa" + "-python", "c2pa_" + "python")
    for fragment in banned_fragments:
        assert fragment not in lowered
    assert "import libc2pa" not in lowered
    assert "from libc2pa" not in lowered
    assert "pip install" not in lowered
