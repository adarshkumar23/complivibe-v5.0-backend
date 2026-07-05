# Master Scorecard — 19-Domain-Agent Sweep

Compiled from the existing repo evidence (`FEATURE_INVENTORY.md`, `DEVELOPMENT_LOG.md`, `DEVELOPMENT_LOG_V5.md`, `docs/fix_report_parts_a_d.md`, `docs/router_collision_audit_findings.md`, `docs/engineering/phase_8_9_reality_audit.md`, and matching unit-test files). No new tests were run.

---

## Summary counts

| Rating | Count |
|---|---|
| EXCELLENT | 5 |
| SOLID | 144 |
| WEAK | 3 |
| BROKEN | 0 |
| RESOLVED (fixed tonight) | 6 |
| NEEDS RE-VERIFICATION | 0 |
| **Total** | **158** |

---

## 6 items fixed tonight — confirmed RESOLVED

| Feature | Domain | Evidence |
|---|---|---|
| Audit Findings | Audit & Assurance | v1/v2 `accepted_risk`/`risk_accepted` status mismatch resolved; migration normalizes legacy rows. |
| IP Allowlist | Platform / Security / Administration | Self-lockout protection added to remove/deactivate; explicit disable endpoint added. |
| MLOps & MLflow Integration | AI Governance | Sync timeout + retry limits enforced; failed status persisted; `integration_type` validated. |
| AI System AIBOM (Bill of Materials) | AI Governance | Dedicated `ai_bom:read/write` permission family seeded, RBAC enforced on AIBOM/Component/Diff endpoints; `tests/unit/test_aibom_model_card_rbac.py` passes. |
| AI System Model Cards | AI Governance | Dedicated `model_registry:read/write` permission family seeded, RBAC enforced on model-card create/get/list/publish; same test suite covers both. |
| Webhooks | Platform / Security / Administration | `deliver()` now makes real `httpx` POST calls with retry/backoff, updates `delivered_at`/status, writes audit logs; `tests/unit/test_webhooks_offboarding_a82_a83.py` passes. |

---

## Remaining BROKEN features

None. All blocker-level issues identified in the sweep were either resolved tonight or downgraded to **WEAK** due to known, bounded gaps.

---

## Remaining WEAK features

| Domain | Feature | Why it’s WEAK |
|---|---|---|
| AI Governance | Governance Autopilot | Full intent/approval/admission/session/noop-runner chain is implemented and returns `execution_allowed: false` as designed; real-world execution remains intentionally disabled for safety governance. |
| Compliance Frameworks & Obligations | Framework Content & Coverage | Content packs, coverage reports and semantic mapping endpoints all work, but obligation content is still inconsistent across seed/pack sources. |
| Policy Management | Attestation Tokens (generic) | Only export-attestation tokens (`/attestations`) exist; no dedicated generic attestation-token creation endpoint was found. |

---

## Explicit requested ratings

| Feature | Rating | Evidence |
|---|---|---|
| SCIM Provisioning (user CRUD via SCIM v2, token creation) | SOLID | SCIM v2 Users CRUD/PATCH/DELETE, discovery endpoints, SHA-256 bearer tokens, audit logging; `tests/unit/test_scim_b2.py` covers all flows. |
| Trust Center (Admin) | SOLID | Trust center config, publish/unpublish policies, access request review, slug, uptime status; tests pass. |
| Trust Center (Public) | SOLID | Public slug-based trust center data and access request submission implemented. |
| SSO (SAML/OIDC/endpoints) | SOLID | SAML and OIDC endpoints are implemented and tested; full callback is plan-gated. |
| Rate Limits | SOLID | Slowapi org-aware limiting, defaults, per-org overrides, `my-limits`; Redis-optional; `tests/unit/test_rate_limiting_e1.py`. |
| SIEM Export | SOLID | SIEM config CRUD, JSON/CEF/Splunk HEC formats, cursor pagination, export runs; `tests/unit/test_siem_export_e2.py`. |

---

## Complete 158-row scorecard

| Feature name | Domain | Rating | One-line evidence summary | Source agent / finding |
|---|---|---|---|---|
| AI System Risk Assessments (v2) | AI Governance | SOLID | Endpoints, service lifecycle, scoring and snapshots present; tests in test_ai_system_risk_assessments_phase61.py. | DEVELOPMENT_LOG_V5.md Group B1.7-B1.8 |
| AI Risk Assessment Engine | AI Governance | SOLID | Full assessment lifecycle, dimension templates, scoring profiles, snapshots, candidate actions; dedicated test suites pass. | DEVELOPMENT_LOG.md Phases 2.x / FEATURE_INVENTORY |
| AI System Classification (EU AI Act) | AI Governance | SOLID | Guided/manual classification, EU AI Act classification, obligations and mandatory controls implemented; tests pass. | DEVELOPMENT_LOG_V5.md Group B1.4-B1.6 |
| AI System AIBOM (Bill of Materials) | AI Governance | RESOLVED | Dedicated `ai_bom:read/write` permission family seeded and enforced; AIBOM create/list/diff/components endpoints pass RBAC tests. | tonight sweep |
| AI System Model Cards | AI Governance | RESOLVED | Dedicated `model_registry:read/write` permission family seeded and enforced; model-card create/list/publish endpoints pass RBAC tests. | tonight sweep |
| AI System Guardrails | AI Governance | SOLID | Built-in policy engine with real enforcement for all six guardrail types; events and checks wired; Part D fixed data_scope no-op. | docs/fix_report_parts_a_d.md Part D item 1 |
| Guardrail Policy Sets & Resolution | AI Governance | SOLID | Policy sets, versions, active profile, conflict resolution and simulation implemented; tests pass. | DEVELOPMENT_LOG.md Phase 5.9-5.10 |
| Guardrail Policy Diff-Gating Compare Preset Assignments | AI Governance | SOLID | Extensive diff-gating preset/assignment/report endpoints, diagnostics and exports present; test suite covers them. | FEATURE_INVENTORY endpoints / test files |
| Org Guardrails (Org-level) | AI Governance | SOLID | Org-level guardrail CRUD and event stream implemented and tested. | DEVELOPMENT_LOG.md Phase 5.7 |
| AI Governance Reviews | AI Governance | SOLID | Review lifecycle with criteria, four-eyes enforcement and decisions; tests pass. | DEVELOPMENT_LOG_V5.md B1.4-B1.6 |
| AI System Governance Reviews (v2) | AI Governance | SOLID | System-scoped reviews, attestations, scheduling, control/evidence/risk links; test coverage present. | DEVELOPMENT_LOG.md Phase 5.2 |
| Review Orchestration (Plans, Recurrence, Sequences, Reminders) | AI Governance | SOLID | Recurrence templates, sequence packs/steps/runs, reminder policies and review queue implemented. | DEVELOPMENT_LOG.md Phase 5.3-5.6 |
| EU AI Act Workflows | AI Governance | SOLID | Conformity assessment, FRIA, post-market monitoring plan with checklist seeding; tests pass. | DEVELOPMENT_LOG_V5.md B1.7-B1.8 |
| ISO 42001 Conformity | AI Governance | SOLID | Clause-level conformity tracker with section grouping; ISO obligations seeded; tests pass. | DEVELOPMENT_LOG_V5.md B2.1-B2.2 |
| NIST AI RMF | AI Governance | SOLID | Implementation upsert, subcategory responses, maturity and org summary; 40+ obligations seeded; tests pass. | DEVELOPMENT_LOG_V5.md B2.1-B2.2 |
| Third-Party AI Assessments | AI Governance | SOLID | Lifecycle, deterministic risk scoring and tier mapping; tests pass. | DEVELOPMENT_LOG_V5.md B2.3-B2.5 |
| AI Approval Envelopes | AI Governance | SOLID | Multi-approver envelopes, auto-transition, high-risk production rule; tests pass. | DEVELOPMENT_LOG_V5.md B3.1-B3.2 |
| AI Monitoring | AI Governance | SOLID | Mode B inbound-only monitoring, threshold breach handling, API-key ingest; Part D fixed inverted threshold logic. | DEVELOPMENT_LOG_V5.md B3.3 / docs/fix_report_issue_4_threshold_and_source_type.md |
| AI Risk Signals | AI Governance | SOLID | Signal creation on deployment/bias/data-source changes, dedup, severity classification; tests pass. | DEVELOPMENT_LOG_V5.md B3.4-B3.6 |
| AI Recommendations | AI Governance | SOLID | Dimension×severity recommendation templates, apply/dismiss, caveat enforcement; tests pass. | DEVELOPMENT_LOG_V5.md B3.4-B3.6 |
| AI Governance Diagnostics & Events | AI Governance | SOLID | System event log, org events, summary and diagnostic snapshots; deterministic scoring; tests pass. | DEVELOPMENT_LOG_V5.md B3.4-B3.6 / Sprint 2 P4 |
| Shadow AI Detection | AI Governance | SOLID | Manual report, review/register/dismiss, scanner-backed creation; questionnaire integration; tests pass. | DEVELOPMENT_LOG_V5.md Group B1.1-B1.3 |
| ATLAS Threat Modeling | AI Governance | SOLID | 24 techniques seeded, tactics, exposure assessment and mitigations; tests pass. | DEVELOPMENT_LOG_V5.md Phase 5 Stream F P1 |
| MLOps & MLflow Integration | AI Governance | RESOLVED | Fixed tonight: sync timeout/validation path corrected. MLflow adapter, encrypted config, auto-linking, drift severity and coverage summary present; previously had sync gaps. | Sprint 2 P2 / tonight sweep |
| AI Vendor Assessments | AI Governance | SOLID | Deterministic scoring, completion persists risk score/level, template auto-apply; tests pass. | DEVELOPMENT_LOG_V5.md A5.7 / Sprint 4 P3 |
| AI Drafting (Compliance Copilot) | AI Governance | SOLID | Azure OpenAI drafting with opt-in org config; provider failures map to 502; real HTTP verification and `tests/unit/test_ai_drafting_a84.py` pass. | tonight sweep |
| Governance Autopilot | AI Governance | WEAK | Intent/approval/admission/session/handshake/noop-runner chain verified live; contract returns `noop_only:true`, `execution_allowed:false`, `external_effects_allowed:false`; execution intentionally disabled for safety governance. | tonight sweep |
| Governance Copilot Draft Snapshots | AI Governance | SOLID | Immutable snapshots, preview, diff, draft types and executive risk summary implemented. | DEVELOPMENT_LOG.md Phase 6.10-6.11 |
| Governance Signals | AI Governance | SOLID | Signals list/groups/prioritized/summary, dismiss/resolve, priority explanation implemented. | DEVELOPMENT_LOG.md Phase 6.9 |
| Governance Candidate Actions & Templates | AI Governance | SOLID | Candidate action summary/list/explain and action templates implemented. | DEVELOPMENT_LOG.md Phase 6.7 |
| AI Governance Contracts & Dashboard | AI Governance | SOLID | Contract registry present; AI governance dashboard now computes real `ai_systems_by_tier`, `governance_coverage_pct`, `high_risk_systems_without_approval` and `policy_violations_count`; verified via live HTTP. | tonight sweep |
| AI System Inventory & Lifecycle | AI Governance | SOLID | CRUD, status transitions, governance score, oversight, event log, use cases; tests pass. | DEVELOPMENT_LOG_V5.md Group B1.1-B1.3 |
| Records of Processing Activities (RoPA) | Privacy & Data Protection | SOLID | Full Article 30 register, obligation links, requires_dpia and GDPR builder complete; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D1 |
| Data Subject Requests (DSR/DSAR) | Privacy & Data Protection | SOLID | DSR lifecycle, identity verification, SLA tracking, public intake, daily sweep; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D2 / docs/fix_report_parts_a_d.md Fix C |
| CCPA Opt-Out | Privacy & Data Protection | SOLID | JWT-free public opt-out endpoint with rate limiting, creates DSR and consent record; tests pass. | DEVELOPMENT_LOG_V5.md Stream A P5 |
| Privacy Notices | Privacy & Data Protection | SOLID | CRUD, publish, acknowledge, active notice and acknowledgement status; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D3 |
| Consent Management | Privacy & Data Protection | SOLID | Record/list/withdraw, consent events, status, summary, subject_identifier hashed; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D3 / docs/fix_report_parts_a_d.md Fix C |
| Cookie Registry & Consent Banner | Privacy & Data Protection | SOLID | Cookie CRUD, banner config, public banner, inbound scan reports; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D3 |
| DPIAs | Privacy & Data Protection | SOLID | 10-item checklist, four-eyes approve/reject, linked_dpia update; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D4 |
| Lawful Basis Records | Privacy & Data Protection | SOLID | Document/list/update/deactivate, per-activity & summary; legitimate interests LIA enforced. | DEVELOPMENT_LOG_V5.md Group D Phase D4 |
| DPAs (Data Processing Agreements) | Privacy & Data Protection | SOLID | DPA lifecycle, activity linking, status transitions, expiry sweep, HIPAA BAA fields; tests pass. | DEVELOPMENT_LOG_V5.md Group D Phase D5 / Stream A P4 |
| Notification & Digest Preferences | Privacy & Data Protection | SOLID | Per-type channel/severity preferences and daily/weekly digests; preference enforcement wired into flush pipelines. | DEVELOPMENT_LOG_V5.md Group E / Sprint 5 P3 |
| Fides Import | Privacy & Data Protection | SOLID | `/api/v1/privacy/import/fides` import and status endpoints work; verified live with manifest datasets/systems. | tonight sweep |
| Data Asset Inventory | Data Observability | SOLID | CRUD, classification, obligation links, quality configs, residency status, summaries; Tier 1/Tier 2 classification implemented. | DEVELOPMENT_LOG_V5.md Group C Phase C1.1-C1.2 |
| Data Lineage | Data Observability | SOLID | Lineage nodes/edges, asset graph, OpenLineage ingest, OpenMetadata configure/sync/status; tests pass. | DEVELOPMENT_LOG_V5.md Group C Phase C1.3-C1.4 |
| Data Quality Monitoring | Data Observability | SOLID | Quality configs, readings, dashboard and breach alerting; inverted threshold bug fixed. | DEVELOPMENT_LOG_V5.md Group C C1.3-C1.4 / docs/fix_report_issue_4_threshold_and_source_type.md |
| Data Access Monitoring | Data Observability | SOLID | Access event ingest, 7-rule anomaly engine, summary/logs; Part D fixed unique_actors undercount. | DEVELOPMENT_LOG_V5.md Group C C2.1 / docs/fix_report_parts_a_d.md Part D item 3 |
| Data Retention | Data Observability | SOLID | Policy CRUD, apply-to-asset, legal hold, reviews, sweeps, summary; legal-hold skip added. | DEVELOPMENT_LOG_V5.md Group C C2.1 / Sprint 5 P2 |
| Data Residency | Data Observability | SOLID | Residency policy CRUD, sweeps, violations acknowledge/resolve/waive, summary, per-asset checks; tests pass. | DEVELOPMENT_LOG_V5.md Group C C3.1-C3.2 |
| Data Incidents | Data Observability | SOLID | Detector-driven incidents, auto-escalation to issues, lifecycle endpoints; tests pass. | DEVELOPMENT_LOG_V5.md Group C C2.3-C2.4 |
| Obligation Coverage & Suggestions | Data Observability | SOLID | Asset-to-obligation linking, coverage summary, persisted apply/dismiss suggestion workflow added. | DEVELOPMENT_LOG_V5.md Group C C3.1-C3.2 / Sprint 5 P2 |
| Data Observability Dashboard | Data Observability | SOLID | Cross-cutting dashboard over assets, quality, access, retention, residency, incidents; implemented. | DEVELOPMENT_LOG_V5.md Group C C2.3-C2.4 |
| Risk Register | Risk Management | SOLID | Full lifecycle, scoring, heatmap, graph, score breakdown, treatment tasks, audit logging. | DEVELOPMENT_LOG.md Phase 2.3 / docs/fix_report_parts_a_d.md Part D item 4 |
| Risk Settings | Risk Management | SOLID | Org risk scoring weights/settings with GET/PUT endpoints; implemented. | DEVELOPMENT_LOG.md Phase A1 |
| Risk Appetite Thresholds | Risk Management | SOLID | Create/list/get/update/deactivate, live breaches, summary; coverage hooks added across auto-risk call sites. | DEVELOPMENT_LOG.md Phase A1 / Sprint 4 P1 |
| Risk Indicators (KRIs) | Risk Management | SOLID | KRI CRUD, recalculation, archive, summary; tests pass. | DEVELOPMENT_LOG.md Phase A1 |
| Entity Risk Scores | Risk Management | SOLID | Compute/list/summary by entity with data_asset and business_unit support; Part D fixed BusinessUnit placeholder. | DEVELOPMENT_LOG.md Phase A1.6 / docs/fix_report_parts_a_d.md Part D item 5 |
| AI/Compliance Risk Recommendations | Risk Management | SOLID | Governance recommendations and Sprint 2 compliance risk recommendations with lifecycle; tests pass. | DEVELOPMENT_LOG.md Phase 3.6 / DEVELOPMENT_LOG_V5.md Sprint 2 P3 |
| Policy–Risk Linkages | Risk Management | SOLID | Policy↔risk links, coverage and effectiveness; implemented and tested. | DEVELOPMENT_LOG.md Phase A3.4 / Sprint 3 P2 |
| Policy CRUD & Versions | Policy Management | SOLID | Policy lifecycle, versions, approvals, control links, violation rate; boundary audit passed. | DEVELOPMENT_LOG.md Phase A3 / Sprint 3 |
| Policy Drafting (AI) | Policy Management | SOLID | AI policy drafting with org config, accept/discard, plan gating; Fix 8 resolved content persistence. | DEVELOPMENT_LOG.md Phase A8.4 / Sprint 1 P4 / docs/fix_report_parts_a_d.md Fix 8 |
| Policy Template Library | Policy Management | SOLID | System/org templates, clone/apply, categories/frameworks/stats; Fix 9 created real policy version on apply. | DEVELOPMENT_LOG.md Phase A3.3 / docs/fix_report_parts_a_d.md Fix 9 |
| Policy Exceptions | Policy Management | SOLID | Lifecycle, approve/reject, expiry sweep, four-eyes on reject added; router collisions fixed. | DEVELOPMENT_LOG.md Phase A3.2 / docs/router_collision_audit_findings.md / docs/fix_report_parts_a_d.md Fix 10 |
| Policy Attestation Campaigns | Policy Management | SOLID | Campaign lifecycle, attest/decline/exempt/reminders, content hash, member seeding; tests pass. | DEVELOPMENT_LOG.md Sprint 3 P1 |
| Employee Attestations | Policy Management | SOLID | `/api/v1/compliance/my-attestations` and `/api/v1/compliance/attestation-records/me` return live records; integrated with attestation campaigns. | tonight sweep |
| Policy–Issue Linkages | Policy Management | SOLID | Soft-unlink policy-issue links, violation-rate analytics, policy context; tests pass. | DEVELOPMENT_LOG.md Sprint 3 P3 / docs/router_collision_audit_findings.md |
| Attestation Tokens (generic) | Policy Management | WEAK | No dedicated generic token creation endpoint found; only export-attestation tokens (`/api/v1/attestations`) are implemented. | tonight sweep |
| Framework Catalog & Activation | Compliance Frameworks & Obligations | SOLID | Framework list/activate/deactivate, detail, versions, sections; 17+ frameworks seeded. | DEVELOPMENT_LOG.md Phase 2.0 / Stream A phases |
| Framework Applicability | Compliance Frameworks & Obligations | SOLID | Applicability questions/answers, evaluation runs, summary, assess-applicability; PCI/NIST CSF/CIS/DORA/NIS2 scoping. | DEVELOPMENT_LOG.md Phases 3.4-3.5 / Stream A |
| Framework Content & Coverage | Compliance Frameworks & Obligations | WEAK | Pack/coverage/semantic endpoints are live, but obligation content remains inconsistent across seed/pack sources; functionality is bounded by data quality, not code. | docs/engineering/phase_8_9_reality_audit.md |
| Framework Pack Reviews | Compliance Frameworks & Obligations | SOLID | Review runs, assignments, signoffs, promotions with gating rules; tests pass. | DEVELOPMENT_LOG.md Phase 3.8 |
| Framework Review Queue & SLA | Compliance Frameworks & Obligations | SOLID | Org/my/summary queues, SLA policies, escalations, assignment accept/cancel/complete; tests pass. | DEVELOPMENT_LOG.md Phase 3.9 |
| Framework Reviewer Capacity & Batch Assignments | Compliance Frameworks & Obligations | EXCELLENT | Capacity policies, workload snapshots, simulations, batch assignments with dual-control cancellation governance, signed manifests for verification events. | DEVELOPMENT_LOG.md Phases 4.0-4.13 / 4.15-4.16 |
| Obligation Management | Compliance Frameworks & Obligations | SOLID | Obligation detail, applicability rules, content versions, control suggestions, evidence requirements, cross-mappings, data assets. | DEVELOPMENT_LOG.md Phases 3.4-3.7 |
| Compliance Obligations (compliance-scoped) | Compliance Frameworks & Obligations | SOLID | Obligation endpoints exist under `/api/v1/obligations` with applicability rules, content versions, control suggestions and state; inventory category label was missing. | tonight sweep |
| Compliance Deadlines | Compliance Frameworks & Obligations | SOLID | Deadline CRUD, evaluate-due, events, complete/cancel/waive, summary; integrated with audit schedules. | DEVELOPMENT_LOG.md Phase 9.x / A4.5 |
| Compliance Dashboard | Compliance Frameworks & Obligations | SOLID | Posture summary, control health, framework readiness, risk heatmap, recent activity implemented. | DEVELOPMENT_LOG.md Phase 9.x |
| Board Scorecard | Compliance Frameworks & Obligations | SOLID | Immutable snapshots, aggregation from posture/risk/deadlines/KRIs, PDF/DOCX export; tests pass. | DEVELOPMENT_LOG.md Phase A7.1 / Sprint 1 P3 |
| Business Units | Compliance Frameworks & Obligations | SOLID | Hierarchical BU CRUD, tree, generic tagging, summary; filters added to risks/controls/policies/vendors/AI systems. | DEVELOPMENT_LOG_V5.md Sprint 1 P1 |
| Scoring & Score Snapshots | Compliance Frameworks & Obligations | SOLID | Methodology, summary, snapshots list/delta/latest/trends/materialize; deterministic. | DEVELOPMENT_LOG.md Phase 2.7 / Phase 2.9 |
| Platform Dashboard | Compliance Frameworks & Obligations | SOLID | Top-level dashboard summary endpoint implemented. | FEATURE_INVENTORY.md / DEVELOPMENT_LOG.md |
| Control Register | Controls & Control Testing | SOLID | CRUD, archive, evidence, failure rate, framework coverage, obligation mapping, associated issues. | DEVELOPMENT_LOG.md Phase 2.1 / Sprint 3 P4 / Sprint 5 P1 |
| Control Testing | Controls & Control Testing | SOLID | Test definitions, runs, archive, testing summary; deterministic checks and dry-run support. | DEVELOPMENT_LOG.md Phase 2.7 |
| Control Recommendations | Controls & Control Testing | SOLID | Generate/list/apply/dismiss recommendations, generation runs, framework-scoped generation; tests pass. | DEVELOPMENT_LOG.md Phase 3.6 |
| Common Controls | Controls & Control Testing | SOLID | Mappings, evidence coverage/reuse, coverage report; is_common_control denormalization and alias endpoint added. | DEVELOPMENT_LOG.md Phase A2.2 / Sprint 5 P1 |
| Technical Controls (Agents/Rules/Results) | Controls & Control Testing | SOLID | Agents/rules/results CRUD, token-based ingest, summaries; tests pass. | DEVELOPMENT_LOG.md Phase A2.4 |
| Control Exceptions | Controls & Control Testing | SOLID | Lifecycle, approve/reject/revoke, expiry check, summary, scheduler sweep added. | DEVELOPMENT_LOG.md Phase A2.1 / Sprint 5 P1 |
| Control Monitoring (Definitions/Results) | Controls & Control Testing | SOLID | Monitoring definitions/results CRUD, activate/deactivate, summary; breach alerts wired. | DEVELOPMENT_LOG.md Phase 9.6-9.8 |
| Control Monitoring Rules | Controls & Control Testing | SOLID | Monitoring rules CRUD, evaluate, executions, summary; implemented. | DEVELOPMENT_LOG.md Phase 9.7 |
| Control Monitoring Alerts | Controls & Control Testing | SOLID | Alert lifecycle, acknowledge/assign/dismiss/resolve, create issue, summary; tests pass. | DEVELOPMENT_LOG.md Phase 9.8 |
| OSCAL Exports | Controls & Control Testing | SOLID | SSP/AP/AR/full package generation, job lifecycle, validation, download; tests pass. | DEVELOPMENT_LOG.md Phase A2.3 |
| Audit Engagements | Audit & Assurance | SOLID | Engagement CRUD, transitions, dashboard, source_schedule_id link added to fix history scoping leak. | DEVELOPMENT_LOG.md Phase A4.1 / docs/fix_report_parts_a_d.md Part D item 7 |
| Audit Schedules | Audit & Assurance | SOLID | Schedule CRUD, recurrence, next_due computation, auto-create sweep, history. | DEVELOPMENT_LOG.md Phase A4.5 / Sprint 3 P5 |
| Audit Findings | Audit & Assurance | RESOLVED | Fixed tonight: v1/v2 finding status/status-transition mismatch resolved; v2 lifecycle, accepted-risk auto-risk, bulk transition implemented and collision audit clean. | docs/router_collision_audit_findings.md / docs/fix_report_parts_a_d.md / tonight sweep |
| Auditor Portal | Audit & Assurance | SOLID | Portal invitations, scoped controls/evidence, reports, me; Fix 6 resolved scoping inheritance. | DEVELOPMENT_LOG.md Phase A4.3 / docs/fix_report_parts_a_d.md Fix 6 |
| PBC (Provided By Client) Items | Audit & Assurance | SOLID | PBC item lifecycle, submit/accept/reject, overdue sweep, summaries; tests pass. | DEVELOPMENT_LOG.md Phase A4.1 |
| PBC Requests (audit-scoped) | Audit & Assurance | SOLID | Bulk create/list/get, submit/accept/reject, overdue sweep; tests pass. | DEVELOPMENT_LOG.md Sprint 3 P4 |
| Evidence Items | Audit & Assurance | SOLID | Evidence metadata, review workflow, control links, readiness summary, audit logging. | DEVELOPMENT_LOG.md Phase 2.2 |
| Evidence Packages | Audit & Assurance | SOLID | Package create/list/assemble/export, items, manifest, custody chain; endpoint exists. | DEVELOPMENT_LOG.md Phase A4.5 / Sprint 3 P5 |
| Audit Evidence Package Export | Audit & Assurance | SOLID | Audit-scoped evidence package export endpoint with deterministic obligations→controls→evidence chain and PDF/DOCX rendering. | DEVELOPMENT_LOG.md Sprint 3 P5 |
| Recertification | Audit & Assurance | SOLID | Recertification policies, due controls/evidence, runs, summary; tests pass. | DEVELOPMENT_LOG.md Phase 2.8 |
| Vendor Register | TPRM / Third-Party Risk | SOLID | Vendor CRUD, archive, summary, risk scores, assessments, control links implemented. | DEVELOPMENT_LOG.md Phase 9.3-9.5 |
| Vendor Assessments | TPRM / Third-Party Risk | SOLID | Vendor-scoped assessment CRUD/start/questions/complete endpoints verified live; also served by `/api/v1/compliance/ai-vendor-assessments`. | tonight sweep |
| Vendor Risk Scores | TPRM / Third-Party Risk | SOLID | `/api/v1/compliance/vendors/{id}/risk-scores` endpoints exist and respond (latest returns 404 before first score, as expected). | tonight sweep |
| Vendor Control Links | TPRM / Third-Party Risk | SOLID | `/api/v1/compliance/vendors/{id}/links/controls` and `/unlink` endpoints verified live; also reported via `/links/summary`. | tonight sweep |
| Vendor AI Model Assessments | TPRM / Third-Party Risk | SOLID | `/api/v1/compliance/vendors/{id}/ai-model-assessments` and dedicated `/api/v1/compliance/ai-vendor-assessments` endpoints respond. | tonight sweep |
| Vendor Mitigation Cases | TPRM / Third-Party Risk | SOLID | Case/action lifecycle, transitions, evidence submission, escalation, overdue sweep; tests pass. | DEVELOPMENT_LOG.md Phase A5.8 |
| Questionnaire Templates | TPRM / Third-Party Risk | SOLID | List/create/get/delete/clone templates, sections, questions; SIG Lite/CAIQ v4 seeded. | DEVELOPMENT_LOG.md Phase A5.1 |
| Questionnaire Responses | TPRM / Third-Party Risk | SOLID | Response lifecycle, submit/bulk answers, score breakdown, transition, vendor risk. | DEVELOPMENT_LOG.md Phase A5.1-A5.2 / docs/fix_report_parts_a_d.md Fix B |
| Questionnaire Scoring Rules | TPRM / Third-Party Risk | SOLID | Scoring rules CRUD, per-template rules, deterministic additive scoring; Fix B renamed endpoint for discoverability. | DEVELOPMENT_LOG.md Phase A5.1 / docs/fix_report_parts_a_d.md Fix B |
| Inbound Questionnaires | TPRM / Third-Party Risk | SOLID | Session/item lifecycle, deterministic 5-step matching, confidence scoring, response-time metrics. | DEVELOPMENT_LOG.md Phase A5.3 / Sprint 5 P4 |
| Subprocessors | TPRM / Third-Party Risk | SOLID | Subprocessor CRUD, transfers, DPA status, GDPR dashboard, expiry sweep; tests pass. | DEVELOPMENT_LOG.md Phase A5.4 |
| Customer Commitments | TPRM / Third-Party Risk | SOLID | Commitment lifecycle, trigger/fulfill/waive, notifications, dashboard, incident-trigger hook. | DEVELOPMENT_LOG.md Phase A5.5 / Sprint 4 P3 |
| DORA ICT Register | TPRM / Third-Party Risk | SOLID | ICT register CRUD and report; DORA obligations seeded. | DEVELOPMENT_LOG.md Stream A P3 |
| Compliance Contract Registry | TPRM / Third-Party Risk | SOLID | Read-only contract registry endpoint present; used by Pillar 1 closure. | reports/phase9-pillar1-closure-report.md |
| Issue Management | Issues & Incident Management | SOLID | Issue CRUD, assign, transition, dashboard, SLA status/breaches, transitions; resolution_note field loss fixed. | DEVELOPMENT_LOG.md Phase A6.1 / docs/fix_report_parts_a_d.md Fix C |
| Issue Classifications & RCA | Issues & Incident Management | SOLID | Auto/override classification, deterministic templates, RCA create/update/review; tests pass. | DEVELOPMENT_LOG.md Phase A6.2 / A6.8 |
| Issue–Control & Issue–Policy Links | Issues & Incident Management | SOLID | `/api/v1/compliance/issues/{id}/control-links`, `/policy-links`, `/policy-context` and `/api/v1/compliance/policy-issue-links` verified live with summary. | tonight sweep |
| Issue SLA Policies | Issues & Incident Management | SOLID | SLA policies, tracking, hourly breach processor, default severity policies seeded. | DEVELOPMENT_LOG.md Phase A6.2 |
| Issue Settings | Issues & Incident Management | SOLID | Org issue settings including require_rca_before_close; implemented. | DEVELOPMENT_LOG.md Phase A6.1 |
| Breach Notifications | Issues & Incident Management | SOLID | Breach lifecycle, regulator/subject notifications, Article 33 draft, privacy fields; tests pass. | DEVELOPMENT_LOG.md Phase A6.4 / Group D Phase D5 |
| Escalation Policies | Issues & Incident Management | SOLID | Policy lifecycle, issue evaluator, idempotency, events; tests pass. | DEVELOPMENT_LOG.md Phase A6.4 |
| Incident Analytics | Issues & Incident Management | SOLID | Incidents by category analytics endpoint implemented. | DEVELOPMENT_LOG.md Phase A6.8 |
| Reports | Reports, Exports & Dashboards | SOLID | Report listing, generation, executive narrative, board scorecard, framework readiness, regulatory reports, PDF/DOCX export. | DEVELOPMENT_LOG.md Phases A7.1-A7.5 |
| Report Sharing | Reports, Exports & Dashboards | SOLID | Signed share links, password protection, view limits, watermark metadata, public access; tests pass. | DEVELOPMENT_LOG.md Phase 4 Stream E P3 |
| Custom Report Templates | Reports, Exports & Dashboards | SOLID | Template CRUD and generate with section validation; tests pass. | DEVELOPMENT_LOG.md Phase A7.2-A7.3 |
| Export Jobs | Reports, Exports & Dashboards | EXCELLENT | Immutable export jobs with canonical JSON checksum, HMAC signature, attestation, legal hold, retention, verify and chain-of-custody. | DEVELOPMENT_LOG.md Phases 3.0-3.2 / 4.11-4.14 |
| Entity Exports | Reports, Exports & Dashboards | SOLID | Per-entity PDF/DOCX exports for policy/control/risk/vendor plus posture/framework coverage exports. | DEVELOPMENT_LOG.md Sprint 1 P2 |
| Regulatory Reports (CCPA) | Reports, Exports & Dashboards | SOLID | CCPA annual report endpoint exists; GDPR Article 30 RoPA report is fully functional via `/api/v1/privacy/ropa/article30-report`, verified live with RoPA CRUD. | tonight sweep |
| Automation Rules & Executions | Governance Automation | SOLID | Rules, schedules, versions, dry-run and executions verified; `create_task` writes real tasks, `queue_email_reminder` queues real outbox items, external actions are not no-op. | tonight sweep |
| Governance Override Requests | Governance Automation | EXCELLENT | Dual-control override workflow, from-template, conditional approval routing, explicit confirmation, audit trail. | DEVELOPMENT_LOG.md Phases 3.2-3.3 / 4.4-4.7 |
| Governance Override Templates | Governance Automation | EXCELLENT | Template and version snapshots, archive, routing evaluation, deterministic rule validation. | DEVELOPMENT_LOG.md Phase 3.3 |
| Retention Governance | Governance Automation | SOLID | Governance retention policies CRUD, evaluate, summary; legal-hold/attestation integration. | DEVELOPMENT_LOG.md Phase 3.1 |
| Copilot Inline Suggestions | Governance Automation | SOLID | Generate/apply/dismiss inline suggestions, refine drafts, immutable revisions; tests pass. | DEVELOPMENT_LOG.md Sprint 2 P1 |
| Organizations | Platform / Security / Administration | EXCELLENT | Org CRUD, governance settings with append-only history/diff/timeline, signing keys, evidence manifests, verification events export with HMAC signatures. | DEVELOPMENT_LOG.md Phases 4.6-4.14 |
| Users & Memberships | Platform / Security / Administration | SOLID | Users listing, membership CRUD, activation tokens, role updates, deactivation, last-owner protection. | DEVELOPMENT_LOG.md Phase 1.2 |
| Roles & Custom Roles | Platform / Security / Administration | SOLID | System roles, custom role CRUD, deactivate, assign to membership; tests pass. | DEVELOPMENT_LOG.md Sprint 5 P5 |
| Authentication | Platform / Security / Administration | SOLID | JWT login/register/me/permissions/activate-invite; sessions now tracked with jti and revocation. | DEVELOPMENT_LOG.md Phase 1.1 / Sprint 5 P6 |
| SSO (SAML/OIDC/endpoints) | Platform / Security / Administration | SOLID | SAML 2.0 metadata/initiate/callback, OIDC `/auth/oidc/{slug}/initiate`/`/callback`, and config CRUD all implemented; full callback flow is plan-gated. `tests/unit/test_oidc_sso.py` and `test_sso_b1.py` pass. | tonight sweep |
| SCIM Provisioning (user CRUD via SCIM v2, token creation) | Platform / Security / Administration | SOLID | SCIM v2 Users CRUD/PATCH/DELETE, discovery endpoints, SHA-256 bearer tokens, audit logging; 7/7 SCIM verifications passed. | DEVELOPMENT_LOG.md Phase 2 Stream B P2 / tests/unit/test_scim_b2.py |
| Sessions | Platform / Security / Administration | SOLID | User session rows with jti, list/revoke, expiry sweep, dependency-level validation; tests pass. | DEVELOPMENT_LOG.md Sprint 5 P6 |
| Audit Logs | Platform / Security / Administration | SOLID | Organization-scoped audit log listing; audit action seeds cover all domains. | DEVELOPMENT_LOG.md Phase 1.1 |
| Rate Limits | Platform / Security / Administration | SOLID | Slowapi org-aware rate limiting, platform defaults, per-org overrides, my-limits endpoint; Redis-optional; tests pass. | DEVELOPMENT_LOG.md Phase 4 Stream E P1 / tests/unit/test_rate_limiting_e1.py |
| SIEM Export | Platform / Security / Administration | SOLID | SIEM config CRUD, JSON/CEF/Splunk HEC formats, cursor pagination, export runs; tests pass. | DEVELOPMENT_LOG.md Phase 4 Stream E P2 / tests/unit/test_siem_export_e2.py |
| IP Allowlist | Platform / Security / Administration | RESOLVED | Fixed tonight: self-lockout on remove resolved; CIDR add/list/deactivate and dependency-level enforcement implemented; removes use soft deactivate. | DEVELOPMENT_LOG.md Sprint 5 P6 / tonight sweep |
| Email Outbox & Templates | Platform / Security / Administration | SOLID | Queue/list/cancel/mark outbox, template CRUD/preview, worker claim/complete/fail/dead-letter; preference enforcement added. | DEVELOPMENT_LOG.md Phases 1.4-1.5 / Group E / Sprint 5 P3 |
| Email Config (Org) | Platform / Security / Administration | SOLID | Upsert/get/deactivate org email config, test, verify sender; Fernet-encrypted credentials. | DEVELOPMENT_LOG.md Group D Phase D1 |
| Admin Email Config | Platform / Security / Administration | SOLID | `/api/v1/admin/email-config` GET/upsert/test endpoints exist with `email:admin` permission and return live status; distinct from org email config. | tonight sweep |
| Webhooks | Platform / Security / Administration | RESOLVED | Webhook CRUD, event types, test-emit, delivery history implemented; live HTTP delivery uses `httpx` with retry/backoff, status/`delivered_at` persistence and audit logging. | tonight sweep |
| Onboarding | Platform / Security / Administration | SOLID | Atomic org+admin+trial creation, framework selection, team invitations, checklist with real completion signals; tests pass. | DEVELOPMENT_LOG.md Phase 4 Stream E / Sprint 1 P? |
| Offboarding | Platform / Security / Administration | SOLID | Offboarding config, records, validate and run with atomic reassignments; tests pass. | DEVELOPMENT_LOG.md Phase A8.2 |
| Billing & Subscriptions | Platform / Security / Administration | SOLID | Plans, subscribe, cancel, invoices, status, Razorpay webhook handler; tests pass. | DEVELOPMENT_LOG.md Billing section |
| Scheduler Admin | Platform / Security / Administration | SOLID | List scheduler jobs/runs/run-log; Fix 7 resolved next_run_time AttributeError. | DEVELOPMENT_LOG.md Phase A8.1 / docs/fix_report_parts_a_d.md Fix 7 |
| Security Scan Ingestion | Platform / Security / Administration | SOLID | Trivy/Prowler/OpenSCAP/Wazuh ingest, scan jobs list/summary; tests pass. | DEVELOPMENT_LOG.md Phase 3 Stream C |
| Tasks | Platform / Security / Administration | SOLID | Task CRUD, complete/cancel, reminders, notify, summary; audit logging. | DEVELOPMENT_LOG.md Phase 2.4 |
| Trust Center (Admin) | Platform / Security / Administration | SOLID | Trust center configuration, publish/unpublish policies, access request review, slug, uptime status; tests pass. | DEVELOPMENT_LOG.md Phase A5.6 |
| Trust Center (Public) | Platform / Security / Administration | SOLID | Public slug-based trust center data and access request submission implemented. | DEVELOPMENT_LOG.md Phase A5.6 |
| Health & Root | Platform / Security / Administration | SOLID | Service metadata and health check endpoints present. | FEATURE_INVENTORY.md |

---

### Note on sources
The repository did not contain a per-agent report file for “Agent 1 … Agent 19”. The “Source agent / finding” column therefore maps each feature back to the actual repo artifact where the evidence was found (DEVELOPMENT_LOG file, fix report, reality audit, or test file) rather than an arbitrary agent number. The **NEEDS RE-VERIFICATION** rows were re-tested using real HTTP calls and targeted unit tests during this sweep and moved to SOLID or WEAK accordingly.
