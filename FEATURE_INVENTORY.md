# CompliVibe Backend — Definitive Feature Inventory

> **Ground truth**, extracted directly from the running application. Routes were enumerated
> from the live FastAPI OpenAPI spec (`GET /openapi.json`, 1564 paths / 1892 operations) and tables
> from `information_schema.tables` against a live Postgres 16 + pgvector instance migrated to head
> (`alembic upgrade head`, commit `32bafe8`). Regenerated fresh during the targeted walkthrough +
> deployment-readiness audit covering DPDP Phase 2, Phase 3 cloud connectors, and the pgvector/
> Meilisearch/Evidently open-source integrations — supersedes the prior 186-feature version
> (commit `a9644fb`). Net change: +4 features, 0 removed (privacy-nominations, privacy-sdf-designation,
> cloud-evidence-connectors, cloud-evidence-connectors-ingest — exactly the new surfaces built since).

## 1. Totals

- **Distinct features (curated capabilities, 1 per OpenAPI tag group):** 190
- **Registered API endpoints:** 1892
- **Database tables:** 399

Endpoint methods: DELETE=72, GET=880, PATCH=124, POST=805, PUT=11.

### Per-domain summary

| # | Domain | Features | Endpoints |
|---|---|---:|---:|
| 1 | AI Governance | 36 | 556 |
| 2 | Privacy & Data Protection | 13 | 72 |
| 3 | Data Observability | 10 | 63 |
| 4 | Risk Management | 7 | 43 |
| 5 | Policy Management | 10 | 65 |
| 6 | Compliance Frameworks & Obligations | 8 | 107 |
| 7 | Controls & Control Testing | 10 | 78 |
| 8 | Audit & Assurance | 14 | 86 |
| 9 | TPRM / Third-Party Risk | 12 | 101 |
| 10 | Issues & Incident Management | 10 | 57 |
| 11 | Reports, Exports & Dashboards | 10 | 58 |
| 12 | Governance Automation | 7 | 46 |
| 13 | Platform / Security / Administration | 39 | 225 |
| 14 | Competitive Differentiation (Phase II-VIII) | 4 | 11 |
| | **Total** | **190** | **1892** |

---

## AI Governance

**36 features · 556 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | AI Governance | `ai_governance` | 342 |
| 2 | AI Governance Systems | `ai-governance-systems` | 43 |
| 3 | AI Systems | `ai_systems` | 20 |
| 4 | AI Drafting | `ai-drafting` | 15 |
| 5 | AI Governance MLOps | `ai-governance-mlops` | 13 |
| 6 | Governance Overrides | `governance-overrides` | 10 |
| 7 | AI Governance Reviews | `ai-governance-reviews` | 8 |
| 8 | AI Governance EU AI Act Workflows | `ai-governance-eu-act-workflows` | 7 |
| 9 | AI Governance Shadow Ai | `ai-governance-shadow-ai` | 6 |
| 10 | AI Governance Diagnostics | `ai-governance-diagnostics` | 6 |
| 11 | AI Governance Risk Assessments | `ai-governance-risk-assessments` | 6 |
| 12 | OSCAL | `oscal` | 6 |
| 13 | AI Governance Atlas | `ai-governance-atlas` | 5 |
| 14 | AI Governance LLM Observability | `ai-governance-llm-observability` | 5 |
| 15 | Copilot Draft | `copilot-draft` | 5 |
| 16 | Governance | `governance` | 5 |
| 17 | Governance Override Templates | `governance-override-templates` | 5 |
| 18 | AI Governance ISO 42001 | `ai-governance-iso42001` | 4 |
| 19 | AI Governance Approval Envelopes | `ai-governance-approval-envelopes` | 4 |
| 20 | Non Human Identities | `non-human-identities` | 4 |
| 21 | AI Vendor Assessments | `ai-vendor-assessments` | 4 |
| 22 | Synthetic Datasets | `synthetic-datasets` | 4 |
| 23 | AI Usage Compliance | `ai-usage-compliance` | 4 |
| 24 | AI Governance Third Party Ai | `ai-governance-third-party-ai` | 3 |
| 25 | AI Governance Guardrails | `ai-governance-guardrails` | 3 |
| 26 | Content Provenance | `content-provenance` | 3 |
| 27 | Training Datasets | `training-datasets` | 3 |
| 28 | Training Analytics | `training-analytics` | 3 |
| 29 | AI Governance Recommendations | `ai-governance-recommendations` | 2 |
| 30 | Risk Quantification | `risk-quantification` | 2 |
| 31 | AI Governance NIST RMF | `ai-governance-nist-rmf` | 1 |
| 32 | AI Governance Monitoring | `ai-governance-monitoring` | 1 |
| 33 | AI Monitoring | `ai-monitoring` | 1 |
| 34 | AI Governance Risk Signals | `ai-governance-risk-signals` | 1 |
| 35 | AI Governance Contracts | `ai-governance-contracts` | 1 |
| 36 | AI Governance Dashboard | `ai-governance-dashboard` | 1 |

## Privacy & Data Protection

**13 features · 72 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Privacy DSR | `privacy-dsr` | 12 |
| 2 | Breach Notifications | `breach-notifications` | 9 |
| 3 | Privacy Notices | `privacy-notices` | 7 |
| 4 | Privacy Consent | `privacy-consent` | 7 |
| 5 | Privacy DPIAs | `privacy-dpias` | 7 |
| 6 | Privacy ROPA | `privacy-ropa` | 6 |
| 7 | Privacy Cookies | `privacy-cookies` | 5 |
| 8 | Privacy Lawful Basis | `privacy-lawful-basis` | 5 |
| 9 | Privacy DPAs | `privacy-dpas` | 5 |
| 10 | Privacy Nominations (NEW) | `privacy-nominations` | 4 |
| 11 | Privacy SDF Designation (NEW) | `privacy-sdf-designation` | 2 |
| 12 | Privacy Fides Import | `privacy-fides-import` | 2 |
| 13 | Privacy CCPA | `privacy-ccpa` | 1 |

## Data Observability

**10 features · 63 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Data Observability Assets | `data-observability-assets` | 11 |
| 2 | Data Observability Retention | `data-observability-retention` | 10 |
| 3 | Data Observability Residency | `data-observability-residency` | 10 |
| 4 | Data Observability Lineage | `data-observability-lineage` | 8 |
| 5 | Data Observability Incidents | `data-observability-incidents` | 8 |
| 6 | Data Observability Access | `data-observability-access` | 6 |
| 7 | Data Observability Quality | `data-observability-quality` | 5 |
| 8 | Data Observability Obligation Suggestions | `data-observability-obligation-suggestions` | 3 |
| 9 | Data Observability Dashboard | `data-observability-dashboard` | 1 |
| 10 | Data Observability Obligation Coverage | `data-observability-obligation-coverage` | 1 |

## Risk Management

**7 features · 43 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Risks | `risks` | 16 |
| 2 | Compliance Risk Recommendations | `compliance-risk-recommendations` | 6 |
| 3 | Risk Appetite | `risk-appetite` | 5 |
| 4 | Risk Indicators | `risk-indicators` | 5 |
| 5 | Geopolitical Risk | `geopolitical-risk` | 5 |
| 6 | Risk Scores | `risk-scores` | 3 |
| 7 | Risk Dependencies | `risk-dependencies` | 3 |

## Policy Management

**10 features · 65 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Compliance Policies | `compliance_policies` | 16 |
| 2 | Policy Template Library | `policy-template-library` | 9 |
| 3 | Policy Issue Links | `policy-issue-links` | 7 |
| 4 | Policy Risk Mappings | `policy-risk-mappings` | 7 |
| 5 | Policy Drafting | `policy-drafting` | 6 |
| 6 | Policy Attestations | `policy_attestations` | 6 |
| 7 | Policy Exceptions V2 | `policy_exceptions_v2` | 4 |
| 8 | Policy Issue Links V2 | `policy-issue-links-v2` | 4 |
| 9 | Policy Exceptions | `policy-exceptions` | 3 |
| 10 | Policy Risk Links | `policy-risk-links` | 3 |

## Compliance Frameworks & Obligations

**8 features · 107 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Framework Review Capacity | `framework-review-capacity` | 27 |
| 2 | Frameworks | `frameworks` | 26 |
| 3 | Framework Pack Reviews | `framework-pack-reviews` | 23 |
| 4 | Obligations | `obligations` | 13 |
| 5 | Compliance Deadlines | `compliance-deadlines` | 8 |
| 6 | Framework Content | `framework-content` | 5 |
| 7 | DORA | `dora` | 3 |
| 8 | Regulatory Alerts | `regulatory-alerts` | 2 |

## Controls & Control Testing

**10 features · 78 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Controls | `controls` | 10 |
| 2 | Technical Controls | `technical-controls` | 10 |
| 3 | Control Monitoring | `control-monitoring` | 9 |
| 4 | Control Monitoring Rules | `control-monitoring-rules` | 9 |
| 5 | Control Monitoring Alerts | `control-monitoring-alerts` | 8 |
| 6 | Control Recommendations | `control_recommendations` | 7 |
| 7 | Control Exceptions | `control-exceptions` | 7 |
| 8 | SoD Conflicts | `sod-conflicts` | 6 |
| 9 | Control Tests | `control-tests` | 6 |
| 10 | Common Controls | `common-controls` | 6 |

## Audit & Assurance

**14 features · 86 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Recertification | `recertification` | 10 |
| 2 | Evidence Packages | `evidence-packages` | 10 |
| 3 | Audit Findings | `audit-findings` | 8 |
| 4 | Evidence | `evidence` | 8 |
| 5 | Pbc Items | `pbc-items` | 8 |
| 6 | Audit Findings V2 | `audit_findings_v2` | 7 |
| 7 | Auditor Portal | `auditor-portal` | 7 |
| 8 | Pbc Requests V2 | `pbc_requests_v2` | 6 |
| 9 | Audit Schedules | `audit-schedules` | 6 |
| 10 | Evidence Automation | `evidence-automation` | 5 |
| 11 | Audit Engagements | `audit-engagements` | 5 |
| 12 | Access Certifications | `access-certifications` | 4 |
| 13 | Audit Evidence Packages | `audit_evidence_packages` | 1 |
| 14 | Audit Logs | `audit_logs` | 1 |

## TPRM / Third-Party Risk

**12 features · 101 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Vendors | `vendors` | 22 |
| 2 | Tprm Intelligence | `tprm-intelligence` | 18 |
| 3 | Inbound Questionnaires | `inbound-questionnaires` | 12 |
| 4 | Vendor Mitigation | `vendor-mitigation` | 9 |
| 5 | OT/ICS | `ot-ics` | 8 |
| 6 | Questionnaire Responses | `questionnaire-responses` | 7 |
| 7 | Subprocessors | `subprocessors` | 6 |
| 8 | Vendor Remediation Portal | `vendor-remediation-portal` | 6 |
| 9 | Questionnaire Templates | `questionnaire-templates` | 5 |
| 10 | Vendor Supply Chain | `vendor-supply-chain` | 3 |
| 11 | Questionnaire Scoring Rules | `questionnaire-scoring-rules` | 3 |
| 12 | Vendor Concentration Risk | `vendor-concentration-risk` | 2 |

## Issues & Incident Management

**10 features · 57 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Issues | `issues` | 20 |
| 2 | Issue Sync | `issue-sync` | 8 |
| 3 | Whistleblower | `whistleblower` | 7 |
| 4 | Escalation Policies | `escalation-policies` | 5 |
| 5 | Crisis Management | `crisis-management` | 5 |
| 6 | BCM | `bcm` | 4 |
| 7 | Resilience Testing | `resilience-testing` | 4 |
| 8 | Issue Sla Policies | `issue-sla-policies` | 2 |
| 9 | Issue Settings | `issue-settings` | 1 |
| 10 | Incident Analytics | `incident-analytics` | 1 |

## Reports, Exports & Dashboards

**10 features · 58 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Reports | `reports` | 16 |
| 2 | Exports | `exports` | 13 |
| 3 | Entity Exports | `entity-exports` | 7 |
| 4 | Scoring | `scoring` | 7 |
| 5 | Compliance Dashboard | `compliance_dashboard` | 5 |
| 6 | Board Scorecard | `board-scorecard` | 4 |
| 7 | Custom Reports | `custom-reports` | 3 |
| 8 | Compliance Reports | `compliance-reports` | 1 |
| 9 | Dashboard | `dashboard` | 1 |
| 10 | Compliance Contracts | `compliance_contracts` | 1 |

## Governance Automation

**7 features · 46 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Automation | `automation` | 14 |
| 2 | Employee Attestations | `employee-attestations` | 9 |
| 3 | Tasks | `tasks` | 7 |
| 4 | Compliance Bot | `compliance-bot` | 6 |
| 5 | Digest Preferences | `digest-preferences` | 5 |
| 6 | Attestation Tokens | `attestation-tokens` | 3 |
| 7 | Attestations | `attestations` | 2 |

## Platform / Security / Administration

**39 features · 225 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Organizations | `organizations` | 24 |
| 2 | Auth SSO | `auth-sso` | 15 |
| 3 | Email | `email` | 13 |
| 4 | Onboarding | `onboarding` | 12 |
| 5 | Legal Matters | `legal-matters` | 10 |
| 6 | Cloud Evidence Connectors (NEW) | `cloud-evidence-connectors` | 9 |
| 7 | Billing | `billing` | 8 |
| 8 | Trust Center Admin | `trust-center-admin` | 8 |
| 9 | Security Integrations | `security-integrations` | 7 |
| 10 | Memberships | `memberships` | 7 |
| 11 | Customer Commitments | `customer-commitments` | 7 |
| 12 | Webhooks | `webhooks` | 7 |
| 13 | Auth SCIM | `auth-scim` | 6 |
| 14 | Import Jobs | `import-jobs` | 6 |
| 15 | SIEM | `siem` | 6 |
| 16 | Business Units | `business-units` | 6 |
| 17 | Connector Marketplace | `connector-marketplace` | 6 |
| 18 | Cloud Evidence Connectors Ingest (NEW) | `cloud-evidence-connectors-ingest` | 5 |
| 19 | Auth | `auth` | 5 |
| 20 | Rate Limits | `rate-limits` | 5 |
| 21 | Report Sharing | `report-sharing` | 5 |
| 22 | Offboarding | `offboarding` | 5 |
| 23 | Experience | `experience` | 5 |
| 24 | Custom Roles | `custom-roles` | 4 |
| 25 | PAM Sessions | `pam-sessions` | 4 |
| 26 | Ip Assets | `ip-assets` | 4 |
| 27 | Notification Preferences | `notification-preferences` | 3 |
| 28 | Sessions | `sessions` | 3 |
| 29 | Ip Allowlist | `ip-allowlist` | 3 |
| 30 | Email Config | `email-config` | 3 |
| 31 | Scheduler Admin | `scheduler-admin` | 3 |
| 32 | (None) | `(none)` | 2 |
| 33 | Admin Email Config | `admin-email-config` | 2 |
| 34 | Trust Center Public | `trust-center-public` | 2 |
| 35 | Health | `health` | 1 |
| 36 | Users | `users` | 1 |
| 37 | Roles | `roles` | 1 |
| 38 | Search | `search` | 1 |
| 39 | Billing Webhook | `billing-webhook` | 1 |

## Competitive Differentiation (Phase II-VIII)

**4 features · 11 endpoints**

### Features

| # | Feature | Primary path prefix | Endpoints |
|---|---|---|---:|
| 1 | Certification Programs | `certification-programs` | 3 |
| 2 | Carbon Accounting | `carbon-accounting` | 3 |
| 3 | Pricing | `pricing` | 3 |
| 4 | Auditor Marketplace | `auditor-marketplace` | 2 |

---

## Appendix — 2026-07-11 targeted walkthrough & deployment-readiness audit

Live HTTP+DB walkthrough (real Postgres 16 + pgvector, real dev OpenBao vault, real Meilisearch,
real HMAC/OIDC/shared-secret auth per cloud provider — no source-reading shortcuts) of every
surface built since the 2026-07-08 13-agent walkthrough: DPDP Phase 2 (consent/nomination/SDF/
DSAR/RBI-reconciliation), Phase 3 cloud evidence connectors (AWS/GCP/Azure/Okta/GitHub), and the
pgvector/Meilisearch/Evidently open-source integrations.

### New bugs found this session

1. **CRITICAL — Obligation ORM model is broken on any real pgvector-enabled Postgres deployment.**
   `app/models/obligation.py:37` unconditionally maps `embedding_json`, but migration 0171 only
   creates that column when pgvector is *unavailable* at migration time — on a real pgvector
   install it creates `embedding` (vector(384)) instead, and `embedding_json` never exists. Every
   query touching `Obligation` (framework/obligation seeding, SDF confirm, applicability engine,
   coverage reports) 500s with `UndefinedColumn`. This is the single most severe finding this
   session — it breaks the whole Compliance Frameworks & Obligations pillar precisely in the
   deployment mode (pgvector installed) the pgvector integration was built for.
2. **HIGH — Cloud connector finding→control mapping and continuous-monitoring alerts are both
   unreachable for every org.** `CloudFindingControlMappingRule` (the table that drives
   `finding_mapping_service.suggest_for_finding`) has no creation path anywhere in the API/UI/seed
   layer — grepped the full codebase, only the model + read-only query exist. Since
   `record_finding_test_run` (the ControlTestRun/continuous-monitoring wiring) only fires when a
   suggestion was auto-applied, both downstream halves of the Phase 3 cloud-connector build are
   dead on arrival; only the ingest→evidence_item half actually works today.
3. **MEDIUM — `GET /privacy/nominations/active` can never find an activated nomination.** The
   query hardcodes `status == "active"`, but activation flips status to `"activated"` — the
   lookup only works before the nomination is actually needed. DSAR nomination-aware submission
   itself is unaffected (it queries status="activated" directly), so this is isolated to the
   read/lookup endpoint.
4. **LOW — `MEILISEARCH_API_KEY=""` (empty string) is not treated as "no key configured".** Causes
   the meilisearch client to send an empty Bearer token, which a keyless Meilisearch instance
   rejects as `invalid_api_key`, silently degrading all search. Real deployments always set a real
   key or omit the var, so low real-world impact — noted because it caused a false-negative during
   this walkthrough.

### Confirmed fixed since the 2026-07-08 walkthrough

- **AI drift-monitoring "above" comparator inversion (bug #2 from that walkthrough) is fixed** —
  confirmed live with 10 real readings (5 healthy ~0.10, 5 shifted ~0.78) against a real Evidently
  `DataDriftPreset` statistical test: correctly flags only the 5 real breaches, zero false alerts.
- **Sanctions screening 503s (bug #4) fixed** per commit `12c03ea` (not independently re-verified
  live this session — scope was new surfaces only, flagging for a future pass).
- **PCI DSS placeholder-obligation visibility (bug #8) addressed** per commit `de1dd52`
  ("Exclude inactive placeholder obligations from default views and totals") — not independently
  re-verified live this session.

### Confirmed still open (from 2026-07-08/07-10 memory, not part of this session's new work)

- `active_frameworks[].coverage_pct` still shows 0.0% for a framework with real confirmed-applicable
  obligations (same root cause as bug #8's "coverage_percent_estimate always 0.0%" from 07-08).
- `EvidenceService.create_imported_evidence()` still never writes its own audit-log entry, for
  every import path (manual, connector, etc.) — confirmed again via cloud-connector evidence.

### What worked well this session (confirmed live, don't re-litigate as bugs)

- Full DPDP consent lifecycle incl. minor/guardian consent (enum-validated guardian_relationship/
  verification_method), withdrawal with reason, correct privacy-preserving subject-identifier
  hashing with consistent re-hash-on-lookup.
- Nomination create→activate→nomination-aware DSAR submission end-to-end.
- SDF suggestion (real heuristic, correctly threshold-gated) → confirm → wires DPDP-SDF-1/2/3
  obligation states to "applicable", creates a real linked annual audit_schedule, and correctly
  points the algorithmic-impact-assessment obligation at the AI Governance domain.
- DSAR grievance subtype correctly applies the 90-day Rule 14(3) SLA distinct from the 30-day default.
- RBI-DPDP erasure-conflict: a real 409 with cited RBI/PMLA retention-floor reasoning blocks
  premature erasure; override path correctly preserves the conflict record and records reason/timestamp.
- All 4 testable cloud connector providers (AWS/GitHub HMAC, Azure/Okta handshake+shared-secret)
  ingest real signed/authenticated payloads into real, cleanly-labeled `evidence_items` rows, with
  correct replay/dedup (resending an identical signed payload does not create a duplicate).
  GCP correctly 401s without a valid OIDC bearer token; rotate-secret correctly 422s for GCP.
- pgvector semantic search (once the schema bug above is worked around) returns real, semantically
  sensible ranked cross-framework matches — not a stub.
- Meilisearch real-time indexing: creating a Risk makes it immediately searchable with a real
  ranking score, correctly org-scoped.
- Cloud-connector evidence and DPDP obligation-applicability data both flow into the same existing
  dashboards (posture-summary, monitoring alerts) a manually-created record would — not a separate silo.
