"""Regression tests for real-client-IP extraction / X-Forwarded-For spoofing (2026-07-20).

Before the fix, IPAllowlistService.extract_request_ip blindly trusted the LEFTMOST
token of X-Forwarded-For, which is fully client-controlled. An attacker could send
`X-Forwarded-For: <any-allowed-ip>` and defeat an org IP allowlist, or forge the IP
recorded on their session/audit rows.

The fix makes both forwarded sources opt-in and safe-by-default:
  * BEHIND_CLOUDFLARE_TUNNEL -> trust CF-Connecting-IP (edge-set, unspoofable) only
    when the upstream hop is a trusted Cloudflare/tunnel peer;
  * TRUSTED_PROXY_COUNT > 0 -> read X-Forwarded-For from the RIGHT (parts[-N]);
  * otherwise the raw socket peer only.

The header values used in the Cloudflare cases below are the exact values captured
from a live cloudflared tunnel with a spoofed X-Forwarded-For (see the commit
message / scratchpad tunnel evidence).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import get_settings
from app.models.org_ip_allowlist import OrgIPAllowlist
from app.platform.services.ip_allowlist_service import IPAllowlistService
from tests.helpers.auth_org import bootstrap_org_user

extract = IPAllowlistService.extract_request_ip

# Exactly what the origin received behind the real tunnel for a request that spoofed
# `X-Forwarded-For: 1.2.3.4, 5.6.7.8` from public IP 161.118.173.100.
LIVE_XFF = "1.2.3.4, 5.6.7.8,161.118.173.100"
LIVE_CF_CONNECTING_IP = "161.118.173.100"
LIVE_SOCKET_PEER = "127.0.0.1"  # cloudflared -> origin is loopback


@pytest.fixture
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_safe_default_ignores_x_forwarded_for(monkeypatch, _clear_settings):
    """Default config: X-Forwarded-For is NOT trusted; only the socket peer is used.

    Pre-fix this returned the leftmost XFF token (1.2.3.4), the whole vulnerability.
    """
    monkeypatch.delenv("BEHIND_CLOUDFLARE_TUNNEL", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    get_settings.cache_clear()

    result = extract(x_forwarded_for="1.2.3.4, 5.6.7.8", client_host="203.0.113.9")
    assert result == "203.0.113.9"


def test_cloudflare_tunnel_trusts_cf_connecting_ip(monkeypatch, _clear_settings):
    monkeypatch.setenv("BEHIND_CLOUDFLARE_TUNNEL", "true")
    get_settings.cache_clear()

    # The exact live-tunnel headers: spoofed XFF present, real IP in CF-Connecting-IP,
    # loopback socket peer. Must resolve to the real client, ignoring the spoof.
    result = extract(
        x_forwarded_for=LIVE_XFF,
        client_host=LIVE_SOCKET_PEER,
        cf_connecting_ip=LIVE_CF_CONNECTING_IP,
    )
    assert result == "161.118.173.100"


def test_cloudflare_ip_not_trusted_from_untrusted_upstream(monkeypatch, _clear_settings):
    """A direct public attacker forging CF-Connecting-IP is NOT believed, because
    their socket peer is neither loopback nor a Cloudflare edge range."""
    monkeypatch.setenv("BEHIND_CLOUDFLARE_TUNNEL", "true")
    get_settings.cache_clear()

    result = extract(
        x_forwarded_for=None,
        client_host="198.51.100.77",  # attacker's own public IP (not Cloudflare)
        cf_connecting_ip="10.0.0.1",  # forged
    )
    assert result == "198.51.100.77"  # falls back to the real socket peer


def test_x_forwarded_for_read_from_the_right(monkeypatch, _clear_settings):
    """With one trusted proxy, the client IP is the rightmost XFF entry (the one our
    proxy appended), never a client-prepended value."""
    monkeypatch.delenv("BEHIND_CLOUDFLARE_TUNNEL", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    get_settings.cache_clear()

    result = extract(x_forwarded_for="1.2.3.4, 5.6.7.8, 9.9.9.9", client_host="127.0.0.1")
    assert result == "9.9.9.9"


def test_x_forwarded_for_two_trusted_proxies(monkeypatch, _clear_settings):
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "2")
    get_settings.cache_clear()

    # attacker prepends "evil"; two real proxies append -> parts[-2] is the client.
    result = extract(x_forwarded_for="evil, 203.0.113.5, 10.0.0.2", client_host="127.0.0.1")
    assert result == "203.0.113.5"


def test_x_forwarded_for_shorter_than_trusted_count_falls_back_to_socket(monkeypatch, _clear_settings):
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "2")
    get_settings.cache_clear()

    result = extract(x_forwarded_for="1.2.3.4", client_host="203.0.113.9")
    assert result == "203.0.113.9"


def test_allowlist_accepts_real_ip_and_rejects_spoof(monkeypatch, db_session, client, _clear_settings):
    """THE PROOF: with an allowlist active, the real client (via the tunnel) is
    admitted and a direct spoofer is rejected."""
    monkeypatch.setenv("BEHIND_CLOUDFLARE_TUNNEL", "true")
    get_settings.cache_clear()

    org = bootstrap_org_user(client, email_prefix="ip-allow")
    org_id = uuid.UUID(org["organization_id"])

    # Allowlist the real client IP only.
    db_session.add(
        OrgIPAllowlist(
            organization_id=org_id,
            cidr_range="161.118.173.100/32",
            label="office",
            is_active=True,
            created_by=uuid.UUID(org["user_id"]),
        )
    )
    db_session.commit()

    svc = IPAllowlistService(db_session)

    # Legitimate request through the tunnel: real IP in CF-Connecting-IP, loopback peer.
    real_ip = extract(
        x_forwarded_for=LIVE_XFF,
        client_host=LIVE_SOCKET_PEER,
        cf_connecting_ip=LIVE_CF_CONNECTING_IP,
    )
    assert svc.is_ip_allowed(org_id=org_id, request_ip=real_ip) is True

    # Spoof attempt: attacker connects directly (public peer) and puts the allowed IP
    # in X-Forwarded-For and a forged CF-Connecting-IP. Extraction ignores both and
    # yields the attacker's real socket IP, which is not in the allowlist.
    spoof_ip = extract(
        x_forwarded_for="161.118.173.100",
        client_host="198.51.100.77",
        cf_connecting_ip="161.118.173.100",
    )
    assert spoof_ip == "198.51.100.77"
    assert svc.is_ip_allowed(org_id=org_id, request_ip=spoof_ip) is False
