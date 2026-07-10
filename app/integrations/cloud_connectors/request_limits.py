"""Request body size limit for cloud connector ingest endpoints.

Real findings from AWS/GCP/Azure/Okta/GitHub are small JSON documents (a few KB at
most). Without an explicit cap, a holder of a valid (or leaked) connector credential
could submit arbitrarily large payloads repeatedly to exhaust database storage/bandwidth
-- a resource-exhaustion vector distinct from (and not mitigated by) signature
verification, since a legitimately-signed oversized payload would otherwise be accepted
and stored verbatim.
"""

from fastapi import HTTPException, Request, status

MAX_INGEST_BODY_BYTES = 1_000_000  # 1 MB


def enforce_max_body_size_from_content_length(request: Request) -> None:
    """Reject before buffering the body if Content-Length already declares an oversized
    payload. This is a cheap pre-check; enforce_max_body_size below is the authoritative
    check against the actual bytes read (Content-Length can be absent or wrong)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            return
        if declared_size > MAX_INGEST_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Request body exceeds the {MAX_INGEST_BODY_BYTES} byte limit for connector ingest",
            )


def enforce_max_body_size(raw_body: bytes) -> None:
    if len(raw_body) > MAX_INGEST_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request body exceeds the {MAX_INGEST_BODY_BYTES} byte limit for connector ingest",
        )
