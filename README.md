# CompliVibe v4.0 Backend

Enterprise-grade backend foundation for CompliVibe using FastAPI, SQLAlchemy 2.x, PostgreSQL, Alembic, and Pydantic v2.

## Stack

- FastAPI (API layer)
- SQLAlchemy 2.x (ORM)
- Alembic (migrations)
- PostgreSQL (database)
- Pydantic v2 + pydantic-settings (config)
- pytest (tests)

## Engineering Traceability

- [Development Log](/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend/DEVELOPMENT_LOG.md)
- [Architecture Decisions](/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend/ARCHITECTURE_DECISIONS.md)
- Initialize Git before production collaboration or deployment promotion.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

2. Copy environment template and adjust values:

```bash
cp .env.example .env
```

3. Run the app:

```bash
uvicorn app.main:app --reload
```

## Environment Variables

- `APP_NAME`: service display name
- `APP_ENV`: runtime environment (`development`, `staging`, `production`, `test`)
- `API_V1_PREFIX`: API prefix, default `/api/v1`
- `DATABASE_URL`: SQLAlchemy PostgreSQL URL
- `SECRET_KEY`: JWT signing key (must be secure and private)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: token expiration
- `ACTIVATION_TOKEN_EXPIRE_HOURS`: invite activation token TTL (default 72)
- `BACKEND_CORS_ORIGINS`: comma-separated CORS origins

## Required local setup: Secrets vault

This project requires a running OpenBao/Vault-compatible dev server for local development and testing. Run `./scripts/setup_dev_vault.sh`, start the printed local dev server command, and add the resulting `VAULT_ADDR`/`VAULT_TOKEN` to your `.env` BEFORE running tests or starting the server. Without this, any feature touching encrypted secrets (SES email, OIDC/SSO, PAM sessions, security scan ingestion, carbon accounting API keys, and others) will fail with `SecretsBackendError`.

```bash
chmod +x scripts/setup_dev_vault.sh
./scripts/setup_dev_vault.sh
```

In a separate terminal, start the printed local OpenBao command:

```bash
.dev_vault/bin/bao server -dev -dev-listen-address=127.0.0.1:8210 -dev-root-token-id=dev-root-token
```

Add the printed values to `.env`:

```bash
VAULT_ADDR=http://127.0.0.1:8210
VAULT_TOKEN=dev-root-token
```

## Run Tests

```bash
pytest
```

## Migrations

Create migration:

```bash
alembic revision -m "your_migration_name"
```

Apply migrations:

```bash
alembic upgrade head
```

## API Health Endpoints

- `GET /health`
- `GET /api/v1/health`

## Auth and Tenant Foundation Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/organizations/me`
- `GET /api/v1/organizations/me/governance-settings`
- `PATCH /api/v1/organizations/me/governance-settings`
- `POST /api/v1/organizations/me/governance-settings/apply-to-open-batch-runs`
- `GET /api/v1/organizations/me/governance-settings/history`
- `GET /api/v1/organizations/me/governance-settings/history/{history_id}`
- `GET /api/v1/organizations/me/governance-settings/timeline`
- `GET /api/v1/organizations/me/governance-settings/diff`
- `GET /api/v1/organizations/me/governance-settings/evidence-bundle`
- `POST /api/v1/organizations/me/governance-settings/evidence-manifests`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}`
- `POST /api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verification-events`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests/verification-events`
- `POST /api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export`
- `POST /api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export/verify-page`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/chain-of-custody`
- `GET /api/v1/organizations/me/governance-settings/evidence-manifests/verification-summary`
- `POST /api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke`
- `GET /api/v1/organizations/me/governance-settings/signing-keys`
- `GET /api/v1/organizations/me/governance-settings/signing-keys/summary`
- `POST /api/v1/organizations/me/governance-settings/signing-keys/rotate`
- `POST /api/v1/organizations/me/governance-settings/signing-keys/{key_id}/deprecate`
- `POST /api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke`
- `GET /api/v1/organizations/{organization_id}`
- `PATCH /api/v1/organizations/{organization_id}`
- `GET /api/v1/audit-logs`
- `GET /api/v1/memberships`
- `GET /api/v1/memberships/{membership_id}`
- `POST /api/v1/memberships`
- `PATCH /api/v1/memberships/{membership_id}/role`
- `PATCH /api/v1/memberships/{membership_id}/deactivate`
- `GET /api/v1/roles`
- `GET /api/v1/auth/permissions`
- `POST /api/v1/ai-systems`
- `GET /api/v1/ai-systems`
- `GET /api/v1/ai-systems/{ai_system_id}`
- `PATCH /api/v1/ai-systems/{ai_system_id}`
- `POST /api/v1/ai-systems/{ai_system_id}/archive`
- `GET /api/v1/ai-systems/summary`
- `POST /api/v1/ai-systems/{ai_system_id}/links/controls`
- `GET /api/v1/ai-systems/{ai_system_id}/links/controls`
- `POST /api/v1/ai-systems/{ai_system_id}/links/controls/{link_id}/unlink`
- `POST /api/v1/ai-systems/{ai_system_id}/links/evidence`
- `GET /api/v1/ai-systems/{ai_system_id}/links/evidence`
- `POST /api/v1/ai-systems/{ai_system_id}/links/evidence/{link_id}/unlink`
- `POST /api/v1/ai-systems/{ai_system_id}/links/risks`
- `GET /api/v1/ai-systems/{ai_system_id}/links/risks`
- `POST /api/v1/ai-systems/{ai_system_id}/links/risks/{link_id}/unlink`
- `GET /api/v1/ai-systems/{ai_system_id}/links/summary`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews`
- `GET /api/v1/ai-systems/{ai_system_id}/governance-reviews`
- `GET /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/start`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/complete`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/cancel`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/schedule`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations`
- `GET /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations`
- `POST /api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations/{attestation_id}/verify`
- `GET /api/v1/ai-systems/{ai_system_id}/governance-summary`
- `POST /api/v1/ai-governance/review-reminder-policies`
- `GET /api/v1/ai-governance/review-reminder-policies`
- `PATCH /api/v1/ai-governance/review-reminder-policies/{policy_id}`
- `POST /api/v1/ai-governance/review-reminder-policies/{policy_id}/archive`
- `GET /api/v1/ai-governance/review-queue`
- `POST /api/v1/ai-governance/review-queue/evaluate-schedules`
- `GET /api/v1/ai-governance/review-events`
- `POST /api/v1/ai-governance/review-events/{event_id}/resolve`
- `GET /api/v1/ai-governance/review-schedule-summary`
- `POST /api/v1/ai-governance/review-recurrence-templates`
- `GET /api/v1/ai-governance/review-recurrence-templates`
- `PATCH /api/v1/ai-governance/review-recurrence-templates/{template_id}`
- `POST /api/v1/ai-governance/review-recurrence-templates/{template_id}/archive`
- `POST /api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan`
- `GET /api/v1/ai-governance/review-plan-runs`
- `GET /api/v1/ai-governance/review-plan-runs/{run_id}`
- `GET /api/v1/ai-governance/review-recurrence-summary`
- `POST /api/v1/ai-governance/review-plan-constraints`
- `GET /api/v1/ai-governance/review-plan-constraints`
- `PATCH /api/v1/ai-governance/review-plan-constraints/{constraint_id}`
- `POST /api/v1/ai-governance/review-plan-constraints/{constraint_id}/archive`
- `GET /api/v1/ai-governance/review-plan-constraints/summary`
- `POST /api/v1/ai-governance/review-sequence-packs`
- `GET /api/v1/ai-governance/review-sequence-packs`
- `PATCH /api/v1/ai-governance/review-sequence-packs/{pack_id}`
- `POST /api/v1/ai-governance/review-sequence-packs/{pack_id}/archive`
- `POST /api/v1/ai-governance/review-sequence-packs/{pack_id}/steps`
- `GET /api/v1/ai-governance/review-sequence-packs/{pack_id}/steps`
- `PATCH /api/v1/ai-governance/review-sequence-packs/{pack_id}/steps/{step_id}`
- `POST /api/v1/ai-governance/review-sequence-packs/{pack_id}/steps/{step_id}/archive`
- `POST /api/v1/ai-governance/review-sequence-packs/{pack_id}/generate-sequence`
- `GET /api/v1/ai-governance/review-sequence-runs`
- `GET /api/v1/ai-governance/review-sequence-runs/{run_id}`
- `GET /api/v1/ai-governance/review-sequence-summary`
- `POST /api/v1/ai-governance/guardrails/freeze-windows`
- `GET /api/v1/ai-governance/guardrails/freeze-windows`
- `PATCH /api/v1/ai-governance/guardrails/freeze-windows/{freeze_window_id}`
- `POST /api/v1/ai-governance/guardrails/freeze-windows/{freeze_window_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-sets`
- `GET /api/v1/ai-governance/guardrails/policy-sets`
- `PATCH /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}`
- `POST /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions`
- `GET /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions`
- `POST /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions/{version_id}/activate`
- `GET /api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/active-profile`
- `GET /api/v1/ai-governance/guardrails/policy-sets/summary`
- `POST /api/v1/ai-governance/guardrails/policy-assignments`
- `GET /api/v1/ai-governance/guardrails/policy-assignments`
- `PATCH /api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}`
- `POST /api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}/history`
- `POST /api/v1/ai-governance/guardrails/policy-assignments/resolve`
- `GET /api/v1/ai-governance/guardrails/policy-assignments/summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/simulate`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-reason-codes`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/classify`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pin-version`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/unpin-version`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pinning-status`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/history`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/health-diagnostics`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-summary`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-report-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/export`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/revoke`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-summary`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reason-codes`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/compare`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pin-version`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/unpin-version`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pinning-status`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-preset`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments`
- `PATCH /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/history`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/resolve`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-default-preset`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-diagnostics`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/health-diagnostics`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-summary`
- `GET /api/v1/ai-governance/contracts/phase5`
- `GET /api/v1/ai-governance/contracts/phase5/compatibility-summary`
- `GET /api/v1/ai-governance/contracts/phase5/{group_key}`
- `GET /api/v1/ai-governance/contracts/phase6`
- `POST /api/v1/ai-governance/ai-risk/assessments`
- `GET /api/v1/ai-governance/ai-risk/assessments`
- `GET /api/v1/ai-governance/ai-risk/assessments/summary`
- `GET /api/v1/ai-governance/ai-risk/assessments/{assessment_id}`
- `PATCH /api/v1/ai-governance/ai-risk/assessments/{assessment_id}`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/submit-for-review`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/complete`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/archive`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/recalculate-score`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/apply-dimension-template`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/preview-residual-risk`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/apply-residual-risk`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/snapshots`
- `GET /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/snapshots`
- `GET /api/v1/ai-governance/ai-risk/assessment-snapshots/{snapshot_id}`
- `POST /api/v1/ai-governance/ai-risk/scoring-profiles`
- `GET /api/v1/ai-governance/ai-risk/scoring-profiles`
- `GET /api/v1/ai-governance/ai-risk/scoring-profiles/summary`
- `GET /api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}`
- `PATCH /api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}`
- `POST /api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/archive`
- `POST /api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/set-default`
- `POST /api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/preview-score`
- `POST /api/v1/ai-governance/ai-risk/dimension-templates`
- `GET /api/v1/ai-governance/ai-risk/dimension-templates`
- `GET /api/v1/ai-governance/ai-risk/dimension-templates/summary`
- `GET /api/v1/ai-governance/ai-risk/dimension-templates/{template_id}`
- `PATCH /api/v1/ai-governance/ai-risk/dimension-templates/{template_id}`
- `POST /api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/archive`
- `POST /api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/set-default`
- `POST /api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/preview-score`
- `POST /api/v1/ai-governance/ai-risk/classification-taxonomies`
- `GET /api/v1/ai-governance/ai-risk/classification-taxonomies`
- `GET /api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}`
- `PATCH /api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}`
- `POST /api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}/archive`
- `POST /api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}/set-default`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications`
- `GET /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications`
- `GET /api/v1/ai-governance/ai-risk/classifications/summary`
- `GET /api/v1/ai-governance/ai-risk/classifications/{classification_id}`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/archive`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/submit-for-review`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/request-changes`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/mark-reviewed`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/reject`
- `POST /api/v1/ai-governance/ai-risk/classifications/{classification_id}/snapshots`
- `GET /api/v1/ai-governance/ai-risk/classifications/{classification_id}/snapshots`
- `GET /api/v1/ai-governance/ai-risk/classification-snapshots/{snapshot_id}`
- `POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/refresh-classification-signals`
- `GET /api/v1/ai-governance/signals`
- `GET /api/v1/ai-governance/signals/{signal_id}`
- `GET /api/v1/ai-governance/signals/prioritized`
- `GET /api/v1/ai-governance/signals/groups`
- `GET /api/v1/ai-governance/signals/priority-summary`
- `GET /api/v1/ai-governance/signals/{signal_id}/priority-explanation`
- `POST /api/v1/ai-governance/signals/{signal_id}/resolve`
- `POST /api/v1/ai-governance/signals/{signal_id}/dismiss`
- `GET /api/v1/ai-governance/signals/summary`
- `GET /api/v1/ai-governance/ai-systems/{ai_system_id}/attention`
- `GET /api/v1/ai-governance/actions/templates`
- `GET /api/v1/ai-governance/actions/candidates`
- `GET /api/v1/ai-governance/actions/candidates/explain`
- `GET /api/v1/ai-governance/actions/candidate-summary`
- `GET /api/v1/ai-governance/ai-systems/{ai_system_id}/candidate-actions`
- `GET /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/candidate-actions`
- `POST /api/v1/ai-governance/recommendations/snapshots/preview`
- `POST /api/v1/ai-governance/recommendations/snapshots`
- `GET /api/v1/ai-governance/recommendations/snapshots`
- `GET /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}`
- `GET /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/diff`
- `GET /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions`
- `GET /api/v1/ai-governance/recommendations/snapshots/latest`
- `GET /api/v1/ai-governance/recommendations/snapshots/summary`
- `POST /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/acknowledge`
- `POST /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/dismiss`
- `POST /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/defer`
- `POST /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/accept-for-manual-work`
- `GET /api/v1/ai-governance/recommendations/action-dispositions`
- `GET /api/v1/ai-governance/recommendations/action-dispositions/summary`
- `GET /api/v1/ai-governance/copilot/draft-types`
- `POST /api/v1/ai-governance/copilot/drafts/preview`
- `GET /api/v1/ai-governance/ai-systems/{ai_system_id}/copilot-brief`
- `GET /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/copilot-brief`
- `GET /api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/copilot-summary`
- `GET /api/v1/ai-governance/copilot/executive-risk-summary`
- `POST /api/v1/ai-governance/copilot/draft-snapshots/preview`
- `POST /api/v1/ai-governance/copilot/draft-snapshots`
- `GET /api/v1/ai-governance/copilot/draft-snapshots`
- `GET /api/v1/ai-governance/copilot/draft-snapshots/{snapshot_id}`
- `GET /api/v1/ai-governance/copilot/draft-snapshots/{snapshot_id}/diff`
- `GET /api/v1/ai-governance/copilot/draft-snapshots/latest`
- `GET /api/v1/ai-governance/copilot/draft-snapshots/summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/summary`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}`
- `POST /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}/archive`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-summary`
- `GET /api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-summary`
- `POST /api/v1/ai-governance/guardrails/check`
- `POST /api/v1/ai-governance/guardrails/resolve-conflicts`
- `GET /api/v1/ai-governance/guardrails/operator-acknowledgements`
- `GET /api/v1/ai-governance/guardrails/summary`
- `POST /api/v1/memberships/{membership_id}/activation-token`
- `POST /api/v1/memberships/{membership_id}/activation-token/revoke`
- `GET /api/v1/memberships/{membership_id}/activation-token/status`
- `POST /api/v1/auth/activate-invite`
- `GET /api/v1/frameworks`
- `GET /api/v1/frameworks/{framework_id}`
- `GET /api/v1/frameworks/active`
- `POST /api/v1/frameworks/{framework_id}/activate`
- `POST /api/v1/frameworks/{framework_id}/deactivate`
- `GET /api/v1/frameworks/{framework_id}/versions`
- `POST /api/v1/frameworks/{framework_id}/versions`
- `GET /api/v1/frameworks/{framework_id}/sections`
- `POST /api/v1/frameworks/{framework_id}/sections`
- `POST /api/v1/frameworks/{framework_id}/applicability-questions`
- `GET /api/v1/frameworks/{framework_id}/applicability-questions`
- `POST /api/v1/frameworks/{framework_id}/applicability-answers`
- `GET /api/v1/frameworks/{framework_id}/applicability-answers`
- `POST /api/v1/frameworks/{framework_id}/applicability/evaluate`
- `GET /api/v1/frameworks/{framework_id}/applicability/evaluations`
- `GET /api/v1/frameworks/{framework_id}/applicability/evaluations/{run_id}`
- `GET /api/v1/frameworks/{framework_id}/applicability/summary`
- `GET /api/v1/frameworks/{framework_id}/content-summary`
- `POST /api/v1/frameworks/{framework_id}/content-imports/preview`
- `POST /api/v1/frameworks/{framework_id}/content-imports/apply`
- `POST /api/v1/frameworks/{framework_id}/coverage-report`
- `GET /api/v1/frameworks/{framework_id}/coverage-reports`
- `GET /api/v1/frameworks/{framework_id}/coverage-gaps`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews`
- `GET /api/v1/frameworks/{framework_id}/pack-reviews`
- `GET /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments`
- `GET /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments`
- `POST /api/v1/frameworks/{framework_id}/pack-promotions/preflight`
- `POST /api/v1/frameworks/{framework_id}/pack-promotions`
- `GET /api/v1/frameworks/{framework_id}/pack-promotions`
- `POST /api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/approve`
- `POST /api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/reject`
- `POST /api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/execute`
- `GET /api/v1/frameworks/{framework_id}/review-summary`
- `GET /api/v1/framework-review-queue/my`
- `GET /api/v1/framework-review-queue`
- `GET /api/v1/framework-review-queue/summary`
- `POST /api/v1/framework-review-queue/evaluate-sla`
- `POST /api/v1/framework-review-assignments/{assignment_id}/accept`
- `POST /api/v1/framework-review-assignments/{assignment_id}/complete`
- `POST /api/v1/framework-review-assignments/{assignment_id}/cancel`
- `POST /api/v1/framework-review-sla-policies`
- `GET /api/v1/framework-review-sla-policies`
- `PATCH /api/v1/framework-review-sla-policies/{policy_id}`
- `POST /api/v1/framework-review-sla-policies/{policy_id}/archive`
- `GET /api/v1/framework-review-escalations`
- `POST /api/v1/framework-review-escalations/{event_id}/resolve`
- `POST /api/v1/framework-review-capacity/policies`
- `GET /api/v1/framework-review-capacity/policies`
- `PATCH /api/v1/framework-review-capacity/policies/{policy_id}`
- `POST /api/v1/framework-review-capacity/policies/{policy_id}/archive`
- `POST /api/v1/framework-review-capacity/workload/calculate`
- `GET /api/v1/framework-review-capacity/workload`
- `GET /api/v1/framework-review-capacity/summary`
- `POST /api/v1/framework-review-capacity/simulations/policy`
- `POST /api/v1/framework-review-capacity/simulations/review-waves`
- `GET /api/v1/framework-review-capacity/simulations/summary`
- `POST /api/v1/framework-review-capacity/batch-assignments/validate`
- `POST /api/v1/framework-review-capacity/batch-assignments/apply`
- `GET /api/v1/framework-review-capacity/batch-assignments/runs`
- `GET /api/v1/framework-review-capacity/batch-assignments/runs/{run_id}`
- `POST /api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/cancel`
- `GET /api/v1/framework-review-capacity/batch-assignments/summary`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/generate`
- `GET /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions`
- `POST /api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/simulate`
- `POST /api/v1/framework-review-assignment-suggestions/{suggestion_id}/apply`
- `POST /api/v1/framework-review-assignment-suggestions/{suggestion_id}/dismiss`
- `GET /api/v1/framework-content/packs`
- `POST /api/v1/framework-content/packs/{pack_key}/validate`
- `POST /api/v1/framework-content/packs/{pack_key}/apply`
- `GET /api/v1/framework-content/coverage-summary`
- `GET /api/v1/frameworks/{framework_id}/obligations`
- `GET /api/v1/obligations/{obligation_id}`
- `POST /api/v1/obligations/{obligation_id}/applicability-rules`
- `GET /api/v1/obligations/{obligation_id}/applicability-rules`
- `POST /api/v1/obligations/{obligation_id}/applicability-rules/{rule_id}/archive`
- `GET /api/v1/obligations/{obligation_id}/applicability-status`
- `POST /api/v1/obligations/{obligation_id}/content-versions`
- `GET /api/v1/obligations/{obligation_id}/content-versions`
- `POST /api/v1/obligations/{obligation_id}/evidence-requirements`
- `GET /api/v1/obligations/{obligation_id}/evidence-requirements`
- `POST /api/v1/obligations/{obligation_id}/control-suggestions`
- `GET /api/v1/obligations/{obligation_id}/control-suggestions`
- `POST /api/v1/obligations/{obligation_id}/control-suggestions/{suggestion_id}/apply`
- `PATCH /api/v1/obligations/{obligation_id}/state`
- `GET /api/v1/controls`
- `POST /api/v1/controls`
- `GET /api/v1/controls/{control_id}`
- `PATCH /api/v1/controls/{control_id}`
- `PATCH /api/v1/controls/{control_id}/archive`
- `POST /api/v1/controls/{control_id}/tests`
- `GET /api/v1/controls/{control_id}/tests`
- `GET /api/v1/controls/{control_id}/test-runs`
- `PATCH /api/v1/control-tests/{test_id}`
- `POST /api/v1/control-tests/{test_id}/archive`
- `POST /api/v1/control-tests/{test_id}/run`
- `GET /api/v1/control-tests/summary`
- `POST /api/v1/controls/{control_id}/obligations`
- `DELETE /api/v1/controls/{control_id}/obligations/{obligation_id}`
- `GET /api/v1/obligations/{obligation_id}/controls`
- `GET /api/v1/controls/gaps/summary`
- `POST /api/v1/frameworks/{framework_id}/control-recommendations/generate`
- `GET /api/v1/control-recommendations`
- `GET /api/v1/control-recommendations/{recommendation_id}`
- `POST /api/v1/control-recommendations/{recommendation_id}/apply`
- `POST /api/v1/control-recommendations/{recommendation_id}/dismiss`
- `GET /api/v1/control-recommendations/runs`
- `GET /api/v1/control-recommendations/summary`
- `GET /api/v1/risks`
- `POST /api/v1/risks`
- `GET /api/v1/risks/summary`
- `GET /api/v1/risks/heatmap`
- `GET /api/v1/risks/{risk_id}`
- `PATCH /api/v1/risks/{risk_id}`
- `PATCH /api/v1/risks/{risk_id}/archive`
- `POST /api/v1/risks/{risk_id}/controls`
- `DELETE /api/v1/risks/{risk_id}/controls/{control_id}`
- `POST /api/v1/risks/{risk_id}/evidence`
- `DELETE /api/v1/risks/{risk_id}/evidence/{evidence_id}`
- `POST /api/v1/risks/{risk_id}/accept`
- `POST /api/v1/risks/{risk_id}/treatment-task`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/summary`
- `POST /api/v1/tasks/reminders/queue`

Batch assignment workflow notes:
- `POST /api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/cancellation-requests`
- `GET /api/v1/framework-review-capacity/batch-assignments/cancellation-requests`
- `GET /api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}`
- `POST /api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve`
- `POST /api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/reject`
- `POST /api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute`
- `POST /api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/require-cancellation-approval`
- Validation is deterministic dry-run only and returns `plan_hash` plus required confirmation text `CONFIRM_BATCH_ASSIGNMENTS`.
- Apply re-validates payload deterministically, requires exact confirmation text, and compares provided `plan_hash` to the recomputed hash.
- No auto-assignment occurs outside the explicit apply endpoint.
- Run cancellation requires an explicit `cancellation_reason`, records immutable cancellation fields on the run, and writes an audit log.
- Dual-approval cancellation governance is optional. When cancellation approval is required for a run, direct cancel is blocked and request -> approve/reject -> execute must be used.
- Organization-level governance defaults can enforce cancellation approval for newly created batch runs via `PATCH /api/v1/organizations/me/governance-settings`; this default is copied to each new run at creation time for immutable provenance and does not retroactively mutate historical runs.
- Admins can explicitly apply the current organization default to eligible existing open batch runs via `POST /api/v1/organizations/me/governance-settings/apply-to-open-batch-runs` with `dry_run` preview or live update; applied/cancelled runs and runs with created assignments are excluded.
- Governance policy history is append-only and versioned per organization; successful settings updates and live open-run rollouts write immutable history events linked to audit logs where available.
- Governance evidence APIs provide tenant-scoped history, merged timeline (history plus audit-derived entries for legacy coverage), version diff evidence, and JSON evidence bundle output only (no PDF/ZIP export).
- Governance evidence manifests provide tenant-scoped signed JSON manifests using internal `HMAC-SHA256` integrity signatures over canonical JSON content, with verify and revoke endpoints.
- Governance evidence manifest caveat: this is an internal integrity signature only and not a legal e-signature, external audit attestation, or certification.
- Internal signing key lifecycle is organization-scoped and supports key rotation (`active` -> `deprecated`/`revoked`) without deleting historical manifests; new manifests use the active `key_id`.
- Manifest verification is multi-key aware: manifests with `key_id` verify against the matching internal key, legacy manifests without `key_id` fall back to legacy `SECRET_KEY` verification, and revoked keys return `trusted=false` even when signature math still matches.
- Internal signing keys are derived from app secret material and metadata (`organization_id`, `purpose`, `key_id`); raw key material is never stored or returned by API responses.
- Manifest verification now writes append-only verification event snapshots for chain-of-custody evidence (actor, timestamp, key status, trusted flag, hash/signature results, and verification metadata) without mutating manifest records.
- Chain-of-custody timeline endpoints merge manifest lifecycle events, immutable verification snapshots, and related key governance audit events for tenant-scoped evidence review.
- Verification-event export is JSON-only (`POST .../verification-events/export`) with deterministic cursor pagination (`verified_at`,`id` ordering), filter-bound cursor validation, and page-level SHA-256 integrity (`canonical_page_sha256`); no PDF/ZIP or external storage.
- Verification-event export supports optional internal page signatures (`include_internal_signature`, default `true`) using organization-scoped internal keys for purpose `verification_event_export`; responses include key metadata and signed payload hash without exposing raw key material.
- Verification-event export replay verification is available via `POST .../verification-events/export/verify-page`; it recomputes canonical page hash, signed payload hash, and internal HMAC signature using the referenced tenant key without persisting uploaded export payloads or mutating evidence/manifests/events.
- Replay verification trust semantics are key-status aware: `active`/`deprecated` keys can produce `trusted=true` only when all checks pass, `revoked` keys always produce `trusted=false` even if signature math is valid, and unknown keys return invalid/untrusted results.
- Signed export page caveat: this is an internal CompliVibe integrity signature and not a legal e-signature, external audit attestation, or certification.
- Replay verification caveat: this endpoint verifies an internal CompliVibe export-page integrity signature and is not legal e-signature validation, external audit attestation, or certification.
- Verification caveat: this is an internal CompliVibe integrity check and not legal e-signature validation or external attestation.
- AI system inventory foundation is organization-scoped and manual-entry only: no AI discovery, no automatic risk classification, and no external provider integration in this phase.
- AI system archive behavior is soft-delete only (`lifecycle_status=archived` with archive provenance), and archived records are excluded from list results unless `include_archived=true`.
- AI system summary endpoint returns tenant-scoped inventory counts by lifecycle and system type, ownership coverage metrics, and missing-owner count for governance triage.
- AI system links to controls, evidence, and risks are explicit manual mappings only; no auto-linking, recommendations, or inference are performed.
- AI system link records are soft-state (`active`/`unlinked`) and non-destructive; unlink requires `unlink_reason` and does not hard delete link history.
- Archived AI systems cannot accept new control/evidence/risk links.
- AI system link summary returns tenant-scoped counts for active/unlinked link totals by target type.
- AI system governance reviews are manual checkpoints with explicit lifecycle (`pending`, `in_progress`, `completed`, `cancelled`) and explicit outcomes; no automatic production approval is performed.
- Archived AI systems only allow new governance reviews of type `retirement_review`.
- AI system attestations are internal signoff records bound to completed reviews; signer duplicates per review are blocked for the same user.
- Governance attestations use internal `HMAC-SHA256` integrity metadata (`content_sha256`, `internal_signature`) and can be replay-verified without mutating stored records.
- Governance attestation caveat: internal integrity signature only, not a legal e-signature, external audit attestation, or certification.
- Governance review scheduling is explicit metadata on each review (`due_at`, optional `reminder_policy_id`, `last_reminder_at`, `escalated_at`) and only applies to `pending`/`in_progress` reviews.
- AI governance reminder policies are tenant-scoped (`active`/`inactive`/`archived`) and define deterministic day offsets for reminder, overdue, and escalation thresholds with optional assignee notification intent.
- Schedule evaluation is manual-trigger only (`POST /api/v1/ai-governance/review-queue/evaluate-schedules`) with deterministic `dry_run` and idempotent live mode; no autonomous scheduler or automatic decisioning is performed.
- Schedule events are non-destructive (`reminder_due`, `review_overdue`, `escalation_due`) with explicit resolve flow and tenant-scoped queue/summary endpoints.
- Optional schedule notifications queue internal email outbox records only when evaluation is live and policy `notify_assignee=true`; no real email sending is performed.
- Recurrence templates are manual governance planning metadata only (`cadence_type`, `interval_value`, defaults for assignee/checklist/reminder policy) and can be archived without deletion.
- Review-plan generation is human-triggered (`POST /api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan`) with deterministic due-date generation, explicit dry-run preview, and live apply modes.
- Live apply creates `pending` governance reviews with `due_at` and template defaults but does not start, approve, or complete reviews automatically and does not send real email.
- Duplicate prevention skips plan entries when a non-cancelled review already exists for the same AI system + review type + due date.
- Plan-run history is tenant-scoped and queryable (`/review-plan-runs`) for previewed/applied runs and recurrence summary metrics.
- Review-plan caveat: review-plan generation is manually triggered; CompliVibe does not autonomously create, approve, or complete AI governance reviews.
- Review-plan constraints are organization-scoped deterministic rules linking a target review type to prerequisite completed review conditions with `warn` or `block` enforcement.
- Constraint types include `prerequisite_completed` and `prerequisite_window` with optional non-negative `min_gap_days` / `max_gap_days` validation.
- Constraint-aware plan generation remains human-triggered only and never auto-creates missing prerequisite reviews.
- `block` constraint failures are skipped as `constraint_blocked`; `warn` failures remain planned with warning metadata in `constraint_results`.
- Constraint evaluation can be toggled (`apply_constraints`) or narrowed to explicit validated `constraint_ids` for deterministic what-if planning.
- Constraint caveat: review-plan constraints are deterministic planning rules only and do not autonomously create, approve, or complete AI governance reviews.
- Sequence packs provide operator-defined ordered multi-review-type rollout steps with deterministic due-date staging via `start_from + offset_days_from_start`.
- Sequence generation is human-triggered only (`generate-sequence`) with `dry_run` preview and live apply, and never auto-starts/approves/completes reviews.
- Sequence steps support optional defaults (assignee, reminder policy, checklist) with tenant-scoped validation and duplicate active `step_order` protection per pack.
- Sequence apply creates only `pending` governance reviews and skips duplicates where an existing non-cancelled review matches `ai_system_id + review_type + due_at`.
- Sequence generation can reuse dependency constraints (`apply_constraints=true`) so block/warn outcomes are reflected in per-item `constraint_results`.
- Sequence run history and summary endpoints provide tenant-scoped evidence of previewed/applied runs and generated/skipped counts over time.
- Sequence-pack caveat: generation is manually triggered and does not autonomously create, start, approve, or complete AI governance reviews.
- Guardrails add tenant-scoped freeze windows (`all_ai_governance`, `review_type`, `sequence_pack`, `ai_system`) to detect restricted rollout windows deterministically.
- Sequence dry-run now reports `guardrail_results` warnings without creating acknowledgements or blocking preview output.
- Sequence live apply during an active freeze requires exact operator acknowledgement text (`CONFIRM_SEQUENCE_APPLY_DURING_FREEZE`), `override_freeze=true`, and `override_reason`; valid overrides record an operator acknowledgement entry.
- Freeze windows support deterministic precedence controls: `priority` (higher first), scope specificity tie-breakers (`ai_system` > `sequence_pack` > `review_type` > `all_ai_governance`), then `starts_at` desc, then `id` asc.
- Guardrail resolution supports `enforcement_level` (`info`, `warn`, `block`) and `override_allowed`; blocking windows with `override_allowed=false` cannot be bypassed during live sequence apply.
- Guardrail check and conflict preview return precedence trace details (`precedence_order`, primary blocking window, final decision) to make conflict handling deterministic and reviewable.
- Guardrail policy sets provide tenant-scoped, versioned profiles; activating a version marks previous active as `deprecated`, and policy-set/profile history remains immutable.
- Optional `policy_set_id` can be provided to guardrail check/resolve and `guardrail_policy_set_id` to sequence generation; active profile settings control acknowledgement text and display categories while preserving block safety.
- Guardrail policy assignments provide deterministic default profile mapping by scope (`sequence_pack`, `ai_system`, `review_type`, `rollout_class`, `all_ai_governance`) with immutable assignment history (`created`, `updated`, `archived`) and no hard deletes.
- Policy resolution order is deterministic: explicit request policy always wins, then mapped defaults by scope precedence (`sequence_pack` -> `ai_system` -> `review_type` -> `rollout_class` -> `all_ai_governance`), then tie-breakers (`priority` desc, `updated_at` desc, `id` asc).
- Guardrail check/resolve and sequence generation can use mapped defaults when explicit policy is omitted, and responses include `policy_resolution` metadata showing source and precedence trace.
- Mapped policy defaults must reference a policy set with an active version; missing active versions fail validation rather than silently falling back.
- Policy resolution simulation supports batch context preview (up to 100 contexts) for explicit-vs-mapped policy outcomes, precedence traces, and per-context guardrail resolution before live sequence apply.
- Simulation is read-only by default; when `persist_report=true`, a tenant-scoped simulation report is stored for auditable planning history and can later be archived (no hard delete).
- Simulation mode never creates reviews, sequence runs, acknowledgements, or policy assignment changes.
- Simulation report diff mode compares two persisted simulation reports with deterministic context matching (`context_key_then_index` or `context_key_only`) and surfaces added/removed/changed/unchanged contexts.
- Diff mode detects deltas for policy resolution source/set/version/assignment, precedence trace changes, and guardrail resolution changes (blocked status, primary blocking window, override/enforcement, matching windows, warnings/info).
- Diff mode now includes deterministic machine-readable reason codes for context-level and field-level changes, plus aggregate reason-code counts for change-control workflows.
- Diff reason-code catalog is available via `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-reason-codes`.
- Policy-diff gating profiles provide tenant-scoped reason-code severity mappings (`info`/`low`/`medium`/`high`/`critical`) and review-required thresholds for deterministic human-review classification.
- Diff classification is read-only by default and can optionally persist a separate gating report (`persist_report=true`) without mutating source diff reports.
- Gating classification computes deterministic `max_severity`, `review_required`, `severity_summary`, and per-code classification output using explicit reason-code rules with default fallback severity.
- Gating baseline compare mode compares two persisted gating reports to show deterministic severity/review-required drift and per-reason-code classification deltas before sign-off.
- Gating compare is read-only by default and can optionally persist immutable compare reports (`persist_compare=true`) without mutating source gating reports.
- Diff mode is read-only by default; `persist_diff=true` stores a tenant-scoped immutable diff report record that can be archived (no hard delete).
- Policy profiles cannot silently bypass block decisions: active block windows still drive final `blocked=true` decisions even if display flags omit block windows from rendered match lists.
- Policy profile caveat: guardrail policy profiles are deterministic configuration records and do not autonomously execute, approve, or complete AI governance work.
- Policy assignment caveat: guardrail policy assignments are deterministic defaults, explicit operator-selected profiles take precedence, and mappings do not autonomously execute, approve, or complete AI governance work.
- Policy simulation caveat: simulations are read-only planning reports and do not create reviews, sequence runs, acknowledgements, or policy changes.
- Policy simulation diff caveat: diff reports are deterministic comparisons and do not create reviews, sequence runs, acknowledgements, freeze windows, policy assignments, or policy changes.
- Policy simulation diff reason-code caveat: reason codes are deterministic labels for review/change-control workflows and do not trigger automation or mutate governance records.
- Policy diff gating caveat: gating is read-only classification for human review and does not approve/reject changes, create tasks/reviews, or trigger automation.
- Policy diff gating compare caveat: compare reports are read-only drift reports for human review and do not approve/reject changes, create tasks/reviews, or trigger automation.
- Gating compare presets provide reusable interpretation profiles with optional baseline report/profile references, watched/ignored reason-code lists, and deterministic interpretation rules.
- Preset versions provide immutable snapshot history for recurring sign-off cycles; versions are created from current preset config, increment version numbers per preset, and support explicit activation with previous active version deprecation.
- Presets support optional version pinning with deterministic selection modes: `active_then_mutable`, `pinned_preferred`, and `pinned_required`.
- Pinned presets can require or block explicit version overrides; when a differing explicit version is allowed, `version_override_reason` is required and recorded in evaluation metadata.
- Preset assignments provide deterministic default preset mapping by scope (`sequence_pack`, `ai_system`, `review_type`, `rollout_class`, `all_ai_governance`) with explicit operator-selected preset precedence.
- Preset assignment resolution order is deterministic: explicit preset first, then mapped scope precedence (`sequence_pack` -> `ai_system` -> `review_type` -> `rollout_class` -> `all_ai_governance`), then tie-breakers (`priority` desc, `updated_at` desc, `id` asc).
- `evaluate-default` resolves explicit-or-mapped preset first, then runs existing preset evaluation (including Phase 5.18 pinning/version-selection rules) and can persist reports with `preset_resolution` metadata.
- Mapped preset defaults must resolve to active presets; inactive/archived mapped presets fail validation instead of silently falling back.
- Read-only bulk coverage diagnostics (`coverage-diagnostics`) evaluate up to 500 candidate contexts and return deterministic resolution traces plus diagnostic codes (for unresolved contexts, conflicting candidates, inactive/archived preset targets, and pinning/version issues) without mutating assignments.
- Coverage diagnostics keep the same read-only default path; persisted snapshots are explicit with `persist_report=true`, storing immutable `input_contexts_json` + `result_json` report records and writing audit only for persisted actions.
- Diagnostic report diff mode deterministically compares two persisted snapshots (context matching via `context_key_then_index` or `context_key_only`) and detects added/removed/changed contexts plus changes in resolution source, resolved preset, severity, diagnostic codes, and precedence trace.
- Diagnostic diff persistence is explicit with `persist_diff=true`; diffing never mutates source reports or assignments.
- Assignment health diagnostics (`health-diagnostics`) and coverage summary (`coverage-summary`) provide tenant-scoped aggregate visibility into assignment status distribution, conflict/duplicate indicators, inactive or archived preset targets, and referenced preset coverage.
- Diagnostic report summary aggregates report/diff totals and unresolved/warning/critical + diagnostic-code-change totals across persisted snapshots.
- Diagnostic caveat: persisted diagnostics reports are immutable operator visibility snapshots and do not approve/reject changes, create tasks/reviews, mutate assignments, or trigger automation.
- Diagnostic snapshot exports are JSON-only and stored internally as immutable export rows (no PDF/ZIP artifacts and no external storage writes).
- Export rows include canonical payload SHA-256 and internal `HMAC-SHA256` signature metadata; export verification recomputes hash/signature without mutating source reports or export rows.
- Revocation is status-based (`revoked`) with retained payload/signature metadata; revocation never hard-deletes export evidence.
- Export caveat: internal integrity signature metadata is not a legal e-signature, external audit attestation, or certification.
- Diagnostic export diff supports deterministic payload comparison between two persisted exports of the same `export_type`, returning JSON-path level changes (`$.field`, `$.array[0].field`) and source verification metadata (`valid_hash`, `valid_signature`, `trusted`).
- Diagnostic export diff responses include normalized reason-code labels with per-path reason metadata (`reason_code`, `severity_hint`), aggregate `reason_code_summary`, and `reason_code_count`; persisted diff rows store the same reason-code summary/count for immutable reporting.
- Export-diff reason-code catalog is available via `GET /api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reason-codes` in deterministic code order.
- Diagnostic export-diff gating profiles provide tenant-scoped reason-code severity mappings (`info`/`low`/`medium`/`high`/`critical`) and review-required thresholds for deterministic human-review classification of persisted export-diff reports.
- Export-diff gating classification is read-only by default; `persist_report=true` stores a separate gating report snapshot and never mutates source exports or source export-diff reports.
- Diagnostic export-diff gating caveat: classification is for human review only and does not approve/reject changes, create tasks/reviews, mutate exports, or trigger automation.
- Diagnostic export-diff gating baseline compare supports read-only comparison of two persisted gating reports with deterministic drift outputs for max severity (`increased`/`decreased`/`unchanged`), review-required (`became_required`/`became_not_required`/`unchanged`), and reason-code deltas (added/removed/severity/review-required/count changes).
- Baseline compare persistence is explicit via `persist_compare=true`; persisted compare snapshots are immutable and source gating reports/export-diff reports are never mutated.
- Diagnostic export-diff gating compare caveat: baseline compare is for human review only and does not approve/reject changes, create tasks/reviews, mutate gating reports, or trigger automation.
- Diagnostic export-diff gating compare presets provide reusable deterministic interpretation rules over baseline compare outputs, including watched/ignored reason-code handling, drift-specific band mapping, and optional change-count thresholds.
- Preset evaluation is read-only by default; `persist_report=true` stores an immutable preset-evaluation snapshot without mutating source compare reports or source gating reports.
- Diagnostic export-diff gating compare preset caveat: presets are interpretation helpers for human review only and do not approve/reject changes, create tasks/reviews, mutate compare reports, or trigger automation.
- Diagnostic export-diff gating compare presets now support immutable version snapshots (`draft`/`active`/`deprecated`/`archived`) with explicit activation and status-based archive; active or pinned versions cannot be archived.
- Diagnostic export-diff gating compare presets support preset-level pinning (`pinned_preferred`, `pinned_required`, `active_then_mutable`) and controlled explicit version overrides with required `version_override_reason` when overriding a different pinned version.
- Diagnostic export-diff gating compare preset reports now store version resolution metadata (`preset_version_id`, `preset_version_number`, `preset_snapshot_json`, `version_resolution_source`, `pinned_version_id`, `explicit_version_override_used`, `version_override_reason`) for immutable replayability.
- Phase 5.30 closure adds read-only assignment coverage diagnostics for diagnostic export-diff gating compare preset assignments (`coverage-diagnostics`, `health-diagnostics`, `coverage-summary`) with no persistence, no mutation, and no diagnostic audit writes.
- Phase 5 is closed. Phase 6.0 Contract Stabilization publishes read-only canonical contract metadata for Phase 5 governance endpoint groups via `/api/v1/ai-governance/contracts/phase5*` routes.
- Phase 6.1 introduces manual-first AI risk assessment records and immutable snapshots under `/api/v1/ai-governance/ai-risk/*` with deterministic display scoring derived only from manually provided `likelihood` and `impact`.
- AI risk caveat: “AI risk assessments are manual governance records. CompliVibe does not make legal determinations or automatically classify regulatory status in this phase.”
- Phase 6.2 adds tenant-scoped manual risk scoring profiles with configurable deterministic weights/thresholds, read-only score preview, and explicit assessment score recalculation.
- Risk presentation contract note: `risk_level` remains manual, while `calculated_risk_level` is deterministic profile output from manual inputs and is not legal/regulatory classification.
- Phase 6.3 adds tenant-scoped manual dimension-weighting templates and residual-risk presentation endpoints with explicit apply/preview flows only.
- Dimension/residual contract note: `risk_level` remains manual; `calculated_dimension_risk_level` and `calculated_residual_risk_level` are deterministic presentation outputs from manual inputs and configured templates/profiles.
- Phase 6.4 adds tenant-scoped manual classification taxonomy templates and classification records for risk assessments, including operator-provided labels, confidence, justification, and optional evidence/control/risk references.
- Phase 6.5 adds manual classification review-state controls, immutable classification snapshots, and deterministic governance signals with preview/persist refresh support.
- Phase 6.6 adds deterministic signal prioritization and next-best-attention read models (`/signals/prioritized`, `/signals/groups`, `/signals/priority-summary`, `/signals/{signal_id}/priority-explanation`, `/ai-systems/{ai_system_id}/attention`) without mutating source signals or source governance records.
- Phase 6.7 adds deterministic, read-only candidate action generation from open governance signals (`/actions/templates`, `/actions/candidates`, `/actions/candidates/explain`, `/actions/candidate-summary`, `/ai-systems/{ai_system_id}/candidate-actions`, `/ai-risk/assessments/{assessment_id}/candidate-actions`) with no task/review creation and no source-record mutation.
- Phase 6.8 adds deterministic recommendation snapshot preview/persist/list/detail/diff/latest/summary endpoints (`/recommendations/snapshots*`) that preserve immutable candidate-action history for audit visibility without executing any actions.
- Phase 6.10 adds deterministic Copilot Draft Layer preview endpoints (`/copilot/draft-types`, `/copilot/drafts/preview`, `/ai-systems/{ai_system_id}/copilot-brief`, `/ai-risk/assessments/{assessment_id}/copilot-brief`, `/recommendations/snapshots/{snapshot_id}/copilot-summary`, `/copilot/executive-risk-summary`) sourced from existing signals, prioritization, candidate actions, recommendation snapshots, and dispositions.
- Phase 6.11 adds deterministic, immutable Copilot draft snapshot history endpoints (`/copilot/draft-snapshots*`) with read-only preview, explicit persisted snapshot creation, deterministic source-context/snapshot hashes, versioned scope+draft lineage, and diffable draft history.

Phase 6.5 caveat:
- Governance signals are deterministic indicators for human attention. They do not approve, reject, certify, classify legally, or trigger automation.
- Signal prioritization caveat: priority ordering is deterministic presentation logic for human attention and does not create tasks, recommendations, or automation.
- Candidate action caveat: candidate actions are deterministic suggestions for human operators and do not create tasks, create reviews, trigger automation, approve/reject decisions, or mutate governance records.
- Recommendation snapshot caveat: snapshots preserve deterministic candidate actions at a point in time and do not create tasks, trigger automation, approve/reject decisions, or mutate governance records.
- Recommendation action disposition caveat: dispositions are human workflow metadata only; they do not execute recommendations, create tasks/reviews, trigger automation, or mutate source governance records.
- Copilot draft caveat: drafts are deterministic template-based previews for human review and do not call external AI/LLM services, execute actions, create tasks/reviews, trigger automation, certify compliance, or make legal/regulatory determinations.
- Copilot draft snapshot caveat: snapshots preserve deterministic draft previews at a point in time and do not create tasks, trigger automation, approve, certify, or make legal/regulatory determinations.
- Phase 6 closure note (Phase 6.12): Phase 6 is closed through a regression and contract-hardening gate (route ordering checks, contract completeness checks, tenant-isolation verification, audit behavior verification, and migration/import sanity checks).
- Phase 6 closure note (Phase 6.12): all Phase 6 intelligence layers remain deterministic and non-executing; they do not create tasks, create reviews, trigger automation, or mutate source governance records.
- Phase 6 closure note (Phase 6.12): no external AI/LLM service is used by Phase 6 intelligence endpoints.
- Phase 6 closure note (Phase 6.12): recommended next phase is safe autopilot policy guardrails over existing deterministic intelligence outputs.
- Classification contract note: `latest_classification_id`, `classification_status`, and `classification_summary_json` are governance metadata for manual assertions and do not change manual `risk_level` or deterministic score fields automatically.
- Classification caveat: classification records are manual governance assertions entered by users; they are not automatic legal or regulatory determinations.
- Contract registry caveat: these schemas are internal API stability contracts for engineering compatibility checks; they are not legal/compliance guarantees and do not change governance workflow behavior.
- Export diff is read-only by default (`persist_diff=false`), and optional persisted diff snapshots are status-archived only; source export records are never mutated, regenerated, or revoked by diff actions.
- Export diff caveat: diffs are deterministic JSON comparison records and do not mutate exports, create files, create reviews, or trigger automation.
- Preset evaluation supports deterministic config selection in this order: explicit `preset_version_id` override, preset `active_version_id`, then backward-compatible mutable preset fields when no active version exists.
- In pinned modes, evaluation returns version-resolution metadata (`version_resolution_source`, `pinned_version_id`, `explicit_version_override_used`, `version_override_reason`) and persisted preset reports retain these fields in `result_json`.
- Persisted preset reports store the exact version linkage and immutable snapshot used for evaluation (`preset_version_id`, `preset_version_number`, `preset_snapshot_json`) so later preset edits do not rewrite historical interpretation context.
- Preset evaluation runs existing gating compare first, then applies preset escalation rules (`severity_increase_band`, `review_required_flip_band`, `watched_reason_code_band`) using deterministic band order (`stable < attention < review_required < critical_review`).
- Ignored reason codes remain visible in raw compare output and hit counts, and can be configured to not affect interpretation band escalation.
- Preset evaluation is read-only by default; `persist_report=true` stores a separate preset report, and `persist_compare_report=true` can additionally persist the underlying compare report using existing compare behavior.
- Gating compare preset caveat: presets are deterministic interpretation configurations for human review and do not approve/reject changes, create tasks/reviews, or trigger automation.
- Preset version caveat: preset versions are immutable interpretation snapshots for human review and do not approve/reject changes, create tasks/reviews, or trigger automation.
- Preset pinning caveat: preset version pinning controls deterministic interpretation snapshots for human review and does not approve/reject changes, create tasks/reviews, or trigger automation.
- Preset assignment caveat: gating compare preset assignments are deterministic defaults for human review interpretation, explicit operator-selected presets take precedence, and mappings do not approve/reject changes, create tasks/reviews, or trigger automation.
- Diagnostic export-diff gating compare preset assignments add deterministic default resolution for compare interpretation with precedence: explicit preset -> compare-report mapping -> gating-profile mapping -> sequence-pack -> ai-system -> review-type -> rollout-class -> export-type -> global.
- Evaluate-default-preset for diagnostic export-diff compare preserves version/pinning resolution from preset evaluation and stores `preset_resolution` metadata in persisted preset report `result_json` for replayable context.
- Guardrail caveat: controls are deterministic operator safeguards only and do not autonomously create, start, approve, or complete AI governance reviews.
- Requesters cannot self-approve cancellation requests, and execute re-checks applied-run protection before cancelling.
- Applied runs that already created assignments cannot be cancelled by batch-run cancellation; assignments are never silently rolled back or deleted.
- Notification support (when enabled) queues internal email outbox records only; no real email sending is performed.
- `GET /api/v1/tasks/{task_id}`
- `PATCH /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/complete`
- `POST /api/v1/tasks/{task_id}/cancel`
- `POST /api/v1/tasks/{task_id}/notify`
- `GET /api/v1/automation/rules`
- `POST /api/v1/automation/rules`
- `GET /api/v1/automation/rules/{rule_id}`
- `PATCH /api/v1/automation/rules/{rule_id}`
- `POST /api/v1/automation/rules/{rule_id}/archive`
- `POST /api/v1/automation/rules/{rule_id}/run`
- `POST /api/v1/automation/rules/{rule_id}/dry-run`
- `PATCH /api/v1/automation/rules/{rule_id}/schedule`
- `GET /api/v1/automation/rules/{rule_id}/versions`
- `POST /api/v1/automation/run-scan`
- `GET /api/v1/automation/schedules/due`
- `POST /api/v1/automation/schedules/run-due`
- `GET /api/v1/automation/schedules/summary`
- `GET /api/v1/automation/executions`
- `GET /api/v1/automation/executions/{execution_id}`
- `GET /api/v1/automation/summary`
- `POST /api/v1/scoring/snapshots/materialize`
- `GET /api/v1/scoring/snapshots/latest`
- `GET /api/v1/scoring/snapshots`
- `GET /api/v1/scoring/snapshots/trends`
- `GET /api/v1/scoring/snapshots/delta`
- `GET /api/v1/scoring/methodology`
- `POST /api/v1/recertification/policies`
- `GET /api/v1/recertification/policies`
- `PATCH /api/v1/recertification/policies/{policy_id}`
- `POST /api/v1/recertification/policies/{policy_id}/archive`
- `GET /api/v1/recertification/evidence/due`
- `POST /api/v1/recertification/evidence/run`
- `GET /api/v1/recertification/controls/due`
- `POST /api/v1/recertification/controls/run`
- `GET /api/v1/recertification/runs`
- `GET /api/v1/recertification/runs/{run_id}`
- `GET /api/v1/recertification/summary`
- `POST /api/v1/reports/generate`
- `GET /api/v1/reports`
- `GET /api/v1/reports/summary`
- `GET /api/v1/reports/{report_id}`
- `POST /api/v1/reports/{report_id}/archive`
- `GET /api/v1/reports/{report_id}/provenance`
- `GET /api/v1/reports/frameworks/{framework_id}/readiness`
- `POST /api/v1/exports/jobs`
- `GET /api/v1/exports/jobs`
- `GET /api/v1/exports/jobs/{export_job_id}`
- `POST /api/v1/exports/jobs/{export_job_id}/run`
- `POST /api/v1/exports/jobs/{export_job_id}/cancel`
- `POST /api/v1/exports/jobs/{export_job_id}/archive`
- `POST /api/v1/exports/jobs/{export_job_id}/retention/apply`
- `POST /api/v1/exports/jobs/{export_job_id}/legal-hold`
- `GET /api/v1/exports/jobs/{export_job_id}/package`
- `GET /api/v1/exports/jobs/{export_job_id}/manifest`
- `POST /api/v1/exports/jobs/{export_job_id}/verify`
- `GET /api/v1/exports/jobs/{export_job_id}/verification-history`
- `POST /api/v1/exports/jobs/{export_job_id}/attestations`
- `GET /api/v1/exports/jobs/{export_job_id}/attestations`
- `GET /api/v1/attestations/{attestation_id}`
- `POST /api/v1/attestations/{attestation_id}/revoke`
- `GET /api/v1/exports/summary`
- `POST /api/v1/governance/retention/policies`
- `GET /api/v1/governance/retention/policies`
- `PATCH /api/v1/governance/retention/policies/{policy_id}`
- `POST /api/v1/governance/retention/policies/{policy_id}/archive`
- `POST /api/v1/governance/retention/evaluate`
- `GET /api/v1/governance/retention/summary`
- `POST /api/v1/governance/overrides`
- `POST /api/v1/governance/overrides/from-template`
- `GET /api/v1/governance/overrides`
- `GET /api/v1/governance/overrides/{override_id}`
- `GET /api/v1/governance/overrides/{override_id}/routing`
- `POST /api/v1/governance/overrides/{override_id}/approve`
- `POST /api/v1/governance/overrides/{override_id}/reject`
- `POST /api/v1/governance/overrides/{override_id}/cancel`
- `POST /api/v1/governance/overrides/{override_id}/execute`
- `POST /api/v1/governance/overrides/expire`
- `GET /api/v1/governance/overrides/summary`
- `POST /api/v1/governance/override-templates`
- `GET /api/v1/governance/override-templates`
- `GET /api/v1/governance/override-templates/{template_id}`
- `PATCH /api/v1/governance/override-templates/{template_id}`
- `POST /api/v1/governance/override-templates/{template_id}/archive`
- `GET /api/v1/governance/override-templates/{template_id}/versions`
- `GET /api/v1/governance/override-templates/summary`
- `GET /api/v1/email/templates`
- `POST /api/v1/email/templates`
- `PATCH /api/v1/email/templates/{template_id}`

## Framework Content Pack Caveats

- Local framework packs are deterministic JSON files under `app/content_packs/frameworks/`.
- Starter packs are metadata/starter/partial representations and are not legal advice.
- `full_verified` coverage is intentionally blocked for local starter-pack apply in this phase.
- Coverage reports are internal content completeness signals, not legal or regulatory certification.
- `POST /api/v1/email/templates/{template_id}/preview`
- `POST /api/v1/email/outbox`
- `GET /api/v1/email/outbox`
- `GET /api/v1/email/outbox/{email_id}`
- `POST /api/v1/email/outbox/{email_id}/cancel`
- `POST /api/v1/email/outbox/{email_id}/mark-sent`
- `POST /api/v1/email/outbox/{email_id}/mark-failed`
- `POST /api/v1/email/worker/claim`
- `POST /api/v1/email/worker/{email_id}/complete`
- `POST /api/v1/email/worker/{email_id}/fail`
- `POST /api/v1/email/worker/release-expired-locks`
- `POST /api/v1/email/worker/{email_id}/dead-letter`
- `GET /api/v1/evidence`
- `POST /api/v1/evidence`
- `GET /api/v1/evidence/readiness/summary`
- `GET /api/v1/evidence/{evidence_id}`
- `PATCH /api/v1/evidence/{evidence_id}`
- `PATCH /api/v1/evidence/{evidence_id}/archive`
- `POST /api/v1/evidence/{evidence_id}/controls`
- `DELETE /api/v1/evidence/{evidence_id}/controls/{control_id}`
- `POST /api/v1/evidence/{evidence_id}/review`
- `GET /api/v1/controls/{control_id}/evidence`

Organization-scoped endpoints require `X-Organization-ID` header and enforce membership + RBAC checks server-side.

Activation token flow:
- Raw activation token is returned once at creation time.
- Only a token hash is stored in the database.
- Tokens are one-time use and can be expired/revoked.

Framework catalog note:
- Seeded frameworks are metadata-focused with `coverage_level` values such as `metadata_only` and `starter`.
- Seed data does not claim complete legal or compliance coverage.
- Framework versions/content packs may use `metadata_only`, `starter`, `partial`, `reviewed`, or `full_verified`; seeded baseline remains non-`full_verified`.

Obligation content architecture note:
- Obligation content supports versioned text, applicability questions, evidence requirement hints, and control suggestions with provenance metadata.
- Control suggestions are guidance metadata; controls are created only when explicitly applied by API and remain organization-scoped.
- Import preview/apply endpoints are deterministic and local-only (no scraping, no external legal data provider, no AI legal interpretation).

Framework pack review/promotion governance note:
- Coverage promotion (`metadata_only -> starter -> partial -> reviewed -> full_verified`) is explicit and policy-gated.
- Promotion cannot skip levels and must pass deterministic review gates with stored sign-off provenance.
- Review and promotion status are internal content-governance signals only and do not constitute legal advice, regulatory approval, or external audit certification.

Framework review assignment/SLA note:
- Reviewer assignment is tenant-scoped and tracked with explicit assignment status transitions.
- SLA evaluation supports dry-run and live modes; live mode creates internal escalation events and can queue internal email outbox reminders.
- No external scheduler or real email delivery is used in this phase.

Framework review capacity and assignment suggestion note:
- Reviewer capacity balancing is deterministic and policy-based only (non-AI).
- Assignment suggestions are explainable with persisted scoring provenance (`scoring_json`) and rationale text.
- Suggestions never auto-assign; assignment records are only created through explicit apply action.
- Workload snapshots are tenant-scoped and can be calculated ad hoc or persisted for historical traceability.
- What-if simulation endpoints are deterministic and preview-only; they do not create assignments or persist workload snapshots/suggestions.
- Multi-review wave planning simulation is deterministic and preview-only; it does not create assignments, persist suggestions, persist workload snapshots, or send notifications.

Applicability evaluation note:
- Organizations submit framework-scoped applicability answers with historical supersession (no hard deletes).
- Applicability evaluation is deterministic and rules-based, with dry-run and live modes plus provenance on results.
- Suggested applicability is explicitly non-legal guidance and includes caveats; it is not legal advice or a final regulatory determination.

Deterministic control recommendation note:
- Obligation-to-control recommendations are generated deterministically from applicability state, mappings, control suggestions, and evidence freshness.
- Dry-run generation computes recommendations without persisting records.
- Live generation persists open recommendations and skips duplicates by deterministic keys.
- Applying a recommendation is explicit and required for creating controls/mappings/tasks.
- Recommendation output is guidance only and not legal advice or a final compliance determination.

Control layer note:
- Controls and control-obligation mappings track implementation workflow structure.
- Control status or mapping alone does not imply evidence-backed compliance completion.

Evidence metadata note:
- This phase supports evidence metadata and control linking only.
- No binary upload or external object storage integration is configured.
- Evidence presence does not automatically imply compliant or verified control operation.

Risk register note:
- Risk scoring is deterministic (`likelihood x impact`) with explicit severity bands.
- Risk summary/heatmap provide operational visibility only, not an enterprise-wide final risk score.

Task orchestration note:
- Tasks are operational workflow records for treatment/remediation/review ownership.
- Task notifications use internal email outbox records only; no real email sending occurs in this phase.

Automation policy note:
- Automation uses deterministic, allowlisted condition and action types only.
- No AI-generated decisions, arbitrary code execution, or external workflow providers are used.
- Rule execution supports manual scans plus manually triggered due-schedule runs.
- Dry-run mode records execution/action logs with `would_create` status and does not create tasks or outbox records.
- Rule version snapshots are stored when schedule/important config changes, and idempotency keys include rule version.

Control testing and scoring note:
- Control tests support manual attestation and deterministic internal checks against CompliVibe DB state only.
- Dry-run test execution computes results without writing `control_test_runs` rows.
- Score snapshot materialization stores explainable readiness/health metrics (`inputs_json` and `breakdown_json`) and does not claim audit completion.

Recertification and reassessment note:
- Evidence recertification and control reassessment are deterministic internal workflows over existing DB state.
- Dry-run recertification/reassessment writes run/action logs with `would_create` and does not create tasks or outbox records.
- Live runs create tenant-scoped tasks (and optional outbox reminders) with idempotency keys to prevent duplicates.

Compliance reporting note:
- Reports are generated from deterministic, source-backed backend data and stored as structured JSON/markdown sections.
- `dry_run` preview mode returns report content without persisting report records.
- Reports always include a caveat that output is not legal advice, audit certification, or regulatory approval.
- No AI narrative generation and no PDF/ZIP export is implemented in this phase.

Export contract note:
- Export jobs create deterministic JSON packages stored in DB (`package_json`) with manifest/provenance metadata.
- Package integrity uses SHA-256 checksums over canonical JSON and an internal HMAC integrity signature (`HMAC-SHA256`).
- Integrity signatures are internal tamper-detection metadata, not legal digital signatures.
- Completed exports are immutable through normal APIs; archive is status-based and does not delete package data.
- No PDF/ZIP generation, file storage provider, or external signing service is used in this phase.

Retention and attestation governance note:
- Retention policies provide software-level lock windows and retention dates; evaluation is dry-run and non-destructive in this phase.
- Legal hold flags block archival actions while enabled.
- Export attestations are internal integrity attestations, not legal e-signatures or regulatory certificates.
- Attestation payloads are checksummed and HMAC-signed for tamper evidence using internal application secrets.

Governed override workflow note:
- Overrides require explicit requests, approval records, and execution events with full audit trails.
- Requesters cannot self-approve, and individual approvers cannot approve the same request twice.
- Override execution only supports allowlisted metadata-governance actions and never deletes records.
- Completed export payload content (`package_json`, `manifest_json`, `provenance_json`, checksums/signatures) remains unchanged.

Policy-bound override template note:
- Override templates provide deterministic, allowlisted conditional routing to derive required approvals and approver role restrictions.
- Template-bound requests store `template_id`, `template_version`, and routing context facts/rule matches at creation time.
- Conditional routing uses static operators/effects only; no AI routing, eval, or arbitrary code execution is used.

Internal email module note:
- Email templates and outbox are internal-only in this phase.
- No external email provider is configured and no real sending occurs.
- Delivery state transitions are tracked in `email_delivery_events`.
- Worker orchestration is DB-backed (claim, lock, retry, dead-letter) and provider-agnostic.

## Phase 7.0 - Safe Autopilot Policy Guardrails Foundation

Phase 7.0 introduces deterministic, operator-controlled autopilot policy guardrails only.

- Added autopilot policy CRUD, default policy selection, resolved-policy fallback, and policy summary endpoints under:
  - `/api/v1/ai-governance/autopilot/...`
- Added deterministic read-only policy evaluation endpoints for:
  - candidate actions
  - recommendation snapshots
  - copilot draft snapshots
- Added Phase 7 contracts endpoint:
  - `GET /api/v1/ai-governance/contracts/phase7`

Safety caveat:
- Phase 7.0 does not execute automation.
- Phase 7.0 does not create tasks or reviews.
- Phase 7.0 does not approve/publish anything.
- Phase 7.0 does not mutate assessments, classifications, signals, AI systems, recommendation snapshots/dispositions, or copilot draft snapshots.
- No external AI/LLM or legal/regulatory API is used.

## Phase 7.1 - Safe Autopilot Execution Planning (Dry-Run Intents)

Phase 7.1 adds deterministic dry-run execution planning on top of Phase 7.0 guardrails.

- Added deny-by-default capability matrix:
  - `GET /api/v1/ai-governance/autopilot/capabilities`
- Added dry-run preview endpoints:
  - `POST /api/v1/ai-governance/autopilot/execution-intents/preview-candidate-action`
  - `POST /api/v1/ai-governance/autopilot/execution-intents/preview-recommendation-snapshot`
  - `POST /api/v1/ai-governance/autopilot/execution-intents/preview-copilot-draft-snapshot`
- Added optional persisted execution intent records:
  - `POST /api/v1/ai-governance/autopilot/execution-intents`
  - `GET /api/v1/ai-governance/autopilot/execution-intents`
  - `GET /api/v1/ai-governance/autopilot/execution-intents/{intent_id}`
  - `POST /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/archive`
  - `GET /api/v1/ai-governance/autopilot/execution-intents/summary`

Safety caveat:
- Execution intents are planning artifacts only.
- Phase 7.1 does not execute actions.
- Phase 7.1 does not create tasks or reviews.
- Phase 7.1 does not send notifications or call external services.
- Phase 7.1 does not mutate governance source records.

## Phase 7.2 - Manual Approval Envelope for Execution Intents

Phase 7.2 adds a manual approval lifecycle around dry-run execution intents while keeping all behavior non-executing.

- Added approval requirements/readiness endpoints:
  - `GET /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requirements`
  - `GET /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/readiness`
- Added approval request/lifecycle endpoints:
  - `POST /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requests`
  - `GET /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requests`
  - `GET /api/v1/ai-governance/autopilot/execution-approvals`
  - `GET /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/approve`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/reject`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/cancel`
  - `GET /api/v1/ai-governance/autopilot/execution-approvals/summary`
- Added Phase 7 contracts group:
  - `governance_autopilot_execution_approvals`

Safety caveat:
- Approval records are human authorization metadata only.
- Phase 7.2 does not execute actions.
- Phase 7.2 does not create tasks or reviews.
- Phase 7.2 does not send notifications or trigger automation.
- Phase 7.2 does not mutate assessments, classifications, signals, recommendation snapshots/dispositions, copilot snapshots, or other source governance records.

## Phase 7.3 - Dual-Control Approval Policy and Quorum Rules

Phase 7.3 adds organization-scoped approval policies and quorum vote controls for execution-intent approvals while remaining fully non-executing.

- Added approval policy governance:
  - `POST /api/v1/ai-governance/autopilot/approval-policies`
  - `GET /api/v1/ai-governance/autopilot/approval-policies`
  - `GET /api/v1/ai-governance/autopilot/approval-policies/{policy_id}`
  - `PATCH /api/v1/ai-governance/autopilot/approval-policies/{policy_id}`
  - `POST /api/v1/ai-governance/autopilot/approval-policies/{policy_id}/archive`
  - `POST /api/v1/ai-governance/autopilot/approval-policies/{policy_id}/set-default`
  - `GET /api/v1/ai-governance/autopilot/approval-policies/resolved`
  - `GET /api/v1/ai-governance/autopilot/approval-policies/summary`
- Added quorum/vote endpoints:
  - `GET /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/quorum-status`
  - `GET /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes/approve`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes/reject`
- Existing compatibility endpoints remain available and now route through vote/quorum logic:
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/approve`
  - `POST /api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/reject`

Safety caveat:
- Quorum and dual-control are readiness controls only.
- Phase 7.3 does not execute actions.
- Phase 7.3 does not create tasks or reviews.
- Phase 7.3 does not send notifications or trigger automation.
- Phase 7.3 does not mutate assessments, classifications, signals, recommendation snapshots/dispositions, copilot snapshots, or other source governance records.

## Phase 7.4 - Runner Interface Contract and Dry-Run Runner Simulation

Phase 7.4 adds a non-executing runner handoff contract and dry-run runner simulations.

- Added runner interface contract and handoff verification:
  - `GET /api/v1/ai-governance/autopilot/runner-interface/contract`
  - `POST /api/v1/ai-governance/autopilot/runner-interface/verify-handoff`
- Added dry-run runner handoff preview:
  - `POST /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/runner-handoff/preview`
- Added persisted dry-run runner simulation records:
  - `POST /api/v1/ai-governance/autopilot/execution-intents/{intent_id}/runner-simulations`
  - `GET /api/v1/ai-governance/autopilot/runner-simulations`
  - `GET /api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}`
  - `POST /api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/archive`
  - `GET /api/v1/ai-governance/autopilot/runner-simulations/summary`
- Added Phase 7 contracts:
  - `governance_autopilot_runner_interface`
  - `governance_autopilot_runner_simulations`

Safety caveat:
- Runner handoff and runner simulation are dry-run-only in Phase 7.4.
- Phase 7.4 does not queue jobs, execute actions, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 7.5 - Runner Admission Controls and Replay-Safe Handoff Token

Phase 7.5 adds non-executing runner admission controls on top of dry-run runner simulations.

- Added runner admission preview and persisted admission endpoints:
  - `POST /api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/admission-preview`
  - `POST /api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/admissions`
  - `GET /api/v1/ai-governance/autopilot/runner-admissions`
  - `GET /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}`
  - `POST /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/verify-token`
  - `POST /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/revoke`
  - `POST /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/archive`
  - `GET /api/v1/ai-governance/autopilot/runner-admissions/summary`
- Added replay-safe token handling:
  - plaintext handoff token is returned only once on admitted creation
  - only token hash/fingerprint are persisted
  - token verification is hash-based and read-only
  - duplicate active idempotency admissions return existing metadata without reissuing plaintext token
- Added Phase 7 contract group:
  - `governance_autopilot_runner_admissions`

Safety caveat:
- Runner admissions and handoff tokens are non-executing guardrail artifacts.
- Phase 7.5 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 7.6 - Runner Lease / Session Envelope

Phase 7.6 adds short-lived non-executing runner lease/session envelopes bound to admitted runner handoff tokens.

- Added runner session preview and create endpoints:
  - `POST /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/session-preview`
  - `POST /api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/sessions`
- Added runner session lifecycle endpoints:
  - `GET /api/v1/ai-governance/autopilot/runner-sessions`
  - `GET /api/v1/ai-governance/autopilot/runner-sessions/{session_id}`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/{session_id}/verify`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/{session_id}/revoke`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/{session_id}/archive`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/expire-stale`
  - `GET /api/v1/ai-governance/autopilot/runner-sessions/summary`
- Added secure session token handling:
  - plaintext session token is returned once on create only
  - only token hash/fingerprint are persisted
  - verification increments attempt counters and enforces lock on max attempts
  - replay-window checks and expiration checks invalidate verification
- Added Phase 7 contract group:
  - `governance_autopilot_runner_sessions`

Safety caveat:
- Runner sessions and leases are non-executing guardrail artifacts.
- Phase 7.6 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.
- No real runner exists in Phase 7.6.

## Architecture Overview

- `app/main.py`: FastAPI app factory and initialization
- `app/core/`: config and security primitives
- `app/db/`: declarative base, session, common mixins
- `app/models/`: SQLAlchemy domain models
- `app/schemas/`: Pydantic schemas
- `app/api/v1/`: versioned routers under `/api/v1`
- `app/repositories/`: repository abstractions
- `app/services/`: domain service layer
- `alembic/`: DB migration config and revisions
- `tests/`: unit/integration tests

## Current Scope

This phase provides foundational scaffolding only. Business workflows, tenant enforcement dependencies, RBAC checks in endpoints, and full audit logging integration are next steps.

## Phase 7.7 - Session-to-Future-Runner Handshake Contract

Phase 7.7 adds a non-executing session-to-future-runner handshake contract envelope for dry-run-only future runner readiness.

- Added future-runner handshake contract and preview/create endpoints:
  - `GET /api/v1/ai-governance/autopilot/runner-handshake/contract`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/{session_id}/handshake-preview`
  - `POST /api/v1/ai-governance/autopilot/runner-sessions/{session_id}/handshakes`
- Added handshake lifecycle and verification endpoints:
  - `GET /api/v1/ai-governance/autopilot/runner-handshakes`
  - `GET /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}`
  - `POST /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/verify`
  - `POST /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/revoke`
  - `POST /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/archive`
  - `GET /api/v1/ai-governance/autopilot/runner-handshakes/summary`
- Added deterministic handshake integrity and idempotency controls:
  - persisted handshake records include deterministic `handshake_sha256` and `handshake_fingerprint`
  - create path enforces session-token verification gate and reuses existing active handshake rows for duplicate idempotency keys
  - preview is read-only and does not increment session verification attempts
- Added Phase 7 contract group:
  - `governance_autopilot_runner_handshakes`

Safety caveat:
- Runner handshakes are non-executing future-runner contract artifacts.
- Phase 7.7 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.
- No real runner exists in Phase 7.7.

## Phase 7.8 - Phase 7 Regression Gate + Autopilot Boundary Hardening

Phase 7.8 is a stabilization/closure gate for the full non-executing autopilot stack before any future runner design work.

- Completed broader regression gate across Phase 7 + affected Phase 6 intelligence layers.
- Verified static-before-dynamic ordering for conflict-prone routes (`summary/resolved/contract/capabilities` and nested static paths before `/{id}` where applicable).
- Hardened Phase 7 contract payload completeness:
  - added explicit `endpoints`
  - added explicit `protected_fields`
  - added explicit `read_write_semantics`
  - retained caveats and explicit non-execution/no-legal-determination wording
- Added Phase 7.8 regression tests:
  - `tests/unit/test_ai_system_autopilot_regression_gate_phase78.py`
- Added closure report artifacts:
  - `reports/phase7-regression-report.md`
  - `reports/phase7-regression-report.json`

Safety caveat:
- Phase 7 remains non-executing.
- No real runner exists yet.
- Runner handoff, simulation, admission, session/lease, and handshake layers are guardrail contracts only.
- Phase 7.8 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 7.9 - Execution-Safety Architecture Review / Future Runner Decision Gate

Phase 7.9 is a formal non-executing architecture decision gate before any future runner work.

- Added execution-safety architecture review reports:
  - `reports/phase7-execution-safety-architecture-review.md`
  - `reports/phase7-execution-safety-architecture-review.json`
- Added Phase 7 contract boundary metadata:
  - `execution_allowed=false`
  - `real_runner_present=false`
  - `job_queue_present=false`
  - `future_runner_requires_architecture_review=true`
- Added Phase 7.9 safety regression test:
  - `tests/unit/test_ai_system_autopilot_execution_safety_phase79.py`

Safety decision:
- Phase 7 remains non-executing and manual-first.
- No real runner exists in Phase 7.9.
- Any future runner requires a separate architecture approval gate with dual-control and dry-run-first controls.
- Phase 7.9 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 8.0 - No-Op Runner Event Log Only

Phase 8.0 adds the safest runner-adjacent control-plane surface: a no-op runner event log that records future-runner eligibility checkpoints without executing any action.

- Added Phase 8 contract registry endpoint:
  - `GET /api/v1/ai-governance/contracts/phase8`
- Added no-op runner contract and event lifecycle endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/contract`
  - `POST /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/noop-runner/preview`
  - `POST /api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/noop-runner/events`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/events`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/events/{event_id}`
  - `POST /api/v1/ai-governance/autopilot/noop-runner/events/{event_id}/verify`
  - `POST /api/v1/ai-governance/autopilot/noop-runner/events/{event_id}/archive`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/events/summary`
- Added deterministic no-op event idempotency + hash integrity:
  - active duplicate idempotency keys reuse existing event records
  - persisted records include deterministic `event_sha256`
- Added Phase 8 contract group:
  - `governance_noop_runner_events`

Safety caveat:
- No-op runner events are control-plane guardrail artifacts only.
- No real runner exists in Phase 8.0.
- Phase 8.0 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 8.1 - No-Op Runner Observability + Operator Ledger

Phase 8.1 adds read-only control-plane observability over no-op runner events so operators can inspect readiness and safety posture without introducing execution behavior.

- Added read-only observability endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/ledger`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/timeline`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/blockers`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/readiness`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/idempotency`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/control-plane-health`
- Added Phase 8 contract group:
  - `governance_noop_runner_observability`
- Added report coverage for:
  - operator ledger rows
  - timeline/event trends
  - blocked reason aggregation
  - handshake-to-event readiness gap
  - idempotency duplication diagnostics
  - hard safety-flag health posture

Safety caveat:
- Observability is read-only and non-executing.
- No real runner exists in Phase 8.1.
- Phase 8.1 does not execute actions, queue jobs, create tasks, create reviews, send notifications, call external services, or mutate source governance records.

## Phase 8.2 - Operator Diagnostics Contract Polish + Bounded Export Payloads

Phase 8.2 adds stable diagnostics metadata and bounded JSON export payloads for no-op runner reports without introducing storage or execution.

- Added diagnostics contract and manifest endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/contract`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest`
- Added bounded export/checksum endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/checksum`
- Added common diagnostics metadata standard:
  - `report_schema_version=noop_runner_reports.v1`
  - `generated_at`, `query_hash`, `result_hash`
  - hard safety flags (`execution_allowed=false`, `real_runner_present=false`, `job_queue_present=false`, `noop_runner_only=true`)
- Added Phase 8 contract group:
  - `governance_noop_runner_operator_diagnostics`

Safety caveat:
- Bounded exports are JSON API responses only.
- No files are created and no PDF/ZIP/export storage is used.
- Phase 8.2 remains read-only and non-executing.

## Phase 8.3 - Diagnostics Compatibility Guarantees + Golden Response-Shape Tests

Phase 8.3 adds explicit diagnostics API compatibility guarantees for future operator UI integration while preserving strict non-execution boundaries.

- Added compatibility policy endpoint:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy`
- Extended diagnostics contract endpoint metadata:
  - `compatibility_policy_version`
  - `compatibility_policy_endpoint`
  - `additive_fields_allowed`
  - `breaking_changes_require_new_schema_version`
  - `minimum_supported_schema_version`
  - `current_supported_schema_version`
- Extended diagnostics manifest metadata:
  - `compatibility_policy_version`
  - `compatibility_policy_endpoint`
  - `minimum_supported_schema_version`
  - `current_supported_schema_version`
- Added compatibility-policy contract group in Phase 8 contract registry:
  - `governance_noop_runner_diagnostics_compatibility`
- Added golden response-shape tests for diagnostics/reporting endpoints:
  - `tests/unit/test_ai_system_autopilot_noop_runner_diagnostics_compatibility_phase83.py`

Safety caveat:
- Compatibility metadata endpoints are read-only.
- Additive-only behavior is guaranteed for `noop_runner_reports.v1`; breaking changes require a future schema version.
- No execution behavior is introduced and no runner/job queue exists.
- No files/PDF/ZIP exports are produced or stored.

## Phase 8.4 - Read-Only Client Integration Polish for No-Op Runner Diagnostics

Phase 8.4 adds client-integration metadata endpoints and backward-compatible pagination/filter contract polish for no-op runner diagnostics while preserving strict read-only behavior.

- Added client metadata endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/client-contract`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/filter-options`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract`
- Extended bounded export response in a backward-compatible way:
  - retained existing top-level `limit`, `offset`, `truncated`, `next_offset`, `row_count`
  - added nested `pagination` metadata with `pagination_contract_version` and `max_limit`
- Extended diagnostics contract/manifest links:
  - `filter_options_endpoint`
  - `pagination_contract_endpoint`
  - `client_contract_endpoint`
- Added Phase 8 contract group:
  - `governance_noop_runner_client_integration`

Safety caveat:
- Client integration polish is read-only metadata only.
- No reports are persisted and no files are created.
- Phase 8.4 does not execute actions, queue jobs, create tasks, create reviews, call external services, send notifications, or mutate source governance records.

## Phase 8.5 - Field-Level Client Docs + Display Metadata for No-Op Runner Diagnostics

Phase 8.5 adds read-only field-level docs and display metadata so future client integrations can render diagnostics consistently without introducing any execution behavior.

- Added metadata endpoints:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/field-docs`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/localization-map`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/client-hints`
- Extended existing read-only metadata endpoints with non-breaking links:
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/client-contract`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/filter-options`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/contract`
  - `GET /api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest`
- Added Phase 8 contract group:
  - `governance_noop_runner_client_field_docs`

Safety caveat:
- Field docs and display metadata are read-only API metadata only.
- No execution, no runner, no job queue, and no source mutation were introduced.
- No files/PDF/ZIP exports or external localization services are used.

## Phase 8.6 - Phase 8 Diagnostics Contract Lint + Integration Readiness Gate

Phase 8.6 is a stabilization gate that lint-checks endpoint inventory, route ordering, contract completeness, response-shape stability, backward compatibility, and read-only safety boundaries for no-op runner diagnostics.

- Added integration-readiness lint test:
  - `tests/unit/test_ai_system_autopilot_noop_runner_integration_readiness_phase86.py`
- Verified endpoint families are reachable:
  - Phase 8 contract
  - no-op runner event contract/create/verify/archive/list/detail/summary
  - observability ledger/reports
  - diagnostics contract/manifest/bounded-export/checksum
  - compatibility/client/filter/pagination/field-docs/display/localization/client-hints
- Verified route ordering remains safe:
  - static routes (for example `/events/summary`, `/reports/*`) are ordered before dynamic `/events/{event_id}`
- Verified Phase 8 contract groups and hard flags:
  - `execution_allowed=false`
  - `real_runner_present=false`
  - `job_queue_present=false`
  - `noop_runner_only=true`
- Verified backward compatibility:
  - bounded export keeps top-level pagination keys and nested `pagination`
  - schema/version constants remain at v1

Safety caveat:
- Phase 8.6 adds no execution features and no runner.
- No external calls, no task/review/job creation, no source mutation, and no API-driven file generation were introduced.

## Phase 8.7 - Phase 8 API Ergonomics Cleanup + Closure Freeze Gate

Phase 8.7 is a final closure/freeze stabilization pass for no-op runner diagnostics and client metadata APIs.

- Verified naming/version consistency across all Phase 8 diagnostics/client metadata surfaces:
  - `noop_runner_reports.v1`
  - `noop_runner_client_contract.v1`
  - `noop_runner_pagination.v1`
  - `noop_runner_compatibility.v1`
  - `noop_runner_field_docs.v1`
  - `noop_runner_display_metadata.v1`
  - `noop_runner_localization_map.v1`
  - `noop_runner_client_hints.v1`
- Verified route inventory and static-before-dynamic ordering remain safe for:
  - no-op runner events
  - observability reports
  - diagnostics/compatibility/client metadata endpoints
- Tightened caveat consistency for Phase 8 diagnostics/client responses:
  - explicit no real runner / no job queue language
  - explicit JSON-only diagnostics language (no PDF/ZIP, no external storage)
- Added closure gate test coverage:
  - `tests/unit/test_ai_system_autopilot_noop_runner_phase8_closure_phase87.py`
- Added closure report artifacts:
  - `reports/phase8-closure-report.md`
  - `reports/phase8-closure-report.json`

Safety caveat:
- Phase 8.7 remains no-op-only and non-executing.
- No real runner exists; no job queue exists.
- No task/review creation, no source mutation, no external services, and no API-generated files are introduced.
