from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.compliance_bot import (
    ComplianceBotCommandResponse,
    ComplianceBotOutboxRead,
    ComplianceBotSubscriptionCreate,
    ComplianceBotSubscriptionRead,
    ComplianceBotSweepResult,
    SlackSlashCommandPayload,
    TeamsCommandPayload,
)
from app.services.compliance_bot_service import ComplianceBotService

router = APIRouter(prefix="/compliance-bot", tags=["compliance-bot"])


def _subscription_read(row) -> ComplianceBotSubscriptionRead:
    return ComplianceBotSubscriptionRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        user_id=row.user_id,
        platform=row.platform,
        channel_ref=row.channel_ref,
        is_active=row.is_active,
        digest_enabled=row.digest_enabled,
        digest_time_utc=row.digest_time_utc,
        sla_alerts_enabled=row.sla_alerts_enabled,
        last_digest_sent_at=row.last_digest_sent_at,
        last_sla_alert_sent_at=row.last_sla_alert_sent_at,
        created_by_user_id=row.created_by_user_id,
    )


def _outbox_read(row) -> ComplianceBotOutboxRead:
    return ComplianceBotOutboxRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        subscription_id=row.subscription_id,
        message_type=row.message_type,
        status=row.status,
        command_text=row.command_text,
        content_text=row.content_text,
        payload_json=row.payload_json or {},
        scheduled_for=row.scheduled_for,
        sent_at=row.sent_at,
        failed_at=row.failed_at,
        error_message=row.error_message,
    )


@router.post("/subscriptions", response_model=ComplianceBotSubscriptionRead)
def upsert_subscription(
    payload: ComplianceBotSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:configure_subscription")),
) -> ComplianceBotSubscriptionRead:
    row = ComplianceBotService(db).upsert_subscription(
        organization_id=organization.id,
        user_id=current_user.id,
        platform=payload.platform,
        channel_ref=payload.channel_ref,
        is_active=payload.is_active,
        digest_enabled=payload.digest_enabled,
        digest_time_utc=payload.digest_time_utc,
        sla_alerts_enabled=payload.sla_alerts_enabled,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _subscription_read(row)


@router.get("/subscriptions", response_model=list[ComplianceBotSubscriptionRead])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:list_subscriptions")),
) -> list[ComplianceBotSubscriptionRead]:
    rows = ComplianceBotService(db).list_subscriptions(organization.id, current_user.id)
    return [_subscription_read(row) for row in rows]


@router.post("/slack/commands", response_model=ComplianceBotCommandResponse)
def handle_slack_command(
    payload: SlackSlashCommandPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:slack_command")),
) -> ComplianceBotCommandResponse:
    result = ComplianceBotService(db).handle_command(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        platform="slack",
        command=payload.command,
        text=payload.text,
    )
    db.commit()
    return ComplianceBotCommandResponse(**result)


@router.post("/teams/commands", response_model=ComplianceBotCommandResponse)
def handle_teams_command(
    payload: TeamsCommandPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:teams_command")),
) -> ComplianceBotCommandResponse:
    result = ComplianceBotService(db).handle_command(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        platform="teams",
        command="/complivibe",
        text=payload.text,
    )
    db.commit()
    return ComplianceBotCommandResponse(**result)


@router.post("/proactive/run-digest", response_model=ComplianceBotSweepResult)
def run_proactive_digest(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Organization = Depends(get_current_organization),
    ___: Membership = Depends(require_permission("compliance_bot:run_digest")),
) -> ComplianceBotSweepResult:
    payload = ComplianceBotService(db).run_daily_digest_dispatch()
    db.commit()
    return ComplianceBotSweepResult(**payload)


@router.post("/proactive/run-sla-alerts", response_model=ComplianceBotSweepResult)
def run_proactive_sla_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Organization = Depends(get_current_organization),
    ___: Membership = Depends(require_permission("compliance_bot:run_sla_alerts")),
) -> ComplianceBotSweepResult:
    payload = ComplianceBotService(db).run_sla_alert_dispatch()
    db.commit()
    return ComplianceBotSweepResult(**payload)


@router.get("/outbox/{platform}", response_model=list[ComplianceBotOutboxRead])
def list_outbox(
    platform: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:read_outbox")),
) -> list[ComplianceBotOutboxRead]:
    rows = ComplianceBotService(db).list_outbox(organization.id, current_user.id, platform, min(max(limit, 1), 200))
    return [_outbox_read(row) for row in rows]
