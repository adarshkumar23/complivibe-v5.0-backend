# Final Sweep C: TPRM, Financial Resilience, Financial Crime Remainder

Worktree: `/home/ubuntu/complivibe-v4.0/complivibe-sweep-c`
Branch: `final-sweep-c`
Date: 2026-07-05

## Scope And Method

This sweep covered TPRM T1-1 through T1-6 plus T4-5/T4-6, Financial Resilience T2-1 through T2-5, and Financial Crime T4-7/T4-8. I copied the real backend `.env` into this worktree before verification, installed the local test environment, checked Alembic head, exercised the feature endpoints through FastAPI test clients, and confirmed side effects with ORM/SQLAlchemy database reads in the same tests.

External source check: official sanctions/export-control screening sources were checked to calibrate realistic denied-party test expectations. The code verification itself used local seeded test data and did not call production systems.

Alembic status:

```text
.venv/bin/alembic heads
0243_export_control_compliance (head)
```

No migrations were added.

## Fixes Made

1. Vendor mitigation case ownership validation
   - Before: `assigned_owner_id` on vendor mitigation cases was persisted without proving same-organization active membership.
   - Fix: `VendorMitigationService.create_case` now requires `assigned_owner_id` to belong to the case organization and to have active user/account/membership status.
   - Evidence: added HTTP tests that submit Org B's user and an inactive same-org user; both return `422`, and DB queries confirm no mitigation case rows are created.

2. BCM/BIA inactive user handling
   - Before: BCM process owner and BIA reviewer checks only required a membership row, not active membership/account status. Staleness only detected `User.is_active=False`.
   - Fix: `BcmService._validate_org_user` now requires active user status, `is_active=True`, and active membership. Staleness now also detects inactive owner user status and inactive/missing owner organization membership.
   - Evidence: added HTTP tests rejecting inactive process owner and BIA reviewer references, with DB non-persistence checks; added stale-review test where owner membership/status are deactivated after process creation.

3. KYB/AML own-vendor risk and stale cleanup
   - Before: KYB/AML only propagated nth-party alerts; the screened vendor's own `risk_tier` stayed unchanged. A clean recompute did not resolve previous KYB nth-party alerts/flags. There was no scheduled KYB rescreen path.
   - Fix: KYB compute now applies a shared `compute_vendor_kyb_check_and_apply_effects` helper for API and sweep paths. Risky KYB escalates the screened vendor's own risk tier, persists pre-escalation metadata, emits audit rows, propagates nth-party alerts, and refreshes existing concentration detections. A clean recompute resolves `kyb_aml_risk_flagged` supply-chain alerts and restores KYB-escalated own risk tier when safe. Added `run_periodic_vendor_kyb_rescreen_sweep` and scheduler registration `vendor_kyb_rescreen_sweep`.
   - Evidence: added HTTP/DB tests for risky KYB self-escalation, clean recompute restoration and alert resolution, and periodic KYB rescreen discovering new adverse-media risk.

## Verification Commands

Focused regression after fixes:

```text
.venv/bin/pytest tests/unit/test_trust_ai_mitigation_a56_a57_a58.py tests/unit/test_bcm_t2_2.py tests/unit/test_tprm_intelligence_satellite.py -q
Result: exit 0
```

Full assigned-slice suite:

```text
.venv/bin/pytest tests/unit/test_risk_quantification_t2_1.py tests/unit/test_bcm_t2_2.py tests/unit/test_crisis_management_t2_3.py tests/unit/test_resilience_testing_t2_4.py tests/unit/test_whistleblower_t2_5.py tests/unit/test_bribery_risk_assessment_t4_7.py tests/unit/test_export_control_t4_8.py tests/unit/test_tprm_intelligence_satellite.py tests/unit/test_vendor_criticality_scoring_t1_4.py tests/unit/test_vendor_remediation_portal_t1_5.py tests/unit/test_vendor_concentration_risk_t1_6.py tests/unit/test_chain_sanctions_concentration_crosscheck.py tests/unit/test_trust_ai_mitigation_a56_a57_a58.py -q
Result: exit 0
```

Final full regression on final code state:

```text
.venv/bin/pytest -q
Result: exit 0
Collected tests: 1369
Skipped: tests/integration/test_postgres_migration_smoke.py::test_postgres_migration_smoke_upgrade_head because POSTGRES_TEST_DATABASE_URL is not set
```

Other checks:

```text
git diff --check
Result: exit 0
```

## Per-Feature Verdicts

| Feature | Verdict | Evidence |
| --- | --- | --- |
| T1-1 Continuous Vendor Monitoring | SOLID | HTTP compute/get tests persist `VendorExternalRating`; DB asserts rating row and audit log; stale threat-intel history covered. Cross-org vendor compute returns 404. |
| T1-2 Threat Intelligence | SOLID | HTTP compute/get/history tests persist threat intel, show trend/staleness, and reject malformed/cross-org access; DB row/audit asserted. |
| T1-3 Supply Chain Visibility | SOLID | HTTP link/graph tests cover A->B->C->A cycle detection, bad/cross-org links, depth-bounded graph traversal, nth-party alert propagation, and DB alert state. |
| T1-4 Criticality Scoring | SOLID | HTTP recompute tests manually verify weighted formula inputs/outputs and DB persistence/audit. Invalid/boundary inputs covered. |
| T1-5 Remediation Portal | SOLID | Portal token tests cover happy path, expiry, revocation, malformed/forged token, cross-tenant use, and DB evidence/message side effects. |
| T1-6 Concentration Risk | SOLID | Recompute tests cover HHI math, duplicate-prevention on repeated recompute, risk creation only once, and sanctions/KYB-driven concentration refresh when already tracked. |
| T4-5 AML/KYC Workflow | SOLID after fix | Happy path persists `AmlKycCheck`; adverse/offshore result now escalates own vendor risk tier, propagates nth-party alert, and writes audit rows. Clean recompute resolves stale KYB alerts and restores KYB-escalated tier. Periodic KYB sweep now exists and is scheduler-registered. |
| T4-6 Sanctions Screening | SOLID | Local denied-party dataset match creates `SanctionsScreenResult`, escalates own vendor risk, propagates nth-party risk, clear restores pre-escalation tier, and periodic rescreen catches newly listed vendor. Cross-org and no-false-match cases covered. |
| T2-1 Quantitative Risk Assessment | SOLID | HTTP quantify/history tests persist runs and audit rows. FAIR/Monte Carlo output is hand-verified in tests for deterministic input; degenerate inputs (`min > max`, missing key, negative frequency) return 422 instead of NaN/negative loss propagation. |
| T2-2 BCM/BIA | SOLID after fix | HTTP process/BIA tests cover happy path and stale review window. Owner deactivation now detects inactive account/status and inactive membership. Inactive owner/reviewer references are rejected with DB non-persistence. |
| T2-3 Crisis Management Playbooks | SOLID | HTTP playbook activation tests persist activations and messages; activation cross-references linked business processes and high/critical risks; org isolation and bad transitions covered. |
| T2-4 DORA Resilience Testing | SOLID | HTTP resilience tests verify org-configured cadence overdue calculation, completion workflow, DB persistence, and auto-created issue entries for high/critical findings. Existing implementation creates issues, not separate risk rows; this matches the observed code path and tests. |
| T2-5 Whistleblower Hotline | SOLID with bearer-token hardening note | Public submit, reporter status/message, investigator list/reply/status update are exercised end-to-end. DB checks show no user/IP/session identity stored for anonymous submission; audit rows for public submit/reporter message do not include actor/IP/user-agent. Adversarial checks did not find an endpoint, log, or audit trail that maps anonymous ID to a real identity. Residual note: reporter tracking code is a bearer secret in URL paths, so deployment should avoid logging full paths at proxies/APM. |
| T4-7 Anti-Bribery & Corruption | SOLID | HTTP compute/get/history tests cover 3+ records without `MultipleResultsFound`, score persistence, audit rows, invalid PEP exposure, negative gift value, and cross-org vendor isolation. |
| T4-8 Export Control Compliance | SOLID | HTTP screen/get/history tests cover realistic denied-party/local sanctions entity matching, ECCN/destination validation, DB persistence/audit, invalid ECCN/destination rejection, and cross-org isolation. |

## Cross-Tenant Reference Audit

The recurring owner/assignee/contact/reference class was checked in this slice:

- Vendor owner references: existing vendor create/update tests validate same-org owner handling.
- Vendor assessment assigned user references: existing tests cover same-org assignment behavior.
- Vendor mitigation `assigned_owner_id`: broken class reproduced and fixed in this sweep.
- Vendor mitigation `evidence_id`: existing tests reject wrong-org evidence.
- BCM process `owner_user_id` and BIA `reviewed_by_user_id`: inactive reference weakness reproduced and fixed; wrong-org membership already rejected.
- TPRM graph references (`sub_vendor_id`, alert triggering vendor): existing tests reject wrong-org graph links and cross-org reads.
- Sanctions/KYB/bribery/export-control vendor references: `VendorService.require_vendor_in_org` gates compute/get/history paths; cross-org HTTP tests return 404.
- Whistleblower investigator workflow: investigator endpoints are organization-scoped and tested through authenticated org headers; public reporter flow uses tracking secret rather than user identity.

## Whistleblower Anonymity Verdict

Verdict: SOLID with operational hardening note.

Reproduction attempts:

- Submitted anonymous report through public endpoint with no authenticated user.
- Queried reporter status/replies using the returned tracking code.
- Used investigator workflow to list, view, reply, and change status.
- Queried DB rows for `WhistleblowerReport`, `WhistleblowerMessage`, and `AuditLog` side effects.
- Checked public audit trail behavior for actor/IP/user-agent leakage.

Result:

- The anonymous report can be investigated and responded to end-to-end.
- DB rows retain anonymous tracking/report metadata needed for workflow, but do not link to a platform `User`, membership, IP address, or user agent for the public reporter.
- No endpoint tested exposed a real identity behind the anonymous report.
- The tracking code remains a bearer secret in URL paths. That does not identify the reporter by itself, but it should be treated as sensitive in ingress/proxy/APM logs.

## Residual Risks / Out Of Scope

- PostgreSQL migration smoke was skipped because `POSTGRES_TEST_DATABASE_URL` is not set in this worktree environment. Alembic head was checked locally and no new migration was introduced.
- The sweep did not touch production or push any branch.
- Sanctions/export-control verification used local seeded realistic denied-party data for deterministic tests, not live production list downloads.
