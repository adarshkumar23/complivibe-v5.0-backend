from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from authlib.jose import JsonWebKey, jwt
from sqlalchemy import select

from app.auth.services.oidc_config_service import OIDCConfigService
from app.auth.services.oidc_service import OIDCService
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.oidc_auth_state import OIDCAuthState
from app.models.oidc_config import OIDCConfig
from app.models.organization import Organization
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

ISSUER = "https://issuer.example.com"
CLIENT_ID = "complivibe-client"


def _enable_sso_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "growth"
    db_session.commit()


def _org_slug(client, headers: dict[str, str]) -> str:
    response = client.get("/api/v1/organizations/me", headers=headers)
    assert response.status_code == 200
    return response.json()[0]["slug"]


def _discovery() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
    }


def _create_oidc_config(client, db_session, org: dict, monkeypatch, *, jit_provisioning: bool = True) -> tuple[str, str]:
    _enable_sso_feature(db_session, org["organization_id"])
    slug = _org_slug(client, org["headers"])
    monkeypatch.setattr(OIDCConfigService, "_fetch_discovery_document", lambda self, issuer_url: _discovery())
    response = client.post(
        "/api/v1/oidc-configs",
        headers=org["org_headers"],
        json={
            "provider": "oidc",
            "issuer_url": ISSUER,
            "client_id": CLIENT_ID,
            "client_secret": "super-secret-client-value",
            "scopes": ["openid", "email", "profile"],
            "claim_mapping": {"email": "email", "subject": "sub", "name": "name"},
            "jit_provisioning": jit_provisioning,
            "default_role": "member",
        },
    )
    assert response.status_code == 201, response.text
    config_id = response.json()["id"]
    activate = client.post(f"/api/v1/oidc-configs/{config_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200, activate.text
    return config_id, slug


def _key(kid: str):
    return JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": kid})


def _id_token(
    key,
    *,
    issuer: str = ISSUER,
    audience: str = CLIENT_ID,
    nonce: str,
    email: str = "oidc-user@example.com",
    subject: str = "oidc-subject-1",
    expires_delta: int = 300,
) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "email": email,
        "name": "OIDC User",
        "nonce": nonce,
        "iat": now,
        "exp": now + expires_delta,
    }
    token = jwt.encode({"alg": "RS256", "kid": key.as_dict()["kid"]}, payload, key)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def _initiate(client, slug: str) -> tuple[str, str]:
    response = client.post(f"/api/v1/auth/oidc/{slug}/initiate")
    assert response.status_code == 200, response.text
    parsed = urlparse(response.json()["redirect_url"])
    params = parse_qs(parsed.query)
    return params["state"][0], params["nonce"][0]


def test_oidc_config_discovery_encrypts_secret_and_initiate_persists_state(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="oidc-discovery")
    config_id, slug = _create_oidc_config(client, db_session, org, monkeypatch)

    row = db_session.get(OIDCConfig, UUID(config_id))
    assert row is not None
    assert row.authorization_endpoint == f"{ISSUER}/authorize"
    assert row.token_endpoint == f"{ISSUER}/token"
    assert row.jwks_uri == f"{ISSUER}/jwks"
    assert row.client_secret_enc != "super-secret-client-value"
    assert OIDCConfigService.decrypt_secret(row.client_secret_enc) == "super-secret-client-value"

    state, nonce = _initiate(client, slug)
    state_rows = db_session.execute(select(OIDCAuthState).where(OIDCAuthState.organization_id == UUID(org["organization_id"]))).scalars().all()
    assert len(state_rows) == 1
    assert state_rows[0].state_hash == OIDCService._sha256(state)
    assert state_rows[0].nonce_hash == OIDCService._sha256(nonce)
    assert state_rows[0].expires_at is not None


def test_oidc_callback_existing_user_jwks_rotation_and_audit(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="oidc-existing")
    _, slug = _create_oidc_config(client, db_session, org, monkeypatch, jit_provisioning=False)

    keys = [_key("kid-1"), _key("kid-2")]
    active_key = {"value": keys[0]}
    monkeypatch.setattr(OIDCService, "_fetch_jwks", lambda self, uri: {"keys": [active_key["value"].as_dict(is_private=False)]})

    state, nonce = _initiate(client, slug)
    monkeypatch.setattr(
        OIDCService,
        "_fetch_token",
        lambda self, config, code, redirect_uri: {
            "id_token": _id_token(active_key["value"], nonce=nonce, email=org["email"], subject="existing-subject-1")
        },
    )
    callback = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code-1", "state": state})
    assert callback.status_code == 200, callback.text
    assert callback.json()["auth_method"] == "oidc"

    active_key["value"] = keys[1]
    state_2, nonce_2 = _initiate(client, slug)
    monkeypatch.setattr(
        OIDCService,
        "_fetch_token",
        lambda self, config, code, redirect_uri: {
            "id_token": _id_token(active_key["value"], nonce=nonce_2, email=org["email"], subject="existing-subject-2")
        },
    )
    callback_2 = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code-2", "state": state_2})
    assert callback_2.status_code == 200, callback_2.text

    users = db_session.execute(select(User).where(User.email == org["email"])).scalars().all()
    assert len(users) == 1
    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "sso.login",
            AuditLog.metadata_json["auth_method"].as_string() == "oidc",
        )
    ).scalars().first()
    assert audit_row is not None


def test_oidc_callback_jit_disabled_unknown_user_returns_401(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="oidc-jit-disabled")
    _, slug = _create_oidc_config(client, db_session, org, monkeypatch, jit_provisioning=False)
    key = _key("kid-jit")
    monkeypatch.setattr(OIDCService, "_fetch_jwks", lambda self, uri: {"keys": [key.as_dict(is_private=False)]})
    state, nonce = _initiate(client, slug)
    monkeypatch.setattr(
        OIDCService,
        "_fetch_token",
        lambda self, config, code, redirect_uri: {"id_token": _id_token(key, nonce=nonce, email="unknown-oidc@example.com")},
    )

    callback = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code", "state": state})
    assert callback.status_code == 401


class _BadTokenCase:
    def __init__(self, *, issuer=ISSUER, audience=CLIENT_ID, expires_delta=300, nonce_override: str | None = None, jwks_key=None):
        self.issuer = issuer
        self.audience = audience
        self.expires_delta = expires_delta
        self.nonce_override = nonce_override
        self.jwks_key = jwks_key


def test_oidc_callback_rejects_invalid_state_nonce_claims_and_signature(client, db_session, monkeypatch):
    cases = [
        ("state", None),
        ("nonce", _BadTokenCase(nonce_override="wrong-nonce")),
        ("issuer", _BadTokenCase(issuer="https://evil.example.com")),
        ("audience", _BadTokenCase(audience="wrong-client")),
        ("expiry", _BadTokenCase(expires_delta=-300)),
        ("signature", _BadTokenCase()),
    ]

    for case_name, bad_case in cases:
        org = bootstrap_org_user(client, email_prefix=f"oidc-invalid-{case_name}")
        _, slug = _create_oidc_config(client, db_session, org, monkeypatch, jit_provisioning=True)
        signing_key = _key(f"sign-{case_name}")
        jwks_key = _key(f"jwks-{case_name}") if case_name == "signature" else signing_key
        monkeypatch.setattr(OIDCService, "_fetch_jwks", lambda self, uri, key=jwks_key: {"keys": [key.as_dict(is_private=False)]})
        state, nonce = _initiate(client, slug)

        if case_name == "state":
            callback = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code", "state": "bad-state"})
            assert callback.status_code == 401
            continue

        assert bad_case is not None
        token_nonce = bad_case.nonce_override or nonce
        monkeypatch.setattr(
            OIDCService,
            "_fetch_token",
            lambda self, config, code, redirect_uri, case=bad_case, key=signing_key, token_nonce=token_nonce: {
                "id_token": _id_token(
                    key,
                    issuer=case.issuer,
                    audience=case.audience,
                    expires_delta=case.expires_delta,
                    nonce=token_nonce,
                    email="invalid-token@example.com",
                )
            },
        )
        callback = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code", "state": state})
        assert callback.status_code == 401, callback.text


def test_oidc_callback_jit_provisions_new_user(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="oidc-jit-enabled")
    _, slug = _create_oidc_config(client, db_session, org, monkeypatch, jit_provisioning=True)
    key = _key("kid-provision")
    monkeypatch.setattr(OIDCService, "_fetch_jwks", lambda self, uri: {"keys": [key.as_dict(is_private=False)]})
    state, nonce = _initiate(client, slug)
    monkeypatch.setattr(
        OIDCService,
        "_fetch_token",
        lambda self, config, code, redirect_uri: {"id_token": _id_token(key, nonce=nonce, email="new-oidc@example.com")},
    )

    callback = client.get(f"/api/v1/auth/oidc/{slug}/callback", params={"code": "code", "state": state})
    assert callback.status_code == 200, callback.text
    user = db_session.execute(select(User).where(User.email == "new-oidc@example.com")).scalar_one_or_none()
    assert user is not None
    membership = db_session.execute(
        select(Membership).where(Membership.organization_id == UUID(org["organization_id"]), Membership.user_id == user.id)
    ).scalar_one_or_none()
    assert membership is not None
