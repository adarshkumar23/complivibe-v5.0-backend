from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.organization import Organization
from app.models.scim_token import ScimToken


def get_scim_organization(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> Organization:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SCIM requires Bearer token authentication",
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired SCIM token")

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)

    token_record = db.execute(
        select(ScimToken).where(
            ScimToken.token_hash == token_hash,
            ScimToken.is_active.is_(True),
            ScimToken.deleted_at.is_(None),
            or_(
                ScimToken.expires_at.is_(None),
                ScimToken.expires_at > now,
            ),
        )
    ).scalar_one_or_none()
    if token_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired SCIM token")

    token_record.last_used_at = now
    db.flush()

    org = db.execute(
        select(Organization).where(
            Organization.id == token_record.organization_id,
            Organization.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Organization not found or inactive")

    return org
