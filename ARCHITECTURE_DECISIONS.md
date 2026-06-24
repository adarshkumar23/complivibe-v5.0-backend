# ARCHITECTURE_DECISIONS

Initial Architecture Decision Records (ADRs) for CompliVibe v4.0 backend.

## ADR-001: Backend-only v4.0 rebuild while preserving existing frontend
- Status: Accepted
- Context: Backend v4.0 is being rebuilt from zero while an existing frontend already exists and must remain stable.
- Decision: Implement backend changes only and preserve frontend boundaries.
- Consequence: Backend contracts evolve safely without introducing frontend redesign risk.

## ADR-002: Multi-tenant architecture with organization_id scoping
- Status: Accepted
- Context: The platform is organization-based and must prevent cross-tenant data leakage.
- Decision: Use strict `organization_id` scoping for organization-owned records and APIs.
- Consequence: Tenant isolation becomes a default invariant across models, services, and endpoints.

## ADR-003: RBAC enforced server-side, not frontend-only
- Status: Accepted
- Context: Frontend gating alone cannot provide security guarantees.
- Decision: Enforce permission checks in backend dependencies/services for protected actions.
- Consequence: Unauthorized calls are blocked regardless of frontend behavior.

## ADR-004: Audit logs for privileged/compliance-significant actions
- Status: Accepted
- Context: Compliance workflows require traceability for sensitive operations.
- Decision: Write immutable-style audit records for privileged and governance-significant actions.
- Consequence: Operational accountability and historical forensics are available for review.

## ADR-005: Framework catalog uses safe coverage levels, no fake full coverage claims
- Status: Accepted
- Context: Regulatory content evolves and early-phase data is intentionally limited.
- Decision: Seed framework metadata with explicit coverage levels (e.g., metadata_only/starter) and avoid full-coverage claims.
- Consequence: Product behavior remains accurate and avoids overstatement of compliance posture.

## ADR-006: Internal email outbox before external provider integration
- Status: Accepted
- Context: Notification workflows are needed now, but provider selection/approval is not finalized.
- Decision: Build internal templates, outbox, delivery events, and manual transitions without provider connectivity.
- Consequence: Reliable internal workflow orchestration exists and provider coupling is deferred.

## ADR-007: Email provider integration requires explicit provider approval
- Status: Accepted
- Context: Provider choice has security, compliance, and operational impact.
- Decision: Do not integrate SES/SMTP/third-party email services without explicit approval.
- Consequence: No external email credentials or delivery assumptions are introduced prematurely.

## ADR-008: No hard deletes for sensitive compliance workflows; use status-based lifecycle
- Status: Accepted
- Context: Compliance operations require traceable lifecycle history.
- Decision: Prefer status transitions (active/inactive/archived/dead_letter/etc.) over hard deletes for sensitive entities.
- Consequence: Historical continuity is preserved for audits and incident review.

## ADR-009: Three-pillar domain separation
- Status: Accepted
- Context: CompliVibe v5.0 introduces three core domains with distinct responsibilities and ownership boundaries.
- Decision: Establish `compliance`, `ai_governance`, and `data_observability` as separate pillars, each with isolated routers, services, and models; require cross-pillar references to flow through the service layer only.
- Consequence: Domain coupling is reduced, internal boundaries become explicit, and incremental migration can proceed without direct module-level dependency sprawl.

## ADR-010: Data observability boundaries
- Status: Accepted
- Context: Observability capabilities are needed for governance visibility, but must avoid expanding into invasive or autonomous data operations.
- Decision: Constrain data observability to metadata and lineage tracking only; prohibit direct DB inspection of customer data and disallow automatic remediation actions.
- Consequence: Observability remains explainable and low-risk, preserving tenant privacy expectations and preventing unapproved operational interventions.

## ADR-011: Email provider decision
- Status: Accepted
- Context: Email workflows currently run through internal orchestration and external provider integration has not been approved.
- Decision: Keep the internal outbox as the only send path for now; do not integrate SES/SMTP/external providers until explicitly approved; require this ADR to be revisited before any provider integration begins.
- Consequence: Delivery architecture remains controlled and audit-friendly while deferring external provider risk and configuration complexity until a formal approval checkpoint.
