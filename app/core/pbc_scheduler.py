import logging

from fastapi import FastAPI

try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional in local test environments
    sentry_sdk = None  # type: ignore[assignment]

from sqlalchemy import select

from app.compliance.services.audit_schedule_service import run_daily_audit_schedule_reminder_sweep
from app.compliance.services.customer_commitment_service import run_daily_customer_commitment_trigger_sweep
from app.compliance.services.escalation_service import run_daily_escalation_policy_evaluation
from app.compliance.services.breach_notification_service import run_daily_breach_notification_deadline_sweep
from app.compliance.services.vendor_mitigation_service import run_daily_vendor_mitigation_overdue_action_sweep
from app.compliance.services.pbc_service import run_daily_pbc_overdue_sweep
from app.compliance.services.pbc_request_service import run_daily_pbc_request_overdue_sweep
from app.compliance.services.control_exception_service import run_daily_control_exception_expiry_sweep
from app.compliance.services.subprocessor_service import run_daily_subprocessor_dpa_expiry_sweep
from app.compliance.services.sla_service import run_hourly_issue_sla_breach_check
from app.ai_governance.services.mlops_sync_service import run_daily_mlops_sync_sweep
from app.data_observability.services.lineage_service import run_daily_openmetadata_sync_sweep
from app.data_observability.services.retention_service import run_daily_data_retention_sweep
from app.data_observability.services.residency_service import run_daily_data_residency_sweep
from app.privacy.services.dsar_service import run_daily_dsr_sla_sweep
from app.privacy.services.consent_service import run_daily_consent_expiry_sweep
from app.privacy.services.dpa_service import run_daily_dpa_expiry_sweep
from app.services.regulatory_intelligence_service import run_daily_regulatory_change_poll
from app.compliance.services.digest_service import run_daily_digest_send_sweep, run_weekly_digest_send_sweep
from app.satellites.tprm_intelligence.sanctions_screening import (
    run_daily_sanctions_dataset_refresh,
    run_periodic_vendor_sanctions_rescreen_sweep,
)
from app.satellites.tprm_intelligence.security_rating_monitoring import run_daily_vendor_security_rating_continuous_refresh
from app.core.scheduler_logger import SchedulerJobLogger
from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models.organization import Organization
from app.platform.services.email_outbox_flush_service import EmailOutboxFlushService

logger = logging.getLogger(__name__)

SCHEDULER_JOB_IDS: list[str] = [
    "pbc_overdue_daily_sweep",
    "pbc_request_overdue_sweep",
    "audit_schedule_reminder_sweep",
    "audit_schedule_auto_create_sweep",
    "subprocessor_dpa_expiry_sweep",
    "policy_exception_expiry_sweep",
    "commitment_trigger_sweep",
    "mitigation_overdue_action_sweep",
    "issue_sla_breach_check",
    "escalation_policy_evaluation",
    "breach_notification_deadline_sweep",
    "mlops_daily_sync",
    "openmetadata_daily_sync",
    "data_retention_sweep",
    "data_residency_sweep",
    "email_outbox_flush",
    "dsr_sla_sweep",
    "consent_expiry_sweep",
    "dpa_expiry_sweep",
    "daily_digest_send",
    "weekly_digest_send",
    "control_exception_expiry_sweep",
    "regulatory_change_poll",
    "sanctions_dataset_refresh",
    "vendor_sanctions_rescreen_sweep",
    "vendor_security_rating_continuous_refresh",
]


def _capture_scheduler_exception(exc: Exception) -> None:
    settings = get_settings()
    if not settings.SENTRY_DSN or sentry_sdk is None:
        return
    sentry_sdk.capture_exception(exc)


def _records_from_result(result: dict | None) -> int | None:
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("records_processed"), int):
        return int(result["records_processed"])
    values = [value for value in result.values() if isinstance(value, int) and not isinstance(value, bool)]
    if not values:
        return None
    return int(sum(values))


def _run_sweep_job_internal(*, db) -> dict:
    try:
        marked = run_daily_pbc_overdue_sweep(db)
        db.commit()
        logger.info("PBC overdue sweep complete", extra={"items_marked": marked})
        return {"items_marked": marked, "records_processed": marked}
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("PBC overdue sweep failed")
        raise


def _run_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="pbc_overdue_daily_sweep",
        job_fn=_run_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_pbc_request_sweep_job_internal(*, db) -> dict:
    try:
        marked = run_daily_pbc_request_overdue_sweep(db)
        db.commit()
        logger.info("PBC request overdue sweep complete", extra={"items_marked": marked})
        return {"items_marked": marked, "records_processed": marked}
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("PBC request overdue sweep failed")
        raise


def _run_pbc_request_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="pbc_request_overdue_sweep",
        job_fn=_run_pbc_request_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_audit_schedule_reminder_job_internal(*, db) -> dict:
    try:
        result = run_daily_audit_schedule_reminder_sweep(db)
        db.commit()
        logger.info("Audit schedule reminder sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Audit schedule reminder sweep failed")
        raise


def _run_audit_schedule_reminder_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="audit_schedule_reminder_sweep",
        job_fn=_run_audit_schedule_reminder_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_audit_schedule_auto_create_job_internal(*, db) -> dict:
    try:
        from app.compliance.services.audit_schedule_service import run_daily_scheduled_audit_creation_sweep

        result = run_daily_scheduled_audit_creation_sweep(db)
        db.commit()
        logger.info("Audit schedule auto-create sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Audit schedule auto-create sweep failed")
        raise


def _run_audit_schedule_auto_create_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="audit_schedule_auto_create_sweep",
        job_fn=_run_audit_schedule_auto_create_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_subprocessor_dpa_expiry_job_internal(*, db) -> dict:
    try:
        result = run_daily_subprocessor_dpa_expiry_sweep(db)
        db.commit()
        logger.info("Subprocessor DPA expiry sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Subprocessor DPA expiry sweep failed")
        raise


def _run_subprocessor_dpa_expiry_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="subprocessor_dpa_expiry_sweep",
        job_fn=_run_subprocessor_dpa_expiry_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_policy_exception_expiry_job_internal(*, db) -> dict:
    try:
        from app.compliance.services.policy_exception_service import PolicyExceptionService

        expired = PolicyExceptionService(db).expire_overdue_exceptions()
        db.commit()
        logger.info("Policy exception expiry sweep complete", extra={"expired_count": expired})
        return {"expired_count": expired, "records_processed": expired}
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Policy exception expiry sweep failed")
        raise


def _run_policy_exception_expiry_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="policy_exception_expiry_sweep",
        job_fn=_run_policy_exception_expiry_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_commitment_trigger_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_customer_commitment_trigger_sweep(db)
        db.commit()
        logger.info("Customer commitment trigger sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Customer commitment trigger sweep failed")
        raise


def _run_commitment_trigger_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="commitment_trigger_sweep",
        job_fn=_run_commitment_trigger_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_mitigation_overdue_action_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_vendor_mitigation_overdue_action_sweep(db)
        db.commit()
        logger.info("Vendor mitigation overdue action sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Vendor mitigation overdue action sweep failed")
        raise


def _run_mitigation_overdue_action_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="mitigation_overdue_action_sweep",
        job_fn=_run_mitigation_overdue_action_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_issue_sla_breach_check_job_internal(*, db) -> dict:
    try:
        org_ids = [row.id for row in db.execute(select(Organization.id)).scalars().all()]
        total = {"response_breached": 0, "resolution_breached": 0, "notifications_queued": 0}
        for org_id in org_ids:
            result = run_hourly_issue_sla_breach_check(db, org_id)
            for key in total:
                total[key] += result.get(key, 0)
        db.commit()
        logger.info("Issue SLA breach check complete", extra=total)
        payload = dict(total)
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Issue SLA breach check failed")
        raise


def _run_issue_sla_breach_check_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="issue_sla_breach_check",
        job_fn=_run_issue_sla_breach_check_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_escalation_policy_evaluation_job_internal(*, db) -> dict:
    try:
        result = run_daily_escalation_policy_evaluation(db)
        db.commit()
        logger.info("Escalation policy evaluation complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Escalation policy evaluation failed")
        raise


def _run_escalation_policy_evaluation_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="escalation_policy_evaluation",
        job_fn=_run_escalation_policy_evaluation_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_breach_notification_deadline_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_breach_notification_deadline_sweep(db)
        db.commit()
        logger.info("Breach notification deadline sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Breach notification deadline sweep failed")
        raise


def _run_breach_notification_deadline_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="breach_notification_deadline_sweep",
        job_fn=_run_breach_notification_deadline_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_mlops_daily_sync_job_internal(*, db) -> dict:
    try:
        result = run_daily_mlops_sync_sweep(db)
        db.commit()
        logger.info("MLOps daily sync complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("MLOps daily sync failed")
        raise


def _run_mlops_daily_sync_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="mlops_daily_sync",
        job_fn=_run_mlops_daily_sync_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_openmetadata_daily_sync_job_internal(*, db) -> dict:
    try:
        result = run_daily_openmetadata_sync_sweep(db)
        db.commit()
        logger.info("OpenMetadata daily sync complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("OpenMetadata daily sync failed")
        raise


def _run_openmetadata_daily_sync_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="openmetadata_daily_sync",
        job_fn=_run_openmetadata_daily_sync_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_data_retention_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_data_retention_sweep(db)
        db.commit()
        logger.info("Data retention sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Data retention sweep failed")
        raise


def _run_data_retention_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="data_retention_sweep",
        job_fn=_run_data_retention_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_data_residency_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_data_residency_sweep(db)
        db.commit()
        logger.info("Data residency sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Data residency sweep failed")
        raise


def _run_data_residency_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="data_residency_sweep",
        job_fn=_run_data_residency_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_email_outbox_flush_job_internal(*, db) -> dict:
    try:
        result = EmailOutboxFlushService(db).flush()
        db.commit()
        logger.info("Email outbox flush complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Email outbox flush failed")
        raise


def _run_email_outbox_flush_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="email_outbox_flush",
        job_fn=_run_email_outbox_flush_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_dsr_sla_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_dsr_sla_sweep(db)
        db.commit()
        logger.info("DSR SLA sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("DSR SLA sweep failed")
        raise


def _run_dsr_sla_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="dsr_sla_sweep",
        job_fn=_run_dsr_sla_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_consent_expiry_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_consent_expiry_sweep(db)
        db.commit()
        logger.info("Consent expiry sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Consent expiry sweep failed")
        raise


def _run_consent_expiry_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="consent_expiry_sweep",
        job_fn=_run_consent_expiry_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_dpa_expiry_sweep_job_internal(*, db) -> dict:
    try:
        result = run_daily_dpa_expiry_sweep(db)
        db.commit()
        logger.info("DPA expiry sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("DPA expiry sweep failed")
        raise


def _run_dpa_expiry_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="dpa_expiry_sweep",
        job_fn=_run_dpa_expiry_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_daily_digest_send_job_internal(*, db) -> dict:
    try:
        result = run_daily_digest_send_sweep(db)
        db.commit()
        logger.info("Daily digest send sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Daily digest send sweep failed")
        raise


def _run_daily_digest_send_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="daily_digest_send",
        job_fn=_run_daily_digest_send_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_weekly_digest_send_job_internal(*, db) -> dict:
    try:
        result = run_weekly_digest_send_sweep(db)
        db.commit()
        logger.info("Weekly digest send sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Weekly digest send sweep failed")
        raise


def _run_weekly_digest_send_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="weekly_digest_send",
        job_fn=_run_weekly_digest_send_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_control_exception_expiry_job_internal(*, db) -> dict:
    try:
        result = run_daily_control_exception_expiry_sweep(db)
        db.commit()
        logger.info("Control exception expiry sweep complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Control exception expiry sweep failed")
        raise


def _run_control_exception_expiry_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="control_exception_expiry_sweep",
        job_fn=_run_control_exception_expiry_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_sanctions_dataset_refresh_job_internal(*, db) -> dict:
    try:
        result = run_daily_sanctions_dataset_refresh(db)
        db.commit()
        logger.info("Sanctions dataset refresh complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Sanctions dataset refresh failed")
        raise


def _run_sanctions_dataset_refresh_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="sanctions_dataset_refresh",
        job_fn=_run_sanctions_dataset_refresh_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_vendor_sanctions_rescreen_sweep_job_internal(*, db) -> dict:
    try:
        result = run_periodic_vendor_sanctions_rescreen_sweep(db)
        logger.info("Vendor sanctions rescreen sweep complete", extra=result)
        return result
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Vendor sanctions rescreen sweep failed")
        raise


def _run_vendor_sanctions_rescreen_sweep_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="vendor_sanctions_rescreen_sweep",
        job_fn=_run_vendor_sanctions_rescreen_sweep_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_vendor_security_rating_continuous_refresh_job_internal(*, db) -> dict:
    try:
        result = run_daily_vendor_security_rating_continuous_refresh(db)
        logger.info("Vendor security rating continuous refresh complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Vendor security rating continuous refresh failed")
        raise


def _run_vendor_security_rating_continuous_refresh_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="vendor_security_rating_continuous_refresh",
        job_fn=_run_vendor_security_rating_continuous_refresh_job_internal,
        db_session_factory=get_session_maker(),
    )


def _run_regulatory_change_poll_job_internal(*, db) -> dict:
    try:
        result = run_daily_regulatory_change_poll(db)
        db.commit()
        logger.info("Regulatory change poll complete", extra=result)
        payload = dict(result or {})
        payload.setdefault("records_processed", _records_from_result(payload))
        return payload
    except Exception as exc:
        db.rollback()
        _capture_scheduler_exception(exc)
        logger.exception("Regulatory change poll failed")
        raise


def _run_regulatory_change_poll_job() -> None:
    SchedulerJobLogger.run_logged(
        job_name="regulatory_change_poll",
        job_fn=_run_regulatory_change_poll_job_internal,
        db_session_factory=get_session_maker(),
    )


def register_pbc_scheduler(app: FastAPI) -> None:
    settings = get_settings()
    if settings.APP_ENV == "test":
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except Exception:
        logger.warning("APScheduler is not installed; PBC overdue sweep scheduler not started")
        return

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_sweep_job,
        trigger=CronTrigger(hour=0, minute=10),
        id="pbc_overdue_daily_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_audit_schedule_reminder_job,
        trigger=CronTrigger(hour=0, minute=20),
        id="audit_schedule_reminder_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_audit_schedule_auto_create_job,
        trigger=CronTrigger(hour=6, minute=0),
        id="audit_schedule_auto_create_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_subprocessor_dpa_expiry_job,
        trigger=CronTrigger(hour=0, minute=30),
        id="subprocessor_dpa_expiry_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_policy_exception_expiry_job,
        trigger=CronTrigger(hour=0, minute=30),
        id="policy_exception_expiry_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_commitment_trigger_sweep_job,
        trigger=CronTrigger(hour=0, minute=40),
        id="commitment_trigger_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_pbc_request_sweep_job,
        trigger=CronTrigger(hour=0, minute=45),
        id="pbc_request_overdue_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_mitigation_overdue_action_sweep_job,
        trigger=CronTrigger(hour=0, minute=50),
        id="mitigation_overdue_action_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_issue_sla_breach_check_job,
        trigger=IntervalTrigger(hours=1),
        id="issue_sla_breach_check",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_escalation_policy_evaluation_job,
        trigger=CronTrigger(hour=1, minute=0),
        id="escalation_policy_evaluation",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_breach_notification_deadline_sweep_job,
        trigger=CronTrigger(hour=1, minute=10),
        id="breach_notification_deadline_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_mlops_daily_sync_job,
        trigger=CronTrigger(hour=1, minute=20),
        id="mlops_daily_sync",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_openmetadata_daily_sync_job,
        trigger=CronTrigger(hour=1, minute=30),
        id="openmetadata_daily_sync",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_data_retention_sweep_job,
        trigger=CronTrigger(hour=1, minute=40),
        id="data_retention_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_data_residency_sweep_job,
        trigger=CronTrigger(hour=1, minute=50),
        id="data_residency_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_email_outbox_flush_job,
        trigger=IntervalTrigger(minutes=5),
        id="email_outbox_flush",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_dsr_sla_sweep_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="dsr_sla_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_consent_expiry_sweep_job,
        trigger=CronTrigger(hour=2, minute=10),
        id="consent_expiry_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_dpa_expiry_sweep_job,
        trigger=CronTrigger(hour=2, minute=20),
        id="dpa_expiry_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_daily_digest_send_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_digest_send",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_weekly_digest_send_job,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_digest_send",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_control_exception_expiry_job,
        trigger=CronTrigger(hour=2, minute=30),
        id="control_exception_expiry_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_regulatory_change_poll_job,
        trigger=CronTrigger(hour=2, minute=45),
        id="regulatory_change_poll",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_sanctions_dataset_refresh_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="sanctions_dataset_refresh",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_vendor_sanctions_rescreen_sweep_job,
        trigger=CronTrigger(hour=3, minute=10),
        id="vendor_sanctions_rescreen_sweep",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _run_vendor_security_rating_continuous_refresh_job,
        trigger=CronTrigger(hour=3, minute=15),
        id="vendor_security_rating_continuous_refresh",
        replace_existing=True,
        coalesce=True,
    )

    @app.on_event("startup")
    def _start_scheduler() -> None:
        if not scheduler.running:
            scheduler.start()

    @app.on_event("shutdown")
    def _shutdown_scheduler() -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)

    app.state.pbc_scheduler = scheduler  # type: ignore[attr-defined]
