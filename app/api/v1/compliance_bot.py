import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
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


def _subscription_read(row, service: ComplianceBotService) -> ComplianceBotSubscriptionRead:
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
        platform_user_ref=row.platform_user_ref,
        context_flags=service.describe_subscription_context(row),
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
        idempotency_key=row.idempotency_key,
    )


@router.post("/subscriptions", response_model=ComplianceBotSubscriptionRead)
def upsert_subscription(
    payload: ComplianceBotSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:configure_subscription")),
) -> ComplianceBotSubscriptionRead:
    service = ComplianceBotService(db)
    row = service.upsert_subscription(
        organization_id=organization.id,
        user_id=current_user.id,
        platform=payload.platform,
        channel_ref=payload.channel_ref,
        is_active=payload.is_active,
        digest_enabled=payload.digest_enabled,
        digest_time_utc=payload.digest_time_utc,
        sla_alerts_enabled=payload.sla_alerts_enabled,
        actor_user_id=current_user.id,
        platform_user_ref=payload.platform_user_ref,
    )
    db.commit()
    db.refresh(row)
    return _subscription_read(row, service)


@router.get("/subscriptions", response_model=list[ComplianceBotSubscriptionRead])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_bot:list_subscriptions")),
) -> list[ComplianceBotSubscriptionRead]:
    service = ComplianceBotService(db)
    rows = service.list_subscriptions(organization.id, current_user.id)
    return [_subscription_read(row, service) for row in rows]


async def _require_org_by_id(db: Session, organization_id: uuid.UUID) -> Organization:
    organization = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


@router.post("/slack/commands/{organization_id}", response_model=ComplianceBotCommandResponse)
async def handle_slack_command(
    organization_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_compliancebot_signature: str | None = Header(default=None, alias="X-ComplianceBot-Signature"),
) -> ComplianceBotCommandResponse:
    # Real Slack slash-command traffic hits this endpoint directly and can never
    # present an internal Bearer JWT -- authenticity is established purely by an
    # HMAC-SHA256 signature over the raw body using the organization's own
    # compliance_bot_webhook_secret, the same signature-only pattern the Razorpay
    # and issue-sync webhooks use. The org is identified by the URL, not a header.
    organization = await _require_org_by_id(db, organization_id)
    raw_body = await request.body()
    ComplianceBotService.verify_webhook_signature(
        organization.compliance_bot_webhook_secret, raw_body=raw_body, signature=x_compliancebot_signature
    )
    payload = SlackSlashCommandPayload.model_validate_json(raw_body)
    service = ComplianceBotService(db)
    actor_user_id = service.resolve_actor_by_platform_ref(organization.id, "slack", payload.user_id or "")
    result = service.handle_command(
        organization_id=organization.id,
        actor_user_id=actor_user_id,
        platform="slack",
        command=payload.command,
        text=payload.text,
        idempotency_key=payload.trigger_id,
    )
    db.commit()
    return ComplianceBotCommandResponse(**result)


@router.post("/teams/commands/{organization_id}", response_model=ComplianceBotCommandResponse)
async def handle_teams_command(
    organization_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    x_compliancebot_signature: str | None = Header(default=None, alias="X-ComplianceBot-Signature"),
) -> ComplianceBotCommandResponse:
    organization = await _require_org_by_id(db, organization_id)
    raw_body = await request.body()
    ComplianceBotService.verify_webhook_signature(
        organization.compliance_bot_webhook_secret, raw_body=raw_body, signature=x_compliancebot_signature
    )
    payload = TeamsCommandPayload.model_validate_json(raw_body)
    service = ComplianceBotService(db)
    actor_user_id = service.resolve_actor_by_platform_ref(organization.id, "teams", payload.from_user_id or "")
    result = service.handle_command(
        organization_id=organization.id,
        actor_user_id=actor_user_id,
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
