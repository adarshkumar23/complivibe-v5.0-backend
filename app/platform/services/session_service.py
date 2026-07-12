from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.user_session import UserSession


class SessionService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def create_session(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        token_id: str,
        ip_address: str | None,
        user_agent: str | None,
        expires_at: datetime,
    ) -> UserSession:
        now = self.utcnow()
        row = UserSession(
            organization_id=org_id,
            user_id=user_id,
            token_id=token_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="active",
            created_at=now,
            last_active_at=now,
            expires_at=self._as_utc(expires_at),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _get_by_token_id(self, token_id: str) -> UserSession | None:
        return self.db.execute(select(UserSession).where(UserSession.token_id == token_id)).scalar_one_or_none()

    def validate_and_touch_session(self, token_id: str, *, touch_interval_minutes: int = 5) -> bool:
        """
        Validate token-backed session and opportunistically update last_active_at.

        Uses a single SELECT per authenticated request path. We only flush when
        state actually changes (expiry transition or stale activity heartbeat).
        """
        row = self._get_by_token_id(token_id)
        if row is None:
            return False

        now = self.utcnow()
        if row.status != "active":
            return False

        if self._as_utc(row.expires_at) <= now:
            row.status = "expired"
            row.revoked_at = now
            self.db.flush()
            return False

        if self._as_utc(row.last_active_at) < (now - timedelta(minutes=touch_interval_minutes)):
            row.last_active_at = now
            self.db.flush()

        return True

    def validate_session(self, token_id: str) -> bool:
        # Keep existing public method for compatibility with callers/tests.
        return self.validate_and_touch_session(token_id, touch_interval_minutes=10_000_000)

    def update_last_active(self, token_id: str) -> None:
        # Keep existing public method for compatibility with callers/tests.
        row = self._get_by_token_id(token_id)
        if row is None or row.status != "active":
            return

        now = self.utcnow()
        # Throttle writes to reduce write amplification on hot endpoints.
        if self._as_utc(row.last_active_at) >= (now - timedelta(minutes=1)):
            return
        row.last_active_at = now
        self.db.flush()

    def revoke_session_by_token_id(self, token_id: str) -> None:
        row = self._get_by_token_id(token_id)
        if row is None or row.status != "active":
            return
        row.status = "revoked"
        row.revoked_at = self.utcnow()
        self.db.flush()

    def revoke_session(self, *, org_id: uuid.UUID, session_id: uuid.UUID, revoked_by: uuid.UUID) -> UserSession:
        row = self.db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        if row.status != "revoked":
            row.status = "revoked"
            row.revoked_at = self.utcnow()
            row.revoked_by = revoked_by
            self.db.flush()
        return row

    def list_sessions(self, *, org_id: uuid.UUID, user_id: uuid.UUID) -> list[UserSession]:
        return list(
            self.db.execute(
                select(UserSession)
                .where(
                    UserSession.organization_id == org_id,
                    UserSession.user_id == user_id,
                )
                .order_by(UserSession.created_at.desc())
            ).scalars().all()
        )

    def expire_stale_sessions(self, *, org_id: uuid.UUID | None = None) -> int:
        now = self.utcnow()
        stmt = select(UserSession).where(
            UserSession.status == "active",
            UserSession.expires_at <= now,
        )
        if org_id is not None:
            stmt = stmt.where(UserSession.organization_id == org_id)

        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            row.status = "expired"
            row.revoked_at = now
        self.db.flush()
        return len(rows)

    def resolve_login_org_id(self, user_id: uuid.UUID, requested_org_id: uuid.UUID | None) -> uuid.UUID | None:
        if requested_org_id is not None:
            found = self.db.execute(
                select(Membership.id).where(
                    Membership.user_id == user_id,
                    Membership.organization_id == requested_org_id,
                    Membership.status == "active",
                )
            ).scalar_one_or_none()
            if found is not None:
                return requested_org_id

        return self.db.execute(
            select(Membership.organization_id)
            .where(
                Membership.user_id == user_id,
                Membership.status == "active",
            )
            .order_by(Membership.created_at.asc())
        ).scalar_one_or_none()
