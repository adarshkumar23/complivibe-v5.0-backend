"""compliance-bot webhooks: signature-only auth instead of internal Bearer JWT

Revision ID: 0281_compliance_bot_webhook_signature_auth
Revises: 0280_task_escalation_tier
Create Date: 2026-07-09 00:00:00.000001

The Slack/Teams slash-command webhook endpoints (/compliance-bot/slack/commands,
/compliance-bot/teams/commands) required an internal Bearer JWT + org membership
to call, same as every authenticated CompliVibe API endpoint. Real Slack/Teams
webhook traffic can never present that -- it can only present what the operator
configured in the Slack/Teams app (a shared secret used to sign the request), the
same signature-only pattern the Razorpay billing webhook and the Jira/Linear
issue-sync webhooks use. This adds:
  - organizations.compliance_bot_webhook_secret: the shared secret used to verify
    an HMAC-SHA256 signature over the raw request body, scoped per organization
    the same way issue-sync connections carry their own webhook_secret.
  - compliance_bot_subscriptions.platform_user_ref: the external Slack/Teams user
    identifier (Slack `user_id` / Teams `from_user_id`), so an inbound webhook
    request can resolve which CompliVibe user issued the command without a JWT.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0282_compliance_bot_webhook_signature_auth"
down_revision: str | None = "0281_task_escalation_tier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("compliance_bot_webhook_secret", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "compliance_bot_subscriptions",
        sa.Column("platform_user_ref", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_compliance_bot_subscriptions_org_platform_ref",
        "compliance_bot_subscriptions",
        ["organization_id", "platform", "platform_user_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_bot_subscriptions_org_platform_ref", table_name="compliance_bot_subscriptions")
    op.drop_column("compliance_bot_subscriptions", "platform_user_ref")
    op.drop_column("organizations", "compliance_bot_webhook_secret")
