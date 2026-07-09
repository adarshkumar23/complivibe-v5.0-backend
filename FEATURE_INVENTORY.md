# CompliVibe Backend — Definitive Feature Inventory

> **Ground truth**, extracted directly from the running application. Routes were enumerated
> from the live FastAPI OpenAPI spec (`GET /openapi.json`, 1541 paths / 1867 operations) and tables
> from SQLAlchemy `Base.metadata.tables` after importing `app.models`. Regenerated fresh against
> current `main` (commit `a9644fb`) — supersedes the prior 158-feature version, which predated
> the Sprint 1-5 gap-catalog work and the Phase II-VIII competitive-differentiation build-out.

## 1. Totals

- **Distinct features (curated capabilities, 1 per OpenAPI tag group):** 186
- **Registered API endpoints:** 1867
- **Database tables:** 391

Endpoint methods: DELETE=72, GET=871, PATCH=124, POST=789, PUT=11.

### Per-domain summary

| # | Domain | Features | Endpoints |
|---|---|---:|---:|
| 1 | AI Governance | 36 | 643 |
| 2 | Privacy & Data Protection | 11 | 85 |
| 3 | Data Observability | 10 | 77 |
| 4 | Risk Management | 7 | 52 |
| 5 | Policy Management | 10 | 83 |
| 6 | Compliance Frameworks & Obligations | 8 | 125 |
| 7 | Controls & Control Testing | 10 | 97 |
| 8 | Audit & Assurance | 14 | 108 |
| 9 | TPRM / Third-Party Risk | 12 | 130 |
| 10 | Issues & Incident Management | 10 | 78 |
| 11 | Reports, Exports & Dashboards | 10 | 64 |
| 12 | Governance Automation | 7 | 52 |
| 13 | Platform / Security / Administration | 37 | 261 |
| 14 | Competitive Differentiation (Phase II-VIII) | 4 | 12 |
| | **Total** | **186** | **1867** |

---

## AI Governance

**36 features · 643 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | AI Governance | `ai_governance` | 378 |
| 2 | AI Governance Systems | `ai-governance-systems` | 56 |
| 3 | AI Systems | `ai_systems` | 27 |
| 4 | AI Governance MLOps | `ai-governance-mlops` | 17 |
| 5 | AI Drafting | `ai-drafting` | 15 |
| 6 | AI Governance EU AI Act Workflows | `ai-governance-eu-act-workflows` | 13 |
| 7 | Governance Overrides | `governance-overrides` | 11 |
| 8 | AI Governance Reviews | `ai-governance-reviews` | 9 |
| 9 | Non Human Identities | `non-human-identities` | 7 |
| 10 | Governance Override Templates | `governance-override-templates` | 7 |
| 11 | AI Vendor Assessments | `ai-vendor-assessments` | 7 |
| 12 | Synthetic Datasets | `synthetic-datasets` | 7 |
| 13 | AI Governance Shadow Ai | `ai-governance-shadow-ai` | 6 |
| 14 | AI Governance Diagnostics | `ai-governance-diagnostics` | 6 |
| 15 | AI Governance Risk Assessments | `ai-governance-risk-assessments` | 6 |
| 16 | Governance | `governance` | 6 |
| 17 | OSCAL | `oscal` | 6 |
| 18 | Training Datasets | `training-datasets` | 6 |
| 19 | AI Governance Atlas | `ai-governance-atlas` | 5 |
| 20 | AI Governance Third Party Ai | `ai-governance-third-party-ai` | 5 |
| 21 | AI Governance LLM Observability | `ai-governance-llm-observability` | 5 |
| 22 | Copilot Draft | `copilot-draft` | 5 |
| 23 | AI Governance ISO 42001 | `ai-governance-iso42001` | 4 |
| 24 | AI Governance Guardrails | `ai-governance-guardrails` | 4 |
| 25 | AI Governance Approval Envelopes | `ai-governance-approval-envelopes` | 4 |
| 26 | AI Usage Compliance | `ai-usage-compliance` | 4 |
| 27 | Training Analytics | `training-analytics` | 4 |
| 28 | Content Provenance | `content-provenance` | 3 |
| 29 | AI Governance Recommendations | `ai-governance-recommendations` | 2 |
| 30 | Risk Quantification | `risk-quantification` | 2 |
| 31 | AI Governance NIST RMF | `ai-governance-nist-rmf` | 1 |
| 32 | AI Governance Monitoring | `ai-governance-monitoring` | 1 |
| 33 | AI Monitoring | `ai-monitoring` | 1 |
| 34 | AI Governance Risk Signals | `ai-governance-risk-signals` | 1 |
| 35 | AI Governance Contracts | `ai-governance-contracts` | 1 |
| 36 | AI Governance Dashboard | `ai-governance-dashboard` | 1 |

## Privacy & Data Protection

**11 features · 85 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Privacy DSR | `privacy-dsr` | 14 |
| 2 | Privacy ROPA | `privacy-ropa` | 10 |
| 3 | Privacy DPIAs | `privacy-dpias` | 10 |
| 4 | Breach Notifications | `breach-notifications` | 10 |
| 5 | Privacy Consent | `privacy-consent` | 9 |
| 6 | Privacy Notices | `privacy-notices` | 8 |
| 7 | Privacy DPAs | `privacy-dpas` | 8 |
| 8 | Privacy Cookies | `privacy-cookies` | 7 |
| 9 | Privacy Lawful Basis | `privacy-lawful-basis` | 6 |
| 10 | Privacy Fides Import | `privacy-fides-import` | 2 |
| 11 | Privacy CCPA | `privacy-ccpa` | 1 |

## Data Observability

**10 features · 77 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Data Observability Assets | `data-observability-assets` | 16 |
| 2 | Data Observability Retention | `data-observability-retention` | 12 |
| 3 | Data Observability Residency | `data-observability-residency` | 12 |
| 4 | Data Observability Lineage | `data-observability-lineage` | 9 |
| 5 | Data Observability Incidents | `data-observability-incidents` | 9 |
| 6 | Data Observability Quality | `data-observability-quality` | 7 |
| 7 | Data Observability Access | `data-observability-access` | 7 |
| 8 | Data Observability Obligation Suggestions | `data-observability-obligation-suggestions` | 3 |
| 9 | Data Observability Dashboard | `data-observability-dashboard` | 1 |
| 10 | Data Observability Obligation Coverage | `data-observability-obligation-coverage` | 1 |

## Risk Management

**7 features · 52 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Risks | `risks` | 19 |
| 2 | Risk Appetite | `risk-appetite` | 7 |
| 3 | Risk Indicators | `risk-indicators` | 7 |
| 4 | Compliance Risk Recommendations | `compliance-risk-recommendations` | 6 |
| 5 | Geopolitical Risk | `geopolitical-risk` | 6 |
| 6 | Risk Dependencies | `risk-dependencies` | 4 |
| 7 | Risk Scores | `risk-scores` | 3 |

## Policy Management

**10 features · 83 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Compliance Policies | `compliance_policies` | 21 |
| 2 | Policy Template Library | `policy-template-library` | 10 |
| 3 | Policy Issue Links | `policy-issue-links` | 10 |
| 4 | Policy Risk Mappings | `policy-risk-mappings` | 10 |
| 5 | Policy Drafting | `policy-drafting` | 7 |
| 6 | Policy Attestations | `policy_attestations` | 7 |
| 7 | Policy Exceptions V2 | `policy_exceptions_v2` | 5 |
| 8 | Policy Issue Links V2 | `policy-issue-links-v2` | 5 |
| 9 | Policy Exceptions | `policy-exceptions` | 4 |
| 10 | Policy Risk Links | `policy-risk-links` | 4 |

## Compliance Frameworks & Obligations

**8 features · 125 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Frameworks | `frameworks` | 30 |
| 2 | Framework Review Capacity | `framework-review-capacity` | 28 |
| 3 | Framework Pack Reviews | `framework-pack-reviews` | 27 |
| 4 | Obligations | `obligations` | 17 |
| 5 | Compliance Deadlines | `compliance-deadlines` | 10 |
| 6 | DORA | `dora` | 6 |
| 7 | Framework Content | `framework-content` | 5 |
| 8 | Regulatory Alerts | `regulatory-alerts` | 2 |

## Controls & Control Testing

**10 features · 97 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Technical Controls | `technical-controls` | 15 |
| 2 | Controls | `controls` | 12 |
| 3 | Control Monitoring | `control-monitoring` | 11 |
| 4 | Control Monitoring Rules | `control-monitoring-rules` | 11 |
| 5 | SoD Conflicts | `sod-conflicts` | 9 |
| 6 | Control Monitoring Alerts | `control-monitoring-alerts` | 9 |
| 7 | Common Controls | `common-controls` | 8 |
| 8 | Control Exceptions | `control-exceptions` | 8 |
| 9 | Control Tests | `control-tests` | 7 |
| 10 | Control Recommendations | `control_recommendations` | 7 |

## Audit & Assurance

**14 features · 108 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Evidence Packages | `evidence-packages` | 12 |
| 2 | Recertification | `recertification` | 11 |
| 3 | Pbc Items | `pbc-items` | 11 |
| 4 | Audit Findings | `audit-findings` | 10 |
| 5 | Evidence | `evidence` | 10 |
| 6 | Audit Schedules | `audit-schedules` | 9 |
| 7 | Audit Findings V2 | `audit_findings_v2` | 8 |
| 8 | Audit Engagements | `audit-engagements` | 8 |
| 9 | Auditor Portal | `auditor-portal` | 8 |
| 10 | Access Certifications | `access-certifications` | 7 |
| 11 | Pbc Requests V2 | `pbc_requests_v2` | 6 |
| 12 | Evidence Automation | `evidence-automation` | 6 |
| 13 | Audit Evidence Packages | `audit_evidence_packages` | 1 |
| 14 | Audit Logs | `audit_logs` | 1 |

## TPRM / Third-Party Risk

**12 features · 130 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Vendors | `vendors` | 32 |
| 2 | Tprm Intelligence | `tprm-intelligence` | 17 |
| 3 | Inbound Questionnaires | `inbound-questionnaires` | 15 |
| 4 | Vendor Mitigation | `vendor-mitigation` | 12 |
| 5 | OT/ICS | `ot-ics` | 12 |
| 6 | Subprocessors | `subprocessors` | 10 |
| 7 | Questionnaire Responses | `questionnaire-responses` | 8 |
| 8 | Questionnaire Templates | `questionnaire-templates` | 7 |
| 9 | Vendor Remediation Portal | `vendor-remediation-portal` | 7 |
| 10 | Questionnaire Scoring Rules | `questionnaire-scoring-rules` | 5 |
| 11 | Vendor Supply Chain | `vendor-supply-chain` | 3 |
| 12 | Vendor Concentration Risk | `vendor-concentration-risk` | 2 |

## Issues & Incident Management

**10 features · 78 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Issues | `issues` | 28 |
| 2 | Issue Sync | `issue-sync` | 9 |
| 3 | Escalation Policies | `escalation-policies` | 8 |
| 4 | BCM | `bcm` | 7 |
| 5 | Crisis Management | `crisis-management` | 7 |
| 6 | Whistleblower | `whistleblower` | 7 |
| 7 | Resilience Testing | `resilience-testing` | 6 |
| 8 | Issue Sla Policies | `issue-sla-policies` | 3 |
| 9 | Issue Settings | `issue-settings` | 2 |
| 10 | Incident Analytics | `incident-analytics` | 1 |

## Reports, Exports & Dashboards

**10 features · 64 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Reports | `reports` | 16 |
| 2 | Exports | `exports` | 15 |
| 3 | Entity Exports | `entity-exports` | 8 |
| 4 | Scoring | `scoring` | 7 |
| 5 | Custom Reports | `custom-reports` | 6 |
| 6 | Compliance Dashboard | `compliance_dashboard` | 5 |
| 7 | Board Scorecard | `board-scorecard` | 4 |
| 8 | Compliance Reports | `compliance-reports` | 1 |
| 9 | Dashboard | `dashboard` | 1 |
| 10 | Compliance Contracts | `compliance_contracts` | 1 |

## Governance Automation

**7 features · 52 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Automation | `automation` | 16 |
| 2 | Employee Attestations | `employee-attestations` | 10 |
| 3 | Tasks | `tasks` | 9 |
| 4 | Compliance Bot | `compliance-bot` | 7 |
| 5 | Digest Preferences | `digest-preferences` | 5 |
| 6 | Attestation Tokens | `attestation-tokens` | 3 |
| 7 | Attestations | `attestations` | 2 |

## Platform / Security / Administration

**37 features · 261 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Organizations | `organizations` | 27 |
| 2 | Auth SSO | `auth-sso` | 19 |
| 3 | Legal Matters | `legal-matters` | 16 |
| 4 | Email | `email` | 15 |
| 5 | Onboarding | `onboarding` | 12 |
| 6 | Auth SCIM | `auth-scim` | 11 |
| 7 | Customer Commitments | `customer-commitments` | 10 |
| 8 | Webhooks | `webhooks` | 10 |
| 9 | SIEM | `siem` | 9 |
| 10 | Business Units | `business-units` | 9 |
| 11 | Trust Center Admin | `trust-center-admin` | 9 |
| 12 | Connector Marketplace | `connector-marketplace` | 9 |
| 13 | Billing | `billing` | 8 |
| 14 | Memberships | `memberships` | 8 |
| 15 | Ip Assets | `ip-assets` | 8 |
| 16 | Security Integrations | `security-integrations` | 7 |
| 17 | Custom Roles | `custom-roles` | 6 |
| 18 | Rate Limits | `rate-limits` | 6 |
| 19 | Import Jobs | `import-jobs` | 6 |
| 20 | Offboarding | `offboarding` | 6 |
| 21 | Auth | `auth` | 5 |
| 22 | Report Sharing | `report-sharing` | 5 |
| 23 | Email Config | `email-config` | 5 |
| 24 | PAM Sessions | `pam-sessions` | 5 |
| 25 | Experience | `experience` | 5 |
| 26 | Ip Allowlist | `ip-allowlist` | 4 |
| 27 | Notification Preferences | `notification-preferences` | 3 |
| 28 | Admin Email Config | `admin-email-config` | 3 |
| 29 | Sessions | `sessions` | 3 |
| 30 | Scheduler Admin | `scheduler-admin` | 3 |
| 31 | (None) | `(none)` | 2 |
| 32 | Trust Center Public | `trust-center-public` | 2 |
| 33 | Health | `health` | 1 |
| 34 | Users | `users` | 1 |
| 35 | Roles | `roles` | 1 |
| 36 | Search | `search` | 1 |
| 37 | Billing Webhook | `billing-webhook` | 1 |

## Competitive Differentiation (Phase II-VIII)

**4 features · 12 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Auditor Marketplace | `auditor-marketplace` | 3 |
| 2 | Certification Programs | `certification-programs` | 3 |
| 3 | Carbon Accounting | `carbon-accounting` | 3 |
| 4 | Pricing | `pricing` | 3 |

---

## Appendix A — Sprint 1-5 Gap Catalog cross-reference

These 40 gap-catalog items (from migrations 0250-0279) are implemented but were absorbed into their
natural domain above rather than broken out as a separate domain, since each is a genuine extension
of an existing feature area, not a new pillar. Verified present as live endpoints/tables in this pass:

| Gap item | Domain | Tag | Note |
|---|---|---|---|
| risk_dependencies (0273) | Risk Management | `risk-dependencies` | Genuine risk-to-risk cascade graph |
| vendor_assessment_staleness (0274) | TPRM / Third-Party Risk | `vendors` | risk_id linkage for overdue-assessment cascade |
| vendor_risk_tier_source (0275) | TPRM / Third-Party Risk | `vendors` | Provenance column for risk_tier overwrites |
| vendor_annual_spend_amount / HHI (0276) | TPRM / Third-Party Risk | `vendor-concentration-risk` | Spend-weighted concentration risk |
| carbon_accounting_api_key (0277) | Competitive Differentiation (Phase II-VIII) | `carbon-accounting` | Dedicated ingest API key |
| legal_matter_evidence_control_links (0278) | Platform / Security / Administration | `legal-matters` | M2M evidence/control links |
| bia_last_reviewed_at_nullable (0279) | Issues & Incident Management | `bcm` | BIA review-date lifecycle fix |
| control-exceptions schema (G9) | Controls & Control Testing | `control-exceptions` | Required-field validation |
| common-controls / obligation mapping unification (G9) | Controls & Control Testing | `common-controls` | Coverage counting unification |
| evidence_automation_health_idempotency (0266) | Audit & Assurance | `evidence-automation` | Rule health tracking + ingest idempotency |
| compliance_bot_command_idempotency (0267) | Governance Automation | `compliance-bot` | Idempotency key for slash-command retries |
| issue_sync_webhook_idempotency (0268) | Issues & Incident Management | `issue-sync` | Jira/Linear webhook delivery idempotency |
| attestation_token_revocation (0269) | Governance Automation | `attestation-tokens` | Revocation bookkeeping |
| rca_classification_staleness_snapshots (0261) | Issues & Incident Management | `issues` | RCA/classification staleness snapshot columns |
| escalation_events_reason_column (0262) | Issues & Incident Management | `escalation-policies` | Explainability reason |
| audit_finding_scope_snapshot (0263) | Audit & Assurance | `audit_findings_v2` | Scope-drift detection |
| ai_monitoring_config_baseline_model_version (0264) | AI Governance | `ai-monitoring` | Baseline model version tracking |
| baseline_run_single_running_guard (0265) | AI Governance | `ai-governance-diagnostics` | Single running baseline run per org |
| shared_link_password_lockout (0258) | Reports, Exports & Dashboards | `report-sharing` | Password lockout on shared links |
| governance_autopilot_auto_execution (0259) | AI Governance | `governance-overrides` | Auto-execution and reversals |
| generic_attestation_tokens (0260) | Governance Automation | `attestation-tokens` | Generic (non-campaign) attestation tokens |
| tv1_baseline_run / evidence sync (0257) | AI Governance | `ai-governance-diagnostics` | TV1 baseline run + evidence sync |
| draft_requests widen/truncated (0271-0272) | AI Governance | `ai-drafting` | Draft type constraint widen + truncation flag |
| backfill_timestamp_server_defaults (0270) | Platform / Security / Administration | `(cross-cutting)` | created_at/updated_at server defaults across all tables |

(Remaining gap-catalog items from earlier sprints — evidence-automation base, compliance-bot base,
issue-sync base, escalation-policies base, control-monitoring-alerts, sod-conflicts, access-certifications,
recertification, non-human-identities, pam-sessions, offboarding, digest-preferences, custom-reports,
board-scorecard, questionnaire-scoring-rules, ai-vendor-assessments, vendor-remediation-portal,
ot-ics, geopolitical-risk, resilience-testing, crisis-management — are represented as first-class
feature rows in their domain tables above.)

## Appendix B — Phase II-VIII Competitive-Differentiation features

Broken out as their own domain above (12 endpoints across 4 tags: `auditor-marketplace`,
`certification-programs`, `pricing` [competitor pricing + ROI calculator + usage-based pricing],
`carbon-accounting`). All confirmed live and returning 200s from the running OpenAPI schema in
this pass. Backing migrations: 0249 (competitor pricing), 0250 (ROI calculator leads), 0251
(usage-based pricing), 0252 (certification programs), 0253 (auditor marketplace).
