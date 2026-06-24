import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.membership import Membership
from app.models.membership_activation_token import MembershipActivationToken
from app.models.user import User


class ActivationTokenService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _is_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at < now

    def _expire_stale_tokens(self, membership_id: uuid.UUID) -> None:
        now = self._now()
        stmt = select(MembershipActivationToken).where(
            MembershipActivationToken.membership_id == membership_id,
            MembershipActivationToken.status == "active",
            MembershipActivationToken.expires_at < now,
        )
        for token in self.db.execute(stmt).scalars().all():
            token.status = "expired"

    def revoke_active_tokens_for_membership(self, membership_id: uuid.UUID) -> int:
        self._expire_stale_tokens(membership_id)
        now = self._now()
        stmt = select(MembershipActivationToken).where(
            MembershipActivationToken.membership_id == membership_id,
            MembershipActivationToken.status == "active",
        )
        tokens = self.db.execute(stmt).scalars().all()
        for token in tokens:
            token.status = "revoked"
            token.revoked_at = now
        self.db.flush()
        return len(tokens)

    def create_token(
        self,
        *,
        membership: Membership,
        user: User,
        created_by_user_id: uuid.UUID | None,
    ) -> tuple[MembershipActivationToken, str]:
        if membership.status == "inactive":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot issue token for inactive membership")

        self.revoke_active_tokens_for_membership(membership.id)

        raw_token = secrets.token_urlsafe(48)
        token_hash = self.hash_token(raw_token)
        expires_hours = get_settings().ACTIVATION_TOKEN_EXPIRE_HOURS
        expires_at = self._now() + timedelta(hours=expires_hours)

        token = MembershipActivationToken(
            organization_id=membership.organization_id,
            membership_id=membership.id,
            user_id=user.id,
            token_hash=token_hash,
            status="active",
            expires_at=expires_at,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(token)
        self.db.flush()
        return token, raw_token

    def get_active_status(self, membership_id: uuid.UUID) -> tuple[bool, MembershipActivationToken | None]:
        self._expire_stale_tokens(membership_id)
        stmt = (
            select(MembershipActivationToken)
            .where(
                MembershipActivationToken.membership_id == membership_id,
                MembershipActivationToken.status == "active",
            )
            .order_by(MembershipActivationToken.created_at.desc())
        )
        token = self.db.execute(stmt).scalars().first()
        return token is not None, token

    def consume_token_for_activation(self, raw_token: str) -> tuple[MembershipActivationToken, Membership, User]:
        token_hash = self.hash_token(raw_token)
        stmt = select(MembershipActivationToken).where(MembershipActivationToken.token_hash == token_hash)
        token = self.db.execute(stmt).scalar_one_or_none()
        if token is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid activation token")

        self._expire_stale_tokens(token.membership_id)
        self.db.flush()

        if token.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Activation token is not active")
        if self._is_expired(token.expires_at, self._now()):
            token.status = "expired"
            self.db.flush()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Activation token has expired")

        membership = self.db.execute(select(Membership).where(Membership.id == token.membership_id)).scalar_one_or_none()
        user = self.db.execute(select(User).where(User.id == token.user_id)).scalar_one_or_none()
        if membership is None or user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Activation token subject not found")
        if membership.status == "inactive":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Membership is inactive")

        return token, membership, user
