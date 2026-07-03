# CompliVibe Backend — Definitive Feature Inventory

> **Ground truth**, extracted directly from the running application. Routes were enumerated
> from the live FastAPI OpenAPI spec (`app.main:app.openapi()`) and tables from SQLAlchemy
> `Base.metadata.tables` after importing `app.models`. No prior summary was reused.

## 1. Totals

- **Distinct features (curated capabilities):** 158
- **Registered API endpoints:** 1609
- **Database tables:** 316

Endpoint methods: DELETE=55, GET=754, PATCH=105, POST=686, PUT=9.

### Per-domain summary

| # | Domain | Features | Endpoints | Tables |
|---|---|---:|---:|---:|
| 1 | AI Governance | 32 | 565 | 89 |
| 2 | Privacy & Data Protection | 11 | 79 | 16 |
| 3 | Data Observability | 9 | 77 | 16 |
| 4 | Risk Management | 7 | 56 | 8 |
| 5 | Policy Management | 8 | 79 | 15 |
| 6 | Compliance Frameworks & Obligations | 14 | 142 | 36 |
| 7 | Controls & Control Testing | 10 | 94 | 19 |
| 8 | Audit & Assurance | 10 | 91 | 13 |
| 9 | TPRM / Third-Party Risk | 14 | 102 | 20 |
| 10 | Issues & Incident Management | 8 | 53 | 12 |
| 11 | Reports, Exports & Dashboards | 6 | 50 | 8 |
| 12 | Governance Automation | 5 | 45 | 24 |
| 13 | Platform / Security / Administration | 24 | 176 | 40 |
| | **Total** | **158** | **1609** | **316** |

---

## AI Governance

**32 features · 565 endpoints · 89 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | AI System Risk Assessments (v2) | Create/complete AI risk assessments, submit responses, compute bias, snapshots, residual-risk preview, copilot brief; bias assessments. | 8 |
| 2 | AI Risk Assessment Engine | Full AI-risk assessment lifecycle: assessments, classifications, classification taxonomies, dimension templates, scoring profiles, snapshots, candidate actions. | 52 |
| 3 | AI System Classification (EU AI Act) | Guided/manual classification, EU AI Act classification, obligations, mandatory controls. | 8 |
| 4 | AI System AIBOM (Bill of Materials) | Create AIBOM, add components, diff versions, latest. | 4 |
| 5 | AI System Model Cards | Create/list/publish/update model cards. | 6 |
| 6 | AI System Guardrails | System-scoped guardrails: create/list/check/deactivate + freeze windows, operator acknowledgements. | 12 |
| 7 | Guardrail Policy Sets & Resolution | Org guardrail policy sets, versions, active profile, conflict resolution, policy-resolution simulation. | 52 |
| 8 | Guardrail Policy Diff-Gating Compare Preset Assignments | Deep diff-gating compare preset assignment subsystem: assignments, presets, versions, reports, profiles, diagnostics, exports, history. | 73 |
| 9 | Org Guardrails (Org-level) | Org-level guardrail CRUD and guardrail event stream. | 11 |
| 10 | AI Governance Reviews | Create/approve/reject/complete reviews, respond to criteria, per-system reviews. | 9 |
| 11 | AI System Governance Reviews (v2) | Governance reviews, attestations, scheduling, links (controls/evidence/risks), governance summary for AI systems. | 28 |
| 12 | Review Orchestration (Plans, Recurrence, Sequences, Reminders) | Review plan constraints/runs, recurrence templates, sequence packs/steps/runs, reminder policies, review queue, review events. | 34 |
| 13 | EU AI Act Workflows | Conformity assessment, FRIA, post-market monitoring plan, annex sectors. | 13 |
| 14 | ISO 42001 Conformity | ISO 42001 conformity tracker and summary. | 3 |
| 15 | NIST AI RMF | NIST RMF implementation, subcategory updates, maturity, org summary. | 5 |
| 16 | Third-Party AI Assessments | List/get/update/delete/complete third-party AI assessments. | 5 |
| 17 | AI Approval Envelopes | Approval envelopes: list/get/approve/reject, system-scoped creation. | 6 |
| 18 | AI Monitoring | Monitoring configs, readings, dashboard, inbound monitoring ingest. | 7 |
| 19 | AI Risk Signals | Org & system risk signals, review. | 3 |
| 20 | AI Recommendations | System recommendations, apply/dismiss, recommendation snapshots & action dispositions, copilot brief. | 19 |
| 21 | AI Governance Diagnostics & Events | Diagnostic snapshots, generate/export, org events & summary. | 6 |
| 22 | Shadow AI Detection | List/get/review/dismiss/register/report shadow AI detections. | 6 |
| 23 | ATLAS Threat Modeling | ATLAS tactics/techniques, system exposure assessment, mitigations. | 5 |
| 24 | MLOps & MLflow Integration | MLOps integrations, MLflow connections/models/drift, ingest, coverage, sync. | 16 |
| 25 | AI Vendor Assessments | Create/list/get/update/delete/complete AI vendor assessments + summary. | 7 |
| 26 | AI Drafting (Compliance Copilot) | AI-drafted policies, controls, risks, evidence, model cards, RCA, EU Act narratives; config enable/disable; apply drafts. | 14 |
| 27 | Governance Autopilot | Autopilot policies, approval policies, execution intents/approvals/votes, runner simulations/admissions/sessions/handshakes, noop-runner events/ledger/reports, capabilities, evaluation. | 102 |
| 28 | Governance Copilot Draft Snapshots | Copilot draft snapshots, preview, diff, draft types, executive risk summary. | 10 |
| 29 | Governance Signals | Governance signals: list/groups/prioritized/summary, dismiss/resolve, priority explanation. | 9 |
| 30 | Governance Candidate Actions & Templates | Candidate action summary/list/explain, action templates. | 4 |
| 31 | AI Governance Contracts & Dashboard | AI governance contracts (phase5-8), dashboard. | 8 |
| 32 | AI System Inventory & Lifecycle | Register, list, update, delete AI systems; governance score, summary, status, oversight, event log, use cases, EU Act annex sectors, scorecard (catch-all for system-scoped routes). | 20 |

### Endpoints (565)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/ai-governance/risk-assessments/{assessment_id}` | Get Ai Risk Assessment |
| POST | `/api/v1/ai-governance/risk-assessments/{assessment_id}/complete` | Complete Ai Risk Assessment |
| POST | `/api/v1/ai-governance/risk-assessments/{assessment_id}/compute-bias` | Compute Bias Metrics |
| POST | `/api/v1/ai-governance/risk-assessments/{assessment_id}/submit-responses` | Submit Ai Risk Assessment Responses |
| POST | `/api/v1/ai-governance/systems/{system_id}/bias-assessments` | Submit Bias Assessment |
| GET | `/api/v1/ai-governance/systems/{system_id}/bias-assessments` | List Bias Assessments |
| POST | `/api/v1/ai-governance/systems/{system_id}/risk-assessments` | Create Ai Risk Assessment |
| GET | `/api/v1/ai-governance/systems/{system_id}/risk-assessments` | List Ai Risk Assessments For System |
| GET | `/api/v1/ai-governance/ai-risk/assessment-snapshots/{snapshot_id}` | Get Ai Risk Assessment Snapshot |
| POST | `/api/v1/ai-governance/ai-risk/assessments` | Create Ai Risk Assessment |
| GET | `/api/v1/ai-governance/ai-risk/assessments` | List Ai Risk Assessments |
| GET | `/api/v1/ai-governance/ai-risk/assessments/summary` | Get Ai Risk Assessment Summary |
| GET | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}` | Get Ai Risk Assessment |
| PATCH | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}` | Update Ai Risk Assessment |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/apply-dimension-template` | Apply Ai Risk Dimension Template To Assessment |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/apply-residual-risk` | Apply Ai Risk Assessment Residual Risk |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/archive` | Archive Ai Risk Assessment |
| GET | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/candidate-actions` | Get Risk Assessment Candidate Actions |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications` | Create Ai Risk Assessment Classification |
| GET | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications` | List Ai Risk Assessment Classifications |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/complete` | Complete Ai Risk Assessment |
| GET | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/copilot-brief` | Get Risk Assessment Copilot Brief |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/preview-residual-risk` | Preview Ai Risk Assessment Residual Risk |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/recalculate-score` | Recalculate Ai Risk Assessment Score |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/refresh-classification-signals` | Refresh Assessment Classification Signals |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/snapshots` | Create Ai Risk Assessment Snapshot |
| GET | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/snapshots` | List Ai Risk Assessment Snapshots |
| POST | `/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/submit-for-review` | Submit Ai Risk Assessment For Review |
| GET | `/api/v1/ai-governance/ai-risk/classification-snapshots/{snapshot_id}` | Get Ai Risk Classification Snapshot |
| POST | `/api/v1/ai-governance/ai-risk/classification-taxonomies` | Create Ai Risk Classification Taxonomy |
| GET | `/api/v1/ai-governance/ai-risk/classification-taxonomies` | List Ai Risk Classification Taxonomies |
| GET | `/api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}` | Get Ai Risk Classification Taxonomy |
| PATCH | `/api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}` | Update Ai Risk Classification Taxonomy |
| POST | `/api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}/archive` | Archive Ai Risk Classification Taxonomy |
| POST | `/api/v1/ai-governance/ai-risk/classification-taxonomies/{taxonomy_id}/set-default` | Set Ai Risk Classification Taxonomy Default |
| GET | `/api/v1/ai-governance/ai-risk/classifications/summary` | Get Ai Risk Classification Summary |
| GET | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}` | Get Ai Risk Classification Record |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/archive` | Archive Ai Risk Classification Record |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/mark-reviewed` | Mark Ai Risk Classification Reviewed |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/reject` | Reject Ai Risk Classification |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/request-changes` | Request Ai Risk Classification Changes |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/snapshots` | Create Ai Risk Classification Snapshot |
| GET | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/snapshots` | List Ai Risk Classification Snapshots |
| POST | `/api/v1/ai-governance/ai-risk/classifications/{classification_id}/submit-for-review` | Submit Ai Risk Classification For Review |
| POST | `/api/v1/ai-governance/ai-risk/dimension-templates` | Create Ai Risk Dimension Template |
| GET | `/api/v1/ai-governance/ai-risk/dimension-templates` | List Ai Risk Dimension Templates |
| GET | `/api/v1/ai-governance/ai-risk/dimension-templates/summary` | Get Ai Risk Dimension Template Summary |
| GET | `/api/v1/ai-governance/ai-risk/dimension-templates/{template_id}` | Get Ai Risk Dimension Template |
| PATCH | `/api/v1/ai-governance/ai-risk/dimension-templates/{template_id}` | Update Ai Risk Dimension Template |
| POST | `/api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/archive` | Archive Ai Risk Dimension Template |
| POST | `/api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/preview-score` | Preview Ai Risk Dimension Template |
| POST | `/api/v1/ai-governance/ai-risk/dimension-templates/{template_id}/set-default` | Set Ai Risk Dimension Template Default |
| POST | `/api/v1/ai-governance/ai-risk/scoring-profiles` | Create Ai Risk Scoring Profile |
| GET | `/api/v1/ai-governance/ai-risk/scoring-profiles` | List Ai Risk Scoring Profiles |
| GET | `/api/v1/ai-governance/ai-risk/scoring-profiles/summary` | Get Ai Risk Scoring Profile Summary |
| GET | `/api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}` | Get Ai Risk Scoring Profile |
| PATCH | `/api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}` | Update Ai Risk Scoring Profile |
| POST | `/api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/archive` | Archive Ai Risk Scoring Profile |
| POST | `/api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/preview-score` | Preview Ai Risk Scoring Profile |
| POST | `/api/v1/ai-governance/ai-risk/scoring-profiles/{profile_id}/set-default` | Set Ai Risk Scoring Profile Default |
| GET | `/api/v1/ai-governance/systems/{system_id}/classification` | Get Classification |
| POST | `/api/v1/ai-governance/systems/{system_id}/classify/manual` | Manual Classify |
| POST | `/api/v1/ai-governance/systems/{system_id}/classify/start` | Start Guided Classification |
| POST | `/api/v1/ai-governance/systems/{system_id}/classify/submit` | Submit Guided Classification |
| POST | `/api/v1/ai-governance/systems/{system_id}/eu-act-classification` | Classify Eu Act |
| GET | `/api/v1/ai-governance/systems/{system_id}/eu-act-classification` | Get Eu Act Classification |
| GET | `/api/v1/ai-governance/systems/{system_id}/eu-act-obligations` | Get Eu Act Obligations |
| GET | `/api/v1/ai-governance/systems/{system_id}/mandatory-controls` | Get Mandatory Controls |
| POST | `/api/v1/ai-governance/systems/{system_id}/aibom` | Create Aibom |
| POST | `/api/v1/ai-governance/systems/{system_id}/aibom/components` | Add Aibom Component |
| GET | `/api/v1/ai-governance/systems/{system_id}/aibom/diff` | Diff Aibom Versions |
| GET | `/api/v1/ai-governance/systems/{system_id}/aibom/latest` | Get Latest Aibom |
| POST | `/api/v1/ai-governance/systems/{system_id}/model-card` | Create Model Card |
| GET | `/api/v1/ai-governance/systems/{system_id}/model-card` | Get Active Model Card |
| GET | `/api/v1/ai-governance/systems/{system_id}/model-cards` | List Model Cards |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/model-cards/{card_id}` | Update Model Card |
| POST | `/api/v1/ai-governance/systems/{system_id}/model-cards/{card_id}/publish` | Publish Model Card |
| POST | `/api/v1/compliance/drafts/model-card` | Draft Model Card Content |
| POST | `/api/v1/ai-governance/guardrails/check` | Guardrail Check |
| POST | `/api/v1/ai-governance/guardrails/freeze-windows` | Create Freeze Window |
| GET | `/api/v1/ai-governance/guardrails/freeze-windows` | List Freeze Windows |
| PATCH | `/api/v1/ai-governance/guardrails/freeze-windows/{freeze_window_id}` | Update Freeze Window |
| POST | `/api/v1/ai-governance/guardrails/freeze-windows/{freeze_window_id}/archive` | Archive Freeze Window |
| GET | `/api/v1/ai-governance/guardrails/operator-acknowledgements` | List Operator Acknowledgements |
| POST | `/api/v1/ai-governance/guardrails/resolve-conflicts` | Guardrail Resolve Conflicts |
| GET | `/api/v1/ai-governance/guardrails/summary` | Guardrail Summary |
| POST | `/api/v1/ai-governance/systems/{system_id}/guardrails` | Create System Guardrail |
| GET | `/api/v1/ai-governance/systems/{system_id}/guardrails` | List System Guardrails |
| POST | `/api/v1/ai-governance/systems/{system_id}/guardrails/check` | Check System Guardrails |
| POST | `/api/v1/ai-governance/systems/{system_id}/guardrails/{guardrail_id}/deactivate` | Deactivate System Guardrail |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports` | List Policy Diff Gating Compare Preset Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}` | Get Policy Diff Gating Compare Preset Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}/archive` | Archive Policy Diff Gating Compare Preset Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-summary` | Policy Diff Gating Compare Preset Summary |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets` | Create Policy Diff Gating Compare Preset |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets` | List Policy Diff Gating Compare Presets |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default` | Evaluate Policy Diff Gating Compare Preset Default |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}` | Update Policy Diff Gating Compare Preset |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/archive` | Archive Policy Diff Gating Compare Preset |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate` | Evaluate Policy Diff Gating Compare Preset |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pin-version` | Pin Policy Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pinning-status` | Get Policy Diff Gating Compare Preset Pinning Status |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/unpin-version` | Unpin Policy Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions` | Create Policy Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions` | List Policy Diff Gating Compare Preset Versions |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}` | Get Policy Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate` | Activate Policy Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive` | Archive Policy Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports` | List Policy Diff Gating Compare Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}` | Get Policy Diff Gating Compare Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}/archive` | Archive Policy Diff Gating Compare Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-summary` | Policy Diff Gating Compare Summary |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles` | Create Policy Diff Gating Profile |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles` | List Policy Diff Gating Profiles |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile_id}` | Update Policy Diff Gating Profile |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile_id}/archive` | Archive Policy Diff Gating Profile |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports` | List Policy Diff Gating Reports |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare` | Compare Policy Diff Gating Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}` | Get Policy Diff Gating Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}/archive` | Archive Policy Diff Gating Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-summary` | Policy Diff Gating Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-reason-codes` | Policy Resolution Diff Reason Code Catalog |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/simulate` | Simulate Policy Resolution |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports` | List Policy Resolution Simulation Diff Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}` | Get Policy Resolution Simulation Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/archive` | Archive Policy Resolution Simulation Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/classify` | Classify Policy Resolution Simulation Diff Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-summary` | Policy Resolution Simulation Diff Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports` | List Policy Resolution Simulation Reports |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff` | Diff Policy Resolution Simulation Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}` | Get Policy Resolution Simulation Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}/archive` | Archive Policy Resolution Simulation Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/simulation-summary` | Policy Resolution Simulation Summary |
| POST | `/api/v1/ai-governance/guardrails/policy-sets` | Create Guardrail Policy Set |
| GET | `/api/v1/ai-governance/guardrails/policy-sets` | List Guardrail Policy Sets |
| GET | `/api/v1/ai-governance/guardrails/policy-sets/summary` | Guardrail Policy Set Summary |
| PATCH | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}` | Update Guardrail Policy Set |
| GET | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/active-profile` | Get Guardrail Policy Set Active Profile |
| POST | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/archive` | Archive Guardrail Policy Set |
| POST | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions` | Create Guardrail Policy Set Version |
| GET | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions` | List Guardrail Policy Set Versions |
| POST | `/api/v1/ai-governance/guardrails/policy-sets/{policy_set_id}/versions/{version_id}/activate` | Activate Guardrail Policy Set Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments` | Create Policy Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments` | List Policy Diff Gating Compare Preset Assignments |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics` | Policy Diff Gating Compare Preset Assignment Coverage Diagnostics |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-summary` | Policy Diff Gating Compare Preset Assignment Coverage Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports` | List Preset Assignment Diagnostic Diff Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}` | Get Preset Assignment Diagnostic Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/archive` | Archive Preset Assignment Diagnostic Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/export` | Export Preset Assignment Diagnostic Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments` | Create Diagnostic Export Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments` | List Diagnostic Export Diff Gating Compare Preset Assignments |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-diagnostics` | Diagnostic Export Diff Gating Compare Preset Assignment Coverage Diagnostics |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-summary` | Diagnostic Export Diff Gating Compare Preset Assignment Coverage Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/health-diagnostics` | Diagnostic Export Diff Gating Compare Preset Assignment Health Diagnostics |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/resolve` | Resolve Diagnostic Export Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/summary` | Diagnostic Export Diff Gating Compare Preset Assignment Summary |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}` | Update Diagnostic Export Diff Gating Compare Preset Assignment |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/archive` | Archive Diagnostic Export Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/history` | List Diagnostic Export Diff Gating Compare Preset Assignment History |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports` | List Diagnostic Export Diff Gating Compare Preset Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}` | Get Diagnostic Export Diff Gating Compare Preset Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}/archive` | Archive Diagnostic Export Diff Gating Compare Preset Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-summary` | Diagnostic Export Diff Gating Compare Preset Summary |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets` | Create Diagnostic Export Diff Gating Compare Preset |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets` | List Diagnostic Export Diff Gating Compare Presets |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}` | Update Diagnostic Export Diff Gating Compare Preset |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/archive` | Archive Diagnostic Export Diff Gating Compare Preset |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pin-version` | Pin Diagnostic Export Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pinning-status` | Get Diagnostic Export Diff Gating Compare Preset Pinning Status |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/unpin-version` | Unpin Diagnostic Export Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions` | Create Diagnostic Export Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions` | List Diagnostic Export Diff Gating Compare Preset Versions |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}` | Get Diagnostic Export Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate` | Activate Diagnostic Export Diff Gating Compare Preset Version |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive` | Archive Diagnostic Export Diff Gating Compare Preset Version |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports` | List Diagnostic Export Diff Gating Compare Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}` | Get Diagnostic Export Diff Gating Compare Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/archive` | Archive Diagnostic Export Diff Gating Compare Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-default-preset` | Evaluate Diagnostic Export Diff Gating Compare Preset Default |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-preset` | Evaluate Diagnostic Export Diff Gating Compare Preset |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-summary` | Diagnostic Export Diff Gating Compare Summary |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles` | Create Diagnostic Export Diff Gating Profile |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles` | List Diagnostic Export Diff Gating Profiles |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}` | Update Diagnostic Export Diff Gating Profile |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}/archive` | Archive Diagnostic Export Diff Gating Profile |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports` | List Diagnostic Export Diff Gating Reports |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/compare` | Compare Diagnostic Export Diff Gating Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}` | Get Diagnostic Export Diff Gating Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}/archive` | Archive Diagnostic Export Diff Gating Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-summary` | Diagnostic Export Diff Gating Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reason-codes` | Preset Assignment Diagnostic Export Diff Reason Code Catalog |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports` | List Preset Assignment Diagnostic Export Diff Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}` | Get Preset Assignment Diagnostic Export Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/archive` | Archive Preset Assignment Diagnostic Export Diff Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify` | Classify Diagnostic Export Diff Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-summary` | Preset Assignment Diagnostic Export Diff Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-summary` | Preset Assignment Diagnostic Export Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports` | List Preset Assignment Diagnostic Exports |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff` | Diff Preset Assignment Diagnostic Exports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}` | Get Preset Assignment Diagnostic Export |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/revoke` | Revoke Preset Assignment Diagnostic Export |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify` | Verify Preset Assignment Diagnostic Export |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-report-summary` | Preset Assignment Diagnostic Report Summary |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports` | List Preset Assignment Diagnostic Reports |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff` | Diff Preset Assignment Diagnostic Reports |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}` | Get Preset Assignment Diagnostic Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/archive` | Archive Preset Assignment Diagnostic Report |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export` | Export Preset Assignment Diagnostic Report |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/health-diagnostics` | Policy Diff Gating Compare Preset Assignment Health Diagnostics |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve` | Resolve Policy Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/summary` | Policy Diff Gating Compare Preset Assignment Summary |
| PATCH | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}` | Update Policy Diff Gating Compare Preset Assignment |
| POST | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/archive` | Archive Policy Diff Gating Compare Preset Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/history` | List Policy Diff Gating Compare Preset Assignment History |
| GET | `/api/v1/ai-governance/guardrail-events` | List Guardrail Events Alias |
| POST | `/api/v1/ai-governance/guardrails` | Create Org Guardrail |
| GET | `/api/v1/ai-governance/guardrails` | List Org Guardrails |
| GET | `/api/v1/ai-governance/guardrails/events` | List Guardrail Events |
| POST | `/api/v1/ai-governance/guardrails/policy-assignments` | Create Guardrail Policy Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-assignments` | List Guardrail Policy Assignments |
| POST | `/api/v1/ai-governance/guardrails/policy-assignments/resolve` | Resolve Guardrail Policy Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-assignments/summary` | Guardrail Policy Assignment Summary |
| PATCH | `/api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}` | Update Guardrail Policy Assignment |
| POST | `/api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}/archive` | Archive Guardrail Policy Assignment |
| GET | `/api/v1/ai-governance/guardrails/policy-assignments/{assignment_id}/history` | List Guardrail Policy Assignment History |
| POST | `/api/v1/ai-governance/reviews` | Create Review |
| GET | `/api/v1/ai-governance/reviews` | List Reviews |
| GET | `/api/v1/ai-governance/reviews/system/{system_id}` | List Reviews For System |
| GET | `/api/v1/ai-governance/reviews/{review_id}` | Get Review |
| POST | `/api/v1/ai-governance/reviews/{review_id}/approve` | Approve Review |
| POST | `/api/v1/ai-governance/reviews/{review_id}/approve-with-conditions` | Approve With Conditions |
| POST | `/api/v1/ai-governance/reviews/{review_id}/complete-conditional` | Complete Conditional |
| POST | `/api/v1/ai-governance/reviews/{review_id}/reject` | Reject Review |
| POST | `/api/v1/ai-governance/reviews/{review_id}/respond` | Respond To Criteria |
| GET | `/api/v1/ai-governance/ai-systems/{ai_system_id}/attention` | Get Ai System Attention View |
| GET | `/api/v1/ai-governance/ai-systems/{ai_system_id}/candidate-actions` | Get Ai System Candidate Actions |
| GET | `/api/v1/ai-governance/ai-systems/{ai_system_id}/copilot-brief` | Get Ai System Copilot Brief |
| GET | `/api/v1/ai-governance/ai-systems/{ai_system_id}/mlops-coverage` | Get Mlops Coverage |
| GET | `/api/v1/ai-systems/{ai_system_id}` | Get Ai System |
| PATCH | `/api/v1/ai-systems/{ai_system_id}` | Update Ai System |
| POST | `/api/v1/ai-systems/{ai_system_id}/archive` | Archive Ai System |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews` | Create Ai System Governance Review |
| GET | `/api/v1/ai-systems/{ai_system_id}/governance-reviews` | List Ai System Governance Reviews |
| GET | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}` | Get Ai System Governance Review |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations` | Create Ai System Governance Attestation |
| GET | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations` | List Ai System Governance Attestations |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/attestations/{attestation_id}/verify` | Verify Ai System Governance Attestation |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/cancel` | Cancel Ai System Governance Review |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/complete` | Complete Ai System Governance Review |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/schedule` | Schedule Ai System Governance Review |
| POST | `/api/v1/ai-systems/{ai_system_id}/governance-reviews/{review_id}/start` | Start Ai System Governance Review |
| GET | `/api/v1/ai-systems/{ai_system_id}/governance-summary` | Ai System Governance Summary |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/controls` | Link Control To Ai System |
| GET | `/api/v1/ai-systems/{ai_system_id}/links/controls` | List Ai System Control Links |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/controls/{link_id}/unlink` | Unlink Control From Ai System |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/evidence` | Link Evidence To Ai System |
| GET | `/api/v1/ai-systems/{ai_system_id}/links/evidence` | List Ai System Evidence Links |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/evidence/{link_id}/unlink` | Unlink Evidence From Ai System |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/risks` | Link Risk To Ai System |
| GET | `/api/v1/ai-systems/{ai_system_id}/links/risks` | List Ai System Risk Links |
| POST | `/api/v1/ai-systems/{ai_system_id}/links/risks/{link_id}/unlink` | Unlink Risk From Ai System |
| GET | `/api/v1/ai-systems/{ai_system_id}/links/summary` | Ai System Links Summary |
| GET | `/api/v1/ai-governance/review-events` | List Review Events |
| POST | `/api/v1/ai-governance/review-events/{event_id}/resolve` | Resolve Review Event |
| POST | `/api/v1/ai-governance/review-plan-constraints` | Create Review Plan Constraint |
| GET | `/api/v1/ai-governance/review-plan-constraints` | List Review Plan Constraints |
| GET | `/api/v1/ai-governance/review-plan-constraints/summary` | Review Plan Constraint Summary |
| PATCH | `/api/v1/ai-governance/review-plan-constraints/{constraint_id}` | Update Review Plan Constraint |
| POST | `/api/v1/ai-governance/review-plan-constraints/{constraint_id}/archive` | Archive Review Plan Constraint |
| GET | `/api/v1/ai-governance/review-plan-runs` | List Recurrence Plan Runs |
| GET | `/api/v1/ai-governance/review-plan-runs/{run_id}` | Get Recurrence Plan Run |
| GET | `/api/v1/ai-governance/review-queue` | Due Review Queue |
| POST | `/api/v1/ai-governance/review-queue/evaluate-schedules` | Evaluate Review Schedules |
| GET | `/api/v1/ai-governance/review-recurrence-summary` | Recurrence Summary |
| POST | `/api/v1/ai-governance/review-recurrence-templates` | Create Recurrence Template |
| GET | `/api/v1/ai-governance/review-recurrence-templates` | List Recurrence Templates |
| PATCH | `/api/v1/ai-governance/review-recurrence-templates/{template_id}` | Update Recurrence Template |
| POST | `/api/v1/ai-governance/review-recurrence-templates/{template_id}/archive` | Archive Recurrence Template |
| POST | `/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan` | Generate Recurrence Plan |
| POST | `/api/v1/ai-governance/review-reminder-policies` | Create Review Reminder Policy |
| GET | `/api/v1/ai-governance/review-reminder-policies` | List Review Reminder Policies |
| PATCH | `/api/v1/ai-governance/review-reminder-policies/{policy_id}` | Update Review Reminder Policy |
| POST | `/api/v1/ai-governance/review-reminder-policies/{policy_id}/archive` | Archive Review Reminder Policy |
| GET | `/api/v1/ai-governance/review-schedule-summary` | Review Schedule Summary |
| POST | `/api/v1/ai-governance/review-sequence-packs` | Create Sequence Pack |
| GET | `/api/v1/ai-governance/review-sequence-packs` | List Sequence Packs |
| PATCH | `/api/v1/ai-governance/review-sequence-packs/{pack_id}` | Update Sequence Pack |
| POST | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/archive` | Archive Sequence Pack |
| POST | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/generate-sequence` | Generate Sequence |
| POST | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps` | Create Sequence Step |
| GET | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps` | List Sequence Steps |
| PATCH | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps/{step_id}` | Update Sequence Step |
| POST | `/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps/{step_id}/archive` | Archive Sequence Step |
| GET | `/api/v1/ai-governance/review-sequence-runs` | List Sequence Runs |
| GET | `/api/v1/ai-governance/review-sequence-runs/{run_id}` | Get Sequence Run |
| GET | `/api/v1/ai-governance/review-sequence-summary` | Review Sequence Summary |
| POST | `/api/v1/ai-governance/systems/{system_id}/conformity-assessment` | Create Conformity Assessment |
| GET | `/api/v1/ai-governance/systems/{system_id}/conformity-assessment` | Get Conformity Assessment |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/conformity-assessment` | Update Conformity Assessment |
| POST | `/api/v1/ai-governance/systems/{system_id}/conformity-assessment/complete` | Complete Conformity Assessment |
| POST | `/api/v1/ai-governance/systems/{system_id}/conformity-assessment/complete-item` | Complete Conformity Checklist Item |
| POST | `/api/v1/ai-governance/systems/{system_id}/fria` | Create Fria |
| GET | `/api/v1/ai-governance/systems/{system_id}/fria` | Get Fria |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/fria` | Update Fria |
| POST | `/api/v1/ai-governance/systems/{system_id}/fria/complete` | Complete Fria |
| POST | `/api/v1/ai-governance/systems/{system_id}/post-market-plan` | Create Post Market Plan |
| GET | `/api/v1/ai-governance/systems/{system_id}/post-market-plan` | Get Post Market Plan |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/post-market-plan` | Update Post Market Plan |
| POST | `/api/v1/ai-governance/systems/{system_id}/post-market-plan/activate` | Activate Post Market Plan |
| GET | `/api/v1/ai-governance/iso42001/conformity-tracker` | Get Conformity Tracker |
| POST | `/api/v1/ai-governance/iso42001/conformity-tracker/{clause_ref}/update` | Update Conformity Tracker |
| GET | `/api/v1/ai-governance/iso42001/summary` | Get Conformity Summary |
| GET | `/api/v1/ai-governance/nist-rmf/org-summary` | Get Org Summary |
| POST | `/api/v1/ai-governance/systems/{system_id}/nist-rmf` | Create Or Get Nist Rmf Implementation |
| GET | `/api/v1/ai-governance/systems/{system_id}/nist-rmf` | Get Nist Rmf Implementation |
| GET | `/api/v1/ai-governance/systems/{system_id}/nist-rmf/maturity` | Get Nist Rmf Maturity |
| POST | `/api/v1/ai-governance/systems/{system_id}/nist-rmf/update-subcategory` | Update Nist Rmf Subcategory |
| GET | `/api/v1/ai-governance/third-party-assessments` | List Third Party Assessments |
| GET | `/api/v1/ai-governance/third-party-assessments/{assessment_id}` | Get Third Party Assessment |
| PATCH | `/api/v1/ai-governance/third-party-assessments/{assessment_id}` | Update Third Party Assessment |
| DELETE | `/api/v1/ai-governance/third-party-assessments/{assessment_id}` | Delete Third Party Assessment |
| POST | `/api/v1/ai-governance/third-party-assessments/{assessment_id}/complete` | Complete Third Party Assessment |
| GET | `/api/v1/ai-governance/approval-envelopes` | List Envelopes |
| GET | `/api/v1/ai-governance/approval-envelopes/{envelope_id}` | Get Envelope |
| POST | `/api/v1/ai-governance/approval-envelopes/{envelope_id}/approve` | Approve Envelope |
| POST | `/api/v1/ai-governance/approval-envelopes/{envelope_id}/reject` | Reject Envelope |
| POST | `/api/v1/ai-governance/systems/{system_id}/approval-envelopes` | Create System Approval Envelope |
| GET | `/api/v1/ai-governance/systems/{system_id}/approval-envelopes` | List System Approval Envelopes |
| POST | `/api/v1/ai-governance/monitoring/readings` | Submit Monitoring Reading |
| POST | `/api/v1/ai-governance/systems/{system_id}/monitoring-configs` | Create Monitoring Config |
| GET | `/api/v1/ai-governance/systems/{system_id}/monitoring-configs` | List Monitoring Configs |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/monitoring-configs/{config_id}` | Update Monitoring Config |
| POST | `/api/v1/ai-governance/systems/{system_id}/monitoring-configs/{config_id}/deactivate` | Deactivate Monitoring Config |
| GET | `/api/v1/ai-governance/systems/{system_id}/monitoring-dashboard` | Get Monitoring Dashboard |
| POST | `/api/v1/ai-monitoring/readings` | Receive Inbound Monitoring Reading |
| GET | `/api/v1/ai-governance/risk-signals` | List Org Risk Signals |
| GET | `/api/v1/ai-governance/systems/{system_id}/risk-signals` | List System Risk Signals |
| POST | `/api/v1/ai-governance/systems/{system_id}/risk-signals/{signal_id}/review` | Review System Risk Signal |
| GET | `/api/v1/ai-governance/recommendations/action-dispositions` | List Governance Recommendation Action Dispositions |
| GET | `/api/v1/ai-governance/recommendations/action-dispositions/summary` | Get Governance Recommendation Action Disposition Summary |
| POST | `/api/v1/ai-governance/recommendations/snapshots` | Create Governance Recommendation Snapshot |
| GET | `/api/v1/ai-governance/recommendations/snapshots` | List Governance Recommendation Snapshots |
| GET | `/api/v1/ai-governance/recommendations/snapshots/latest` | Get Latest Governance Recommendation Snapshot |
| POST | `/api/v1/ai-governance/recommendations/snapshots/preview` | Preview Governance Recommendation Snapshot |
| GET | `/api/v1/ai-governance/recommendations/snapshots/summary` | Get Governance Recommendation Snapshot Summary |
| GET | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}` | Get Governance Recommendation Snapshot Detail |
| GET | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions` | List Governance Recommendation Snapshot Actions |
| POST | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/accept-for-manual-work` | Accept Governance Recommendation Action For Manual Work |
| POST | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/acknowledge` | Acknowledge Governance Recommendation Action |
| POST | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/defer` | Defer Governance Recommendation Action |
| POST | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/dismiss` | Dismiss Governance Recommendation Action |
| GET | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/copilot-summary` | Get Recommendation Snapshot Copilot Summary |
| GET | `/api/v1/ai-governance/recommendations/snapshots/{snapshot_id}/diff` | Diff Governance Recommendation Snapshots |
| POST | `/api/v1/ai-governance/recommendations/{rec_id}/apply` | Apply Recommendation |
| POST | `/api/v1/ai-governance/recommendations/{rec_id}/dismiss` | Dismiss Recommendation |
| POST | `/api/v1/ai-governance/systems/{system_id}/generate-recommendations` | Generate System Recommendations |
| GET | `/api/v1/ai-governance/systems/{system_id}/recommendations` | List System Recommendations |
| GET | `/api/v1/ai-governance/diagnostics` | List Diagnostics |
| POST | `/api/v1/ai-governance/diagnostics/generate` | Generate Diagnostic Snapshot |
| GET | `/api/v1/ai-governance/diagnostics/{snapshot_id}` | Get Diagnostic Snapshot |
| GET | `/api/v1/ai-governance/diagnostics/{snapshot_id}/export` | Export Diagnostic Snapshot |
| GET | `/api/v1/ai-governance/events` | List Org Events |
| GET | `/api/v1/ai-governance/events/summary` | Get Events Summary |
| GET | `/api/v1/ai-governance/shadow-ai/detections` | List Detections |
| GET | `/api/v1/ai-governance/shadow-ai/detections/{detection_id}` | Get Detection |
| POST | `/api/v1/ai-governance/shadow-ai/detections/{detection_id}/dismiss` | Dismiss Detection |
| POST | `/api/v1/ai-governance/shadow-ai/detections/{detection_id}/register` | Register Detection |
| POST | `/api/v1/ai-governance/shadow-ai/detections/{detection_id}/review` | Review Detection |
| POST | `/api/v1/ai-governance/shadow-ai/report` | Report Detection |
| GET | `/api/v1/ai-governance/atlas/tactics` | Get Tactics |
| GET | `/api/v1/ai-governance/atlas/techniques` | List Techniques |
| GET | `/api/v1/ai-governance/atlas/techniques/{technique_id}` | Get Technique |
| POST | `/api/v1/ai-governance/systems/{system_id}/atlas-assessment` | Assess System Exposure |
| GET | `/api/v1/ai-governance/systems/{system_id}/atlas-mitigations` | Get System Mitigations |
| GET | `/api/v1/ai-governance/mlflow/drift` | List Mlflow Drift Events |
| GET | `/api/v1/ai-governance/mlflow/models` | List Mlflow Model Registrations |
| PATCH | `/api/v1/ai-governance/mlflow/models/{registration_id}/compliance-status` | Update Mlflow Model Compliance Status |
| POST | `/api/v1/ai-governance/mlflow/models/{registration_id}/link` | Manually Link Model Registration |
| POST | `/api/v1/ai-governance/mlops-integrations` | Create Mlops Integration |
| GET | `/api/v1/ai-governance/mlops-integrations` | List Mlops Integrations |
| GET | `/api/v1/ai-governance/mlops-integrations/{integration_id}` | Get Mlops Integration |
| PATCH | `/api/v1/ai-governance/mlops-integrations/{integration_id}` | Update Mlops Integration |
| POST | `/api/v1/ai-governance/mlops-integrations/{integration_id}/deactivate` | Deactivate Mlops Integration |
| POST | `/api/v1/ai-governance/mlops-integrations/{integration_id}/sync` | Sync Mlops Integration |
| GET | `/api/v1/ai-governance/mlops-integrations/{integration_id}/sync-log` | Get Mlops Sync Log |
| POST | `/api/v1/ingest/mlflow` | Ingest Mlflow Event |
| GET | `/api/v1/organizations/mlflow-connection` | Get Mlflow Connection |
| POST | `/api/v1/organizations/mlflow-connection` | Create Mlflow Connection |
| DELETE | `/api/v1/organizations/mlflow-connection` | Deactivate Mlflow Connection |
| POST | `/api/v1/organizations/mlflow-connection/rotate-token` | Rotate Mlflow Connection Token |
| POST | `/api/v1/compliance/ai-vendor-assessments` | Create Assessment |
| GET | `/api/v1/compliance/ai-vendor-assessments` | List Assessments |
| GET | `/api/v1/compliance/ai-vendor-assessments/summary` | Ai Risk Summary |
| GET | `/api/v1/compliance/ai-vendor-assessments/{assessment_id}` | Get Assessment |
| PATCH | `/api/v1/compliance/ai-vendor-assessments/{assessment_id}` | Update Assessment |
| DELETE | `/api/v1/compliance/ai-vendor-assessments/{assessment_id}` | Delete Assessment |
| POST | `/api/v1/compliance/ai-vendor-assessments/{assessment_id}/complete` | Complete Assessment |
| GET | `/api/v1/compliance/drafts` | List Drafts |
| GET | `/api/v1/compliance/drafts/ai-config` | Get Ai Config |
| POST | `/api/v1/compliance/drafts/ai-config/disable` | Disable Ai Drafting |
| POST | `/api/v1/compliance/drafts/ai-config/enable` | Enable Ai Drafting |
| POST | `/api/v1/compliance/drafts/ai-policy` | Draft Ai Policy |
| POST | `/api/v1/compliance/drafts/ai-risk-assessment` | Draft Ai Risk Assessment Narrative |
| POST | `/api/v1/compliance/drafts/control-description` | Draft Control Description |
| POST | `/api/v1/compliance/drafts/eu-act-conformity` | Draft Eu Act Conformity Narrative |
| POST | `/api/v1/compliance/drafts/evidence-description` | Draft Evidence Description |
| POST | `/api/v1/compliance/drafts/policy-content` | Draft Policy Content |
| POST | `/api/v1/compliance/drafts/rca-summary` | Draft Rca Summary |
| POST | `/api/v1/compliance/drafts/risk-description` | Draft Risk Description |
| GET | `/api/v1/compliance/drafts/{draft_id}` | Get Draft |
| POST | `/api/v1/compliance/drafts/{draft_id}/apply` | Apply Draft |
| POST | `/api/v1/ai-governance/autopilot/approval-policies` | Create Governance Autopilot Approval Policy |
| GET | `/api/v1/ai-governance/autopilot/approval-policies` | List Governance Autopilot Approval Policies |
| GET | `/api/v1/ai-governance/autopilot/approval-policies/resolved` | Get Governance Autopilot Approval Policy Resolved |
| GET | `/api/v1/ai-governance/autopilot/approval-policies/summary` | Get Governance Autopilot Approval Policy Summary |
| GET | `/api/v1/ai-governance/autopilot/approval-policies/{policy_id}` | Get Governance Autopilot Approval Policy Detail |
| PATCH | `/api/v1/ai-governance/autopilot/approval-policies/{policy_id}` | Update Governance Autopilot Approval Policy |
| POST | `/api/v1/ai-governance/autopilot/approval-policies/{policy_id}/archive` | Archive Governance Autopilot Approval Policy |
| POST | `/api/v1/ai-governance/autopilot/approval-policies/{policy_id}/set-default` | Set Default Governance Autopilot Approval Policy |
| GET | `/api/v1/ai-governance/autopilot/capabilities` | Get Governance Autopilot Capabilities |
| POST | `/api/v1/ai-governance/autopilot/evaluate-candidate-action` | Evaluate Governance Autopilot Candidate Action |
| POST | `/api/v1/ai-governance/autopilot/evaluate-copilot-draft-snapshot` | Evaluate Governance Autopilot Copilot Draft Snapshot |
| POST | `/api/v1/ai-governance/autopilot/evaluate-recommendation-snapshot` | Evaluate Governance Autopilot Recommendation Snapshot |
| GET | `/api/v1/ai-governance/autopilot/execution-approvals` | List Governance Autopilot Execution Approvals |
| GET | `/api/v1/ai-governance/autopilot/execution-approvals/summary` | Get Governance Autopilot Execution Approvals Summary |
| GET | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}` | Get Governance Autopilot Execution Approval Detail |
| POST | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/approve` | Approve Governance Autopilot Execution Approval |
| POST | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/cancel` | Cancel Governance Autopilot Execution Approval |
| GET | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/quorum-status` | Get Governance Autopilot Execution Approval Quorum Status |
| POST | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/reject` | Reject Governance Autopilot Execution Approval |
| GET | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes` | List Governance Autopilot Execution Approval Votes |
| POST | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes/approve` | Vote Approve Governance Autopilot Execution Approval |
| POST | `/api/v1/ai-governance/autopilot/execution-approvals/{approval_id}/votes/reject` | Vote Reject Governance Autopilot Execution Approval |
| POST | `/api/v1/ai-governance/autopilot/execution-intents` | Create Governance Autopilot Execution Intent |
| GET | `/api/v1/ai-governance/autopilot/execution-intents` | List Governance Autopilot Execution Intents |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/preview-candidate-action` | Preview Governance Autopilot Execution Intent Candidate Action |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/preview-copilot-draft-snapshot` | Preview Governance Autopilot Execution Intent Copilot Draft Snapshot |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/preview-recommendation-snapshot` | Preview Governance Autopilot Execution Intent Recommendation Snapshot |
| GET | `/api/v1/ai-governance/autopilot/execution-intents/summary` | Get Governance Autopilot Execution Intents Summary |
| GET | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}` | Get Governance Autopilot Execution Intent Detail |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requests` | Request Governance Autopilot Execution Intent Approval |
| GET | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requests` | List Governance Autopilot Execution Intent Approval Requests |
| GET | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/approval-requirements` | Get Governance Autopilot Execution Intent Approval Requirements |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/archive` | Archive Governance Autopilot Execution Intent |
| GET | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/readiness` | Get Governance Autopilot Execution Intent Readiness |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/runner-handoff/preview` | Preview Governance Autopilot Runner Handoff For Execution Intent |
| POST | `/api/v1/ai-governance/autopilot/execution-intents/{intent_id}/runner-simulations` | Create Governance Autopilot Runner Simulation |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/contract` | Get Governance Autopilot Noop Runner Contract |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/events` | List Governance Autopilot Noop Runner Events |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/events/summary` | Get Governance Autopilot Noop Runner Event Summary |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/events/{event_id}` | Get Governance Autopilot Noop Runner Event Detail |
| POST | `/api/v1/ai-governance/autopilot/noop-runner/events/{event_id}/archive` | Archive Governance Autopilot Noop Runner Event |
| POST | `/api/v1/ai-governance/autopilot/noop-runner/events/{event_id}/verify` | Verify Governance Autopilot Noop Runner Event |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/ledger` | List Governance Autopilot Noop Runner Ledger |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/blockers` | Get Governance Autopilot Noop Runner Blocker Report |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export` | Get Governance Autopilot Noop Runner Bounded Export |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/checksum` | Get Governance Autopilot Noop Runner Report Checksum |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract` | Get Governance Autopilot Noop Runner Client Contract |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/client-hints` | Get Governance Autopilot Noop Runner Client Hints |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy` | Get Governance Autopilot Noop Runner Compatibility Policy |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/contract` | Get Governance Autopilot Noop Runner Reports Contract |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/control-plane-health` | Get Governance Autopilot Noop Runner Control Plane Health Report |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest` | Get Governance Autopilot Noop Runner Diagnostics Manifest |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata` | Get Governance Autopilot Noop Runner Display Metadata |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/field-docs` | Get Governance Autopilot Noop Runner Field Docs |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options` | Get Governance Autopilot Noop Runner Filter Options |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/idempotency` | Get Governance Autopilot Noop Runner Idempotency Report |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/localization-map` | Get Governance Autopilot Noop Runner Localization Map |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract` | Get Governance Autopilot Noop Runner Pagination Contract |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/readiness` | Get Governance Autopilot Noop Runner Readiness Report |
| GET | `/api/v1/ai-governance/autopilot/noop-runner/reports/timeline` | Get Governance Autopilot Noop Runner Timeline Report |
| POST | `/api/v1/ai-governance/autopilot/policies` | Create Governance Autopilot Policy |
| GET | `/api/v1/ai-governance/autopilot/policies` | List Governance Autopilot Policies |
| GET | `/api/v1/ai-governance/autopilot/policies/resolved` | Get Governance Autopilot Policy Resolved |
| GET | `/api/v1/ai-governance/autopilot/policies/{policy_id}` | Get Governance Autopilot Policy Detail |
| PATCH | `/api/v1/ai-governance/autopilot/policies/{policy_id}` | Update Governance Autopilot Policy |
| POST | `/api/v1/ai-governance/autopilot/policies/{policy_id}/archive` | Archive Governance Autopilot Policy |
| POST | `/api/v1/ai-governance/autopilot/policies/{policy_id}/set-default` | Set Default Governance Autopilot Policy |
| GET | `/api/v1/ai-governance/autopilot/runner-admissions` | List Governance Autopilot Runner Admissions |
| GET | `/api/v1/ai-governance/autopilot/runner-admissions/summary` | Get Governance Autopilot Runner Admission Summary |
| GET | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}` | Get Governance Autopilot Runner Admission Detail |
| POST | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/archive` | Archive Governance Autopilot Runner Admission |
| POST | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/revoke` | Revoke Governance Autopilot Runner Admission |
| POST | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/session-preview` | Preview Governance Autopilot Runner Session |
| POST | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/sessions` | Create Governance Autopilot Runner Session |
| POST | `/api/v1/ai-governance/autopilot/runner-admissions/{admission_id}/verify-token` | Verify Governance Autopilot Runner Admission Token |
| GET | `/api/v1/ai-governance/autopilot/runner-handshake/contract` | Get Governance Autopilot Runner Handshake Contract |
| GET | `/api/v1/ai-governance/autopilot/runner-handshakes` | List Governance Autopilot Runner Handshakes |
| GET | `/api/v1/ai-governance/autopilot/runner-handshakes/summary` | Get Governance Autopilot Runner Handshake Summary |
| GET | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}` | Get Governance Autopilot Runner Handshake Detail |
| POST | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/archive` | Archive Governance Autopilot Runner Handshake |
| POST | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/noop-runner/events` | Create Governance Autopilot Noop Runner Event |
| POST | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/noop-runner/preview` | Preview Governance Autopilot Noop Runner Event |
| POST | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/revoke` | Revoke Governance Autopilot Runner Handshake |
| POST | `/api/v1/ai-governance/autopilot/runner-handshakes/{handshake_id}/verify` | Verify Governance Autopilot Runner Handshake |
| GET | `/api/v1/ai-governance/autopilot/runner-interface/contract` | Get Governance Autopilot Runner Interface Contract |
| POST | `/api/v1/ai-governance/autopilot/runner-interface/verify-handoff` | Verify Governance Autopilot Runner Handoff |
| GET | `/api/v1/ai-governance/autopilot/runner-sessions` | List Governance Autopilot Runner Sessions |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/expire-stale` | Expire Stale Governance Autopilot Runner Sessions |
| GET | `/api/v1/ai-governance/autopilot/runner-sessions/summary` | Get Governance Autopilot Runner Session Summary |
| GET | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}` | Get Governance Autopilot Runner Session Detail |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}/archive` | Archive Governance Autopilot Runner Session |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}/handshake-preview` | Preview Governance Autopilot Runner Handshake |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}/handshakes` | Create Governance Autopilot Runner Handshake |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}/revoke` | Revoke Governance Autopilot Runner Session |
| POST | `/api/v1/ai-governance/autopilot/runner-sessions/{session_id}/verify` | Verify Governance Autopilot Runner Session |
| GET | `/api/v1/ai-governance/autopilot/runner-simulations` | List Governance Autopilot Runner Simulations |
| GET | `/api/v1/ai-governance/autopilot/runner-simulations/summary` | Get Governance Autopilot Runner Simulation Summary |
| GET | `/api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}` | Get Governance Autopilot Runner Simulation Detail |
| POST | `/api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/admission-preview` | Preview Governance Autopilot Runner Admission |
| POST | `/api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/admissions` | Create Governance Autopilot Runner Admission |
| POST | `/api/v1/ai-governance/autopilot/runner-simulations/{simulation_id}/archive` | Archive Governance Autopilot Runner Simulation |
| GET | `/api/v1/ai-governance/autopilot/summary` | Get Governance Autopilot Summary |
| POST | `/api/v1/ai-governance/copilot/draft-snapshots` | Create Governance Copilot Draft Snapshot |
| GET | `/api/v1/ai-governance/copilot/draft-snapshots` | List Governance Copilot Draft Snapshots |
| GET | `/api/v1/ai-governance/copilot/draft-snapshots/latest` | Get Latest Governance Copilot Draft Snapshot |
| POST | `/api/v1/ai-governance/copilot/draft-snapshots/preview` | Preview Governance Copilot Draft Snapshot |
| GET | `/api/v1/ai-governance/copilot/draft-snapshots/summary` | Get Governance Copilot Draft Snapshot Summary |
| GET | `/api/v1/ai-governance/copilot/draft-snapshots/{snapshot_id}` | Get Governance Copilot Draft Snapshot Detail |
| GET | `/api/v1/ai-governance/copilot/draft-snapshots/{snapshot_id}/diff` | Diff Governance Copilot Draft Snapshots |
| GET | `/api/v1/ai-governance/copilot/draft-types` | List Governance Copilot Draft Types |
| POST | `/api/v1/ai-governance/copilot/drafts/preview` | Preview Governance Copilot Draft |
| GET | `/api/v1/ai-governance/copilot/executive-risk-summary` | Get Executive Risk Copilot Summary |
| GET | `/api/v1/ai-governance/signals` | List Governance Signals |
| GET | `/api/v1/ai-governance/signals/groups` | List Governance Signal Groups |
| GET | `/api/v1/ai-governance/signals/prioritized` | List Prioritized Governance Signals |
| GET | `/api/v1/ai-governance/signals/priority-summary` | Get Governance Signals Priority Summary |
| GET | `/api/v1/ai-governance/signals/summary` | Get Governance Signals Summary |
| GET | `/api/v1/ai-governance/signals/{signal_id}` | Get Governance Signal Detail |
| POST | `/api/v1/ai-governance/signals/{signal_id}/dismiss` | Dismiss Governance Signal |
| GET | `/api/v1/ai-governance/signals/{signal_id}/priority-explanation` | Get Governance Signal Priority Explanation |
| POST | `/api/v1/ai-governance/signals/{signal_id}/resolve` | Resolve Governance Signal |
| GET | `/api/v1/ai-governance/actions/candidate-summary` | Get Governance Candidate Action Summary |
| GET | `/api/v1/ai-governance/actions/candidates` | List Governance Candidate Actions |
| GET | `/api/v1/ai-governance/actions/candidates/explain` | Explain Governance Candidate Action |
| GET | `/api/v1/ai-governance/actions/templates` | List Governance Action Templates |
| GET | `/api/v1/ai-governance/contracts` | Get Ai Governance Contracts |
| GET | `/api/v1/ai-governance/contracts/phase5` | Get Phase5 Contracts |
| GET | `/api/v1/ai-governance/contracts/phase5/compatibility-summary` | Get Phase5 Contract Compatibility Summary |
| GET | `/api/v1/ai-governance/contracts/phase5/{group_key}` | Get Phase5 Contract Group |
| GET | `/api/v1/ai-governance/contracts/phase6` | Get Phase6 Contracts |
| GET | `/api/v1/ai-governance/contracts/phase7` | Get Phase7 Contracts |
| GET | `/api/v1/ai-governance/contracts/phase8` | Get Phase8 Contracts |
| GET | `/api/v1/ai-governance/dashboard` | Get Ai Governance Dashboard |
| GET | `/api/v1/ai-governance/scorecard` | Get Ai Governance Scorecard |
| POST | `/api/v1/ai-governance/systems` | Create System |
| GET | `/api/v1/ai-governance/systems` | List Systems |
| GET | `/api/v1/ai-governance/systems/eu-act/annex-sectors` | List Eu Act Annex Sectors |
| GET | `/api/v1/ai-governance/systems/summary` | Get Summary |
| GET | `/api/v1/ai-governance/systems/{system_id}` | Get System |
| PATCH | `/api/v1/ai-governance/systems/{system_id}` | Update System |
| DELETE | `/api/v1/ai-governance/systems/{system_id}` | Delete System |
| GET | `/api/v1/ai-governance/systems/{system_id}/event-log` | Get System Event Log |
| GET | `/api/v1/ai-governance/systems/{system_id}/governance-score` | Get Governance Score |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/oversight` | Update Oversight |
| POST | `/api/v1/ai-governance/systems/{system_id}/status` | Update System Status |
| POST | `/api/v1/ai-governance/systems/{system_id}/use-cases` | Create Use Case |
| GET | `/api/v1/ai-governance/systems/{system_id}/use-cases` | List Use Cases |
| GET | `/api/v1/ai-governance/systems/{system_id}/use-cases/{use_case_id}` | Get Use Case |
| PATCH | `/api/v1/ai-governance/systems/{system_id}/use-cases/{use_case_id}` | Update Use Case |
| DELETE | `/api/v1/ai-governance/systems/{system_id}/use-cases/{use_case_id}` | Delete Use Case |
| POST | `/api/v1/ai-systems` | Create Ai System |
| GET | `/api/v1/ai-systems` | List Ai Systems |
| GET | `/api/v1/ai-systems/summary` | Ai System Summary |

### Database Tables (89)

| Table | Description |
|---|---|
| `ai_approval_envelopes` | Approval envelopes bundling AI system changes for sign-off. |
| `ai_bias_assessments` | Bias/fairness assessments for AI systems. |
| `ai_content_drafts` | AI-generated content drafts (policies, controls, narratives). |
| `ai_draft_revisions` | Revision history of AI content drafts. |
| `ai_envelope_approvals` | Approval decisions on AI approval envelopes. |
| `ai_governance_diagnostic_snapshots` | Point-in-time diagnostic snapshots of AI governance posture. |
| `ai_governance_events` | Stream of AI governance events for an org. |
| `ai_governance_reviews` | AI governance reviews and their decisions. |
| `ai_guardrail_events` | Events emitted by AI guardrail evaluations. |
| `ai_inline_suggestions` | Inline AI suggestions (compliance copilot). |
| `ai_monitoring_configs` | Monitoring configurations for AI systems. |
| `ai_monitoring_readings` | Monitoring readings/metrics ingested for AI systems. |
| `ai_policy_guardrails` | Org-level AI policy guardrails. |
| `ai_review_criteria_responses` | Responses to review criteria within a governance review. |
| `ai_risk_assessment_questions` | Questions within an AI risk assessment. |
| `ai_risk_assessment_responses` | Responses to AI risk assessment questions. |
| `ai_risk_assessments` | AI risk assessments (questions, responses, scoring). |
| `ai_risk_classifications` | AI risk classifications (risk tier/level). |
| `ai_risk_recommendations` | Recommendations generated from AI risk assessments. |
| `ai_risk_signals` | Risk signals generated for AI systems. |
| `ai_rmf_function_responses` | Responses mapped to NIST AI RMF functions. |
| `ai_system_control_links` | Links between AI systems and controls. |
| `ai_system_evidence_links` | Links between AI systems and evidence. |
| `ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a` | Diagnostic-export diff-gating compare presets (alias). |
| `ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8` | Diagnostic-export diff-gating compare preset assignment history (alias). |
| `ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb` | Diagnostic-export diff-gating compare preset assignments (alias). |
| `ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df` | Diagnostic-export diff-gating compare preset reports (alias). |
| `ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c` | Diagnostic-export diff-gating compare preset versions (alias). |
| `ai_system_gov_diag_export_diff_gating_cmp_rpts_884d7a31` | Diagnostic-export diff-gating compare reports (alias). |
| `ai_system_gov_pol_diff_gating_cmp_pst_assign_hist_044c72ec` | Policy diff-gating compare preset assignment history (alias). |
| `ai_system_gov_pol_diff_gating_cmp_pst_assigns_8aba1d54` | Policy diff-gating compare preset assignments (alias). |
| `ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b` | Policy diff-gating compare preset versions (alias). |
| `ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83` | Preset-assignment diagnostic export diff reports (alias). |
| `ai_system_governance_attestations` | Attestations recorded during AI system governance reviews. |
| `ai_system_governance_diagnostic_export_diff_gating_profiles` | Profiles for diagnostic-export diff gating. |
| `ai_system_governance_diagnostic_export_diff_gating_reports` | Reports for diagnostic-export diff gating. |
| `ai_system_governance_freeze_windows` | Freeze windows blocking guardrail/policy changes. |
| `ai_system_governance_guardrail_policy_assignment_history` | History of guardrail policy assignment changes. |
| `ai_system_governance_guardrail_policy_assignments` | Assignments of guardrail policy sets to systems. |
| `ai_system_governance_guardrail_policy_set_versions` | Versioned snapshots of guardrail policy sets. |
| `ai_system_governance_guardrail_policy_sets` | Guardrail policy sets scoped to an AI system. |
| `ai_system_governance_operator_acknowledgements` | Operator acknowledgements of guardrail state. |
| `ai_system_governance_policy_diff_gating_compare_preset_reports` | Reports evaluating diff-gating compare presets. |
| `ai_system_governance_policy_diff_gating_compare_presets` | Reusable presets for policy diff-gating comparisons. |
| `ai_system_governance_policy_diff_gating_compare_reports` | Comparison reports for policy diff gating. |
| `ai_system_governance_policy_diff_gating_profiles` | Profiles configuring policy diff gating. |
| `ai_system_governance_policy_diff_gating_reports` | Reports produced by policy diff gating. |
| `ai_system_governance_policy_resolution_simulation_diff_reports` | Diff reports between policy-resolution simulations. |
| `ai_system_governance_policy_resolution_simulation_reports` | Policy-resolution simulation reports. |
| `ai_system_governance_preset_assignment_diagnostic_diff_reports` | Diff reports for preset-assignment diagnostics. |
| `ai_system_governance_preset_assignment_diagnostic_exports` | Diagnostic exports for preset assignments. |
| `ai_system_governance_preset_assignment_diagnostic_reports` | Diagnostic reports for preset assignments. |
| `ai_system_governance_review_events` | Events emitted during AI system governance reviews. |
| `ai_system_governance_review_plan_constraints` | Constraints applied to governance review plans. |
| `ai_system_governance_review_plan_runs` | Executions of governance review plans. |
| `ai_system_governance_review_recurrence_templates` | Templates defining recurring review schedules. |
| `ai_system_governance_review_reminder_policies` | Reminder policies for governance reviews. |
| `ai_system_governance_review_sequence_packs` | Packs of sequenced governance review steps. |
| `ai_system_governance_review_sequence_runs` | Runs of review sequences. |
| `ai_system_governance_review_sequence_steps` | Individual steps within a review sequence pack. |
| `ai_system_governance_reviews` | Governance reviews scoped to an AI system (v2 lifecycle). |
| `ai_system_risk_assessment_snapshots` | Snapshots of AI system risk assessments. |
| `ai_system_risk_assessments` | Risk assessments scoped to an AI system (v1). |
| `ai_system_risk_classification_record_snapshots` | Snapshots of AI risk classification records. |
| `ai_system_risk_classification_records` | Risk classification records for AI systems. |
| `ai_system_risk_classification_taxonomy_templates` | Templates defining AI risk classification taxonomies. |
| `ai_system_risk_dimension_templates` | Templates for AI risk dimensions/scoring. |
| `ai_system_risk_links` | Links between AI systems and risks. |
| `ai_system_risk_scoring_profiles` | Scoring profiles for AI system risk. |
| `ai_systems` | Registered AI systems (inventory, status, owner, oversight). |
| `ai_use_cases` | Approved/proposed use cases for an AI system. |
| `ai_vendor_assessments` | Assessments of vendor-provided AI models. |
| `aibom_components` | Components listed in an AIBOM. |
| `aibom_records` | AI bill-of-materials records for an AI system. |
| `atlas_techniques` | MITRE ATLAS threat-modeling techniques catalog. |
| `eu_act_annex_mappings` | EU AI Act annex/article reference mappings. |
| `eu_act_conformity_assessments` | EU AI Act conformity assessments. |
| `eu_act_frias` | Fundamental Rights Impact Assessments (EU AI Act). |
| `eu_act_post_market_plans` | Post-market monitoring plans (EU AI Act). |
| `eu_ai_act_classifications` | EU AI Act risk classifications for AI systems. |
| `iso42001_conformity_trackers` | ISO/IEC 42001 clause conformity tracking. |
| `mlflow_connections` | MLflow tracking server connections. |
| `mlflow_drift_events` | Model drift events ingested from MLflow. |
| `mlflow_model_registrations` | Model registrations ingested from MLflow. |
| `mlops_integrations` | MLOps platform integrations. |
| `model_cards` | Model cards documenting AI model characteristics. |
| `nist_ai_rmf_implementations` | NIST AI RMF implementation status per AI system. |
| `shadow_ai_detections` | Detected unsanctioned ('shadow') AI usage. |
| `third_party_ai_assessments` | Assessments of third-party AI systems. |

---

## Privacy & Data Protection

**11 features · 79 endpoints · 16 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Records of Processing Activities (RoPA) | Create/list/get/update/delete processing activities, obligation links, Article 30 report. | 10 |
| 2 | Data Subject Requests (DSR/DSAR) | Create/list/get DSR, verify identity, assign, extensions, fulfillment steps, SLA, transitions, public submit. | 14 |
| 3 | CCPA Opt-Out | Submit CCPA opt-out request. | 1 |
| 4 | Privacy Notices | Create/list/get/update/publish/acknowledge notices, active notice, acknowledgement status. | 8 |
| 5 | Consent Management | Record/list/withdraw consent, consent events, status, summary. | 7 |
| 6 | Cookie Registry & Consent Banner | Cookie CRUD, banner config, public banner, cookie scan reports. | 6 |
| 7 | DPIAs | Create/list/get/update/delete DPIAs, checklist, approve/reject/submit-for-review. | 10 |
| 8 | Lawful Basis Records | Document/list/update/deactivate lawful basis records, per-activity & summary. | 6 |
| 9 | DPAs (Data Processing Agreements) | Create/list/get/update/delete DPAs, link activity, status transitions, summary. | 8 |
| 10 | Notification & Digest Preferences | User notification preferences (bulk/per-type) and digest configs (daily/weekly/send-now). | 7 |
| 11 | Fides Import | Import Fides manifest and check import status. | 2 |

### Endpoints (79)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/privacy/ropa/activities` | Create Activity |
| GET | `/api/v1/privacy/ropa/activities` | List Activities |
| GET | `/api/v1/privacy/ropa/activities/summary` | Get Summary |
| GET | `/api/v1/privacy/ropa/activities/{activity_id}` | Get Activity |
| PATCH | `/api/v1/privacy/ropa/activities/{activity_id}` | Update Activity |
| DELETE | `/api/v1/privacy/ropa/activities/{activity_id}` | Delete Activity |
| POST | `/api/v1/privacy/ropa/activities/{activity_id}/obligation-links` | Link Obligation |
| GET | `/api/v1/privacy/ropa/activities/{activity_id}/obligation-links` | List Obligation Links |
| DELETE | `/api/v1/privacy/ropa/activities/{activity_id}/obligation-links/{obligation_id}` | Unlink Obligation |
| GET | `/api/v1/privacy/ropa/article30-report` | Article30 Report |
| POST | `/api/v1/privacy/dsr` | Create Request |
| GET | `/api/v1/privacy/dsr` | List Requests |
| GET | `/api/v1/privacy/dsr/overdue` | Get Overdue Requests |
| POST | `/api/v1/privacy/dsr/submit` | Submit Public Dsr |
| GET | `/api/v1/privacy/dsr/summary` | Get Summary |
| GET | `/api/v1/privacy/dsr/{request_id}` | Get Request |
| POST | `/api/v1/privacy/dsr/{request_id}/assign` | Assign Handler |
| POST | `/api/v1/privacy/dsr/{request_id}/grant-extension` | Grant Extension |
| POST | `/api/v1/privacy/dsr/{request_id}/steps` | Add Step |
| GET | `/api/v1/privacy/dsr/{request_id}/steps` | List Steps |
| PATCH | `/api/v1/privacy/dsr/{request_id}/steps/{step_id}` | Update Step |
| POST | `/api/v1/privacy/dsr/{request_id}/steps/{step_id}/complete` | Complete Step |
| POST | `/api/v1/privacy/dsr/{request_id}/transition` | Transition Status |
| POST | `/api/v1/privacy/dsr/{request_id}/verify-identity` | Verify Identity |
| POST | `/api/v1/privacy/ccpa/opt-out` | Submit Ccpa Opt Out |
| POST | `/api/v1/privacy/notices` | Create Notice |
| GET | `/api/v1/privacy/notices` | List Notices |
| GET | `/api/v1/privacy/notices/active` | Get Active Notice |
| GET | `/api/v1/privacy/notices/{notice_id}` | Get Notice |
| PATCH | `/api/v1/privacy/notices/{notice_id}` | Update Notice |
| POST | `/api/v1/privacy/notices/{notice_id}/acknowledge` | Acknowledge Notice |
| GET | `/api/v1/privacy/notices/{notice_id}/acknowledgements` | Acknowledgement Status |
| POST | `/api/v1/privacy/notices/{notice_id}/publish` | Publish Notice |
| POST | `/api/v1/privacy/consent` | Record Consent |
| GET | `/api/v1/privacy/consent` | List Consents |
| GET | `/api/v1/privacy/consent-banner/{org_slug}` | Get Public Banner |
| POST | `/api/v1/privacy/consent/events` | Receive Consent Event |
| GET | `/api/v1/privacy/consent/status` | Consent Status |
| GET | `/api/v1/privacy/consent/summary` | Consent Summary |
| POST | `/api/v1/privacy/consent/{consent_id}/withdraw` | Withdraw Consent |
| POST | `/api/v1/privacy/banner-config` | Create Or Update Banner |
| GET | `/api/v1/privacy/banner-config` | Get Banner Config |
| POST | `/api/v1/privacy/cookie-registry/scan-report` | Receive Cookie Scan Report |
| POST | `/api/v1/privacy/cookies` | Create Cookie |
| GET | `/api/v1/privacy/cookies` | List Cookies |
| PATCH | `/api/v1/privacy/cookies/{cookie_id}` | Update Cookie |
| POST | `/api/v1/privacy/dpias` | Create Dpia |
| GET | `/api/v1/privacy/dpias` | List Dpias |
| GET | `/api/v1/privacy/dpias/summary` | Get Summary |
| GET | `/api/v1/privacy/dpias/{dpia_id}` | Get Dpia |
| PATCH | `/api/v1/privacy/dpias/{dpia_id}` | Update Dpia |
| DELETE | `/api/v1/privacy/dpias/{dpia_id}` | Delete Dpia |
| POST | `/api/v1/privacy/dpias/{dpia_id}/approve` | Approve Dpia |
| POST | `/api/v1/privacy/dpias/{dpia_id}/checklist` | Respond Checklist |
| POST | `/api/v1/privacy/dpias/{dpia_id}/reject` | Reject Dpia |
| POST | `/api/v1/privacy/dpias/{dpia_id}/submit-for-review` | Submit For Review |
| POST | `/api/v1/privacy/lawful-basis` | Document Basis |
| GET | `/api/v1/privacy/lawful-basis` | List All |
| GET | `/api/v1/privacy/lawful-basis/activity/{activity_id}` | Get Activity Records |
| GET | `/api/v1/privacy/lawful-basis/summary` | Get Summary |
| PATCH | `/api/v1/privacy/lawful-basis/{record_id}` | Update Basis |
| POST | `/api/v1/privacy/lawful-basis/{record_id}/deactivate` | Deactivate Basis |
| POST | `/api/v1/privacy/dpas` | Create Dpa |
| GET | `/api/v1/privacy/dpas` | List Dpas |
| GET | `/api/v1/privacy/dpas/summary` | Get Summary |
| GET | `/api/v1/privacy/dpas/{dpa_id}` | Get Dpa |
| PATCH | `/api/v1/privacy/dpas/{dpa_id}` | Update Dpa |
| DELETE | `/api/v1/privacy/dpas/{dpa_id}` | Delete Dpa |
| POST | `/api/v1/privacy/dpas/{dpa_id}/link-activity` | Link Activity |
| POST | `/api/v1/privacy/dpas/{dpa_id}/status` | Transition Status |
| GET | `/api/v1/preferences/digest` | Get Digest Configs |
| PUT | `/api/v1/preferences/digest/daily` | Update Daily Digest |
| POST | `/api/v1/preferences/digest/send-now/{digest_type}` | Send Digest Now |
| PUT | `/api/v1/preferences/digest/weekly` | Update Weekly Digest |
| GET | `/api/v1/preferences/notifications` | Get Notification Preferences |
| PUT | `/api/v1/preferences/notifications/bulk` | Bulk Update Notification Preferences |
| PUT | `/api/v1/preferences/notifications/{notification_type}` | Update Notification Preference |
| POST | `/api/v1/privacy/import/fides` | Import Fides Manifest |
| GET | `/api/v1/privacy/import/fides/status` | Get Fides Import Status |

### Database Tables (16)

| Table | Description |
|---|---|
| `consent_banner_configs` | Consent banner configurations. |
| `consent_records` | Consent records (grant/withdraw). |
| `cookie_registries` | Registered cookies and trackers. |
| `data_subject_requests` | Data subject access/erasure requests (DSR/DSAR). |
| `digest_configs` | Digest (daily/weekly) configurations per user. |
| `dpa_agreements` | Data Processing Agreements. |
| `dpia_checklist_items` | Checklist items within a DPIA. |
| `dpias` | Data Protection Impact Assessments. |
| `dsr_fulfillment_steps` | Fulfillment steps for a DSR. |
| `dsr_sla_tracking` | SLA tracking for DSRs. |
| `lawful_basis_records` | Lawful basis records for processing activities. |
| `notice_user_acknowledgements` | User acknowledgements of privacy notices. |
| `privacy_notices` | Privacy notice versions. |
| `processing_activities` | Records of processing activities (RoPA core). |
| `ropa_framework_links` | Links between processing activities and obligations/frameworks. |
| `user_notification_preferences` | Per-user notification preferences. |

---

## Data Observability

**9 features · 77 endpoints · 16 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Data Asset Inventory | Create/list/get/update/delete data assets, classification, obligation links, quality configs, residency status, summaries. | 16 |
| 2 | Data Lineage | Lineage nodes/edges, asset lineage graph, OpenLineage events, OpenMetadata configure/sync/status. | 9 |
| 3 | Data Quality Monitoring | Quality config CRUD, readings, quality dashboard. | 7 |
| 4 | Data Access Monitoring | Access anomaly rules, access event ingest, access logs, summary. | 7 |
| 5 | Data Retention | Retention policy CRUD, apply-to-asset, legal hold, reviews, sweeps, summary. | 12 |
| 6 | Data Residency | Residency policy CRUD, sweeps, violations (acknowledge/resolve/waive), summary, per-asset checks. | 12 |
| 7 | Data Incidents | Create/list/get/contain/dismiss/escalate/investigate/resolve data incidents. | 9 |
| 8 | Obligation Coverage & Suggestions | Obligation coverage summary, data obligation suggestions (apply/dismiss). | 4 |
| 9 | Data Observability Dashboard | Cross-cutting data observability dashboard. | 1 |

### Endpoints (77)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/data-observability/assets` | Create Data Asset |
| GET | `/api/v1/data-observability/assets` | List Data Assets |
| GET | `/api/v1/data-observability/assets/summary` | Get Data Asset Summary |
| GET | `/api/v1/data-observability/assets/{asset_id}` | Get Data Asset |
| PATCH | `/api/v1/data-observability/assets/{asset_id}` | Update Data Asset |
| DELETE | `/api/v1/data-observability/assets/{asset_id}` | Delete Data Asset |
| GET | `/api/v1/data-observability/assets/{asset_id}/access-logs` | List Asset Access Logs |
| POST | `/api/v1/data-observability/assets/{asset_id}/classify-sample` | Classify Data Asset Sample |
| POST | `/api/v1/data-observability/assets/{asset_id}/confirm-classification` | Confirm Data Asset Classification |
| POST | `/api/v1/data-observability/assets/{asset_id}/obligation-links` | Link Asset To Obligation |
| GET | `/api/v1/data-observability/assets/{asset_id}/obligation-links` | List Asset Obligation Links |
| DELETE | `/api/v1/data-observability/assets/{asset_id}/obligation-links/{obligation_id}` | Unlink Asset From Obligation |
| GET | `/api/v1/data-observability/assets/{asset_id}/quality-configs` | List Asset Quality Configs |
| GET | `/api/v1/data-observability/assets/{asset_id}/residency-status` | Get Asset Residency Status |
| GET | `/api/v1/data-observability/assets/{asset_id}/suggest-obligations` | Suggest Asset Obligations |
| POST | `/api/v1/data-observability/assets/{asset_id}/suggest-obligations` | Generate Asset Obligation Suggestions |
| GET | `/api/v1/data-observability/lineage/assets/{asset_id}/lineage` | Get Asset Lineage Graph |
| POST | `/api/v1/data-observability/lineage/edges` | Create Lineage Edge |
| POST | `/api/v1/data-observability/lineage/events` | Receive Openlineage Event |
| POST | `/api/v1/data-observability/lineage/nodes` | Create Lineage Node |
| GET | `/api/v1/data-observability/lineage/nodes` | List Lineage Nodes |
| POST | `/api/v1/data-observability/lineage/nodes/{node_id}/link-asset/{asset_id}` | Link Asset To Lineage Node |
| POST | `/api/v1/data-observability/lineage/openmetadata/configure` | Configure Openmetadata |
| GET | `/api/v1/data-observability/lineage/openmetadata/status` | Get Openmetadata Status |
| POST | `/api/v1/data-observability/lineage/openmetadata/sync` | Sync Openmetadata |
| POST | `/api/v1/data-observability/quality/configs` | Create Quality Config |
| GET | `/api/v1/data-observability/quality/configs` | List Quality Configs |
| GET | `/api/v1/data-observability/quality/configs/{config_id}` | Get Quality Config |
| PATCH | `/api/v1/data-observability/quality/configs/{config_id}` | Update Quality Config |
| POST | `/api/v1/data-observability/quality/configs/{config_id}/deactivate` | Deactivate Quality Config |
| POST | `/api/v1/data-observability/quality/configs/{config_id}/readings` | Submit Quality Reading |
| GET | `/api/v1/data-observability/quality/dashboard` | Get Quality Dashboard |
| GET | `/api/v1/data-observability/access/anomaly-rules` | List Anomaly Rules |
| POST | `/api/v1/data-observability/access/anomaly-rules` | Create Anomaly Rule |
| PATCH | `/api/v1/data-observability/access/anomaly-rules/{rule_id}` | Update Anomaly Rule |
| POST | `/api/v1/data-observability/access/anomaly-rules/{rule_id}/deactivate` | Deactivate Anomaly Rule |
| POST | `/api/v1/data-observability/access/events` | Ingest Access Event |
| GET | `/api/v1/data-observability/access/logs` | List Access Logs |
| GET | `/api/v1/data-observability/access/summary` | Get Access Summary |
| POST | `/api/v1/data-observability/retention/policies` | Create Retention Policy |
| GET | `/api/v1/data-observability/retention/policies` | List Retention Policies |
| GET | `/api/v1/data-observability/retention/policies/{policy_id}` | Get Retention Policy |
| PATCH | `/api/v1/data-observability/retention/policies/{policy_id}` | Update Retention Policy |
| POST | `/api/v1/data-observability/retention/policies/{policy_id}/apply-to-asset` | Apply Policy To Asset |
| POST | `/api/v1/data-observability/retention/policies/{policy_id}/deactivate` | Deactivate Retention Policy |
| GET | `/api/v1/data-observability/retention/reviews` | List Retention Reviews |
| POST | `/api/v1/data-observability/retention/reviews/{review_id}/resolve` | Resolve Retention Review |
| POST | `/api/v1/data-observability/retention/reviews/{review_id}/waive` | Waive Retention Review |
| GET | `/api/v1/data-observability/retention/summary` | Get Retention Summary |
| POST | `/api/v1/data-observability/retention/trigger-sweep` | Trigger Retention Sweep |
| POST | `/api/v1/data-observability/retention/{policy_id}/legal-hold` | Set Retention Policy Legal Hold |
| POST | `/api/v1/data-observability/residency/check-asset/{asset_id}` | Check Single Asset |
| POST | `/api/v1/data-observability/residency/policies` | Create Residency Policy |
| GET | `/api/v1/data-observability/residency/policies` | List Residency Policies |
| GET | `/api/v1/data-observability/residency/policies/{policy_id}` | Get Residency Policy |
| PATCH | `/api/v1/data-observability/residency/policies/{policy_id}` | Update Residency Policy |
| POST | `/api/v1/data-observability/residency/policies/{policy_id}/deactivate` | Deactivate Residency Policy |
| GET | `/api/v1/data-observability/residency/summary` | Get Residency Summary |
| POST | `/api/v1/data-observability/residency/trigger-sweep` | Trigger Residency Sweep |
| GET | `/api/v1/data-observability/residency/violations` | List Residency Violations |
| POST | `/api/v1/data-observability/residency/violations/{violation_id}/acknowledge` | Acknowledge Violation |
| POST | `/api/v1/data-observability/residency/violations/{violation_id}/resolve` | Resolve Violation |
| POST | `/api/v1/data-observability/residency/violations/{violation_id}/waive` | Waive Violation |
| POST | `/api/v1/data-observability/incidents` | Create Manual Incident |
| GET | `/api/v1/data-observability/incidents` | List Incidents |
| GET | `/api/v1/data-observability/incidents/summary` | Get Incident Summary |
| GET | `/api/v1/data-observability/incidents/{incident_id}` | Get Incident |
| POST | `/api/v1/data-observability/incidents/{incident_id}/contain` | Contain Incident |
| POST | `/api/v1/data-observability/incidents/{incident_id}/dismiss` | Dismiss Incident |
| POST | `/api/v1/data-observability/incidents/{incident_id}/escalate-to-issue` | Escalate Incident To Issue |
| POST | `/api/v1/data-observability/incidents/{incident_id}/investigate` | Investigate Incident |
| POST | `/api/v1/data-observability/incidents/{incident_id}/resolve` | Resolve Incident |
| GET | `/api/v1/data-observability/obligation-coverage` | Get Obligation Coverage Summary |
| GET | `/api/v1/data-observability/obligation-suggestions` | List Data Obligation Suggestions |
| POST | `/api/v1/data-observability/obligation-suggestions/{suggestion_id}/apply` | Apply Data Obligation Suggestion |
| POST | `/api/v1/data-observability/obligation-suggestions/{suggestion_id}/dismiss` | Dismiss Data Obligation Suggestion |
| GET | `/api/v1/data-observability/dashboard` | Get Data Observability Dashboard |

### Database Tables (16)

| Table | Description |
|---|---|
| `data_access_anomaly_rules` | Anomaly detection rules for data access. |
| `data_access_logs` | Data access logs. |
| `data_asset_obligation_links` | Links between data assets and obligations. |
| `data_asset_risk_links` | Links between data assets and risks. |
| `data_assets` | Cataloged data assets. |
| `data_incidents` | Data observability incidents. |
| `data_lineage_edges` | Edges in the data lineage graph. |
| `data_lineage_nodes` | Nodes in the data lineage graph. |
| `data_obligation_suggestions` | Suggested obligation links for data assets. |
| `data_quality_configs` | Data quality metric configurations per asset. |
| `data_quality_readings` | Data quality metric readings. |
| `data_residency_policies` | Data residency policies. |
| `data_residency_violations` | Detected data residency violations. |
| `data_retention_policies` | Data retention policies. |
| `data_retention_reviews` | Retention reviews due for data assets. |
| `openmetadata_integrations` | OpenMetadata integration configs. |

---

## Risk Management

**7 features · 56 endpoints · 8 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Risk Register | Create/list/get/update/archive risks, accept, heatmap, summary, graph, score breakdown, treatment tasks. | 23 |
| 2 | Risk Settings | Org risk scoring weights/settings. | 2 |
| 3 | Risk Appetite Thresholds | Create/list/get/update/deactivate thresholds, live breaches, summary. | 7 |
| 4 | Risk Indicators (KRIs) | Create/list/get/update/archive/recalculate risk indicators, summary. | 7 |
| 5 | Entity Risk Scores | Compute entity scores, scores by entity, summary. | 3 |
| 6 | AI/Compliance Risk Recommendations | Generate/list/accept/dismiss/snooze risk recommendations. | 6 |
| 7 | Policy–Risk Linkages | Policy↔risk links & mappings, risk/policy coverage, effectiveness. | 8 |

### Endpoints (56)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/compliance/policies/{policy_id}/risks` | Link Policy Risk |
| GET | `/api/v1/compliance/policies/{policy_id}/risks` | List Risks For Policy |
| DELETE | `/api/v1/compliance/policies/{policy_id}/risks/{risk_id}` | Unlink Policy Risk |
| GET | `/api/v1/compliance/risks/{risk_id}/graph` | Get Risk Graph Compliance Alias |
| GET | `/api/v1/compliance/risks/{risk_id}/policies` | List Policies For Risk |
| GET | `/api/v1/compliance/risks/{risk_id}/policy-coverage` | Get Risk Policy Coverage |
| GET | `/api/v1/compliance/risks/{risk_id}/policy-mappings` | List Policy Risk Mappings For Risk |
| GET | `/api/v1/compliance/risks/{risk_id}/score-breakdown` | Get Risk Score Breakdown Compliance Alias |
| GET | `/api/v1/risks` | List Risks |
| POST | `/api/v1/risks` | Create Risk |
| GET | `/api/v1/risks/heatmap` | Risk Heatmap |
| GET | `/api/v1/risks/summary` | Risk Summary |
| GET | `/api/v1/risks/{risk_id}` | Get Risk Detail |
| PATCH | `/api/v1/risks/{risk_id}` | Update Risk |
| POST | `/api/v1/risks/{risk_id}/accept` | Accept Risk |
| PATCH | `/api/v1/risks/{risk_id}/archive` | Archive Risk |
| POST | `/api/v1/risks/{risk_id}/controls` | Link Risk To Control |
| DELETE | `/api/v1/risks/{risk_id}/controls/{control_id}` | Unlink Risk From Control |
| POST | `/api/v1/risks/{risk_id}/evidence` | Link Risk To Evidence |
| DELETE | `/api/v1/risks/{risk_id}/evidence/{evidence_id}` | Unlink Risk From Evidence |
| GET | `/api/v1/risks/{risk_id}/graph` | Get Risk Graph |
| GET | `/api/v1/risks/{risk_id}/score-breakdown` | Get Risk Score Breakdown |
| POST | `/api/v1/risks/{risk_id}/treatment-task` | Create Risk Treatment Task |
| GET | `/api/v1/compliance/risk-settings` | Get Risk Settings |
| PUT | `/api/v1/compliance/risk-settings` | Upsert Risk Settings |
| POST | `/api/v1/compliance/risk-appetite` | Create Threshold |
| GET | `/api/v1/compliance/risk-appetite` | List Thresholds |
| GET | `/api/v1/compliance/risk-appetite/breaches` | List Live Breaches |
| GET | `/api/v1/compliance/risk-appetite/summary` | Summary Thresholds |
| GET | `/api/v1/compliance/risk-appetite/{threshold_id}` | Get Threshold |
| PATCH | `/api/v1/compliance/risk-appetite/{threshold_id}` | Update Threshold |
| POST | `/api/v1/compliance/risk-appetite/{threshold_id}/deactivate` | Deactivate Threshold |
| POST | `/api/v1/compliance/risk-indicators` | Create Risk Indicator |
| GET | `/api/v1/compliance/risk-indicators` | List Risk Indicators |
| GET | `/api/v1/compliance/risk-indicators/summary` | Risk Indicator Summary |
| GET | `/api/v1/compliance/risk-indicators/{indicator_id}` | Get Risk Indicator |
| PATCH | `/api/v1/compliance/risk-indicators/{indicator_id}` | Update Risk Indicator |
| POST | `/api/v1/compliance/risk-indicators/{indicator_id}/archive` | Archive Risk Indicator |
| POST | `/api/v1/compliance/risk-indicators/{indicator_id}/recalculate` | Recalculate Risk Indicator |
| GET | `/api/v1/compliance/risk-scores/by-entity` | Get Scores By Entity |
| POST | `/api/v1/compliance/risk-scores/compute-entity` | Compute Entity Score |
| GET | `/api/v1/compliance/risk-scores/summary` | Get Entity Score Summary |
| GET | `/api/v1/compliance/risk-recommendations` | List Recommendations |
| POST | `/api/v1/compliance/risk-recommendations/generate` | Generate Recommendations |
| GET | `/api/v1/compliance/risk-recommendations/{recommendation_id}` | Get Recommendation |
| POST | `/api/v1/compliance/risk-recommendations/{recommendation_id}/accept` | Accept Recommendation |
| POST | `/api/v1/compliance/risk-recommendations/{recommendation_id}/dismiss` | Dismiss Recommendation |
| POST | `/api/v1/compliance/risk-recommendations/{recommendation_id}/snooze` | Snooze Recommendation |
| GET | `/api/v1/compliance/policies/{policy_id}/risk-coverage` | Get Policy Risk Coverage |
| GET | `/api/v1/compliance/policies/{policy_id}/risk-mappings` | List Policy Risk Mappings For Policy |
| POST | `/api/v1/compliance/policy-risk-mappings` | Create Policy Risk Mapping |
| GET | `/api/v1/compliance/policy-risk-mappings` | List Policy Risk Mappings |
| GET | `/api/v1/compliance/policy-risk-mappings/summary` | Get Org Policy Risk Mapping Summary |
| GET | `/api/v1/compliance/policy-risk-mappings/{mapping_id}` | Get Policy Risk Mapping |
| PATCH | `/api/v1/compliance/policy-risk-mappings/{mapping_id}` | Update Policy Risk Mapping |
| DELETE | `/api/v1/compliance/policy-risk-mappings/{mapping_id}` | Delete Policy Risk Mapping |

### Database Tables (8)

| Table | Description |
|---|---|
| `compliance_risk_recommendations` | AI-generated risk recommendations. |
| `entity_risk_scores` | Composite risk scores for arbitrary entities. |
| `org_risk_settings` | Org-level risk scoring weights/settings. |
| `risk_appetite_thresholds` | Risk appetite thresholds. |
| `risk_control_links` | Links between risks and controls. |
| `risk_evidence_links` | Links between risks and evidence. |
| `risk_indicators` | Risk indicators (KRIs). |
| `risks` | Risk register entries. |

---

## Policy Management

**8 features · 79 endpoints · 15 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Policy CRUD & Versions | Create/list/get/update/archive policies, versions, approval requests, control links, violation rate, summary. | 33 |
| 2 | Policy Drafting (AI) | AI policy drafts, accept/discard, org AI configuration. | 2 |
| 3 | Policy Template Library | List/get/clone/apply policy templates, categories, frameworks, stats, slug lookup. | 10 |
| 4 | Policy Exceptions | Create/list/get/update/withdraw/approve/reject policy exceptions, dashboard, summary. | 8 |
| 5 | Policy Attestation Campaigns | Create/list/get/update/cancel campaigns, attest, exemptions, reminders, records, completion, declines, summaries. | 16 |
| 6 | Employee Attestations | My/user attestation records, policy attestation summary (employee attestation workflow). | 0 |
| 7 | Policy–Issue Linkages | Policy↔issue links, policy effectiveness, issue policy context. | 8 |
| 8 | Attestation Tokens (generic) | Get/revoke attestation detail (generic attestation access). | 2 |

### Endpoints (79)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/compliance/policies` | Create Policy |
| GET | `/api/v1/compliance/policies` | List Policies |
| POST | `/api/v1/compliance/policies/draft` | Create Policy Draft |
| GET | `/api/v1/compliance/policies/draft/{draft_id}` | Get Policy Draft |
| POST | `/api/v1/compliance/policies/draft/{draft_id}/accept` | Accept Policy Draft |
| POST | `/api/v1/compliance/policies/draft/{draft_id}/discard` | Discard Policy Draft |
| GET | `/api/v1/compliance/policies/drafts` | List Policy Drafts |
| GET | `/api/v1/compliance/policies/summary` | Policies Summary |
| GET | `/api/v1/compliance/policies/{policy_id}` | Get Policy |
| PATCH | `/api/v1/compliance/policies/{policy_id}` | Update Policy |
| POST | `/api/v1/compliance/policies/{policy_id}/approval-requests` | Create Policy Approval Request |
| GET | `/api/v1/compliance/policies/{policy_id}/approval-requests` | List Policy Approval Requests |
| POST | `/api/v1/compliance/policies/{policy_id}/approval-requests/{request_id}/approve` | Approve Policy Approval Request |
| POST | `/api/v1/compliance/policies/{policy_id}/approval-requests/{request_id}/cancel` | Cancel Policy Approval Request |
| POST | `/api/v1/compliance/policies/{policy_id}/approval-requests/{request_id}/reject` | Reject Policy Approval Request |
| POST | `/api/v1/compliance/policies/{policy_id}/archive` | Archive Policy |
| GET | `/api/v1/compliance/policies/{policy_id}/associated-issues` | Get Policy Associated Issues |
| GET | `/api/v1/compliance/policies/{policy_id}/attestation-summary` | Policy Attestation Summary |
| GET | `/api/v1/compliance/policies/{policy_id}/effectiveness` | Get Policy Effectiveness |
| GET | `/api/v1/compliance/policies/{policy_id}/exception-summary` | Policy Exception Summary |
| GET | `/api/v1/compliance/policies/{policy_id}/issue-links` | List Policy Issue Links For Policy |
| POST | `/api/v1/compliance/policies/{policy_id}/issues` | Link Issue To Policy |
| GET | `/api/v1/compliance/policies/{policy_id}/issues` | List Issues For Policy |
| DELETE | `/api/v1/compliance/policies/{policy_id}/issues/{issue_id}` | Unlink Issue From Policy |
| POST | `/api/v1/compliance/policies/{policy_id}/links/controls` | Link Control To Policy |
| GET | `/api/v1/compliance/policies/{policy_id}/links/controls` | List Policy Control Links |
| POST | `/api/v1/compliance/policies/{policy_id}/links/controls/{link_id}/unlink` | Unlink Control From Policy |
| GET | `/api/v1/compliance/policies/{policy_id}/links/summary` | Policy Links Summary |
| POST | `/api/v1/compliance/policies/{policy_id}/versions` | Create Policy Version |
| GET | `/api/v1/compliance/policies/{policy_id}/versions` | List Policy Versions |
| GET | `/api/v1/compliance/policies/{policy_id}/versions/{version_id}` | Get Policy Version |
| POST | `/api/v1/compliance/policies/{policy_id}/versions/{version_id}/submit-for-approval` | Submit Policy Version For Approval |
| GET | `/api/v1/compliance/policies/{policy_id}/violation-rate` | Get Policy Violation Rate |
| GET | `/api/v1/organizations/ai-configuration` | Get Org Ai Configuration |
| PUT | `/api/v1/organizations/ai-configuration` | Put Org Ai Configuration |
| GET | `/api/v1/compliance/policy-templates` | List Policy Templates |
| POST | `/api/v1/compliance/policy-templates` | Create Org Template |
| GET | `/api/v1/compliance/policy-templates/categories` | List Policy Template Categories |
| GET | `/api/v1/compliance/policy-templates/clones` | List Policy Template Clones |
| GET | `/api/v1/compliance/policy-templates/frameworks` | List Policy Template Frameworks |
| GET | `/api/v1/compliance/policy-templates/slug/{slug}` | Get Policy Template By Slug |
| GET | `/api/v1/compliance/policy-templates/{template_id}` | Get Policy Template |
| POST | `/api/v1/compliance/policy-templates/{template_id}/apply` | Apply Template |
| POST | `/api/v1/compliance/policy-templates/{template_id}/clone` | Clone Policy Template |
| GET | `/api/v1/compliance/policy-templates/{template_id}/stats` | Get Policy Template Stats |
| POST | `/api/v1/compliance/policy-exceptions` | Create Policy Exception |
| GET | `/api/v1/compliance/policy-exceptions` | List Policy Exceptions |
| GET | `/api/v1/compliance/policy-exceptions/dashboard` | Policy Exception Dashboard |
| GET | `/api/v1/compliance/policy-exceptions/{exception_id}` | Get Policy Exception |
| PATCH | `/api/v1/compliance/policy-exceptions/{exception_id}` | Update Policy Exception |
| DELETE | `/api/v1/compliance/policy-exceptions/{exception_id}` | Withdraw Policy Exception |
| POST | `/api/v1/compliance/policy-exceptions/{exception_id}/approve` | Approve Policy Exception |
| POST | `/api/v1/compliance/policy-exceptions/{exception_id}/reject` | Reject Policy Exception |
| POST | `/api/v1/compliance/attestation-campaigns` | Create Attestation Campaign |
| GET | `/api/v1/compliance/attestation-campaigns` | List Attestation Campaigns |
| GET | `/api/v1/compliance/attestation-campaigns/dashboard` | Attestation Dashboard |
| GET | `/api/v1/compliance/attestation-campaigns/{campaign_id}` | Get Attestation Campaign |
| PATCH | `/api/v1/compliance/attestation-campaigns/{campaign_id}` | Update Attestation Campaign |
| DELETE | `/api/v1/compliance/attestation-campaigns/{campaign_id}` | Cancel Attestation Campaign |
| POST | `/api/v1/compliance/attestation-campaigns/{campaign_id}/attest` | Submit My Attestation |
| GET | `/api/v1/compliance/attestation-campaigns/{campaign_id}/attestations` | List Campaign Attestations |
| GET | `/api/v1/compliance/attestation-campaigns/{campaign_id}/completion` | Attestation Campaign Completion |
| POST | `/api/v1/compliance/attestation-campaigns/{campaign_id}/decline` | Decline Campaign |
| POST | `/api/v1/compliance/attestation-campaigns/{campaign_id}/exempt/{user_id}` | Exempt User Attestation |
| POST | `/api/v1/compliance/attestation-campaigns/{campaign_id}/remind/{user_id}` | Send Single Attestation Reminder |
| POST | `/api/v1/compliance/attestation-campaigns/{campaign_id}/reminders` | Send Attestation Bulk Reminders |
| GET | `/api/v1/compliance/attestation-records/me` | List My Attestation Records |
| GET | `/api/v1/compliance/attestation-records/user/{user_id}` | List User Attestation Records |
| GET | `/api/v1/compliance/my-attestations` | My Attestations |
| GET | `/api/v1/compliance/issues/{issue_id}/policies` | List Policies For Issue |
| GET | `/api/v1/compliance/issues/{issue_id}/policy-context` | Get Issue Policy Context |
| POST | `/api/v1/compliance/policy-issue-links` | Create Policy Issue Link |
| GET | `/api/v1/compliance/policy-issue-links` | List Policy Issue Links |
| GET | `/api/v1/compliance/policy-issue-links/summary` | Get Org Policy Issue Link Summary |
| GET | `/api/v1/compliance/policy-issue-links/{link_id}` | Get Policy Issue Link |
| PATCH | `/api/v1/compliance/policy-issue-links/{link_id}` | Update Policy Issue Link |
| DELETE | `/api/v1/compliance/policy-issue-links/{link_id}` | Delete Policy Issue Link |
| GET | `/api/v1/attestations/{attestation_id}` | Get Attestation Detail |
| POST | `/api/v1/attestations/{attestation_id}/revoke` | Revoke Attestation |

### Database Tables (15)

| Table | Description |
|---|---|
| `compliance_policies` | Compliance policies. |
| `compliance_policy_approval_requests` | Approval requests for policy versions. |
| `compliance_policy_control_links` | Links between policies and controls. |
| `compliance_policy_versions` | Versioned content snapshots of policies. |
| `draft_requests` | AI draft generation requests. |
| `policy_attestation_campaigns` | Attestation campaigns for policies. |
| `policy_attestation_records` | Attestation records per user/campaign. |
| `policy_attestations` | Attestation records (legacy). |
| `policy_exception_approvals` | Approval decisions on policy exceptions. |
| `policy_exceptions` | Policy exceptions with approval workflow. |
| `policy_issue_links` | Links between policies and issues. |
| `policy_risk_links` | Links between policies and risks. |
| `policy_risk_mappings` | Mappings between policies and risks. |
| `policy_template_clones` | Records of templates cloned into policies. |
| `policy_templates` | Reusable policy templates. |

---

## Compliance Frameworks & Obligations

**14 features · 142 endpoints · 36 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Framework Catalog & Activation | List frameworks, activate/deactivate, framework detail, active frameworks, versions, sections. | 46 |
| 2 | Framework Applicability | Applicability questions/answers, evaluation runs, summary, assess-applicability. | 4 |
| 3 | Framework Content & Coverage | Content summary, coverage gaps/reports, content imports (preview/apply), cross-mappings, embeddings, semantic mappings. | 6 |
| 4 | Framework Pack Reviews | Start/list/get/complete pack reviews, assignments, signoffs, review summary, promotions (preflight/approve/execute/reject). | 0 |
| 5 | Framework Review Queue & SLA | Review queue (org/my/summary), SLA policies, escalations, assignment accept/cancel/complete. | 13 |
| 6 | Framework Reviewer Capacity & Batch Assignments | Capacity policies, workload, simulations, batch assignments (apply/validate/cancel), assignment suggestions, cancellation requests. | 25 |
| 7 | Obligation Management | Obligation detail, applicability rules, content versions, control suggestions, evidence requirements, state, controls, cross-mappings, data assets, semantic similarity. | 12 |
| 8 | Compliance Obligations (compliance-scoped) | Compliance-scoped obligation cross-mappings, data assets, semantic similarity. | 0 |
| 9 | Compliance Deadlines | Create/list/get/update deadlines, evaluate-due, events, complete/cancel/waive, summary. | 10 |
| 10 | Compliance Dashboard | Posture summary, control health, framework readiness, risk heatmap, recent activity. | 5 |
| 11 | Board Scorecard | Generate/list/get/export board scorecard snapshots. | 4 |
| 12 | Business Units | Create/list/get/update/delete business units, tree, tag, deactivate, summary. | 9 |
| 13 | Scoring & Score Snapshots | Scoring methodology, summary, score snapshots (list/delta/latest/trends/materialize). | 7 |
| 14 | Platform Dashboard | Top-level dashboard summary. | 1 |

### Endpoints (142)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/compliance/frameworks/{framework_id}/applicability-questions` | List Applicability Questions Compliance |
| POST | `/api/v1/compliance/frameworks/{framework_id}/assess-applicability` | Assess Framework Applicability |
| GET | `/api/v1/compliance/frameworks/{framework_id}/cross-mappings` | List Framework Cross Mappings |
| POST | `/api/v1/compliance/frameworks/{framework_id}/embed` | Embed Framework Obligations |
| POST | `/api/v1/compliance/frameworks/{source_framework_id}/discover-mappings` | Discover Semantic Mappings |
| GET | `/api/v1/frameworks` | List Framework Catalog |
| GET | `/api/v1/frameworks/active` | List Active Organization Frameworks |
| GET | `/api/v1/frameworks/{framework_id}` | Get Framework Detail |
| POST | `/api/v1/frameworks/{framework_id}/activate` | Activate Framework |
| POST | `/api/v1/frameworks/{framework_id}/applicability-answers` | Submit Applicability Answers |
| GET | `/api/v1/frameworks/{framework_id}/applicability-answers` | List Applicability Answers |
| POST | `/api/v1/frameworks/{framework_id}/applicability-questions` | Create Applicability Question |
| GET | `/api/v1/frameworks/{framework_id}/applicability-questions` | List Applicability Questions |
| POST | `/api/v1/frameworks/{framework_id}/applicability/evaluate` | Evaluate Framework Applicability |
| GET | `/api/v1/frameworks/{framework_id}/applicability/evaluations` | List Applicability Evaluation Runs |
| GET | `/api/v1/frameworks/{framework_id}/applicability/evaluations/{run_id}` | Get Applicability Evaluation Run Detail |
| GET | `/api/v1/frameworks/{framework_id}/applicability/summary` | Applicability Summary |
| POST | `/api/v1/frameworks/{framework_id}/content-imports/apply` | Framework Content Import Apply |
| POST | `/api/v1/frameworks/{framework_id}/content-imports/preview` | Framework Content Import Preview |
| GET | `/api/v1/frameworks/{framework_id}/content-summary` | Framework Content Summary |
| GET | `/api/v1/frameworks/{framework_id}/coverage-gaps` | Framework Coverage Gaps |
| POST | `/api/v1/frameworks/{framework_id}/coverage-report` | Generate Framework Coverage Report |
| GET | `/api/v1/frameworks/{framework_id}/coverage-reports` | List Framework Coverage Reports |
| POST | `/api/v1/frameworks/{framework_id}/deactivate` | Deactivate Framework |
| GET | `/api/v1/frameworks/{framework_id}/obligations` | List Framework Obligations |
| POST | `/api/v1/frameworks/{framework_id}/pack-promotions` | Create Framework Pack Promotion Request |
| GET | `/api/v1/frameworks/{framework_id}/pack-promotions` | List Framework Pack Promotions |
| POST | `/api/v1/frameworks/{framework_id}/pack-promotions/preflight` | Preflight Framework Pack Promotion |
| POST | `/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/approve` | Approve Framework Pack Promotion |
| POST | `/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/execute` | Execute Framework Pack Promotion |
| POST | `/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/reject` | Reject Framework Pack Promotion |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews` | Start Framework Pack Review |
| GET | `/api/v1/frameworks/{framework_id}/pack-reviews` | List Framework Pack Reviews |
| GET | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}` | Get Framework Pack Review |
| GET | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions` | List Assignment Suggestions |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/generate` | Generate Assignment Suggestions |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignment-suggestions/simulate` | Simulate Assignment Suggestions |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments` | Assign Framework Review |
| GET | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments` | List Framework Review Assignments |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete` | Complete Framework Pack Review |
| POST | `/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs` | Signoff Framework Pack Review |
| GET | `/api/v1/frameworks/{framework_id}/review-summary` | Framework Review Summary |
| GET | `/api/v1/frameworks/{framework_id}/sections` | List Framework Sections |
| POST | `/api/v1/frameworks/{framework_id}/sections` | Create Framework Section |
| GET | `/api/v1/frameworks/{framework_id}/versions` | List Framework Versions |
| POST | `/api/v1/frameworks/{framework_id}/versions` | Create Framework Version |
| POST | `/api/v1/obligations/{obligation_id}/applicability-rules` | Create Obligation Applicability Rule |
| GET | `/api/v1/obligations/{obligation_id}/applicability-rules` | List Obligation Applicability Rules |
| POST | `/api/v1/obligations/{obligation_id}/applicability-rules/{rule_id}/archive` | Archive Obligation Applicability Rule |
| GET | `/api/v1/obligations/{obligation_id}/applicability-status` | Get Obligation Applicability Status |
| GET | `/api/v1/compliance/obligations/{obligation_id}/cross-mappings` | List Obligation Cross Mappings |
| GET | `/api/v1/compliance/semantic/status` | Get Semantic Status |
| GET | `/api/v1/framework-content/coverage-summary` | Global Framework Coverage Summary |
| GET | `/api/v1/framework-content/packs` | List Local Content Packs |
| POST | `/api/v1/framework-content/packs/{pack_key}/apply` | Apply Local Content Pack |
| POST | `/api/v1/framework-content/packs/{pack_key}/validate` | Validate Local Content Pack |
| POST | `/api/v1/framework-review-assignments/{assignment_id}/accept` | Accept Framework Review Assignment |
| POST | `/api/v1/framework-review-assignments/{assignment_id}/cancel` | Cancel Framework Review Assignment |
| POST | `/api/v1/framework-review-assignments/{assignment_id}/complete` | Complete Framework Review Assignment |
| GET | `/api/v1/framework-review-escalations` | List Framework Review Escalations |
| POST | `/api/v1/framework-review-escalations/{event_id}/resolve` | Resolve Framework Review Escalation |
| GET | `/api/v1/framework-review-queue` | Organization Framework Review Queue |
| POST | `/api/v1/framework-review-queue/evaluate-sla` | Evaluate Framework Review Sla |
| GET | `/api/v1/framework-review-queue/my` | My Framework Review Queue |
| GET | `/api/v1/framework-review-queue/summary` | Framework Review Queue Summary |
| POST | `/api/v1/framework-review-sla-policies` | Create Framework Review Sla Policy |
| GET | `/api/v1/framework-review-sla-policies` | List Framework Review Sla Policies |
| PATCH | `/api/v1/framework-review-sla-policies/{policy_id}` | Update Framework Review Sla Policy |
| POST | `/api/v1/framework-review-sla-policies/{policy_id}/archive` | Archive Framework Review Sla Policy |
| POST | `/api/v1/framework-review-assignment-suggestions/{suggestion_id}/apply` | Apply Assignment Suggestion |
| POST | `/api/v1/framework-review-assignment-suggestions/{suggestion_id}/dismiss` | Dismiss Assignment Suggestion |
| POST | `/api/v1/framework-review-capacity/batch-assignments/apply` | Apply Batch Assignments |
| GET | `/api/v1/framework-review-capacity/batch-assignments/cancellation-requests` | List Batch Cancellation Requests |
| GET | `/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}` | Get Batch Cancellation Request |
| POST | `/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/approve` | Approve Batch Cancellation Request |
| POST | `/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/execute` | Execute Batch Cancellation Request |
| POST | `/api/v1/framework-review-capacity/batch-assignments/cancellation-requests/{request_id}/reject` | Reject Batch Cancellation Request |
| GET | `/api/v1/framework-review-capacity/batch-assignments/runs` | List Batch Assignment Runs |
| GET | `/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}` | Get Batch Assignment Run |
| POST | `/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/cancel` | Cancel Batch Assignment Run |
| POST | `/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/cancellation-requests` | Create Batch Cancellation Request |
| POST | `/api/v1/framework-review-capacity/batch-assignments/runs/{run_id}/require-cancellation-approval` | Update Batch Cancellation Requirement |
| GET | `/api/v1/framework-review-capacity/batch-assignments/summary` | Batch Assignment Summary |
| POST | `/api/v1/framework-review-capacity/batch-assignments/validate` | Validate Batch Assignments |
| POST | `/api/v1/framework-review-capacity/policies` | Create Capacity Policy |
| GET | `/api/v1/framework-review-capacity/policies` | List Capacity Policies |
| PATCH | `/api/v1/framework-review-capacity/policies/{policy_id}` | Update Capacity Policy |
| POST | `/api/v1/framework-review-capacity/policies/{policy_id}/archive` | Archive Capacity Policy |
| POST | `/api/v1/framework-review-capacity/simulations/policy` | Simulate Capacity Policy |
| POST | `/api/v1/framework-review-capacity/simulations/review-waves` | Simulate Review Waves |
| GET | `/api/v1/framework-review-capacity/simulations/summary` | Simulation Summary |
| GET | `/api/v1/framework-review-capacity/summary` | Capacity Summary |
| GET | `/api/v1/framework-review-capacity/workload` | List Workload |
| POST | `/api/v1/framework-review-capacity/workload/calculate` | Calculate Workload |
| GET | `/api/v1/compliance/obligations/{obligation_id}/data-assets` | List Obligation Data Assets |
| GET | `/api/v1/compliance/obligations/{obligation_id}/semantic-similar` | List Semantic Similar Obligations |
| GET | `/api/v1/obligations/{obligation_id}` | Get Obligation Detail |
| POST | `/api/v1/obligations/{obligation_id}/content-versions` | Create Obligation Content Version |
| GET | `/api/v1/obligations/{obligation_id}/content-versions` | List Obligation Content Versions |
| POST | `/api/v1/obligations/{obligation_id}/control-suggestions` | Create Obligation Control Suggestion |
| GET | `/api/v1/obligations/{obligation_id}/control-suggestions` | List Obligation Control Suggestions |
| POST | `/api/v1/obligations/{obligation_id}/control-suggestions/{suggestion_id}/apply` | Apply Control Suggestion |
| GET | `/api/v1/obligations/{obligation_id}/controls` | List Controls For Obligation |
| POST | `/api/v1/obligations/{obligation_id}/evidence-requirements` | Create Obligation Evidence Requirement |
| GET | `/api/v1/obligations/{obligation_id}/evidence-requirements` | List Obligation Evidence Requirements |
| PATCH | `/api/v1/obligations/{obligation_id}/state` | Update Obligation State |
| POST | `/api/v1/compliance/deadlines` | Create Deadline |
| GET | `/api/v1/compliance/deadlines` | List Deadlines |
| POST | `/api/v1/compliance/deadlines/evaluate-due` | Evaluate Due Deadlines |
| GET | `/api/v1/compliance/deadlines/events` | List Deadline Events |
| GET | `/api/v1/compliance/deadlines/summary` | Compliance Deadline Summary |
| GET | `/api/v1/compliance/deadlines/{deadline_id}` | Get Deadline |
| PATCH | `/api/v1/compliance/deadlines/{deadline_id}` | Update Deadline |
| POST | `/api/v1/compliance/deadlines/{deadline_id}/cancel` | Cancel Deadline |
| POST | `/api/v1/compliance/deadlines/{deadline_id}/complete` | Complete Deadline |
| POST | `/api/v1/compliance/deadlines/{deadline_id}/waive` | Waive Deadline |
| GET | `/api/v1/compliance/dashboard/control-health` | Control Health |
| GET | `/api/v1/compliance/dashboard/framework-readiness` | Framework Readiness |
| GET | `/api/v1/compliance/dashboard/posture-summary` | Posture Summary |
| GET | `/api/v1/compliance/dashboard/recent-activity` | Recent Activity |
| GET | `/api/v1/compliance/dashboard/risk-heatmap` | Risk Heatmap |
| GET | `/api/v1/compliance/board-scorecard` | List Board Scorecard Snapshots |
| POST | `/api/v1/compliance/board-scorecard/generate` | Generate Board Scorecard Snapshot |
| GET | `/api/v1/compliance/board-scorecard/{snapshot_id}` | Get Board Scorecard Snapshot |
| GET | `/api/v1/compliance/board-scorecard/{snapshot_id}/export` | Export Board Scorecard Snapshot |
| POST | `/api/v1/compliance/business-units` | Create Business Unit |
| GET | `/api/v1/compliance/business-units` | List Business Units |
| POST | `/api/v1/compliance/business-units/tag` | Tag Entity To Business Unit |
| GET | `/api/v1/compliance/business-units/tree` | Get Business Unit Tree |
| GET | `/api/v1/compliance/business-units/{bu_id}` | Get Business Unit |
| PATCH | `/api/v1/compliance/business-units/{bu_id}` | Update Business Unit |
| DELETE | `/api/v1/compliance/business-units/{bu_id}` | Delete Business Unit |
| POST | `/api/v1/compliance/business-units/{bu_id}/deactivate` | Deactivate Business Unit |
| GET | `/api/v1/compliance/business-units/{bu_id}/summary` | Get Business Unit Summary |
| GET | `/api/v1/scoring/methodology` | Scoring Methodology |
| GET | `/api/v1/scoring/snapshots` | List Score Snapshots |
| GET | `/api/v1/scoring/snapshots/delta` | Score Snapshot Delta |
| GET | `/api/v1/scoring/snapshots/latest` | Latest Score Snapshots |
| POST | `/api/v1/scoring/snapshots/materialize` | Materialize Score Snapshots |
| GET | `/api/v1/scoring/snapshots/trends` | Score Snapshot Trends |
| GET | `/api/v1/scoring/summary` | Scoring Summary |
| GET | `/api/v1/dashboard/summary` | Dashboard Summary |

### Database Tables (36)

| Table | Description |
|---|---|
| `applicability_evaluation_results` | Results of applicability evaluations. |
| `applicability_evaluation_runs` | Runs of applicability evaluations. |
| `board_scorecard_snapshots` | Board scorecard snapshots. |
| `business_units` | Business units hierarchy. |
| `compliance_certifications` | Compliance certifications held. |
| `compliance_deadline_events` | Events emitted by deadline processing. |
| `compliance_deadlines` | Compliance deadlines. |
| `cross_framework_obligation_mappings` | Mappings between obligations across frameworks. |
| `framework_content_imports` | Content imports for frameworks. |
| `framework_pack_coverage_reports` | Coverage reports for content packs. |
| `framework_pack_promotion_requests` | Requests to promote pack coverage levels. |
| `framework_pack_review_assignments` | Assignments for framework pack reviews. |
| `framework_pack_review_runs` | Runs of framework pack reviews. |
| `framework_pack_review_signoffs` | Sign-offs on framework pack reviews. |
| `framework_review_assignment_suggestions` | Suggested reviewers for assignments. |
| `framework_review_batch_assignment_items` | Items within a batch assignment run. |
| `framework_review_batch_assignment_runs` | Batch assignment runs for reviews. |
| `framework_review_batch_cancellation_requests` | Cancellation requests for batch runs. |
| `framework_review_escalation_events` | Escalation events for framework reviews. |
| `framework_review_sla_policies` | SLA policies for framework reviews. |
| `framework_reviewer_capacity_policies` | Reviewer capacity policies. |
| `framework_reviewer_workload_snapshots` | Reviewer workload snapshots. |
| `framework_sections` | Sections/clauses within a framework. |
| `framework_versions` | Versions of a framework. |
| `frameworks` | Compliance framework catalog. |
| `obligation_applicability_questions` | Applicability questions for obligations. |
| `obligation_applicability_rules` | Rules determining obligation applicability. |
| `obligation_content_versions` | Versioned text of obligations. |
| `obligation_control_recommendations` | AI-generated control recommendations for obligations. |
| `obligation_control_suggestions` | Suggested controls for obligations. |
| `obligation_evidence_requirements` | Evidence requirements per obligation. |
| `obligations` | Compliance obligations extracted from frameworks. |
| `organization_applicability_answers` | Org answers to applicability questions. |
| `organization_frameworks` | Frameworks activated for an organization. |
| `organization_obligation_states` | Obligation applicability/implementation state per org. |
| `score_snapshots` | Compliance score snapshots. |

---

## Controls & Control Testing

**10 features · 94 endpoints · 19 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Control Register | Create/list/get/update/archive controls, gaps, evidence, failure rate, framework coverage, obligation mapping, associated issues. | 15 |
| 2 | Control Testing | Control test definitions (create/list/get/update/archive/run), test runs, testing summary. | 4 |
| 3 | Control Recommendations | List/get/apply/dismiss control recommendations, generation runs, generate per framework, summary. | 7 |
| 4 | Common Controls | Common control mappings, evidence coverage, evidence reuse, coverage, summary. | 8 |
| 5 | Technical Controls (Agents/Rules/Results) | Technical control agents, rules, results, ingest, summaries. | 15 |
| 6 | Control Exceptions | Create/list/get/approve/reject/revoke control exceptions, expiry check, summary. | 8 |
| 7 | Control Monitoring (Definitions/Results) | Monitoring definitions CRUD, activate/deactivate, record results, results list, summary. | 11 |
| 8 | Control Monitoring Rules | Monitoring rules CRUD, activate/deactivate, evaluate, executions, summary. | 11 |
| 9 | Control Monitoring Alerts | Create/list/get/acknowledge/assign/dismiss/resolve alerts, create issue from alert, summary. | 9 |
| 10 | OSCAL Exports | Create/list/get/download/validate OSCAL exports, summary. | 6 |

### Endpoints (94)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/controls` | List Controls |
| POST | `/api/v1/controls` | Create Control |
| GET | `/api/v1/controls/gaps/summary` | Control Gap Summary |
| GET | `/api/v1/controls/{control_id}` | Get Control Detail |
| PATCH | `/api/v1/controls/{control_id}` | Update Control |
| PATCH | `/api/v1/controls/{control_id}/archive` | Archive Control |
| GET | `/api/v1/controls/{control_id}/associated-issues` | Get Control Associated Issues |
| GET | `/api/v1/controls/{control_id}/evidence` | List Evidence For Control |
| GET | `/api/v1/controls/{control_id}/failure-rate` | Get Control Failure Rate |
| GET | `/api/v1/controls/{control_id}/framework-coverage` | Get Control Framework Coverage |
| POST | `/api/v1/controls/{control_id}/obligations` | Map Control To Obligation |
| DELETE | `/api/v1/controls/{control_id}/obligations/{obligation_id}` | Unmap Control From Obligation |
| GET | `/api/v1/controls/{control_id}/test-runs` | List Control Test Runs |
| POST | `/api/v1/controls/{control_id}/tests` | Create Control Test Definition |
| GET | `/api/v1/controls/{control_id}/tests` | List Control Test Definitions |
| GET | `/api/v1/control-tests/summary` | Control Testing Summary |
| PATCH | `/api/v1/control-tests/{test_id}` | Update Control Test Definition |
| POST | `/api/v1/control-tests/{test_id}/archive` | Archive Control Test Definition |
| POST | `/api/v1/control-tests/{test_id}/run` | Run Control Test |
| GET | `/api/v1/control-recommendations` | List Control Recommendations |
| GET | `/api/v1/control-recommendations/runs` | List Recommendation Generation Runs |
| GET | `/api/v1/control-recommendations/summary` | Control Recommendation Summary |
| GET | `/api/v1/control-recommendations/{recommendation_id}` | Get Control Recommendation Detail |
| POST | `/api/v1/control-recommendations/{recommendation_id}/apply` | Apply Control Recommendation |
| POST | `/api/v1/control-recommendations/{recommendation_id}/dismiss` | Dismiss Control Recommendation |
| POST | `/api/v1/frameworks/{framework_id}/control-recommendations/generate` | Generate Control Recommendations |
| GET | `/api/v1/compliance/common-controls/coverage/{control_id}` | Get Common Control Coverage |
| POST | `/api/v1/compliance/common-controls/evidence-coverage` | Add Common Control Evidence Coverage |
| GET | `/api/v1/compliance/common-controls/evidence-reuse` | Get Evidence Reuse Report |
| POST | `/api/v1/compliance/common-controls/mappings` | Create Common Control Mapping |
| GET | `/api/v1/compliance/common-controls/mappings` | List Common Control Mappings |
| PATCH | `/api/v1/compliance/common-controls/mappings/{mapping_id}` | Update Common Control Mapping |
| DELETE | `/api/v1/compliance/common-controls/mappings/{mapping_id}` | Deactivate Common Control Mapping |
| GET | `/api/v1/compliance/common-controls/summary` | Get Common Controls Summary |
| POST | `/api/v1/compliance/technical-control-agents` | Register Technical Control Agent |
| GET | `/api/v1/compliance/technical-control-agents` | List Technical Control Agents |
| GET | `/api/v1/compliance/technical-control-agents/{agent_id}` | Get Technical Control Agent |
| DELETE | `/api/v1/compliance/technical-control-agents/{agent_id}` | Deregister Technical Control Agent |
| GET | `/api/v1/compliance/technical-control-results` | List Technical Control Results |
| GET | `/api/v1/compliance/technical-control-results/summary` | Technical Control Org Summary |
| GET | `/api/v1/compliance/technical-control-results/{result_id}` | Get Technical Control Result |
| POST | `/api/v1/compliance/technical-control-rules` | Create Technical Control Rule |
| GET | `/api/v1/compliance/technical-control-rules` | List Technical Control Rules |
| GET | `/api/v1/compliance/technical-control-rules/{rule_id}` | Get Technical Control Rule |
| PATCH | `/api/v1/compliance/technical-control-rules/{rule_id}` | Update Technical Control Rule |
| DELETE | `/api/v1/compliance/technical-control-rules/{rule_id}` | Deactivate Technical Control Rule |
| GET | `/api/v1/compliance/technical-control-rules/{rule_id}/results` | List Technical Control Rule Results |
| GET | `/api/v1/compliance/technical-control-rules/{rule_id}/summary` | Technical Control Rule Summary |
| POST | `/api/v1/technical-control-results/ingest` | Ingest Technical Control Result |
| POST | `/api/v1/compliance/control-exceptions` | Create Control Exception |
| GET | `/api/v1/compliance/control-exceptions` | List Control Exceptions |
| POST | `/api/v1/compliance/control-exceptions/check-expiry` | Check Control Exception Expiry |
| GET | `/api/v1/compliance/control-exceptions/summary` | Control Exception Summary |
| GET | `/api/v1/compliance/control-exceptions/{exception_id}` | Get Control Exception |
| POST | `/api/v1/compliance/control-exceptions/{exception_id}/approve` | Approve Control Exception |
| POST | `/api/v1/compliance/control-exceptions/{exception_id}/reject` | Reject Control Exception |
| POST | `/api/v1/compliance/control-exceptions/{exception_id}/revoke` | Revoke Control Exception |
| POST | `/api/v1/compliance/monitoring/definitions` | Create Monitoring Definition |
| GET | `/api/v1/compliance/monitoring/definitions` | List Monitoring Definitions |
| GET | `/api/v1/compliance/monitoring/definitions/{definition_id}` | Get Monitoring Definition |
| PATCH | `/api/v1/compliance/monitoring/definitions/{definition_id}` | Update Monitoring Definition |
| POST | `/api/v1/compliance/monitoring/definitions/{definition_id}/activate` | Activate Monitoring Definition |
| POST | `/api/v1/compliance/monitoring/definitions/{definition_id}/archive` | Archive Monitoring Definition |
| POST | `/api/v1/compliance/monitoring/definitions/{definition_id}/deactivate` | Deactivate Monitoring Definition |
| POST | `/api/v1/compliance/monitoring/definitions/{definition_id}/record-result` | Record Monitoring Result |
| GET | `/api/v1/compliance/monitoring/definitions/{definition_id}/results` | List Definition Results |
| GET | `/api/v1/compliance/monitoring/results` | List Org Monitoring Results |
| GET | `/api/v1/compliance/monitoring/summary` | Monitoring Summary |
| POST | `/api/v1/compliance/monitoring/rules` | Create Monitoring Rule |
| GET | `/api/v1/compliance/monitoring/rules` | List Monitoring Rules |
| POST | `/api/v1/compliance/monitoring/rules/evaluate` | Evaluate Monitoring Rules |
| GET | `/api/v1/compliance/monitoring/rules/executions` | List Monitoring Rule Executions |
| GET | `/api/v1/compliance/monitoring/rules/executions/{execution_id}` | Get Monitoring Rule Execution |
| GET | `/api/v1/compliance/monitoring/rules/summary` | Monitoring Rule Summary |
| GET | `/api/v1/compliance/monitoring/rules/{rule_id}` | Get Monitoring Rule |
| PATCH | `/api/v1/compliance/monitoring/rules/{rule_id}` | Update Monitoring Rule |
| POST | `/api/v1/compliance/monitoring/rules/{rule_id}/activate` | Activate Monitoring Rule |
| POST | `/api/v1/compliance/monitoring/rules/{rule_id}/archive` | Archive Monitoring Rule |
| POST | `/api/v1/compliance/monitoring/rules/{rule_id}/deactivate` | Deactivate Monitoring Rule |
| POST | `/api/v1/compliance/monitoring/alerts` | Create Manual Alert |
| GET | `/api/v1/compliance/monitoring/alerts` | List Alerts |
| GET | `/api/v1/compliance/monitoring/alerts/summary` | Monitoring Alert Summary |
| GET | `/api/v1/compliance/monitoring/alerts/{alert_id}` | Get Alert |
| POST | `/api/v1/compliance/monitoring/alerts/{alert_id}/acknowledge` | Acknowledge Alert |
| POST | `/api/v1/compliance/monitoring/alerts/{alert_id}/assign` | Assign Alert |
| POST | `/api/v1/compliance/monitoring/alerts/{alert_id}/create-issue` | Create Issue From Alert |
| POST | `/api/v1/compliance/monitoring/alerts/{alert_id}/dismiss` | Dismiss Alert |
| POST | `/api/v1/compliance/monitoring/alerts/{alert_id}/resolve` | Resolve Alert |
| POST | `/api/v1/compliance/oscal/export` | Create And Build Export |
| GET | `/api/v1/compliance/oscal/exports` | List Exports |
| GET | `/api/v1/compliance/oscal/exports/{job_id}` | Get Export Detail |
| GET | `/api/v1/compliance/oscal/exports/{job_id}/download` | Download Export |
| GET | `/api/v1/compliance/oscal/exports/{job_id}/validate` | Validate Export |
| GET | `/api/v1/compliance/oscal/summary` | Oscal Summary |

### Database Tables (19)

| Table | Description |
|---|---|
| `common_control_evidence_coverage` | Evidence coverage for common controls. |
| `common_control_mappings` | Mappings of common controls across frameworks. |
| `control_exception_approvals` | Approval decisions on control exceptions. |
| `control_exceptions` | Control exceptions with approval workflow. |
| `control_monitoring_alerts` | Alerts raised by control monitoring. |
| `control_monitoring_definitions` | Continuous control monitoring definitions. |
| `control_monitoring_results` | Results of control monitoring checks. |
| `control_monitoring_rule_executions` | Executions of monitoring rules. |
| `control_monitoring_rules` | Rules driving control monitoring. |
| `control_obligation_mappings` | Mappings between controls and obligations. |
| `control_test_definitions` | Control test definitions. |
| `control_test_runs` | Executions of control tests. |
| `controls` | Compliance controls register. |
| `openscap_rule_mappings` | OpenSCAP rule mappings. |
| `oscal_export_jobs` | OSCAL export jobs. |
| `recommendation_generation_runs` | Runs generating control recommendations. |
| `technical_control_agents` | Registered technical control agents. |
| `technical_control_results` | Results from technical control evaluations. |
| `technical_control_rules` | Technical control rules (config checks). |

---

## Audit & Assurance

**10 features · 91 endpoints · 13 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Audit Engagements | Create/list/get/update/delete engagements, transition, dashboard. | 7 |
| 2 | Audit Schedules | Create/list/get/update/delete schedules, history, link engagement, status, reminder sweep. | 9 |
| 3 | Audit Findings | Create/list/get/update/delete findings, transition, bulk-transition, create issue, link risk, accept-risk/close/resolve/remediation, summaries. | 18 |
| 4 | Auditor Portal | Portal invitations, controls, evidence, reports, me. | 8 |
| 5 | PBC (Provided By Client) Items | Create/list/get/update/delete PBC items, accept/reject/submit, summaries. | 11 |
| 6 | PBC Requests (audit-scoped) | List/bulk-create/get PBC requests, accept/reject/submit. | 6 |
| 7 | Evidence Items | Create/list/get/update/archive evidence, link/unlink to controls, review, readiness summary. | 23 |
| 8 | Evidence Packages | Create/list/get/delete/archive/assemble/export packages, items, manifest, per-engagement. | 0 |
| 9 | Audit Evidence Package Export | Export audit evidence package. | 0 |
| 10 | Recertification | Recertification policies, due controls/evidence, run, runs, summary. | 9 |

### Endpoints (91)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/compliance/audit-engagements` | Create Engagement |
| GET | `/api/v1/compliance/audit-engagements` | List Engagements |
| GET | `/api/v1/compliance/audit-engagements/dashboard` | Engagement Dashboard |
| GET | `/api/v1/compliance/audit-engagements/{engagement_id}` | Get Engagement |
| PATCH | `/api/v1/compliance/audit-engagements/{engagement_id}` | Update Engagement |
| DELETE | `/api/v1/compliance/audit-engagements/{engagement_id}` | Delete Engagement |
| POST | `/api/v1/compliance/audit-engagements/{engagement_id}/transition` | Transition Engagement Status |
| POST | `/api/v1/compliance/audit-schedules` | Create Schedule |
| GET | `/api/v1/compliance/audit-schedules` | List Schedules |
| POST | `/api/v1/compliance/audit-schedules/trigger-reminder-sweep` | Trigger Schedule Reminder Sweep |
| GET | `/api/v1/compliance/audit-schedules/{schedule_id}` | Get Schedule |
| PATCH | `/api/v1/compliance/audit-schedules/{schedule_id}` | Update Schedule |
| DELETE | `/api/v1/compliance/audit-schedules/{schedule_id}` | Delete Schedule |
| GET | `/api/v1/compliance/audit-schedules/{schedule_id}/history` | Get Schedule History |
| POST | `/api/v1/compliance/audit-schedules/{schedule_id}/link-engagement` | Link Schedule Engagement |
| POST | `/api/v1/compliance/audit-schedules/{schedule_id}/status` | Set Schedule Status |
| POST | `/api/v1/compliance/audit-findings` | Create Finding |
| GET | `/api/v1/compliance/audit-findings` | List Findings |
| POST | `/api/v1/compliance/audit-findings/bulk-transition` | Bulk Transition Findings |
| GET | `/api/v1/compliance/audit-findings/engagement/{engagement_id}` | List Findings For Engagement |
| GET | `/api/v1/compliance/audit-findings/engagement/{engagement_id}/summary` | Finding Summary For Engagement |
| GET | `/api/v1/compliance/audit-findings/summary` | Get Finding Summary |
| GET | `/api/v1/compliance/audit-findings/{finding_id}` | Get Finding |
| PATCH | `/api/v1/compliance/audit-findings/{finding_id}` | Update Finding |
| DELETE | `/api/v1/compliance/audit-findings/{finding_id}` | Delete Finding |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/accept-risk` | Accept Finding Risk |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/close` | Close Finding |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/create-issue` | Create Issue From Finding |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/link-risk` | Link Finding To Risk |
| PATCH | `/api/v1/compliance/audit-findings/{finding_id}/remediation` | Update Finding Remediation |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/resolve` | Resolve Finding |
| POST | `/api/v1/compliance/audit-findings/{finding_id}/transition` | Transition Finding Status |
| POST | `/api/v1/compliance/audits/{audit_id}/findings` | Create Audit Finding |
| GET | `/api/v1/compliance/audits/{audit_id}/findings` | List Audit Findings |
| GET | `/api/v1/audit-portal/controls` | Portal Controls |
| GET | `/api/v1/audit-portal/evidence` | Portal Evidence |
| POST | `/api/v1/audit-portal/invitations` | Create Auditor Invitation |
| GET | `/api/v1/audit-portal/invitations` | List Invitations |
| GET | `/api/v1/audit-portal/invitations/{invitation_id}` | Get Invitation |
| POST | `/api/v1/audit-portal/invitations/{invitation_id}/revoke` | Revoke Invitation |
| GET | `/api/v1/audit-portal/me` | Portal Me |
| GET | `/api/v1/audit-portal/reports` | Portal Reports |
| POST | `/api/v1/compliance/pbc-items` | Create Pbc Item |
| GET | `/api/v1/compliance/pbc-items` | List Pbc Items |
| GET | `/api/v1/compliance/pbc-items/engagement/{engagement_id}` | List Pbc Items For Engagement |
| GET | `/api/v1/compliance/pbc-items/engagement/{engagement_id}/summary` | Get Pbc Summary For Engagement |
| GET | `/api/v1/compliance/pbc-items/summary` | Get Org Pbc Summary |
| GET | `/api/v1/compliance/pbc-items/{item_id}` | Get Pbc Item |
| PATCH | `/api/v1/compliance/pbc-items/{item_id}` | Update Pbc Item |
| DELETE | `/api/v1/compliance/pbc-items/{item_id}` | Delete Pbc Item |
| POST | `/api/v1/compliance/pbc-items/{item_id}/accept` | Accept Pbc Item |
| POST | `/api/v1/compliance/pbc-items/{item_id}/reject` | Reject Pbc Item |
| POST | `/api/v1/compliance/pbc-items/{item_id}/submit` | Submit Pbc Item |
| GET | `/api/v1/compliance/audits/{audit_id}/pbc-requests` | List Pbc Requests For Audit |
| POST | `/api/v1/compliance/audits/{audit_id}/pbc-requests/bulk` | Bulk Create Pbc Requests |
| GET | `/api/v1/compliance/pbc-requests/{request_id}` | Get Pbc Request |
| POST | `/api/v1/compliance/pbc-requests/{request_id}/accept` | Accept Pbc Request |
| POST | `/api/v1/compliance/pbc-requests/{request_id}/reject` | Reject Pbc Request |
| POST | `/api/v1/compliance/pbc-requests/{request_id}/submit` | Submit Pbc Request |
| GET | `/api/v1/compliance/audits/{audit_id}/evidence-package/export` | Export Audit Evidence Package |
| POST | `/api/v1/compliance/evidence-packages` | Create Package |
| GET | `/api/v1/compliance/evidence-packages` | List Packages |
| GET | `/api/v1/compliance/evidence-packages/engagement/{engagement_id}` | List Packages For Engagement |
| GET | `/api/v1/compliance/evidence-packages/{package_id}` | Get Package |
| DELETE | `/api/v1/compliance/evidence-packages/{package_id}` | Delete Package |
| POST | `/api/v1/compliance/evidence-packages/{package_id}/archive` | Archive Package |
| POST | `/api/v1/compliance/evidence-packages/{package_id}/assemble` | Assemble Package |
| POST | `/api/v1/compliance/evidence-packages/{package_id}/export` | Export Package |
| POST | `/api/v1/compliance/evidence-packages/{package_id}/items` | Add Package Item |
| DELETE | `/api/v1/compliance/evidence-packages/{package_id}/items/{item_id}` | Remove Package Item |
| GET | `/api/v1/compliance/evidence-packages/{package_id}/manifest` | Get Package Manifest |
| GET | `/api/v1/evidence` | List Evidence |
| POST | `/api/v1/evidence` | Create Evidence |
| GET | `/api/v1/evidence/readiness/summary` | Readiness Summary |
| GET | `/api/v1/evidence/{evidence_id}` | Get Evidence Detail |
| PATCH | `/api/v1/evidence/{evidence_id}` | Update Evidence |
| PATCH | `/api/v1/evidence/{evidence_id}/archive` | Archive Evidence |
| POST | `/api/v1/evidence/{evidence_id}/controls` | Link Evidence To Control |
| DELETE | `/api/v1/evidence/{evidence_id}/controls/{control_id}` | Unlink Evidence From Control |
| POST | `/api/v1/evidence/{evidence_id}/review` | Review Evidence |
| GET | `/api/v1/recertification/evidence/due` | Due Evidence |
| POST | `/api/v1/recertification/evidence/run` | Run Evidence |
| GET | `/api/v1/recertification/controls/due` | Due Controls |
| POST | `/api/v1/recertification/controls/run` | Run Controls |
| POST | `/api/v1/recertification/policies` | Create Policy |
| GET | `/api/v1/recertification/policies` | List Policies |
| PATCH | `/api/v1/recertification/policies/{policy_id}` | Update Policy |
| POST | `/api/v1/recertification/policies/{policy_id}/archive` | Archive Policy |
| GET | `/api/v1/recertification/runs` | List Runs |
| GET | `/api/v1/recertification/runs/{run_id}` | Run Detail |
| GET | `/api/v1/recertification/summary` | Recertification Summary |

### Database Tables (13)

| Table | Description |
|---|---|
| `audit_engagements` | Audit engagements. |
| `audit_findings` | Audit findings. |
| `audit_schedules` | Recurring audit schedules. |
| `auditor_portal_invitations` | Auditor portal invitations. |
| `evidence_control_links` | Links between evidence and controls. |
| `evidence_items` | Evidence items repository. |
| `evidence_package_items` | Items within an evidence package. |
| `evidence_packages` | Assembled evidence packages. |
| `evidence_recertification_policies` | Policies governing evidence recertification. |
| `pbc_items` | Provided-By-Client items. |
| `pbc_requests` | PBC requests (audit-scoped). |
| `recertification_action_logs` | Action logs for recertification runs. |
| `recertification_runs` | Runs of evidence/control recertification. |

---

## TPRM / Third-Party Risk

**14 features · 102 endpoints · 20 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Vendor Register | Create/list/get/update/archive vendors, summary. | 28 |
| 2 | Vendor Assessments | Create/list/get/update/cancel/complete/start assessments, questions, answers, summary. | 0 |
| 3 | Vendor Risk Scores | Create/list/get/latest vendor risk scores. | 0 |
| 4 | Vendor Control Links | Link/unlink/list controls to vendor, links summary. | 0 |
| 5 | Vendor AI Model Assessments | Create/list vendor AI model assessments. | 0 |
| 6 | Vendor Mitigation Cases | Create/list/get/delete cases, actions (accept/reject/submit-evidence), escalate, transition, summary. | 12 |
| 7 | Questionnaire Templates | List/create/get/delete/clone templates, sections, questions. | 7 |
| 8 | Questionnaire Responses | Create/list/get responses, submit/bulk answers, score breakdown, transition, vendor risk. | 8 |
| 9 | Questionnaire Scoring Rules | List/create/update/deactivate scoring rules, per-template rules. | 5 |
| 10 | Inbound Questionnaires | Create/list/get/delete inbound sessions, items (add/bulk/draft/review/mark-sent), complete, draft-all, metrics, summary. | 15 |
| 11 | Subprocessors | Create/list/get/update/delete subprocessors, transfers, DPA status, mark-reviewed, GDPR dashboard. | 10 |
| 12 | Customer Commitments | Create/list/get/update/delete commitments, fulfill, trigger, waive, notifications, dashboard. | 10 |
| 13 | DORA ICT Register | Create/list/get/update/delete ICT third-party register entries, report. | 6 |
| 14 | Compliance Contract Registry | Compliance contract registry view. | 1 |

### Endpoints (102)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/compliance/vendors` | Create Vendor |
| GET | `/api/v1/compliance/vendors` | List Vendors |
| GET | `/api/v1/compliance/vendors/summary` | Vendors Summary |
| GET | `/api/v1/compliance/vendors/{vendor_id}` | Get Vendor |
| PATCH | `/api/v1/compliance/vendors/{vendor_id}` | Update Vendor |
| POST | `/api/v1/compliance/vendors/{vendor_id}/ai-model-assessments` | Create Vendor Ai Model Assessment |
| GET | `/api/v1/compliance/vendors/{vendor_id}/ai-model-assessments` | List Vendor Ai Model Assessments |
| POST | `/api/v1/compliance/vendors/{vendor_id}/archive` | Archive Vendor |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments` | Create Vendor Assessment |
| GET | `/api/v1/compliance/vendors/{vendor_id}/assessments` | List Vendor Assessments |
| GET | `/api/v1/compliance/vendors/{vendor_id}/assessments/summary` | Vendor Assessment Summary |
| GET | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}` | Get Vendor Assessment |
| PATCH | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}` | Update Vendor Assessment |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/cancel` | Cancel Vendor Assessment |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/complete` | Complete Vendor Assessment |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/questions` | Create Vendor Assessment Question |
| GET | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/questions` | List Vendor Assessment Questions |
| PATCH | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/questions/{question_id}` | Update Vendor Assessment Question |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/questions/{question_id}/answer` | Answer Vendor Assessment Question |
| POST | `/api/v1/compliance/vendors/{vendor_id}/assessments/{assessment_id}/start` | Start Vendor Assessment |
| POST | `/api/v1/compliance/vendors/{vendor_id}/links/controls` | Link Control To Vendor |
| GET | `/api/v1/compliance/vendors/{vendor_id}/links/controls` | List Vendor Control Links |
| POST | `/api/v1/compliance/vendors/{vendor_id}/links/controls/{link_id}/unlink` | Unlink Control From Vendor |
| GET | `/api/v1/compliance/vendors/{vendor_id}/links/summary` | Vendor Links Summary |
| POST | `/api/v1/compliance/vendors/{vendor_id}/risk-scores` | Create Vendor Risk Score |
| GET | `/api/v1/compliance/vendors/{vendor_id}/risk-scores` | List Vendor Risk Scores |
| GET | `/api/v1/compliance/vendors/{vendor_id}/risk-scores/latest` | Get Latest Vendor Risk Score |
| GET | `/api/v1/compliance/vendors/{vendor_id}/risk-scores/{score_id}` | Get Vendor Risk Score |
| POST | `/api/v1/compliance/vendor-mitigation/cases` | Create Case |
| GET | `/api/v1/compliance/vendor-mitigation/cases` | List Cases |
| GET | `/api/v1/compliance/vendor-mitigation/cases/summary` | Mitigation Summary |
| GET | `/api/v1/compliance/vendor-mitigation/cases/{case_id}` | Get Case |
| DELETE | `/api/v1/compliance/vendor-mitigation/cases/{case_id}` | Delete Case |
| GET | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/actions` | List Actions |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/actions` | Add Action |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/actions/{action_id}/accept` | Accept Action |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/actions/{action_id}/reject` | Reject Action |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/actions/{action_id}/submit-evidence` | Submit Action Evidence |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/escalate` | Escalate Case |
| POST | `/api/v1/compliance/vendor-mitigation/cases/{case_id}/transition` | Transition Case |
| GET | `/api/v1/compliance/questionnaire-templates` | List Questionnaire Templates |
| POST | `/api/v1/compliance/questionnaire-templates` | Create Custom Questionnaire Template |
| GET | `/api/v1/compliance/questionnaire-templates/{template_id}` | Get Questionnaire Template |
| DELETE | `/api/v1/compliance/questionnaire-templates/{template_id}` | Delete Questionnaire Template |
| POST | `/api/v1/compliance/questionnaire-templates/{template_id}/clone` | Clone Questionnaire Template |
| POST | `/api/v1/compliance/questionnaire-templates/{template_id}/sections` | Add Questionnaire Template Section |
| POST | `/api/v1/compliance/questionnaire-templates/{template_id}/sections/{section_id}/questions` | Add Questionnaire Template Question |
| POST | `/api/v1/compliance/questionnaire-responses` | Create Questionnaire Response |
| GET | `/api/v1/compliance/questionnaire-responses` | List Questionnaire Responses |
| GET | `/api/v1/compliance/questionnaire-responses/vendor/{vendor_id}/risk` | Vendor Questionnaire Risk |
| GET | `/api/v1/compliance/questionnaire-responses/{response_id}` | Get Questionnaire Response |
| POST | `/api/v1/compliance/questionnaire-responses/{response_id}/answers` | Submit Questionnaire Answer |
| POST | `/api/v1/compliance/questionnaire-responses/{response_id}/answers/bulk` | Bulk Submit Questionnaire Answers |
| GET | `/api/v1/compliance/questionnaire-responses/{response_id}/score` | Questionnaire Score Breakdown |
| POST | `/api/v1/compliance/questionnaire-responses/{response_id}/transition` | Transition Questionnaire Response |
| GET | `/api/v1/compliance/scoring-rules` | List Scoring Rules |
| POST | `/api/v1/compliance/scoring-rules` | Create Scoring Rule |
| GET | `/api/v1/compliance/scoring-rules/template/{template_id}` | List Template Scoring Rules |
| PATCH | `/api/v1/compliance/scoring-rules/{rule_id}` | Update Scoring Rule |
| DELETE | `/api/v1/compliance/scoring-rules/{rule_id}` | Deactivate Scoring Rule |
| POST | `/api/v1/compliance/inbound-questionnaires` | Create Inbound Session |
| GET | `/api/v1/compliance/inbound-questionnaires` | List Inbound Sessions |
| GET | `/api/v1/compliance/inbound-questionnaires/response-time-metrics` | Inbound Response Time Metrics |
| GET | `/api/v1/compliance/inbound-questionnaires/{session_id}` | Get Inbound Session |
| DELETE | `/api/v1/compliance/inbound-questionnaires/{session_id}` | Soft Delete Inbound Session |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/complete` | Complete Inbound Session |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/draft-all` | Draft All Inbound Items |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/items` | Add Inbound Item |
| GET | `/api/v1/compliance/inbound-questionnaires/{session_id}/items` | List Inbound Items |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/items/bulk` | Bulk Add Inbound Items |
| GET | `/api/v1/compliance/inbound-questionnaires/{session_id}/items/{item_id}` | Get Inbound Item |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/items/{item_id}/draft` | Draft Inbound Item |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/items/{item_id}/mark-sent` | Mark Inbound Item Sent |
| POST | `/api/v1/compliance/inbound-questionnaires/{session_id}/items/{item_id}/review` | Review Inbound Item |
| GET | `/api/v1/compliance/inbound-questionnaires/{session_id}/summary` | Inbound Session Summary |
| POST | `/api/v1/compliance/subprocessors` | Create Subprocessor |
| GET | `/api/v1/compliance/subprocessors` | List Subprocessors |
| GET | `/api/v1/compliance/subprocessors/gdpr-dashboard` | Gdpr Dashboard |
| GET | `/api/v1/compliance/subprocessors/{subprocessor_id}` | Get Subprocessor |
| PATCH | `/api/v1/compliance/subprocessors/{subprocessor_id}` | Update Subprocessor |
| DELETE | `/api/v1/compliance/subprocessors/{subprocessor_id}` | Delete Subprocessor |
| POST | `/api/v1/compliance/subprocessors/{subprocessor_id}/dpa-status` | Update Subprocessor Dpa Status |
| POST | `/api/v1/compliance/subprocessors/{subprocessor_id}/mark-reviewed` | Mark Subprocessor Reviewed |
| POST | `/api/v1/compliance/subprocessors/{subprocessor_id}/transfers` | Add Subprocessor Transfer |
| GET | `/api/v1/compliance/subprocessors/{subprocessor_id}/transfers` | List Subprocessor Transfers |
| POST | `/api/v1/compliance/customer-commitments` | Create Customer Commitment |
| GET | `/api/v1/compliance/customer-commitments` | List Customer Commitments |
| GET | `/api/v1/compliance/customer-commitments/dashboard` | Customer Commitment Dashboard |
| GET | `/api/v1/compliance/customer-commitments/{commitment_id}` | Get Customer Commitment |
| PATCH | `/api/v1/compliance/customer-commitments/{commitment_id}` | Update Customer Commitment |
| DELETE | `/api/v1/compliance/customer-commitments/{commitment_id}` | Delete Customer Commitment |
| POST | `/api/v1/compliance/customer-commitments/{commitment_id}/fulfill` | Fulfill Customer Commitment |
| GET | `/api/v1/compliance/customer-commitments/{commitment_id}/notifications` | List Commitment Notifications |
| POST | `/api/v1/compliance/customer-commitments/{commitment_id}/trigger` | Trigger Customer Commitment |
| POST | `/api/v1/compliance/customer-commitments/{commitment_id}/waive` | Waive Customer Commitment |
| POST | `/api/v1/compliance/dora/ict-register` | Create Ict Register Entry |
| GET | `/api/v1/compliance/dora/ict-register` | List Ict Register |
| GET | `/api/v1/compliance/dora/ict-register/report` | Get Ict Register Report |
| GET | `/api/v1/compliance/dora/ict-register/{entry_id}` | Get Ict Register Entry |
| PATCH | `/api/v1/compliance/dora/ict-register/{entry_id}` | Update Ict Register Entry |
| DELETE | `/api/v1/compliance/dora/ict-register/{entry_id}` | Soft Delete Ict Register Entry |
| GET | `/api/v1/compliance/contracts` | Get Compliance Contract Registry |

### Database Tables (20)

| Table | Description |
|---|---|
| `commitment_notification_log` | Notification log for customer commitments. |
| `customer_commitments` | Customer commitments/SLAs. |
| `dora_ict_register` | DORA ICT third-party register. |
| `inbound_questionnaire_items` | Items within an inbound questionnaire session. |
| `inbound_questionnaire_sessions` | Inbound (customer) questionnaire sessions. |
| `questionnaire_scoring_rules` | Scoring rules for questionnaire answers. |
| `questionnaire_template_questions` | Questions within questionnaire templates. |
| `questionnaire_template_sections` | Sections within questionnaire templates. |
| `questionnaire_templates` | Questionnaire templates. |
| `subprocessor_data_transfers` | Data transfers by subprocessors. |
| `subprocessors` | Subprocessors register. |
| `vendor_assessment_questions` | Questions within a vendor assessment. |
| `vendor_assessments` | Vendor assessments. |
| `vendor_control_links` | Links between vendors and controls. |
| `vendor_mitigation_actions` | Actions within a vendor mitigation case. |
| `vendor_mitigation_cases` | Vendor remediation/mitigation cases. |
| `vendor_questionnaire_answers` | Answers within a vendor questionnaire response. |
| `vendor_questionnaire_responses` | Vendor questionnaire responses. |
| `vendor_risk_scores` | Risk scores computed for vendors. |
| `vendors` | Vendor register. |

---

## Issues & Incident Management

**8 features · 53 endpoints · 12 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Issue Management | Create/list/get/update/delete issues, assign, transition, dashboard, SLA breaches/status, transitions. | 27 |
| 2 | Issue Classifications & RCA | Auto/override issue classification, RCA create/get/update/review, suggestions. | 2 |
| 3 | Issue–Control & Issue–Policy Links | Link/unlink/list issue controls and policy links. | 0 |
| 4 | Issue SLA Policies | List/create-or-update SLA policies, trigger breach check. | 3 |
| 5 | Issue Settings | Get/update org issue settings (e.g. require RCA before close). | 2 |
| 6 | Breach Notifications | Create/list/get/close breaches, Article 33 drafts, regulator/subject notifications, privacy fields. | 10 |
| 7 | Escalation Policies | Create/list/get/update/delete escalation policies, evaluate, events, deactivate. | 8 |
| 8 | Incident Analytics | Incidents by category analytics. | 1 |

### Endpoints (53)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/compliance/issues` | Create Issue |
| GET | `/api/v1/compliance/issues` | List Issues |
| GET | `/api/v1/compliance/issues/dashboard` | Issue Dashboard |
| GET | `/api/v1/compliance/issues/sla-breaches` | Get Sla Breaches |
| GET | `/api/v1/compliance/issues/{issue_id}` | Get Issue |
| PATCH | `/api/v1/compliance/issues/{issue_id}` | Update Issue |
| DELETE | `/api/v1/compliance/issues/{issue_id}` | Delete Issue |
| POST | `/api/v1/compliance/issues/{issue_id}/assign` | Assign Issue |
| POST | `/api/v1/compliance/issues/{issue_id}/breach-notification` | Create Issue Breach Notification |
| POST | `/api/v1/compliance/issues/{issue_id}/classification` | Auto Classify Issue |
| PATCH | `/api/v1/compliance/issues/{issue_id}/classification` | Override Issue Classification |
| GET | `/api/v1/compliance/issues/{issue_id}/classification` | Get Issue Classification |
| POST | `/api/v1/compliance/issues/{issue_id}/control-links` | Link Issue To Control |
| GET | `/api/v1/compliance/issues/{issue_id}/control-links` | Get Issue Control Links |
| DELETE | `/api/v1/compliance/issues/{issue_id}/control-links/{control_id}` | Unlink Issue From Control |
| POST | `/api/v1/compliance/issues/{issue_id}/generate-suggestions` | Generate Issue Suggestions |
| GET | `/api/v1/compliance/issues/{issue_id}/policy-links` | Get Issue Policy Links |
| POST | `/api/v1/compliance/issues/{issue_id}/policy-links` | Link Issue To Policy |
| DELETE | `/api/v1/compliance/issues/{issue_id}/policy-links/{policy_id}` | Unlink Issue From Policy |
| POST | `/api/v1/compliance/issues/{issue_id}/rca` | Create Issue Rca |
| GET | `/api/v1/compliance/issues/{issue_id}/rca` | Get Issue Rca |
| PATCH | `/api/v1/compliance/issues/{issue_id}/rca` | Update Issue Rca |
| POST | `/api/v1/compliance/issues/{issue_id}/rca/review` | Review Issue Rca |
| GET | `/api/v1/compliance/issues/{issue_id}/sla-status` | Get Issue Sla Status |
| GET | `/api/v1/compliance/issues/{issue_id}/suggestions` | List Issue Suggestions |
| POST | `/api/v1/compliance/issues/{issue_id}/transition` | Transition Issue |
| GET | `/api/v1/compliance/issues/{issue_id}/transitions` | Get Issue Transitions |
| POST | `/api/v1/compliance/remediation-suggestions/{suggestion_id}/apply` | Apply Suggestion |
| POST | `/api/v1/compliance/remediation-suggestions/{suggestion_id}/dismiss` | Dismiss Suggestion |
| GET | `/api/v1/compliance/sla-policies` | List Sla Policies |
| POST | `/api/v1/compliance/sla-policies` | Create Or Update Sla Policy |
| GET | `/api/v1/compliance/sla-policies/trigger-breach-check` | Trigger Breach Check |
| GET | `/api/v1/compliance/issue-settings` | Get Org Issue Settings |
| PATCH | `/api/v1/compliance/issue-settings` | Update Org Issue Settings |
| POST | `/api/v1/compliance/breach-notifications` | Create Breach Notification |
| GET | `/api/v1/compliance/breach-notifications` | List Breaches |
| GET | `/api/v1/compliance/breach-notifications/{breach_id}` | Get Breach |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/close` | Close Breach |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/generate-article33-draft` | Generate Article33 Draft |
| PATCH | `/api/v1/compliance/breach-notifications/{breach_id}/privacy-fields` | Update Privacy Fields |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/record-article33-sent` | Record Article33 Sent |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/record-regulator-notification` | Record Regulator Notification |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/record-subject-notification` | Record Subject Notification |
| POST | `/api/v1/compliance/breach-notifications/{breach_id}/record-subjects-notified` | Record Subjects Notified Privacy |
| POST | `/api/v1/compliance/escalation-policies` | Create Policy |
| GET | `/api/v1/compliance/escalation-policies` | List Policies |
| POST | `/api/v1/compliance/escalation-policies/evaluate` | Evaluate Policies |
| GET | `/api/v1/compliance/escalation-policies/events` | List Escalation Events |
| GET | `/api/v1/compliance/escalation-policies/{policy_id}` | Get Policy |
| PATCH | `/api/v1/compliance/escalation-policies/{policy_id}` | Update Policy |
| DELETE | `/api/v1/compliance/escalation-policies/{policy_id}` | Delete Policy |
| POST | `/api/v1/compliance/escalation-policies/{policy_id}/deactivate` | Deactivate Policy |
| GET | `/api/v1/compliance/incidents/by-category` | Incidents By Category |

### Database Tables (12)

| Table | Description |
|---|---|
| `breach_notifications` | Personal data breach notifications. |
| `escalation_events` | Escalation events raised. |
| `escalation_policies` | Escalation policies. |
| `incident_classifications` | Incident classifications. |
| `issue_control_links` | Links between issues and controls. |
| `issue_policy_links` | Links between issues and policies. |
| `issue_sla_policies` | SLA policies for issues. |
| `issue_sla_tracking` | SLA tracking for issues. |
| `issue_transitions` | Status transitions for issues. |
| `issues` | Issues/incidents register. |
| `remediation_suggestions` | Remediation suggestions for issues. |
| `root_cause_analyses` | Root cause analyses for issues. |

---

## Reports, Exports & Dashboards

**6 features · 50 endpoints · 8 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Reports | List/get/archive reports, generate, executive narrative, board scorecard, framework readiness/coverage matrix, regulatory reports, export PDF/DOCX, provenance, summary. | 23 |
| 2 | Report Sharing | Create/list/revoke share links, access/verify shared reports. | 0 |
| 3 | Custom Report Templates | Create/list/get/update/delete templates, generate custom reports. | 6 |
| 4 | Export Jobs | Create/list/get/archive/cancel/run export jobs, attestations, legal hold, manifest, package, retention, verify, verification history, summary. | 15 |
| 5 | Entity Exports | Export individual control/policy/risk/vendor, framework coverage & posture report exports, export settings. | 6 |
| 6 | Regulatory Reports (CCPA) | CCPA annual regulatory report. | 0 |

### Endpoints (50)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/compliance/reports/framework-coverage/export` | Export Framework Coverage Report |
| GET | `/api/v1/compliance/reports/posture/export` | Export Posture Report |
| GET | `/api/v1/compliance/reports/regulatory/ccpa` | Get Ccpa Annual Report |
| GET | `/api/v1/reports` | List Reports |
| POST | `/api/v1/reports/board-scorecard` | Generate Board Scorecard |
| POST | `/api/v1/reports/executive-narrative` | Generate Executive Narrative |
| GET | `/api/v1/reports/framework-coverage-matrix` | Get Framework Coverage Matrix |
| POST | `/api/v1/reports/framework-coverage-matrix/export-pdf` | Export Framework Coverage Matrix Pdf |
| GET | `/api/v1/reports/frameworks/{framework_id}/readiness` | Framework Readiness Data |
| POST | `/api/v1/reports/generate` | Generate Report |
| GET | `/api/v1/reports/regulatory/available-types` | List Available Regulatory Report Types |
| POST | `/api/v1/reports/regulatory/{report_type}` | Generate Regulatory Report |
| POST | `/api/v1/reports/share` | Create Share Link |
| GET | `/api/v1/reports/shared-links` | List Share Links |
| DELETE | `/api/v1/reports/shared-links/{link_id}` | Revoke Share Link |
| GET | `/api/v1/reports/shared/{token}` | Access Shared Report |
| POST | `/api/v1/reports/shared/{token}/verify` | Verify Share Password |
| GET | `/api/v1/reports/summary` | Reports Summary |
| GET | `/api/v1/reports/{report_id}` | Report Detail |
| POST | `/api/v1/reports/{report_id}/archive` | Archive Report |
| POST | `/api/v1/reports/{report_id}/export/docx` | Export Report Docx |
| POST | `/api/v1/reports/{report_id}/export/pdf` | Export Report Pdf |
| GET | `/api/v1/reports/{report_id}/provenance` | Report Provenance |
| POST | `/api/v1/compliance/custom-report-templates` | Create Custom Report Template |
| GET | `/api/v1/compliance/custom-report-templates` | List Custom Report Templates |
| GET | `/api/v1/compliance/custom-report-templates/{template_id}` | Get Custom Report Template |
| PATCH | `/api/v1/compliance/custom-report-templates/{template_id}` | Update Custom Report Template |
| DELETE | `/api/v1/compliance/custom-report-templates/{template_id}` | Delete Custom Report Template |
| POST | `/api/v1/compliance/custom-report-templates/{template_id}/generate` | Generate Custom Report |
| POST | `/api/v1/exports/jobs` | Create Export Job |
| GET | `/api/v1/exports/jobs` | List Export Jobs |
| GET | `/api/v1/exports/jobs/{export_job_id}` | Get Export Job Detail |
| POST | `/api/v1/exports/jobs/{export_job_id}/archive` | Archive Export Job |
| POST | `/api/v1/exports/jobs/{export_job_id}/attestations` | Create Export Attestation |
| GET | `/api/v1/exports/jobs/{export_job_id}/attestations` | List Export Attestations |
| POST | `/api/v1/exports/jobs/{export_job_id}/cancel` | Cancel Export Job |
| POST | `/api/v1/exports/jobs/{export_job_id}/legal-hold` | Set Export Legal Hold |
| GET | `/api/v1/exports/jobs/{export_job_id}/manifest` | Get Export Manifest |
| GET | `/api/v1/exports/jobs/{export_job_id}/package` | Get Export Package |
| POST | `/api/v1/exports/jobs/{export_job_id}/retention/apply` | Apply Retention Policy To Export |
| POST | `/api/v1/exports/jobs/{export_job_id}/run` | Run Export Job |
| GET | `/api/v1/exports/jobs/{export_job_id}/verification-history` | Export Verification History |
| POST | `/api/v1/exports/jobs/{export_job_id}/verify` | Verify Export Job |
| GET | `/api/v1/exports/summary` | Export Summary |
| GET | `/api/v1/compliance/controls/{control_id}/export` | Export Control |
| GET | `/api/v1/compliance/policies/{policy_id}/export` | Export Policy |
| GET | `/api/v1/organizations/export-settings` | Get Export Settings |
| PUT | `/api/v1/organizations/export-settings` | Upsert Export Settings |
| GET | `/api/v1/risks/{risk_id}/export` | Export Risk |
| GET | `/api/v1/vendors/{vendor_id}/export` | Export Vendor |

### Database Tables (8)

| Table | Description |
|---|---|
| `compliance_report_sections` | Sections within compliance reports. |
| `compliance_reports` | Generated compliance reports. |
| `custom_report_templates` | Custom report templates. |
| `export_attestations` | Attestations on export packages. |
| `export_job_events` | Events for export jobs. |
| `export_jobs` | Export jobs (signed packages). |
| `organization_export_settings` | Org export branding/settings. |
| `shared_report_links` | Shared report links. |

---

## Governance Automation

**5 features · 45 endpoints · 24 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Automation Rules & Executions | Create/list/get/update/archive/run/dry-run rules, schedules, versions, executions, run-scan, due schedules, summary. | 16 |
| 2 | Governance Override Requests | Create/list/get/approve/reject/cancel/execute overrides, from-template, expire, routing, summary. | 11 |
| 3 | Governance Override Templates | Create/list/get/update/archive templates, versions, summary. | 7 |
| 4 | Retention Governance | Governance retention policies CRUD, evaluate, summary. | 6 |
| 5 | Copilot Inline Suggestions | Generate/apply/dismiss inline suggestions, refine drafts, draft revisions. | 5 |

### Endpoints (45)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/automation/executions` | List Executions |
| GET | `/api/v1/automation/executions/{execution_id}` | Get Execution Detail |
| GET | `/api/v1/automation/rules` | List Rules |
| POST | `/api/v1/automation/rules` | Create Rule |
| GET | `/api/v1/automation/rules/{rule_id}` | Get Rule Detail |
| PATCH | `/api/v1/automation/rules/{rule_id}` | Update Rule |
| POST | `/api/v1/automation/rules/{rule_id}/archive` | Archive Rule |
| POST | `/api/v1/automation/rules/{rule_id}/dry-run` | Dry Run Rule |
| POST | `/api/v1/automation/rules/{rule_id}/run` | Run Rule |
| PATCH | `/api/v1/automation/rules/{rule_id}/schedule` | Update Rule Schedule |
| GET | `/api/v1/automation/rules/{rule_id}/versions` | List Rule Versions |
| POST | `/api/v1/automation/run-scan` | Run Scan |
| GET | `/api/v1/automation/schedules/due` | List Due Scheduled Rules |
| POST | `/api/v1/automation/schedules/run-due` | Run Due Scheduled Rules |
| GET | `/api/v1/automation/schedules/summary` | Schedule Summary |
| GET | `/api/v1/automation/summary` | Automation Summary |
| POST | `/api/v1/governance/overrides` | Create Override Request |
| GET | `/api/v1/governance/overrides` | List Override Requests |
| POST | `/api/v1/governance/overrides/expire` | Expire Overrides |
| POST | `/api/v1/governance/overrides/from-template` | Create Override Request From Template |
| GET | `/api/v1/governance/overrides/summary` | Override Summary |
| GET | `/api/v1/governance/overrides/{override_id}` | Get Override Detail |
| POST | `/api/v1/governance/overrides/{override_id}/approve` | Approve Override |
| POST | `/api/v1/governance/overrides/{override_id}/cancel` | Cancel Override |
| POST | `/api/v1/governance/overrides/{override_id}/execute` | Execute Override |
| POST | `/api/v1/governance/overrides/{override_id}/reject` | Reject Override |
| GET | `/api/v1/governance/overrides/{override_id}/routing` | Get Override Routing |
| POST | `/api/v1/governance/override-templates` | Create Template |
| GET | `/api/v1/governance/override-templates` | List Templates |
| GET | `/api/v1/governance/override-templates/summary` | Template Summary |
| GET | `/api/v1/governance/override-templates/{template_id}` | Get Template Detail |
| PATCH | `/api/v1/governance/override-templates/{template_id}` | Update Template |
| POST | `/api/v1/governance/override-templates/{template_id}/archive` | Archive Template |
| GET | `/api/v1/governance/override-templates/{template_id}/versions` | List Template Versions |
| POST | `/api/v1/governance/retention/evaluate` | Evaluate Retention |
| POST | `/api/v1/governance/retention/policies` | Create Retention Policy |
| GET | `/api/v1/governance/retention/policies` | List Retention Policies |
| PATCH | `/api/v1/governance/retention/policies/{policy_id}` | Update Retention Policy |
| POST | `/api/v1/governance/retention/policies/{policy_id}/archive` | Archive Retention Policy |
| GET | `/api/v1/governance/retention/summary` | Retention Summary |
| POST | `/api/v1/compliance/draft/{draft_id}/refine` | Refine Draft |
| GET | `/api/v1/compliance/draft/{draft_id}/revisions` | List Draft Revisions |
| POST | `/api/v1/compliance/suggest` | Generate Inline Suggestions |
| POST | `/api/v1/compliance/suggest/{suggestion_id}/apply` | Apply Inline Suggestion |
| POST | `/api/v1/compliance/suggest/{suggestion_id}/dismiss` | Dismiss Inline Suggestion |

### Database Tables (24)

| Table | Description |
|---|---|
| `automation_action_logs` | Action logs from automation executions. |
| `automation_rule_executions` | Executions of automation rules. |
| `automation_rule_versions` | Versioned automation rules. |
| `automation_rules` | Automation rules. |
| `governance_autopilot_approval_policies` | Approval policies for autopilot execution. |
| `governance_autopilot_execution_approval_votes` | Votes on autopilot execution approvals. |
| `governance_autopilot_execution_approvals` | Approvals for autopilot execution intents. |
| `governance_autopilot_execution_intents` | Execution intents for autopilot actions. |
| `governance_autopilot_noop_runner_events` | No-op runner events ledger. |
| `governance_autopilot_policies` | Governance autopilot policies. |
| `governance_autopilot_runner_admissions` | Runner admissions (handoff tokens). |
| `governance_autopilot_runner_handshakes` | Runner handshakes. |
| `governance_autopilot_runner_sessions` | Runner sessions. |
| `governance_autopilot_runner_simulations` | Runner simulations for autopilot execution. |
| `governance_copilot_draft_snapshots` | Snapshots of copilot drafts. |
| `governance_override_approvals` | Approvals on governance overrides. |
| `governance_override_events` | Events for governance overrides. |
| `governance_override_requests` | Governance override requests. |
| `governance_override_template_versions` | Versions of override templates. |
| `governance_override_templates` | Templates for governance overrides. |
| `governance_recommendation_action_dispositions` | Dispositions for recommendation actions. |
| `governance_recommendation_snapshots` | Snapshots of governance recommendations. |
| `governance_signals` | Governance signals raised across domains. |
| `retention_policies` | Retention policies (governance-scoped). |

---

## Platform / Security / Administration

**24 features · 176 endpoints · 40 tables**

### Features

| # | Feature | Description | Endpoints |
|---|---|---|---:|
| 1 | Organizations | Get/update organization, my organizations, governance settings (history/diff/timeline), signing keys, evidence manifests & verification, apply-to-open-batch-runs. | 37 |
| 2 | Users & Memberships | List users; memberships CRUD, activation tokens, role update, deactivate. | 9 |
| 3 | Roles & Custom Roles | List roles; custom role CRUD, deactivate, assign role to membership. | 1 |
| 4 | Authentication | Login, register, me, permissions, activate-invite. | 5 |
| 5 | SSO (SAML) | SSO config CRUD, activate/deactivate/test, initiate/callback/metadata. | 10 |
| 6 | SCIM Provisioning | SCIM tokens, SCIM v2 Users CRUD, schemas, service provider config. | 11 |
| 7 | Sessions | List/revoke sessions, user sessions for org. | 2 |
| 8 | Audit Logs | List audit logs. | 1 |
| 9 | Rate Limits | Platform/org rate-limit defaults & overrides, my limits, sentry test. | 6 |
| 10 | SIEM Export | SIEM config CRUD, activate/deactivate, export batch/preview/runs. | 9 |
| 11 | IP Allowlist | Add/list/deactivate IP allowlist ranges. | 0 |
| 12 | Email Outbox & Templates | Queue/list/cancel/mark email outbox, templates CRUD/preview, worker claim/complete/fail/dead-letter. | 15 |
| 13 | Email Config (Org) | Upsert/get/deactivate org email config, test, verify sender. | 8 |
| 14 | Admin Email Config | Admin-level email config upsert/status/test. | 0 |
| 15 | Webhooks | Webhook endpoint CRUD, event types, test-emit, deliveries, deactivate. | 9 |
| 16 | Onboarding | Start/complete onboarding, check-slug, checklist, select frameworks, invite team, team invitations. | 9 |
| 17 | Offboarding | Offboarding configuration, records, run, validate. | 6 |
| 18 | Billing & Subscriptions | Plans, subscribe, cancel, invoices, status; Razorpay webhook. | 6 |
| 19 | Scheduler Admin | List scheduler jobs/runs/run-log. | 3 |
| 20 | Security Scan Ingestion | Ingest OpenSCAP/Prowler/Trivy/Wazuh results, scan jobs list/summary. | 7 |
| 21 | Tasks | Create/list/get/update/cancel/complete tasks, reminders, notify, summary. | 9 |
| 22 | Trust Center (Admin) | Trust center configuration, publish/unpublish policies, access requests review, slug, uptime status. | 8 |
| 23 | Trust Center (Public) | Public trust center data & access request submission. | 2 |
| 24 | Health & Root | Service metadata, health checks. | 3 |

### Endpoints (176)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/organizations/custom-roles` | Create Custom Role |
| GET | `/api/v1/organizations/custom-roles` | List Custom Roles |
| GET | `/api/v1/organizations/custom-roles/{role_id}` | Get Custom Role |
| PATCH | `/api/v1/organizations/custom-roles/{role_id}` | Update Custom Role |
| POST | `/api/v1/organizations/custom-roles/{role_id}/deactivate` | Deactivate Custom Role |
| POST | `/api/v1/organizations/ip-allowlist` | Add Ip Allowlist Range |
| GET | `/api/v1/organizations/ip-allowlist` | List Ip Allowlist Ranges |
| DELETE | `/api/v1/organizations/ip-allowlist/{range_id}` | Deactivate Ip Allowlist Range |
| GET | `/api/v1/organizations/me` | Get My Organizations |
| GET | `/api/v1/organizations/me/governance-settings` | Get Organization Governance Settings |
| PATCH | `/api/v1/organizations/me/governance-settings` | Update Organization Governance Settings |
| POST | `/api/v1/organizations/me/governance-settings/apply-to-open-batch-runs` | Apply Governance Settings To Open Batch Runs |
| GET | `/api/v1/organizations/me/governance-settings/diff` | Get Organization Governance Settings Diff |
| GET | `/api/v1/organizations/me/governance-settings/evidence-bundle` | Get Organization Governance Settings Evidence Bundle |
| POST | `/api/v1/organizations/me/governance-settings/evidence-manifests` | Generate Organization Governance Evidence Manifest |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests` | List Organization Governance Evidence Manifests |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events` | List Organization Governance Manifest Verification Events |
| POST | `/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export` | Export Organization Governance Manifest Verification Events |
| POST | `/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export/verify-page` | Verify Organization Governance Manifest Verification Events Export Page Signature |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests/verification-summary` | Summarize Organization Governance Manifest Verifications |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}` | Get Organization Governance Evidence Manifest Detail |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/chain-of-custody` | Get Organization Governance Manifest Chain Of Custody |
| POST | `/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke` | Revoke Organization Governance Evidence Manifest |
| GET | `/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verification-events` | List Organization Governance Manifest Verification Events For Manifest |
| POST | `/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify` | Verify Organization Governance Evidence Manifest |
| GET | `/api/v1/organizations/me/governance-settings/history` | List Organization Governance Settings History |
| GET | `/api/v1/organizations/me/governance-settings/history/{history_id}` | Get Organization Governance Settings History Detail |
| GET | `/api/v1/organizations/me/governance-settings/signing-keys` | List Organization Internal Signing Keys |
| POST | `/api/v1/organizations/me/governance-settings/signing-keys/rotate` | Rotate Organization Internal Signing Key |
| GET | `/api/v1/organizations/me/governance-settings/signing-keys/summary` | Summarize Organization Internal Signing Keys |
| POST | `/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/deprecate` | Deprecate Organization Internal Signing Key |
| POST | `/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke` | Revoke Organization Internal Signing Key |
| GET | `/api/v1/organizations/me/governance-settings/timeline` | Get Organization Governance Settings Timeline |
| POST | `/api/v1/organizations/memberships/{membership_id}/assign-role` | Assign Custom Role |
| GET | `/api/v1/organizations/users/{user_id}/sessions` | List User Sessions For Org |
| GET | `/api/v1/organizations/{organization_id}` | Get Organization |
| PATCH | `/api/v1/organizations/{organization_id}` | Update Organization |
| GET | `/api/v1/memberships` | List Memberships |
| POST | `/api/v1/memberships` | Create Membership |
| GET | `/api/v1/memberships/{membership_id}` | Get Membership |
| POST | `/api/v1/memberships/{membership_id}/activation-token` | Create Activation Token |
| POST | `/api/v1/memberships/{membership_id}/activation-token/revoke` | Revoke Activation Token |
| GET | `/api/v1/memberships/{membership_id}/activation-token/status` | Activation Token Status |
| PATCH | `/api/v1/memberships/{membership_id}/deactivate` | Deactivate Membership |
| PATCH | `/api/v1/memberships/{membership_id}/role` | Update Membership Role |
| GET | `/api/v1/users` | List Users |
| GET | `/api/v1/roles` | List Roles |
| POST | `/api/v1/auth/activate-invite` | Activate Invite |
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/auth/me` | Me |
| GET | `/api/v1/auth/permissions` | Current Permissions |
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/auth/sso/{org_slug}/callback` | Sso Callback |
| POST | `/api/v1/auth/sso/{org_slug}/initiate` | Initiate Sso |
| GET | `/api/v1/auth/sso/{org_slug}/metadata` | Get Sso Metadata |
| POST | `/api/v1/sso-configs` | Create Sso Config |
| GET | `/api/v1/sso-configs` | Get Sso Config |
| PATCH | `/api/v1/sso-configs/{config_id}` | Update Sso Config |
| DELETE | `/api/v1/sso-configs/{config_id}` | Delete Sso Config |
| POST | `/api/v1/sso-configs/{config_id}/activate` | Activate Sso Config |
| POST | `/api/v1/sso-configs/{config_id}/deactivate` | Deactivate Sso Config |
| POST | `/api/v1/sso-configs/{config_id}/test` | Test Sso Config |
| POST | `/api/v1/scim-tokens` | Create Scim Token |
| GET | `/api/v1/scim-tokens` | List Scim Tokens |
| DELETE | `/api/v1/scim-tokens/{token_id}` | Delete Scim Token |
| GET | `/api/v1/scim/v2/Schemas` | Scim Schemas |
| GET | `/api/v1/scim/v2/ServiceProviderConfig` | Service Provider Config |
| GET | `/api/v1/scim/v2/Users` | List Scim Users |
| POST | `/api/v1/scim/v2/Users` | Create Scim User |
| GET | `/api/v1/scim/v2/Users/{user_id}` | Get Scim User |
| PUT | `/api/v1/scim/v2/Users/{user_id}` | Put Scim User |
| PATCH | `/api/v1/scim/v2/Users/{user_id}` | Patch Scim User |
| DELETE | `/api/v1/scim/v2/Users/{user_id}` | Delete Scim User |
| GET | `/api/v1/sessions` | List My Sessions |
| DELETE | `/api/v1/sessions/{session_id}` | Revoke Session |
| GET | `/api/v1/audit-logs` | List Audit Logs |
| GET | `/api/v1/admin/rate-limits/defaults` | Get Platform Defaults |
| GET | `/api/v1/admin/rate-limits/org/{org_id}` | Get Org Overrides |
| PUT | `/api/v1/admin/rate-limits/org/{org_id}` | Set Org Override |
| DELETE | `/api/v1/admin/rate-limits/org/{org_id}/{group}` | Reset Org Override |
| GET | `/api/v1/admin/sentry-test` | Sentry Test Endpoint |
| GET | `/api/v1/rate-limits/my-limits` | Get My Limits |
| POST | `/api/v1/siem/config` | Create Config |
| GET | `/api/v1/siem/config` | Get Config |
| PATCH | `/api/v1/siem/config` | Patch Config |
| DELETE | `/api/v1/siem/config` | Delete Config |
| POST | `/api/v1/siem/config/activate` | Activate Config |
| POST | `/api/v1/siem/config/deactivate` | Deactivate Config |
| POST | `/api/v1/siem/export` | Export Batch |
| GET | `/api/v1/siem/export/preview` | Preview Export |
| GET | `/api/v1/siem/export/runs` | List Export Runs |
| POST | `/api/v1/email/outbox` | Queue Email |
| GET | `/api/v1/email/outbox` | List Outbox |
| GET | `/api/v1/email/outbox/{email_id}` | Outbox Detail |
| POST | `/api/v1/email/outbox/{email_id}/cancel` | Cancel Email |
| POST | `/api/v1/email/outbox/{email_id}/mark-failed` | Mark Failed |
| POST | `/api/v1/email/outbox/{email_id}/mark-sent` | Mark Sent |
| GET | `/api/v1/email/templates` | List Templates |
| POST | `/api/v1/email/templates` | Create Template |
| PATCH | `/api/v1/email/templates/{template_id}` | Update Template |
| POST | `/api/v1/email/templates/{template_id}/preview` | Preview Template |
| POST | `/api/v1/email/worker/claim` | Worker Claim |
| POST | `/api/v1/email/worker/release-expired-locks` | Worker Release Expired Locks |
| POST | `/api/v1/email/worker/{email_id}/complete` | Worker Complete |
| POST | `/api/v1/email/worker/{email_id}/dead-letter` | Worker Dead Letter |
| POST | `/api/v1/email/worker/{email_id}/fail` | Worker Fail |
| POST | `/api/v1/admin/email-config` | Upsert Email Config |
| GET | `/api/v1/admin/email-config` | Get Email Config Status |
| POST | `/api/v1/admin/email-config/test` | Send Test Email |
| POST | `/api/v1/email-config` | Upsert Email Config |
| GET | `/api/v1/email-config` | Get Email Config |
| DELETE | `/api/v1/email-config` | Deactivate Email Config |
| POST | `/api/v1/email-config/test` | Send Test Email |
| GET | `/api/v1/email-config/verify-sender` | Verify Sender |
| POST | `/api/v1/compliance/webhook-endpoints` | Create Endpoint |
| GET | `/api/v1/compliance/webhook-endpoints` | List Endpoints |
| GET | `/api/v1/compliance/webhook-endpoints/event-types` | List Event Types |
| POST | `/api/v1/compliance/webhook-endpoints/test-emit` | Test Emit |
| GET | `/api/v1/compliance/webhook-endpoints/{endpoint_id}` | Get Endpoint |
| PATCH | `/api/v1/compliance/webhook-endpoints/{endpoint_id}` | Update Endpoint |
| DELETE | `/api/v1/compliance/webhook-endpoints/{endpoint_id}` | Delete Endpoint |
| POST | `/api/v1/compliance/webhook-endpoints/{endpoint_id}/deactivate` | Deactivate Endpoint |
| GET | `/api/v1/compliance/webhook-endpoints/{endpoint_id}/deliveries` | List Deliveries |
| POST | `/api/v1/onboarding/accept-invite` | Accept Invite |
| GET | `/api/v1/onboarding/check-slug` | Check Slug |
| GET | `/api/v1/onboarding/checklist` | Checklist |
| POST | `/api/v1/onboarding/complete` | Complete Onboarding |
| POST | `/api/v1/onboarding/invite-team` | Invite Team |
| POST | `/api/v1/onboarding/select-frameworks` | Select Frameworks |
| POST | `/api/v1/onboarding/start` | Start Onboarding |
| GET | `/api/v1/onboarding/team-invitations` | List Team Invitations |
| DELETE | `/api/v1/onboarding/team-invitations/{invitation_id}` | Revoke Team Invitation |
| GET | `/api/v1/compliance/offboarding/configuration` | Get Configuration |
| PATCH | `/api/v1/compliance/offboarding/configuration` | Update Configuration |
| GET | `/api/v1/compliance/offboarding/records` | List Records |
| GET | `/api/v1/compliance/offboarding/records/{record_id}` | Get Record |
| POST | `/api/v1/compliance/offboarding/run` | Run Offboarding |
| POST | `/api/v1/compliance/offboarding/validate/{user_id}` | Validate Offboarding |
| POST | `/api/v1/billing/cancel` | Cancel |
| GET | `/api/v1/billing/invoices` | Invoices |
| GET | `/api/v1/billing/plans` | List Plans |
| GET | `/api/v1/billing/status` | Billing Status |
| POST | `/api/v1/billing/subscribe` | Subscribe |
| POST | `/api/webhook/razorpay` | Razorpay Webhook |
| GET | `/api/v1/admin/scheduler/jobs` | Get Scheduler Jobs |
| GET | `/api/v1/admin/scheduler/runs` | Get Scheduler Runs |
| GET | `/api/v1/admin/scheduler/runs/{log_id}` | Get Scheduler Run Log |
| POST | `/api/v1/security/ingest/openscap` | Ingest Openscap Results |
| POST | `/api/v1/security/ingest/prowler` | Ingest Prowler Results |
| POST | `/api/v1/security/ingest/trivy` | Ingest Trivy Results |
| POST | `/api/v1/security/ingest/wazuh` | Ingest Wazuh Results |
| GET | `/api/v1/security/scan-jobs` | List Scan Jobs |
| GET | `/api/v1/security/scan-jobs/summary` | Get Scan Jobs Summary |
| GET | `/api/v1/security/scan-jobs/{job_id}` | Get Scan Job |
| GET | `/api/v1/tasks` | List Tasks |
| POST | `/api/v1/tasks` | Create Task |
| POST | `/api/v1/tasks/reminders/queue` | Queue Task Reminders |
| GET | `/api/v1/tasks/summary` | Task Summary |
| GET | `/api/v1/tasks/{task_id}` | Get Task Detail |
| PATCH | `/api/v1/tasks/{task_id}` | Update Task |
| POST | `/api/v1/tasks/{task_id}/cancel` | Cancel Task |
| POST | `/api/v1/tasks/{task_id}/complete` | Complete Task |
| POST | `/api/v1/tasks/{task_id}/notify` | Notify Task Assignee |
| GET | `/api/v1/compliance/trust-center/access-requests` | List Access Requests |
| POST | `/api/v1/compliance/trust-center/access-requests/{request_id}/review` | Review Access Request |
| GET | `/api/v1/compliance/trust-center/configuration` | Get Configuration |
| POST | `/api/v1/compliance/trust-center/configuration` | Upsert Configuration |
| DELETE | `/api/v1/compliance/trust-center/policies/{policy_id}/unpublish` | Unpublish Policy |
| POST | `/api/v1/compliance/trust-center/publish-policy` | Publish Policy |
| POST | `/api/v1/compliance/trust-center/slug` | Set Org Slug |
| PATCH | `/api/v1/compliance/trust-center/uptime-status` | Update Uptime Status |
| GET | `/api/v1/trust-center/{slug}` | Get Trust Center Public Data |
| POST | `/api/v1/trust-center/{slug}/request-access` | Submit Trust Center Access Request |
| GET | `/` | Service metadata |
| GET | `/api/v1/health` | API health check |
| GET | `/health` | System health |

### Database Tables (40)

| Table | Description |
|---|---|
| `audit_logs` | Platform audit logs. |
| `billing_events` | Billing events (Razorpay). |
| `email_delivery_events` | Email delivery events. |
| `email_outbox` | Email outbox queue. |
| `email_templates` | Email templates. |
| `membership_activation_tokens` | Activation tokens for memberships. |
| `memberships` | User memberships in organizations. |
| `offboarding_configurations` | User offboarding configurations. |
| `offboarding_records` | Records of executed offboarding. |
| `org_ai_config` | Org AI feature toggle config. |
| `org_email_configs` | Org email provider configs. |
| `org_ip_allowlist` | Org IP allowlist ranges. |
| `org_issue_settings` | Org issue settings (e.g. require RCA). |
| `organization_ai_configurations` | Org AI provider (BYO credential) configurations. |
| `organization_governance_evidence_manifests` | Signed evidence manifests for governance settings. |
| `organization_governance_manifest_verification_events` | Verification events for governance manifests. |
| `organization_governance_setting_history` | History of org governance setting changes. |
| `organization_governance_settings` | Org governance settings. |
| `organization_internal_signing_keys` | Internal signing keys for org manifests. |
| `organizations` | Organizations (tenants). |
| `permissions` | Permission catalog. |
| `rate_limit_configs` | Per-org rate limit overrides. |
| `role_permissions` | Role-permission grants. |
| `roles` | Roles (system and custom). |
| `scheduler_run_logs` | Scheduler run logs. |
| `scim_tokens` | SCIM API tokens. |
| `security_scan_jobs` | Security scan ingestion jobs. |
| `siem_export_configs` | SIEM export configurations. |
| `siem_export_runs` | SIEM export runs. |
| `sso_configs` | SAML SSO configurations. |
| `subscription_plans` | Subscription plans. |
| `tasks` | Tasks (work items). |
| `team_invitations` | Team invitation tokens. |
| `trust_center_access_requests` | Trust center access requests. |
| `trust_center_configurations` | Trust center configurations. |
| `trust_center_published_policies` | Policies published to the trust center. |
| `user_sessions` | User sessions. |
| `users` | Users. |
| `webhook_deliveries` | Webhook delivery attempts. |
| `webhook_endpoints` | Webhook endpoints. |

---
