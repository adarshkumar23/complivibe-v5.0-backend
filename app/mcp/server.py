"""Read-only MCP server exposing compliance data: framework status, obligation counts,
and risk summary. Deliberately narrow scope — no state-changing tools are exposed; every
tool here only reads from the database via app.mcp.read_only_queries.

Run with: python -m app.mcp.server
"""

import uuid

from mcp.server.fastmcp import FastMCP

from app.db.session import get_session_maker
from app.mcp.read_only_queries import get_framework_status, get_obligation_counts, get_risk_summary

mcp = FastMCP("complivibe-compliance-readonly")


@mcp.tool()
def framework_status(organization_id: str, framework_code: str) -> dict:
    """Get the applicability/answer-completion status of a compliance framework for an
    organization (e.g. framework_code='INDIA_DPDP')."""
    session_maker = get_session_maker()
    with session_maker() as db:
        return get_framework_status(db, uuid.UUID(organization_id), framework_code)


@mcp.tool()
def obligation_counts(organization_id: str, framework_code: str) -> dict:
    """Get obligation counts (total/applicable/not_applicable/needs_review/unknown) for a
    compliance framework for an organization."""
    session_maker = get_session_maker()
    with session_maker() as db:
        return get_obligation_counts(db, uuid.UUID(organization_id), framework_code)


@mcp.tool()
def risk_summary(organization_id: str, business_unit_id: str | None = None) -> dict:
    """Get the organization's overall compliance/risk posture summary, optionally scoped
    to a business unit."""
    session_maker = get_session_maker()
    with session_maker() as db:
        return get_risk_summary(
            db,
            uuid.UUID(organization_id),
            uuid.UUID(business_unit_id) if business_unit_id else None,
        )


if __name__ == "__main__":
    mcp.run()
