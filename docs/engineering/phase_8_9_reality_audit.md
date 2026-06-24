# Phase 8.9 Reality Audit

Date: 2026-06-22
Scope: CompliVibe v4.0 backend reality audit before Phase 9.0

## Executive summary
- Migration lineage is intact through `0081_governance_autopilot_noop_runner_events`; Alembic head matches expected.
- Repository is not in a Git working tree in this workspace (no `.git` found), so branch/remotes/default-branch/dirty-state are not discoverable here.
- Obligation content is inconsistent across sources: starter content packs have 1 obligation for each audited framework, while code seeding (`SeedService`) only seeds NIST AI RMF and GDPR obligations.
- AI system, governance, risk-assessment, and risk-classification architecture is present and extensive (models, APIs, services, tests).
- Risk/evidence/control/export/score snapshot architecture is present with linked models, APIs, services, and tests.
- RBAC currently has no permissions for `ai_bom`, `model_registry`, `datasets`, `prompts`, or `agents`.
- Phase 7/8 automation boundary is still no-op only: intent -> approval -> admission -> session -> handshake -> no-op runner event; no real execution path identified.
- Required test commands were run and failed during collection due to Python import-path environment issue (`ModuleNotFoundError: No module named 'tests'`).

## Repo / branch / migration status
- Git root: Not discoverable from this workspace.
- Current branch: Not discoverable (`fatal: not a git repository`).
- Git remotes: Not discoverable (`fatal: not a git repository`).
- Default branch: Not discoverable (no git metadata present).
- Dirty working tree: Not discoverable (no git metadata present).
- Alembic head command used: `.venv/bin/alembic heads`
- Alembic head result: `0081_governance_autopilot_noop_runner_events (head)`
- Expected head match (`0081_governance_autopilot_noop_runner_events`): Yes

## Obligation counts (audited frameworks)
Counts are reported separately by source, as requested.

| Framework | Seed file (`app/services/seed_service.py` `OBLIGATION_SEEDS`) | Content pack JSON (`app/content_packs/frameworks/*_starter.json`) | Migrations explicit data inserts | Test DB baseline (`tests/conftest.py` setup only) | Test DB after `SeedService.ensure_starter_obligations` |
|---|---:|---:|---:|---:|---:|
| EU AI Act | 0 | 1 | 0 | 0 | 0 |
| ISO 42001 | 0 | 1 | 0 | 0 | 0 |
| NIST AI RMF | 1 | 1 | 0 | 0 | 1 |
| India DPDP | 0 | 1 | 0 | 0 | 0 |
| GDPR | 1 | 1 | 0 | 0 | 1 |
| SOC 2 | 0 | 1 | 0 | 0 | 0 |

Notes:
- Seed file contains obligation rows only for NIST AI RMF and GDPR.
- Starter packs contain one obligation each for all six audited frameworks.
- Reviewed migration files create schema/indexes but do not add explicit obligation rows for these frameworks.
- Test fixture DB setup is schema-only; obligations appear only if/when seed logic is invoked.

## AI system architecture inventory

### AI systems / owners / lifecycle
- Models/tables:
  - `app/models/ai_system.py`
- Owner and lifecycle fields (model-level):
  - `business_owner_user_id`, `technical_owner_user_id`, `lifecycle_status`, `archived_at`, `archived_by_user_id`
- Endpoints:
  - `app/api/v1/ai_systems.py` (`POST/GET/PATCH /api/v1/ai-systems`, `GET /summary`, `POST /{ai_system_id}/archive`)
- Services:
  - `app/services/ai_system_service.py`
- Tests:
  - `tests/unit/test_ai_systems_phase50.py`

### AI system links (controls/evidence/risks)
- Models/tables:
  - `app/models/ai_system_control_link.py`
  - `app/models/ai_system_evidence_link.py`
  - `app/models/ai_system_risk_link.py`
- Endpoints:
  - `app/api/v1/ai_systems.py` (`/links/controls`, `/links/evidence`, `/links/risks`, unlink variants, `/links/summary`)
- Services:
  - `app/services/ai_system_service.py`
- Tests:
  - `tests/unit/test_ai_system_links_phase51.py`

### AI system governance reviews / attestations
- Models/tables:
  - `app/models/ai_system_governance_review.py`
  - `app/models/ai_system_governance_attestation.py`
- Endpoints:
  - `app/api/v1/ai_systems.py` (`/governance-reviews`, lifecycle actions, attestations create/list/verify, governance summary)
- Services:
  - `app/services/ai_system_service.py`
- Tests:
  - `tests/unit/test_ai_system_governance_phase52.py`

### AI governance scheduling / reminders / recurrence
- Models/tables:
  - `app/models/ai_system_governance_review_reminder_policy.py`
  - `app/models/ai_system_governance_review_event.py`
  - `app/models/ai_system_governance_review_recurrence_template.py`
- Endpoints:
  - `app/api/v1/ai_governance.py` (`/review-reminder-policies`, `/review-queue*`, `/review-events*`, `/review-schedule-summary`)
- Services:
  - `app/services/ai_system_governance_schedule_service.py`
  - `app/services/ai_system_governance_recurrence_service.py`
- Tests:
  - `tests/unit/test_ai_system_governance_schedule_phase53.py`
  - `tests/unit/test_ai_system_governance_recurrence_phase54.py`

### AI assessments (present)
- Models/tables:
  - `app/models/ai_system_risk_assessment.py`
  - `app/models/ai_system_risk_assessment_snapshot.py`
- Endpoints:
  - `app/api/v1/ai_governance.py` under `/ai-risk/assessments/*`
- Services:
  - `app/services/ai_system_risk_assessment_service.py`
- Tests:
  - `tests/unit/test_ai_system_risk_assessments_phase61.py`

### AI risk classification (present)
- Models/tables:
  - `app/models/ai_system_risk_classification_taxonomy_template.py`
  - `app/models/ai_system_risk_classification_record.py`
  - `app/models/ai_system_risk_classification_record_snapshot.py`
- Endpoints:
  - `app/api/v1/ai_governance.py` under `/ai-risk/classification-taxonomies/*`, `/ai-risk/assessments/{assessment_id}/classifications`, `/ai-risk/classifications/*`
- Services:
  - `app/services/ai_system_risk_assessment_service.py`
- Tests:
  - `tests/unit/test_ai_system_risk_classification_phase64.py`
  - `tests/unit/test_ai_system_risk_classification_review_signals_phase65.py`

## Risk / evidence / control architecture inventory

### Risk register / scoring / history
- Models/tables:
  - `app/models/risk.py`
  - `app/models/ai_system_risk_scoring_profile.py`
  - `app/models/ai_system_risk_assessment_snapshot.py`
  - `app/models/score_snapshot.py`
- Endpoints:
  - `app/api/v1/risks.py` (register CRUD, archive, accept, links)
  - `app/api/v1/scoring.py` (`/summary`, `/snapshots*`, `/methodology`)
  - `app/api/v1/ai_governance.py` (`/ai-risk/scoring-profiles*`, `/ai-risk/dimension-templates*`, `/ai-risk/assessments*`)
- Services:
  - `app/services/risk_service.py`
  - `app/services/scoring_service.py`
  - `app/services/ai_system_risk_assessment_service.py`
- Tests:
  - `tests/unit/test_risks_phase23.py`
  - `tests/unit/test_control_testing_and_scoring_phase27.py`
  - `tests/unit/test_ai_system_risk_scoring_profiles_phase62.py`

### Evidence metadata / evidence links
- Models/tables:
  - `app/models/evidence_item.py`
  - `app/models/evidence_control_link.py`
  - `app/models/risk_evidence_link.py`
  - `app/models/ai_system_evidence_link.py`
- Endpoints:
  - `app/api/v1/evidence.py` (CRUD/archive/review/links)
  - Risk and AI-system link endpoints in `app/api/v1/risks.py` and `app/api/v1/ai_systems.py`
- Services:
  - `app/services/evidence_service.py`
- Tests:
  - `tests/unit/test_evidence_phase22.py`

### Control library / control testing
- Models/tables:
  - `app/models/control.py`
  - `app/models/control_obligation_mapping.py`
  - `app/models/control_test_definition.py`
  - `app/models/control_test_run.py`
  - `app/models/risk_control_link.py`
- Endpoints:
  - `app/api/v1/controls.py`
  - `app/api/v1/control_tests.py`
- Services:
  - `app/services/control_service.py`
  - `app/services/control_test_service.py`
  - `app/services/control_recommendation_service.py`
- Tests:
  - `tests/unit/test_controls_phase21.py`
  - `tests/unit/test_control_testing_and_scoring_phase27.py`
  - `tests/unit/test_control_recommendations_phase36.py`

### Export / manifest integrity
- Models/tables:
  - `app/models/export_job.py`
  - `app/models/export_job_event.py`
  - `app/models/export_attestation.py`
  - `app/models/organization_governance_evidence_manifest.py`
  - `app/models/organization_governance_manifest_verification_event.py`
- Endpoints:
  - `app/api/v1/exports.py` (`/jobs*`, `/manifest`, `/verify`, `/attestations`, verification history, summary)
- Services:
  - `app/services/export_service.py`
- Tests:
  - `tests/unit/test_exports_phase30.py`
  - `tests/unit/test_signed_export_pages_helper.py`

## RBAC inventory

### Existing permission families relevant to requested domains
From `app/services/seed_service.py`:
- AI systems / AI governance: `ai_systems:read`, `ai_systems:write`, `ai_systems:admin`
- Risks: `risks:read`, `risks:write`
- Evidence: `evidence:read`, `evidence:write`
- Controls: `controls:read`, `controls:write`
- Reports: `reports:read`, `reports:write`, `reports:generate`
- Exports: `exports:read`, `exports:write`, `exports:run`, `exports:verify`
- Framework content: `framework_content:review`, `framework_content:promote`, plus `frameworks:read`, `frameworks:activate`
- Automation / governance autopilot boundary: `automation:read`, `automation:write`, `automation:execute`

### Default role mapping pattern (current)
- `owner`, `admin`: all permissions (`set(PERMISSIONS.keys())`)
- `compliance_manager`: broad write/execute scope including `ai_systems:*`, risk/evidence/control/report/export/automation/framework content
- `reviewer`: mostly read, limited write in selected areas, includes `ai_systems:read`
- `auditor`: read-only pattern with `ai_systems:read`, `audit_logs:read`, `exports:verify`
- `readonly`: read-only pattern including `ai_systems:read`

### Recommended placement for future permissions
Proposed additions and fit with current patterns:
- `ai_bom:read` -> owner/admin/compliance_manager/reviewer/auditor/readonly
- `ai_bom:write` -> owner/admin/compliance_manager
- `ai_bom:admin` -> owner/admin (optionally compliance_manager if consistent with `ai_systems:admin` governance policy)
- `model_registry:read` -> owner/admin/compliance_manager/reviewer/auditor/readonly
- `model_registry:write` -> owner/admin/compliance_manager
- `model_registry:admin` -> owner/admin (or +compliance_manager by policy)
- `datasets:read` -> owner/admin/compliance_manager/reviewer/auditor/readonly
- `datasets:write` -> owner/admin/compliance_manager
- `datasets:admin` -> owner/admin (or +compliance_manager by policy)
- `prompts:read` -> owner/admin/compliance_manager/reviewer/auditor/readonly
- `prompts:write` -> owner/admin/compliance_manager
- `prompts:admin` -> owner/admin (or +compliance_manager by policy)
- `agents:read` -> owner/admin/compliance_manager/reviewer/auditor/readonly
- `agents:write` -> owner/admin/compliance_manager
- `agents:admin` -> owner/admin (or +compliance_manager by policy)

Current gap: none of the above new permission keys exist yet.

## No-op automation boundary confirmation
Confirmed chain and boundary artifacts exist:
- Intent:
  - model `app/models/governance_autopilot_execution_intent.py`
  - endpoints in `app/api/v1/ai_governance.py` (`/autopilot/execution-intents*`)
- Approval:
  - models `app/models/governance_autopilot_execution_approval.py`, `..._vote.py`
  - endpoints `/autopilot/execution-intents/{intent_id}/approvals*`, approval vote/approve/reject/cancel
- Admission:
  - model `app/models/governance_autopilot_runner_admission.py`
  - endpoints `/autopilot/runner-simulations/{simulation_id}/admissions*`
- Session/lease:
  - model `app/models/governance_autopilot_runner_session.py`
  - endpoints `/autopilot/runner-admissions/{admission_id}/sessions*`
- Handshake:
  - model `app/models/governance_autopilot_runner_handshake.py`
  - endpoints `/autopilot/runner-sessions/{session_id}/handshakes*`
- No-op runner event:
  - model `app/models/governance_autopilot_noop_runner_event.py`
  - endpoints `/autopilot/runner-handshakes/{handshake_id}/noop-runner/events`, `/autopilot/noop-runner/*`

Evidence that no real execution exists:
- Contract and service payloads enforce no-op/non-execution flags and caveats:
  - `execution_allowed: False`, `noop_only: True`, dry-run-only/no external effects in `app/services/ai_system_risk_assessment_service.py` and `app/services/ai_governance_contract_service.py`
- Tests explicitly assert non-execution boundaries:
  - `tests/unit/test_ai_system_autopilot_execution_safety_phase79.py`
  - `tests/unit/test_ai_system_autopilot_noop_runner_integration_readiness_phase86.py`
- No connector/provider execution surface for GitHub/Jira/Slack/cloud providers was identified in this no-op chain.

## Test results
Commands executed exactly as requested:
1. `.venv/bin/pytest tests/unit`
2. `.venv/bin/pytest`

Results:
- Both commands failed during collection with the same environment/import issue.
- Primary failure: `ModuleNotFoundError: No module named 'tests'`
- Pytest summary for each command:
  - `75 errors during collection`
  - `2 warnings`
  - exit code `2`

Representative failing import:
- `from tests.helpers.auth_org import ...` in many unit test modules.

## Gaps and risks
- Source-of-truth gap in obligation content:
  - starter packs include obligations for all audited frameworks, but core seed obligations only include NIST AI RMF and GDPR.
- Repository metadata visibility gap:
  - no `.git` directory in this workspace path, so branch/remotes/default branch/dirty-state cannot be audited here.
- Test harness/environment gap:
  - collection fails before execution due to import-path setup (`tests` package resolution).
- Permission gap for upcoming AI Trust Layer modules:
  - no existing keys for BOM/model registry/datasets/prompts/agents.

## Recommended Phase 9.0 implementation scope (planning only)
Small, focused foundation only:
- Add `ai_system_boms` model + migration linked to `ai_systems` (tenant scoped).
- Add CRUD/list/detail/archive + summary endpoints (backend only).
- Enforce org scoping and archive constraints.
- Add RBAC keys: `ai_bom:read`, `ai_bom:write`, `ai_bom:admin` and role mappings consistent with current `ai_systems` pattern.
- Add audit actions: `ai_bom.created`, `ai_bom.updated`, `ai_bom.archived`.
- Add focused unit tests for happy path, tenant isolation, permissions, archive behavior, include_archived, summary.

## Explicit warning
No real connectors, no real email sending, and no real automation execution should be implemented before their planned phases. Maintain current no-op-only safety boundary for Phase 7/8 automation surfaces.
