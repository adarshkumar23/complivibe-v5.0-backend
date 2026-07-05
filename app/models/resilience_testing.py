from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ResilienceTest(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A DORA digital operational resilience test record.

    Cadence rules (see app/services/resilience_testing_service.py for the
    computation): Regulation (EU) 2022/2554 (DORA), Articles 24 and 26;
    Joint RTS on Threat-Led Penetration Testing, Commission Delegated
    Regulation (EU) 2025/1190.
    """

    __tablename__ = "resilience_tests"
    __table_args__ = (
        CheckConstraint(
            "test_type IN ('tabletop', 'simulation', 'threat_led_pen_test')",
            name="ck_resilience_tests_test_type",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
            name="ck_resilience_tests_status",
        ),
        CheckConstraint(
            "findings_count >= 0",
            name="ck_resilience_tests_findings_count_nonneg",
        ),
        Index(
            "ix_resilience_tests_org_type_scheduled",
            "organization_id",
            "test_type",
            "scheduled_date",
        ),
        Index(
            "ix_resilience_tests_org_status",
            "organization_id",
            "status",
        ),
    )

    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    results_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    owner_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
