from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.sso_config import SSOConfig
from app.models.user import User
from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user

SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
APP_HOST = "app.example.com"
APP_BASE_URL = f"http://{APP_HOST}"


def _org_slug(client, headers: dict[str, str]) -> str:
    response = client.get("/api/v1/organizations/me", headers=headers)
    assert response.status_code == 200
    return response.json()[0]["slug"]


def _sample_config_payload() -> dict:
    return {
        "provider": "okta",
        "entity_id": "https://example.okta.com/app/issuer",
        "sso_url": "https://example.okta.com/app/sso/saml",
        "slo_url": "https://example.okta.com/app/slo/saml",
        "certificate": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        "attribute_mapping": {
            "email": "NameID",
            "first_name": "firstName",
            "last_name": "lastName",
            "role": "groups",
        },
        "jit_provisioning": True,
        "default_role": "member",
    }


def _idp_keypair(common_name: str = "CompliVibe Test IdP") -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=30))
        .sign(private_key, hashes.SHA256())
    )
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return private_pem, cert_pem


def _sso_config_payload(*, cert_pem: str, issuer: str = "https://example.okta.com/app/issuer", jit: bool = True) -> dict:
    payload = _sample_config_payload()
    payload["certificate"] = cert_pem
    payload["entity_id"] = issuer
    payload["jit_provisioning"] = jit
    return payload


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_saml_response(
    *,
    slug: str,
    email: str,
    issuer: str,
    private_pem: str,
    cert_pem: str,
    audience: str | None = None,
    destination: str | None = None,
    assertion_id: str | None = None,
    not_before: datetime | None = None,
    not_on_or_after: datetime | None = None,
    sign_assertion: bool = True,
) -> str:
    now = datetime.now(UTC)
    acs_url = destination or f"{APP_BASE_URL}/api/v1/auth/sso/{slug}/callback"
    audience = audience or f"{APP_BASE_URL}/api/v1/auth/sso/{slug}/metadata"
    assertion_id = assertion_id or f"_{uuid.uuid4().hex}"
    not_before = not_before or (now - timedelta(minutes=1))
    not_on_or_after = not_on_or_after or (now + timedelta(minutes=5))

    response = etree.Element(
        f"{{{SAMLP_NS}}}Response",
        nsmap={"samlp": SAMLP_NS, "saml": SAML_NS, "ds": DS_NS},
        ID=f"_{uuid.uuid4().hex}",
        Version="2.0",
        IssueInstant=_ts(now),
        Destination=acs_url,
    )
    etree.SubElement(response, f"{{{SAML_NS}}}Issuer").text = issuer
    status = etree.SubElement(response, f"{{{SAMLP_NS}}}Status")
    etree.SubElement(status, f"{{{SAMLP_NS}}}StatusCode", Value="urn:oasis:names:tc:SAML:2.0:status:Success")

    assertion = etree.SubElement(
        response,
        f"{{{SAML_NS}}}Assertion",
        ID=assertion_id,
        Version="2.0",
        IssueInstant=_ts(now),
    )
    issuer_node = etree.SubElement(assertion, f"{{{SAML_NS}}}Issuer")
    issuer_node.text = issuer
    subject = etree.SubElement(assertion, f"{{{SAML_NS}}}Subject")
    name_id = etree.SubElement(
        subject,
        f"{{{SAML_NS}}}NameID",
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )
    name_id.text = email
    confirmation = etree.SubElement(
        subject,
        f"{{{SAML_NS}}}SubjectConfirmation",
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer",
    )
    etree.SubElement(
        confirmation,
        f"{{{SAML_NS}}}SubjectConfirmationData",
        Recipient=acs_url,
        NotOnOrAfter=_ts(not_on_or_after),
    )
    conditions = etree.SubElement(
        assertion,
        f"{{{SAML_NS}}}Conditions",
        NotBefore=_ts(not_before),
        NotOnOrAfter=_ts(not_on_or_after),
    )
    audience_restriction = etree.SubElement(conditions, f"{{{SAML_NS}}}AudienceRestriction")
    etree.SubElement(audience_restriction, f"{{{SAML_NS}}}Audience").text = audience
    authn = etree.SubElement(
        assertion,
        f"{{{SAML_NS}}}AuthnStatement",
        AuthnInstant=_ts(now),
        SessionIndex=f"_{uuid.uuid4().hex}",
    )
    authn_context = etree.SubElement(authn, f"{{{SAML_NS}}}AuthnContext")
    etree.SubElement(authn_context, f"{{{SAML_NS}}}AuthnContextClassRef").text = (
        "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"
    )

    if sign_assertion:
        signature = xmlsec.template.create(
            assertion,
            xmlsec.Transform.EXCL_C14N,
            xmlsec.Transform.RSA_SHA256,
            ns="ds",
        )
        assertion.insert(1, signature)
        reference = xmlsec.template.add_reference(signature, xmlsec.Transform.SHA256, uri=f"#{assertion_id}")
        xmlsec.template.add_transform(reference, xmlsec.Transform.ENVELOPED)
        xmlsec.template.add_transform(reference, xmlsec.Transform.EXCL_C14N)
        key_info = xmlsec.template.ensure_key_info(signature)
        xmlsec.template.add_x509_data(key_info)
        xmlsec.tree.add_ids(response, ["ID"])
        sign_ctx = xmlsec.SignatureContext()
        sign_ctx.key = xmlsec.Key.from_memory(private_pem.encode("utf-8"), xmlsec.KeyFormat.PEM, None)
        sign_ctx.key.load_cert_from_memory(cert_pem.encode("utf-8"), xmlsec.KeyFormat.PEM)
        sign_ctx.sign(signature)

    return base64.b64encode(etree.tostring(response)).decode("ascii")


def _create_active_sso_config(
    client,
    db_session,
    org: dict,
    *,
    cert_pem: str,
    issuer: str = "https://example.okta.com/app/issuer",
    jit: bool = True,
) -> str:
    _enable_sso_feature(db_session, org["organization_id"])
    response = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sso_config_payload(cert_pem=cert_pem, issuer=issuer, jit=jit))
    assert response.status_code == 201, response.text
    config_id = response.json()["id"]
    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200, activate.text
    return config_id


def _latest_sso_failure(db_session, organization_id: str) -> AuditLog:
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == UUID(organization_id), AuditLog.action == "sso.login_failed")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert row is not None
    return row


def _post_saml_callback(client, slug: str, saml_response: str):
    return client.post(
        f"/api/v1/auth/sso/{slug}/callback",
        headers={"host": APP_HOST},
        data={"SAMLResponse": saml_response},
    )


def _enable_sso_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "growth"
    db_session.commit()


def test_sso_config_end_to_end_and_public_endpoints(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sso-a")
    org_b = bootstrap_org_user(client, email_prefix="sso-b")
    _enable_sso_feature(db_session, org_a["organization_id"])
    _enable_sso_feature(db_session, org_b["organization_id"])
    slug_a = _org_slug(client, org_a["headers"])

    tables = set(inspect(db_session.bind).get_table_names())
    assert "sso_configs" in tables

    create_resp = client.post("/api/v1/sso-configs", headers=org_a["org_headers"], json=_sample_config_payload())
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]

    duplicate = client.post("/api/v1/sso-configs", headers=org_a["org_headers"], json=_sample_config_payload())
    assert duplicate.status_code == 409

    metadata = client.get(f"/api/v1/auth/sso/{slug_a}/metadata")
    assert metadata.status_code == 200
    assert "xml" in metadata.headers.get("content-type", "")
    assert f"/auth/sso/{slug_a}/callback" in metadata.text

    initiate = client.post(f"/api/v1/auth/sso/{slug_a}/initiate")
    assert initiate.status_code == 400

    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org_a["org_headers"])
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True

    initiate = client.post(f"/api/v1/auth/sso/{slug_a}/initiate")
    assert initiate.status_code == 200
    assert "redirect_url" in initiate.json()
    assert _sample_config_payload()["sso_url"] in initiate.json()["redirect_url"]

    get_cfg = client.get("/api/v1/sso-configs", headers=org_a["org_headers"])
    assert get_cfg.status_code == 200
    assert "certificate" not in get_cfg.json()

    other_org_get = client.get("/api/v1/sso-configs", headers=org_b["org_headers"])
    assert other_org_get.status_code == 404

    tested = client.post(f"/api/v1/sso-configs/{config_id}/test", headers=org_a["org_headers"])
    assert tested.status_code == 200
    assert set(tested.json().keys()) == {"valid", "errors"}

    deactivated = client.post(f"/api/v1/sso-configs/{config_id}/deactivate", headers=org_a["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    deleted = client.delete(f"/api/v1/sso-configs/{config_id}", headers=org_a["org_headers"])
    assert deleted.status_code == 204

    row = db_session.get(SSOConfig, UUID(config_id))
    assert row is not None
    assert row.deleted_at is not None


def test_sso_callback_valid_assertion_jit_and_existing_user_and_audit_log(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-callback")
    private_pem, cert_pem = _idp_keypair("Valid IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(slug=slug, email="jit-user@example.com", issuer="https://example.okta.com/app/issuer", private_pem=private_pem, cert_pem=cert_pem),
    )
    assert callback.status_code == 200
    payload = callback.json()
    assert payload["auth_method"] == "sso"
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    user = db_session.execute(select(User).where(User.email == "jit-user@example.com")).scalar_one_or_none()
    assert user is not None
    membership = db_session.execute(
        select(Membership).where(
            Membership.organization_id == UUID(org["organization_id"]),
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()
    assert membership is not None

    before_count = db_session.execute(select(User)).scalars().all()
    callback_existing = _post_saml_callback(
        client,
        slug,
        _build_saml_response(slug=slug, email="jit-user@example.com", issuer="https://example.okta.com/app/issuer", private_pem=private_pem, cert_pem=cert_pem),
    )
    assert callback_existing.status_code == 200
    after_count = db_session.execute(select(User)).scalars().all()
    assert len(after_count) == len(before_count)

    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "sso.login",
        )
    ).scalars().first()
    assert audit_row is not None


def test_sso_callback_rejects_unsigned_forged_assertion(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-forged")
    private_pem, cert_pem = _idp_keypair("Unsigned IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(
            slug=slug,
            email="attacker@example.com",
            issuer="https://example.okta.com/app/issuer",
            private_pem=private_pem,
            cert_pem=cert_pem,
            sign_assertion=False,
        ),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "signature"


def test_sso_callback_rejects_assertion_signed_by_other_org_certificate(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sso-crosstenant-a")
    org_b = bootstrap_org_user(client, email_prefix="sso-crosstenant-b")
    _private_a, cert_a = _idp_keypair("Org A IdP")
    private_b, cert_b = _idp_keypair("Org B IdP")
    slug_a = _org_slug(client, org_a["headers"])
    _create_active_sso_config(client, db_session, org_a, cert_pem=cert_a)
    _create_active_sso_config(client, db_session, org_b, cert_pem=cert_b)

    callback = _post_saml_callback(
        client,
        slug_a,
        _build_saml_response(slug=slug_a, email="attacker@example.com", issuer="https://example.okta.com/app/issuer", private_pem=private_b, cert_pem=cert_b),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org_a["organization_id"]).metadata_json["validation_check"] == "signature"


def test_sso_callback_rejects_wrong_issuer(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-wrong-issuer")
    private_pem, cert_pem = _idp_keypair("Issuer IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem, issuer="https://issuer.expected.example")

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(slug=slug, email="issuer@example.com", issuer="https://issuer.evil.example", private_pem=private_pem, cert_pem=cert_pem),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "issuer"


def test_sso_callback_rejects_wrong_audience(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-wrong-audience")
    private_pem, cert_pem = _idp_keypair("Audience IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(slug=slug, email="audience@example.com", issuer="https://example.okta.com/app/issuer", private_pem=private_pem, cert_pem=cert_pem, audience="http://evil.example/saml/metadata"),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "audience"


def test_sso_callback_rejects_expired_assertion(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-expired")
    private_pem, cert_pem = _idp_keypair("Expired IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(
            slug=slug,
            email="expired@example.com",
            issuer="https://example.okta.com/app/issuer",
            private_pem=private_pem,
            cert_pem=cert_pem,
            not_before=datetime.now(UTC) - timedelta(minutes=10),
            not_on_or_after=datetime.now(UTC) - timedelta(minutes=5),
        ),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "timestamp"


def test_sso_callback_rejects_not_yet_valid_assertion(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-not-before")
    private_pem, cert_pem = _idp_keypair("NotBefore IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(
            slug=slug,
            email="future@example.com",
            issuer="https://example.okta.com/app/issuer",
            private_pem=private_pem,
            cert_pem=cert_pem,
            not_before=datetime.now(UTC) + timedelta(minutes=10),
            not_on_or_after=datetime.now(UTC) + timedelta(minutes=20),
        ),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "timestamp"


def test_sso_callback_rejects_wrong_destination(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-wrong-destination")
    private_pem, cert_pem = _idp_keypair("Destination IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(
            slug=slug,
            email="destination@example.com",
            issuer="https://example.okta.com/app/issuer",
            private_pem=private_pem,
            cert_pem=cert_pem,
            destination="http://evil.example/api/v1/auth/sso/evil/callback",
        ),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "destination"


def test_sso_callback_rejects_assertion_replay(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-replay")
    private_pem, cert_pem = _idp_keypair("Replay IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem)
    saml_response = _build_saml_response(
        slug=slug,
        email="replay@example.com",
        issuer="https://example.okta.com/app/issuer",
        private_pem=private_pem,
        cert_pem=cert_pem,
        assertion_id="_fixedreplayassertion",
    )

    first = _post_saml_callback(client, slug, saml_response)
    assert first.status_code == 200, first.text
    second = _post_saml_callback(client, slug, saml_response)
    assert second.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "replay"


def test_sso_callback_jit_disabled_unknown_user_returns_401(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-disabled")
    private_pem, cert_pem = _idp_keypair("JIT Disabled IdP")
    slug = _org_slug(client, org["headers"])
    _create_active_sso_config(client, db_session, org, cert_pem=cert_pem, jit=False)

    callback = _post_saml_callback(
        client,
        slug,
        _build_saml_response(slug=slug, email="unknown-user@example.com", issuer="https://example.okta.com/app/issuer", private_pem=private_pem, cert_pem=cert_pem),
    )
    assert callback.status_code == 401
    assert _latest_sso_failure(db_session, org["organization_id"]).metadata_json["validation_check"] == "user_provisioning"
