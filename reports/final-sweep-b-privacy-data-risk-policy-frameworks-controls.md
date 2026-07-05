# Final Sweep B: Privacy, Data, Risk, Policy, Frameworks, Controls

Worktree: `/home/ubuntu/complivibe-v4.0/complivibe-sweep-b`  
Branch: `final-sweep-b`  
Date: 2026-07-05  
Scope: Privacy & Data Protection, Data Observability, Risk Management, Policy Management, Compliance Frameworks & Obligations, Controls & Control Testing.

## Executive Result

Verdict after fixes: SOLID for the assigned slice. I found and fixed multiple real owner/reference validation gaps in the same cross-tenant pattern Worktree A reported, then reran focused tests, the selected B-domain suite, and the full regression suite.

No production systems were touched. No migrations were added. No enum/array changes were made. `AuditService.write_audit_log` call paths were preserved.

## Environment And Regression Evidence

- Copied real env before regression: `cp /home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend/.env .env`
- Alembic head check: `.venv/bin/alembic heads` -> `0243_export_control_compliance (head)`
- Focused fix regression: passed
  - `tests/unit/test_access_retention_c77_c78.py`
  - `tests/unit/test_partD_unique_actors.py`
  - `tests/unit/test_framework_engine_phase20.py`
  - `tests/unit/test_ropa_d83.py`
  - `tests/unit/test_dpia_lawful_basis_d86_d91.py`
  - `tests/unit/test_risk_appetite_a12.py`
  - `tests/unit/test_risks_phase23.py`
  - `tests/unit/test_controls_phase21.py`
  - `tests/unit/test_control_testing_and_scoring_phase27.py`
- Selected B-domain suite: passed, exit 0, covering privacy, data observability, risk, policy, framework, deadline, dashboard, scorecard, and control tests.
- Full regression suite: `.venv/bin/pytest -q` passed, exit 0. Collection count was 1371 tests; runtime result showed 1 skip for `tests/integration/test_postgres_migration_smoke.py::test_postgres_migration_smoke_upgrade_head` because `POSTGRES_TEST_DATABASE_URL` is not set. Effective result: 1370 passed, 1 skipped.

## Fixes Made

1. RoPA activity cross-tenant owner/reference validation
   - Before: `POST /api/v1/privacy/ropa/activities` could accept an Org B `owner_id`, `linked_dpia_id`, `linked_data_asset_ids`, or `linked_subprocessor_ids` while creating an Org A processing activity.
   - After: create/update validates every supplied user/reference against the current organization and active/non-deleted target rows.
   - Evidence: `test_d83_rejects_cross_tenant_owner_and_linked_references` uses real HTTP calls for each malicious reference and DB-asserts no poisoned Org A `ProcessingActivity`.

2. DPIA reviewer cross-tenant validation
   - Before: `POST /api/v1/privacy/dpias/{id}/submit-for-review` accepted an Org B `reviewer_id` for an Org A DPIA.
   - After: reviewer must be an active user with active membership in the current organization.
   - Evidence: `test_d86_submit_for_review_rejects_cross_tenant_reviewer` verifies 422 and DB state remains `draft` with no `assigned_reviewer_id`.

3. Data access monitoring actor poisoning
   - Before: API-key ingest at `POST /api/v1/data-observability/access/events` validated the asset org but stored arbitrary `actor_id`; that value was then reused as audit and incident `actor_user_id`.
   - After: populated `actor_id` must be an active user in the ingest key's organization. External/machine actors remain supported through `actor_external`.
   - Evidence: `test_c77_ingest_rejects_cross_tenant_actor_id` verifies 422 and DB-asserts no Org A `DataAccessLog` with Org B actor.

4. Obligation state owner poisoning
   - Before: `PATCH /api/v1/obligations/{obligation_id}/state` validated active framework scope but accepted an arbitrary `owner_user_id`.
   - After: owner must be active same-org member.
   - Evidence: `test_obligation_state_rejects_cross_tenant_owner_user` activates a framework, attempts Org B owner assignment through Org A HTTP request, and DB-asserts no poisoned `OrganizationObligationState`.

5. Risk appetite business-unit scope validation
   - Before: thresholds scoped as `scope_type=business_unit` only required `scope_id` to be present; it did not prove the BU belonged to the org.
   - After: `scope_id` must reference an active, non-deleted same-org `BusinessUnit`.
   - Evidence: `test_a12_business_unit_scope_must_belong_to_org` verifies 400 and DB-asserts no threshold persisted with foreign BU scope.

6. Inactive owner acceptance in risk/control/control-test records
   - Before: Risk, Control, and Control Test owner checks accepted active membership rows even if the linked `User` was inactive.
   - After: owner checks require both active membership and active user status.
   - Evidence: `test_risk_owner_rejects_inactive_same_org_user`, `test_control_owner_validation_update_archive_and_audit`, and `test_control_test_definition_create_update_archive_and_tenant_scope` verify HTTP rejection and DB non-persistence.

## Per-Feature Verdicts

### Privacy & Data Protection

| Feature | Verdict | Evidence |
|---|---:|---|
| RoPA | SOLID after fix | Happy path report/activity tests pass; adversarial owner/DPIA/asset/subprocessor cross-tenant references now reject with DB non-persistence. |
| DSR/DSAR | SOLID | Lifecycle/SLA tests pass; status transition edge cases and org isolation covered in `test_dsar_d84_d90.py`. |
| CCPA Opt-Out | SOLID | Consent/notice suite covers preference and opt-out behavior with tenant-scoped HTTP flows. |
| Privacy Notices | SOLID | Publish/acknowledgement happy path and draft acknowledgement rejection covered. |
| Consent Management | SOLID | Consent lifecycle, preference state, and isolation tests pass. |
| Cookie Registry | SOLID | Cookie registry CRUD and notice linkage tests pass. |
| DPIAs | SOLID after fix | Workflow tests pass; cross-tenant reviewer rejected and DB state unchanged. |
| Lawful Basis Records | SOLID | Registry tests include valid and invalid legal basis/LIA behavior. |
| DPAs | SOLID | DPA lifecycle/status transition tests pass; owner/vendor/activity references are org-scoped. |
| Notification Preferences | SOLID | Preference endpoints covered in privacy notice/consent suite. |
| Fides Import | SOLID | Fides import and scorecard reverify tests pass with DB side-effect checks. |

### Data Observability

| Feature | Verdict | Evidence |
|---|---:|---|
| Data Asset Inventory | SOLID | Asset CRUD/classification tests pass; owner/custodian cross-tenant checks already present. |
| Data Lineage | SOLID | Lineage ingestion/configuration and quality linkage tests pass. |
| Data Quality Monitoring | SOLID | Metric submission happy path, invalid reading, and alerting coverage pass. |
| Data Access Monitoring | SOLID after fix | API-key ingest happy path passes; cross-tenant `actor_id` poisoning now rejected with DB non-persistence. |
| Data Retention | SOLID | Retention policy apply/sweep/review tests pass; no hard-delete pattern detected in service test assertion. |
| Data Residency | SOLID | Residency policy/check tests pass for allowed/disallowed geography. |
| Data Incidents | SOLID | Incident detection/status terminal-state tests pass. |
| Obligation Coverage | SOLID | Data-to-obligation linking, unlinking, audit, and org isolation tests pass. |
| Dashboard | SOLID | Dashboard scheduler and data-observability dashboard tests pass. |

### Risk Management

| Feature | Verdict | Evidence |
|---|---:|---|
| Risk Register | SOLID after fix | CRUD/scoring/org isolation tests pass; inactive owner now rejected and DB non-persistence asserted. |
| Risk Settings | SOLID | Existing risk settings and recalculation suites pass in full regression. |
| Risk Appetite Thresholds | SOLID after fix | Business-unit scope must now be same-org active BU; DB non-persistence asserted for foreign BU. |
| KRIs | SOLID | KRI CRUD/readings/threshold tests pass. |
| Entity Risk Scores | SOLID | Entity scoring and BU scoped tests pass. |
| AI/Compliance Risk Recommendations | SOLID | Recommendation generation/apply/dismiss tests pass. |
| Policy-Risk Linkages | SOLID | Mapping and graph tests pass with cross-org link rejection. |

### Policy Management

| Feature | Verdict | Evidence |
|---|---:|---|
| Policy CRUD & Versions | SOLID | Create/update/archive/version/approval tests pass; owner checks already require active user and membership. |
| Policy Drafting (AI) | SOLID | Draft generation/application tests pass; no third-party names added in user-facing text. |
| Policy Template Library | SOLID | Template CRUD/apply/versioning tests pass. |
| Policy Exceptions | SOLID | Exception workflow and org isolation tests pass. |
| Attestation Campaigns | SOLID | Campaign create/assign/remind/expire tests pass. |
| Employee Attestations | SOLID | Submission, exemption, stats, token, and cross-tenant tests pass. |
| Policy-Issue Linkages | SOLID | Link/unlink/filter/effectiveness tests pass. |
| Attestation Tokens | SOLID | Token access and cross-policy/org protections covered in employee attestation suite. |

### Compliance Frameworks & Obligations

| Feature | Verdict | Evidence |
|---|---:|---|
| Framework Catalog & Activation | SOLID | Catalog/detail/activation/idempotency/permission/isolation tests pass. |
| Framework Applicability | SOLID | Applicability rules/evaluation/update-state tests pass. |
| Framework Content & Coverage | SOLID | Content, evidence requirements, suggestions, and coverage-level tests pass. |
| Framework Pack Reviews | SOLID | Promotion/review pack tests pass. |
| Review Queue & SLA | SOLID | Assignment/SLA tests pass with outsider assignee rejection. |
| Reviewer Capacity | SOLID | Capacity policy, wave planning, validation, notifications, suggestions, and analytics tests pass. |
| Obligation Management | SOLID after fix | State update owner now same-org validated; framework activation and audit still pass. |
| Compliance Deadlines | SOLID | Deadline CRUD/status/owner/audit/org-isolation tests pass. |
| Compliance Dashboard | SOLID | Dashboard aggregation tests pass. |
| Board Scorecard | SOLID | Snapshot/BU-scoped scorecard tests pass. |
| Business Units | SOLID | Risk and scorecard BU references are validated against org scope in tested paths. |
| Scoring & Score Snapshots | SOLID | Score snapshot and scoring service tests pass. |

### Controls & Control Testing

| Feature | Verdict | Evidence |
|---|---:|---|
| Control Register | SOLID after fix | CRUD/archive/audit/org isolation tests pass; inactive owner now rejected. |
| Control Testing | SOLID after fix | Test definition/run/scoring tests pass; inactive owner now rejected. |
| Control Recommendations | SOLID | Recommendation generation/apply tests pass. |
| Common Controls | SOLID | Common control CRUD/coverage tests pass. |
| Technical Controls | SOLID | Agent/rule/result ingest tests pass. |
| Control Exceptions | SOLID | Exception workflow, approval, expiry, and org isolation tests pass. |
| Control Monitoring + Rules + Alerts | SOLID | Definition/rule/alert lifecycle and task creation tests pass. |
| OSCAL Exports | SOLID | Export paths covered by full regression; no failures in assigned control export surface. |

## Remaining Weak/Broken Items

None left in this assigned slice after the fixes above.

Residual non-blocking test-suite notes:

- `tests/integration/test_postgres_migration_smoke.py::test_postgres_migration_smoke_upgrade_head` skipped because `POSTGRES_TEST_DATABASE_URL` is not set.
- Warning noise remains from deprecated Starlette/FastAPI/Pydantic APIs, unknown pytest marks, and SQLAlchemy table-sort cycles. These did not fail the suite and were outside this verification slice.

## Commit Notes

Files changed are limited to service/router validation and focused tests. No migrations were required.
