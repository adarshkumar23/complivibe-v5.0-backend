"""FastAPI scoped-key auth dependencies for the P2 satellite endpoints.

Replaces P2's always-allow / plaintext-dict stubs. The satellite authenticates
purely by a Bearer scoped key; the ORGANIZATION IS DERIVED FROM THE KEY (not a
client-supplied header), so a satellite can never act on an org other than the
one its key was issued for.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
from app.core.deps import get_db


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed bearer token")
    return parts[1].strip()


def _require_scope(key_type: str, scope_code: str):
    def _dependency(
        db: Session = Depends(get_db),
        authorization: str | None = Header(default=None),
    ) -> uuid.UUID:
        token = _extract_bearer(authorization)
        org_id = PatentScopedKeyService(db).resolve_org_by_key(token, key_type)
        if org_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Scoped key missing {scope_code}"
            )
        return org_id

    return _dependency


def require_patent_export_scope():
    return _require_scope("export", "patent_export:p2:read")


def require_patent_ingest_scope():
    return _require_scope("ingest", "patent_ingest:p2:write")


def require_p4_ingest_scope():
    """Auth for the P4 monitoring satellite's inbound push.

    A DISTINCT key type from P2's, deliberately. Sharing one would mean a key leaked
    from either satellite authenticated both -- the shared-key hazard migration 0317
    exists to prevent. As with P2, the organisation is derived from the key and never
    from a client-supplied header, so a satellite can only ever write to the org its
    key was issued for.
    """
    return _require_scope("p4_ingest", "patent_ingest:p4:write")


def require_p9_ingest_scope():
    """Auth for the P9 contract-extraction satellite's inbound push.

    A DISTINCT key type again, for the reason spelled out in migration 0328: a
    key leaked from one satellite must not authenticate another. The
    organisation is derived from the key, never from a body field or an
    X-Organization-Id header, so a satellite can only ever register commitments
    against the org its key was issued for.

    That matters more here than for a metric push. A commitment created through
    this route becomes a live monitoring rule that fires on real incidents and
    notifies real customers, so a caller who could name its own org could
    manufacture a customer-facing obligation inside someone else's tenant.
    """
    return _require_scope("p9_ingest", "patent_ingest:p9:write")
