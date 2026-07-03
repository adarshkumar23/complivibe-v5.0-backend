from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.scheduler_logger import SchedulerJobLogger
from app.db.base import Base
from app.models.scheduler_run_log import SchedulerRunLog
from tests.helpers.auth_org import bootstrap_org_user


def test_a77_ai_governance_dashboard_shape_and_permissions(client):
    org = bootstrap_org_user(client, email_prefix="a77-owner")

    ok = client.get("/api/v1/ai-governance/dashboard", headers=org["org_headers"])
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["ai_systems_by_tier"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert payload["governance_coverage_pct"] == 0.0
    assert payload["outstanding_reviews_count"] == 0
    assert payload["policy_violations_count"] == 0
    assert payload["shadow_ai_detected_count"] == 0
    assert payload["high_risk_systems_without_approval"] == 0
    assert payload["monitoring_alerts_by_system"] == []
    assert payload["_pillar2_status"] == "not_yet_activated"

    no_auth = client.get("/api/v1/ai-governance/dashboard", headers={"X-Organization-ID": org["organization_id"]})
    assert no_auth.status_code == 401

    other_org_user = bootstrap_org_user(client, email_prefix="a77-other")
    non_member_headers = {
        "Authorization": f"Bearer {other_org_user['access_token']}",
        "X-Organization-ID": org["organization_id"],
    }
    forbidden = client.get("/api/v1/ai-governance/dashboard", headers=non_member_headers)
    assert forbidden.status_code == 403


def _local_session_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def test_a81_scheduler_job_logger_success_and_failure():
    SessionLocal = _local_session_factory()

    def success_job(*, db: Session):
        _ = db
        return {"records_processed": 7}

    success_result = SchedulerJobLogger.run_logged(
        job_name="unit_success_job",
        job_fn=success_job,
        db_session_factory=SessionLocal,
    )
    assert success_result == {"records_processed": 7}

    db = SessionLocal()
    try:
        success_row = db.query(SchedulerRunLog).filter(SchedulerRunLog.job_name == "unit_success_job").one()
        assert success_row.status == "completed"
        assert success_row.completed_at is not None
        assert success_row.records_processed == 7
    finally:
        db.close()

    def failing_job(*, db: Session):
        _ = db
        raise RuntimeError("x" * 1205)

    with pytest.raises(RuntimeError):
        SchedulerJobLogger.run_logged(
            job_name="unit_failure_job",
            job_fn=failing_job,
            db_session_factory=SessionLocal,
        )

    db = SessionLocal()
    try:
        failure_row = db.query(SchedulerRunLog).filter(SchedulerRunLog.job_name == "unit_failure_job").one()
        assert failure_row.status == "failed"
        assert failure_row.completed_at is not None
        assert failure_row.error_message is not None
        assert len(failure_row.error_message) == 1000
    finally:
        db.close()


class _FakeTrigger:
    def __str__(self) -> str:
        return "interval[0:01:00]"


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.next_run_time = datetime.now(UTC)
        self.trigger = _FakeTrigger()


class _FakeScheduler:
    def get_jobs(self):
        return [_FakeJob("issue_sla_breach_check")]


def test_a81_scheduler_admin_service_and_admin_endpoint_guard(client, db_session):
    from app.compliance.services.scheduler_admin_service import SchedulerAdminService

    db_session.add(
        SchedulerRunLog(
            job_name="issue_sla_breach_check",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="completed",
            records_processed=5,
        )
    )
    db_session.add(
        SchedulerRunLog(
            job_name="other_job",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="failed",
            records_processed=1,
            error_message="boom",
        )
    )
    db_session.commit()

    service = SchedulerAdminService(db_session)
    statuses = service.get_job_status(_FakeScheduler())
    assert statuses
    assert "job_id" in statuses[0]
    assert "next_run_time" in statuses[0]

    filtered = service.get_run_history(job_name="issue_sla_breach_check", limit=50)
    assert filtered
    assert all(row.job_name == "issue_sla_breach_check" for row in filtered)

    sample_id = filtered[0].id
    fetched = service.get_run_log(sample_id)
    assert fetched.id == sample_id

    admin = bootstrap_org_user(client, email_prefix="a81-admin")
    admin_jobs = client.get("/api/v1/admin/scheduler/jobs", headers=admin["org_headers"])
    assert admin_jobs.status_code == 200
    assert isinstance(admin_jobs.json(), list)

    other_org_user = bootstrap_org_user(client, email_prefix="a81-other")
    non_member_headers = {
        "Authorization": f"Bearer {other_org_user['access_token']}",
        "X-Organization-ID": admin["organization_id"],
    }
    forbidden = client.get("/api/v1/admin/scheduler/jobs", headers=non_member_headers)
    assert forbidden.status_code == 403


def test_scheduler_admin_survives_unstarted_apscheduler_job(db_session):
    """Regression test: a real APScheduler Job that hasn't been scheduled by a running
    scheduler yet has no `next_run_time` attribute at all (not just None) -- accessing it
    directly raises AttributeError. get_job_status must tolerate that instead of 500ing."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    from app.compliance.services.scheduler_admin_service import SchedulerAdminService

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(lambda: None, trigger=CronTrigger(hour=0, minute=10), id="unstarted_job")
    assert not hasattr(scheduler.get_jobs()[0], "next_run_time")

    service = SchedulerAdminService(db_session)
    statuses = service.get_job_status(scheduler)
    assert statuses
    assert statuses[0]["job_id"] == "unstarted_job"
    assert statuses[0]["next_run_time"] is None
