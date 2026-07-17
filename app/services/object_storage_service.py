"""Cloudflare R2 object storage for evidence files (S3-compatible API).

Env-configurable and gracefully inert, mirroring the Azure gpt-5.1 fallback
discipline: the service is "configured" ONLY when all four of R2_ACCOUNT_ID,
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME are populated. When
any is missing, callers get a clear StorageNotConfiguredError (surfaced as a 503
"storage not configured") -- never an import-time crash and never a hardcoded
credential. Constructing the service is always safe; the boto3 client is built
lazily on first real use so an unconfigured environment costs nothing.

Retrieval is via short-lived presigned GET URLs only (never public objects).
Tenant isolation is enforced in the key prefix itself: every object lives under
org/<organization_id>/evidence/<evidence_id>/..., and the key is always derived
server-side from the evidence row, never from client input.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from app.core.config import Settings, get_settings

PROVIDER_NAME = "cloudflare_r2"


class StorageNotConfiguredError(RuntimeError):
    """Raised when an object-storage operation is attempted without R2 credentials."""


class ObjectStorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = None  # lazily constructed; never built when unconfigured

    @property
    def is_configured(self) -> bool:
        s = self._settings
        return bool(
            s.R2_ACCOUNT_ID
            and s.R2_ACCESS_KEY_ID
            and s.R2_SECRET_ACCESS_KEY
            and s.R2_BUCKET_NAME
        )

    @property
    def bucket(self) -> str:
        return self._settings.R2_BUCKET_NAME

    def _endpoint_url(self) -> str:
        s = self._settings
        if s.R2_ENDPOINT_URL:
            return s.R2_ENDPOINT_URL
        return f"https://{s.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    def _get_client(self):
        if not self.is_configured:
            raise StorageNotConfiguredError(
                "Object storage (Cloudflare R2) is not configured; set "
                "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and "
                "R2_BUCKET_NAME to enable evidence file storage."
            )
        if self._client is None:
            # Imported here (not at module load) so the dependency is only touched
            # when storage is actually configured and used.
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url(),
                aws_access_key_id=self._settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=self._settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",  # R2 uses the "auto" region
                config=Config(signature_version="s3v4"),
            )
        return self._client

    @staticmethod
    def build_key(organization_id: uuid.UUID, evidence_id: uuid.UUID, filename: str | None) -> str:
        """Org-scoped, collision-free object key derived entirely server-side.

        Tenant isolation lives in the path prefix; the random uuid segment prevents
        overwrite/enumeration and the original extension is preserved for content
        negotiation on download.
        """
        suffix = ""
        if filename:
            suffix = PurePosixPath(filename).suffix.lower()[:16]
        return f"org/{organization_id}/evidence/{evidence_id}/{uuid.uuid4().hex}{suffix}"

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes at key; returns the R2/S3 ETag. Raises if unconfigured."""
        client = self._get_client()
        client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def generate_presigned_get_url(self, key: str, *, expires_in: int | None = None) -> str:
        """Short-lived signed GET URL for a single object. Raises if unconfigured."""
        client = self._get_client()
        ttl = expires_in or self._settings.R2_SIGNED_URL_TTL_SECONDS
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl,
        )

    def delete(self, key: str) -> None:
        client = self._get_client()
        client.delete_object(Bucket=self.bucket, Key=key)
