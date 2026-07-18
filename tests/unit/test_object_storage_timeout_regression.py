"""Regression: the R2 boto3 client must have BOUNDED timeouts + retries.

Without them, boto3 defaults (60s connect x several retries) make a CONFIGURED-but-
unreachable R2 endpoint hang the request for minutes (measured 142s+), tying up the
gunicorn worker (availability/DoS gap found in the 2026-07-18 chaos pass). This test
fails if the timeouts are ever removed, so the hang can't silently reappear.

The read_timeout must stay GENEROUS enough for a legitimate large upload
(EVIDENCE_MAX_UPLOAD_BYTES = 25 MiB, possibly over a slow link) -- so this asserts a
bound, not an aggressively small value.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.object_storage_service import ObjectStorageService


def _configured_client(monkeypatch):
    s = get_settings()
    for k, v in {
        "R2_ACCOUNT_ID": "t",
        "R2_ACCESS_KEY_ID": "t",
        "R2_SECRET_ACCESS_KEY": "t",
        "R2_BUCKET_NAME": "complivibe-evidence-test",
        "R2_ENDPOINT_URL": "https://example.invalid",
    }.items():
        monkeypatch.setattr(s, k, v, raising=False)
    return ObjectStorageService(s)._get_client()


def test_r2_client_has_bounded_connect_timeout(monkeypatch):
    cfg = _configured_client(monkeypatch).meta.config
    # fast-fail an unreachable endpoint (the actual fix for the multi-minute hang).
    assert cfg.connect_timeout is not None, "connect_timeout must be set (else 60s default -> hang)"
    assert cfg.connect_timeout <= 10, f"connect_timeout too high: {cfg.connect_timeout}"


def test_r2_client_has_bounded_read_timeout(monkeypatch):
    cfg = _configured_client(monkeypatch).meta.config
    assert cfg.read_timeout is not None, "read_timeout must be set (else 60s default)"
    # bounded, but GENEROUS -- a legitimate 25 MiB upload over a slow link must not be
    # killed mid-transfer. Guard against both "unset" and "absurdly large".
    assert 30 <= cfg.read_timeout <= 120, f"read_timeout out of the generous-but-bounded range: {cfg.read_timeout}"


def test_r2_client_has_bounded_retries(monkeypatch):
    cfg = _configured_client(monkeypatch).meta.config
    assert cfg.retries is not None, "retries must be bounded (else default retry count)"
    total = cfg.retries.get("total_max_attempts") or cfg.retries.get("max_attempts")
    assert total is not None and total <= 3, f"retries not bounded: {cfg.retries}"
