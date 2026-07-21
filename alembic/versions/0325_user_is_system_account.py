"""users.is_system_account: mark non-human automation principals

Several core tables require a real users.id for authorship and offer no nullable path:
issues.owner_id and issues.created_by are NOT NULL FK users.id ON DELETE RESTRICT, and
ai_governance_reviews.created_by likewise. When core itself decides something -- a
monitoring threshold breached, so open an issue -- there is no human who did it.

Before this, core had no concept of a non-human principal at all: grep for system_user,
service_account, bot_user, is_system_user and user_type across app/ returned nothing
that applies to authentication principals (non_human_identities is an INVENTORY table
describing a customer's service accounts, not a principal that can own a row here).

Why a new column rather than reusing an existing one
----------------------------------------------------
- is_active must stay True and status must stay 'active', because
  IssueService._ensure_active_member requires both. So neither can mark it.
- is_superuser means "may act across tenants" -- the opposite of what this account is;
  it holds a zero-permission role.
There is genuinely nothing to reuse, so the flag is new.

Default false, NOT NULL: every existing row is a person, and a column that defaults to
"this is a robot" would be the wrong way round if a later insert forgot to set it.

Revision ID: 0325_user_is_system_account
Revises: 0324_org_governance_default_reviewer
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0325_user_is_system_account"
down_revision: str | None = "0324_org_governance_default_reviewer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "users"
COLUMN = "is_system_account"
INDEX_NAME = "ix_users_is_system_account"


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names() -> set[str]:
    return {c["name"] for c in _inspector().get_columns(TABLE)}


def _index_names() -> set[str]:
    return {i["name"] for i in _inspector().get_indexes(TABLE)}


def upgrade() -> None:
    if COLUMN in _column_names():
        return

    # server_default so the ALTER can set every existing row in one pass without a
    # separate backfill; every user that exists today is a person.
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Partial on PostgreSQL: system accounts are a handful of rows among all users, and
    # the interesting query is always "exclude them" / "find them". A partial index
    # stays tiny regardless of how many real users exist.
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            INDEX_NAME,
            TABLE,
            [COLUMN],
            postgresql_where=sa.text("is_system_account"),
        )
    else:
        op.create_index(INDEX_NAME, TABLE, [COLUMN])


def downgrade() -> None:
    if COLUMN not in _column_names():
        return
    if INDEX_NAME in _index_names():
        op.drop_index(INDEX_NAME, table_name=TABLE)
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
