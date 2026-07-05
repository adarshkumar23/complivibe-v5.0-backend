# Final Sweep A: AI Governance + LLM Observability

Branch: `final-sweep-a`
Worktree: `/home/ubuntu/complivibe-v4.0/complivibe-sweep-a`

## Summary

Verdict after fixes: **SOLID** for the Worktree A assigned slice.

This sweep used real FastAPI test-client HTTP requests, adversarial cases, and direct DB assertions through the focused test suite plus additional standalone verifier work. A selected Worktree A regression covering 283 `def test_...` functions exited 0. Full repository pytest was also attempted; it requires a test `SECRET_KEY` and then fails only on real external AI provider tests because `GROQ_API_KEY` and Azure endpoint settings are not configured in this environment.

## Local Fixes

| Commit | Finding | Before | After |
| --- | --- | --- | --- |
| `ea0e229` | LLM observability allowed writes to retired/decommissioned systems. | Retired systems could still receive cost/LLM observations. | `_require_active_ai_system` rejects archived, decommissioned, and `archived_at` systems; regression asserts 422. |
| `880bd87` | AI system owners were not org-scoped. | Org A could create/update a system with Org B's user as owner. | Owner validation requires active membership in the same organization. |
| `a4762d0` | AI review assignees were not org-scoped. | Org A could assign a governance review to Org B's user. | Assigned reviewer validation requires active same-org membership. |
| `aa5a379` | Model card contact owners were not org-scoped. | Org A could create/update a model card with Org B's user as contact owner. | Contact owner validation requires active same-org membership. |
| `55ea117` | ATLAS assessment was read-only and did not update governance score inputs. | `atlas_risk_score` stayed null after assessment, so governance score threat-assessment credit stayed absent. | Assessment persists `AISystem.atlas_risk_score`, emits `atlas.assessment_completed`, and writes an audit log. |

## Verification Commands

Focused fix verification:

```bash
.venv/bin/pytest tests/unit/test_atlas_f1.py tests/unit/test_ai_depth_f3.py -q
```

Result: `7 passed`.

Selected Worktree A regression:

```bash
.venv/bin/pytest \
  tests/unit/test_llm_observability_t1_7_t1_10.py \
  tests/unit/test_llm_observability_t1_11_12_13.py \
  tests/unit/test_ai_inventory_a51_a52_a53.py \
  tests/unit/test_governance_classify_a54_a55_a56.py \
  tests/unit/test_trust_ai_mitigation_a56_a57_a58.py \
  tests/unit/test_eu_act_risk_assess_a57_a58.py \
  tests/unit/test_iso42001_nist_rmf_a59_a60.py \
  tests/unit/test_model_cards_aibom_a61_a62_a63.py \
  tests/unit/test_guardrails_envelopes_a64_a65.py \
  tests/unit/test_ai_monitoring_a66.py \
  tests/unit/test_signals_recs_diagnostics_a67_a68_a69.py \
  tests/unit/test_copilot_mlops_contracts_a70_a71_a72.py \
  tests/unit/test_atlas_f1.py \
  tests/unit/test_ai_depth_f3.py \
  tests/unit/test_regulatory_heatmap_a75_a76.py \
  tests/unit/test_ai_governance_dashboard_metrics.py \
  tests/unit/test_ai_systems_phase50.py \
  tests/unit/test_ai_system_links_phase51.py \
  tests/unit/test_ai_system_governance_phase52.py \
  tests/unit/test_ai_system_governance_schedule_phase53.py \
  tests/unit/test_ai_system_governance_recurrence_phase54.py \
  tests/unit/test_ai_system_governance_constraints_phase55.py \
  tests/unit/test_ai_system_governance_sequence_phase56.py \
  tests/unit/test_ai_system_governance_guardrails_phase57.py \
  tests/unit/test_ai_system_governance_guardrail_precedence_phase58.py \
  tests/unit/test_ai_system_governance_guardrail_policy_sets_phase59.py \
  tests/unit/test_ai_system_governance_contracts_phase60.py \
  tests/unit/test_ai_system_risk_assessments_phase61.py \
  tests/unit/test_ai_system_risk_scoring_profiles_phase62.py \
  tests/unit/test_ai_system_risk_dimension_templates_phase63.py \
  tests/unit/test_ai_system_risk_classification_phase64.py \
  tests/unit/test_ai_system_risk_classification_review_signals_phase65.py \
  tests/unit/test_ai_system_signal_prioritization_phase66.py \
  tests/unit/test_ai_system_candidate_actions_phase67.py \
  tests/unit/test_ai_system_recommendation_snapshots_phase68.py \
  tests/unit/test_ai_system_recommendation_action_dispositions_phase69.py \
  tests/unit/test_ai_system_autopilot_policies_phase70.py \
  tests/unit/test_ai_system_autopilot_execution_intents_phase71.py \
  tests/unit/test_ai_system_autopilot_execution_approvals_phase72.py \
  tests/unit/test_ai_system_autopilot_approval_quorum_phase73.py \
  tests/unit/test_ai_system_autopilot_runner_simulations_phase74.py \
  tests/unit/test_ai_system_autopilot_runner_admissions_phase75.py \
  tests/unit/test_ai_system_autopilot_runner_sessions_phase76.py \
  tests/unit/test_ai_system_autopilot_runner_handshakes_phase77.py \
  tests/unit/test_ai_system_autopilot_regression_gate_phase78.py \
  tests/unit/test_ai_system_autopilot_execution_safety_phase79.py \
  tests/unit/test_ai_system_autopilot_noop_runner_events_phase80.py \
  tests/unit/test_ai_system_autopilot_noop_runner_observability_phase81.py \
  tests/unit/test_ai_system_autopilot_noop_runner_diagnostics_compatibility_phase83.py \
  tests/unit/test_ai_system_autopilot_noop_runner_client_integration_phase84.py \
  tests/unit/test_ai_system_autopilot_noop_runner_client_field_docs_phase85.py \
  tests/unit/test_ai_system_autopilot_noop_runner_integration_readiness_phase86.py \
  tests/unit/test_ai_system_autopilot_noop_runner_phase8_closure_phase87.py \
  tests/unit/test_ai_system_governance_policy_resolution_simulation_phase511.py \
  tests/unit/test_ai_system_governance_policy_resolution_diff_phase512.py \
  tests/unit/test_ai_system_governance_policy_resolution_diff_reason_codes_phase513.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_phase514.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_phase515.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_presets_phase516.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_preset_pinning_phase518.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519.py \
  tests/unit/test_ai_system_governance_policy_diff_gating_compare_preset_assignment_diagnostics_phase520.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_reports_phase521.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_exports_phase522.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diffs_phase523.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_reason_codes_phase524.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_phase526.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_presets_phase527.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_versions_phase528.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_assignments_phase529.py \
  tests/unit/test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_assignment_diagnostics_phase530.py \
  tests/unit/test_mlops_adapter_sprint2_p2.py \
  tests/unit/test_ai_governance_diagnostics_sprint2_p4.py \
  -q
```

Result: exit code `0`.

Full suite:

```bash
.venv/bin/pytest -q
```

Result: collection blocked because `SECRET_KEY` is required by unrelated infrastructure tests.

```bash
SECRET_KEY=test-secret-key-for-full-suite .venv/bin/pytest -q
```

Result: full run completed with 8 failures, all real external AI provider tests requiring unset `GROQ_API_KEY` or Azure endpoint settings:

- `tests/unit/test_ai_policy_drafting_sprint1_p4.py::test_real_groq_platform_default_policy_draft`
- `tests/unit/test_ai_policy_drafting_sprint1_p4.py::test_real_azure_fallback_policy_draft`
- `tests/unit/test_ai_policy_drafting_sprint1_p4.py::test_real_endpoint_groq_draft_persists_generated_text`
- `tests/unit/test_compliance_risk_recs_sprint2_p3.py::test_generate_recommendations_real_groq_persists_rows`
- `tests/unit/test_compliance_risk_recs_sprint2_p3.py::test_accept_new_risk_creates_real_risk_and_audit_with_real_groq`
- `tests/unit/test_compliance_risk_recs_sprint2_p3.py::test_accept_treatment_change_updates_linked_risk_with_real_groq_call`
- `tests/unit/test_copilot_draft_sprint2_p1.py::test_refine_draft_real_calls_revision_history_and_org_scoping`
- `tests/unit/test_copilot_draft_sprint2_p1.py::test_inline_suggestions_real_calls_for_policy_control_risk_and_status_updates`

## Per-Feature Verdicts

| Feature | Verdict | Evidence |
| --- | --- | --- |
| A51 AI system inventory and lifecycle | SOLID after fix | HTTP create/get/summary/update/decommission/delete paths; adversarial invalid status, cross-org read, foreign owner create/update; DB system/audit/governance-event counts. Regression: `test_ai_inventory_a51_a52_a53.py`. Fix: `880bd87`. |
| A52 Shadow AI intake/review/register/dismiss | SOLID | HTTP detection lifecycle; adversarial double register/dismiss and invalid transitions; DB system/detection/audit/event side effects. Regression: `test_ai_inventory_a51_a52_a53.py`. |
| A53 AI use cases and dashboard counts | SOLID | HTTP create/list/dashboard counts; adversarial foreign system association rejection; DB use-case and dashboard-backed counts. Regression: `test_ai_inventory_a51_a52_a53.py`. |
| A54 AI governance reviews | SOLID after fix | HTTP review create/respond/approve; adversarial self-approval, early approval, foreign reviewer assignment; DB review criteria/audit/event rows. Regression: `test_governance_classify_a54_a55_a56.py`. Fix: `a4762d0`. |
| A55 Guided/manual AI classification | SOLID | HTTP guided start/submit/manual classification; adversarial malformed manual classification; DB risk classification row and system risk-tier update. Regression: `test_governance_classify_a54_a55_a56.py`. |
| A56 EU AI Act classification / trust center overlap | SOLID | HTTP annex/classify/obligations and trust center admin/public flows; adversarial bad annex and cross-org read; DB classification/workflow/audit rows. Regressions: `test_governance_classify_a54_a55_a56.py`, `test_trust_ai_mitigation_a56_a57_a58.py`. |
| A57 EU Act workflow and AI vendor assessment | SOLID | HTTP workflow create/complete and vendor assessment scoring; adversarial org isolation and invalid state; DB workflow/assessment/audit evidence. Regressions: `test_eu_act_risk_assess_a57_a58.py`, `test_trust_ai_mitigation_a56_a57_a58.py`. |
| A58 AI risk assessment and vendor mitigation workflow | SOLID | HTTP assessment create/complete and mitigation case/action/evidence workflow; adversarial invalid references and transition guards; DB risk assessment/case/action/audit rows. Regressions: `test_eu_act_risk_assess_a57_a58.py`, `test_trust_ai_mitigation_a56_a57_a58.py`. |
| A59 ISO 42001 conformity tracker | SOLID | HTTP tracker seed/update/summary; adversarial foreign/nonexistent evidence rejection; DB duplicate-prevention count for clause `4.1`; audit/event rows. Regression: `test_iso42001_nist_rmf_a59_a60.py`. |
| A60 NIST AI RMF workflow | SOLID | HTTP implementation create/detail/update/maturity/org-summary; adversarial foreign evidence and cross-org read; DB implementation/response counts and maturity recomputation. Regression: `test_iso42001_nist_rmf_a59_a60.py`. |
| A61 Third-party AI assessment | SOLID | HTTP assessment create/update/delete/list; adversarial invalid assessed_by, null required fields, cross-org isolation; DB assessment/audit/event and linked system risk behavior. Regression: `test_model_cards_aibom_a61_a62_a63.py`. |
| A62 Model cards | SOLID after fix | HTTP create/update/publish/version; adversarial published-card immutability and foreign contact owner create/update; DB active/published/archived card rows and audit/event rows. Regression: `test_model_cards_aibom_a61_a62_a63.py`. Fix: `aa5a379`. |
| A63 AIBOM | SOLID | HTTP AIBOM create/add component/diff; adversarial duplicate component and cross-org diff; DB AIBOM record/component/training signal/audit/event rows. Regression: `test_model_cards_aibom_a61_a62_a63.py`. |
| A64 Guardrail engine | SOLID | HTTP guardrail create/evaluate; adversarial unenforceable constraint values; DB guardrail/event/audit rows and violation behavior. Regressions: `test_guardrails_envelopes_a64_a65.py`, `test_partD_ai_guardrail_and_signals.py`. |
| A65 Approval envelopes | SOLID | HTTP envelope create/approval workflow; adversarial unauthorized actor and invalid approval transitions; DB envelope/action/audit rows. Regression: `test_guardrails_envelopes_a64_a65.py`. |
| A66 AI monitoring | SOLID | HTTP config/readings/history/dashboard; adversarial bad metric, wrong key, inactive config, cross-org read; DB readings/alerts/signals/audit/event rows. Regression: `test_ai_monitoring_a66.py`. |
| A67 Governance signals | SOLID | HTTP signal generation/list/prioritization; adversarial cross-org system access; DB signal rows and read-only endpoints verified not to audit. Regressions: `test_signals_recs_diagnostics_a67_a68_a69.py`, `test_ai_system_signal_prioritization_phase66.py`. |
| A68 Recommendations | SOLID | HTTP generate/apply/dismiss/preview; adversarial dismissed apply rejection and read-only preview no rows/audit; DB recommendation/task/audit/event rows. Regressions: `test_signals_recs_diagnostics_a67_a68_a69.py`, `test_ai_system_recommendation_snapshots_phase68.py`. |
| A69 Diagnostics/event log | SOLID | HTTP system event log, org event filters, summary, diagnostics export/list; adversarial org isolation and immutable export behavior; DB event/export/audit rows. Regressions: `test_signals_recs_diagnostics_a67_a68_a69.py`, `test_ai_governance_diagnostics_sprint2_p4.py`. |
| A70 Copilot AI-system context contract | SOLID | HTTP draft endpoint with AI-system context; adversarial cross-org AI system context rejected; DB draft request row scoped to org. Regression: `test_copilot_mlops_contracts_a70_a71_a72.py`. |
| A71 MLOps sync/contracts | SOLID | HTTP integration/sync and service sync; adversarial cross-org model ops endpoints; DB model registrations, AIBOM components, risk side effects, audit rows. Regressions: `test_copilot_mlops_contracts_a70_a71_a72.py`, `test_mlops_adapter_sprint2_p2.py`. |
| A72 Contract registry | SOLID | HTTP static contract registry; adversarial no-auth/no-DB-query behavior; DB query guard confirms static behavior. Regression: `test_copilot_mlops_contracts_a70_a71_a72.py`. |
| A75 Regulatory heatmap builders/storage | SOLID | HTTP regulatory report generation and heatmap storage; adversarial invalid data and org isolation; DB regulatory report/heatmap rows. Regression: `test_regulatory_heatmap_a75_a76.py`. |
| A76 Regulatory heatmap retrieval/export | SOLID | HTTP retrieval/export-style paths; adversarial cross-org heatmap access; DB persisted heatmap evidence. Regression: `test_regulatory_heatmap_a75_a76.py`. |
| F1 MITRE ATLAS | SOLID after fix | HTTP techniques/tactics/filter/detail/assessment/mitigations; adversarial unknown tactic and cross-org assessment; DB 24 seeded techniques, persisted `atlas_risk_score`, audit/event rows. Regression: `test_atlas_f1.py`. Fix: `55ea117`. |
| F3 AI depth / governance score | SOLID | HTTP bias assessment/history, oversight, governance score/scorecard; adversarial invalid oversight/full automation issue/cross-org score; DB bias assessment/issues/audit rows and score fields. Regression: `test_ai_depth_f3.py`. |
| Phase 50 AI systems core contracts | SOLID | HTTP CRUD/permissions/archive behavior; adversarial readonly and invalid owner/status cases; DB systems/audit rows. Regression: `test_ai_systems_phase50.py`. |
| Phase 51 AI system links | SOLID | HTTP link/unlink/list behavior; adversarial cross-org/missing linked object cases; DB link rows and audit side effects. Regression: `test_ai_system_links_phase51.py`. |
| Phase 52 Governance baseline | SOLID | HTTP governance record lifecycle; adversarial scope/state validation; DB governance records/audit rows. Regression: `test_ai_system_governance_phase52.py`. |
| Phase 53 Governance schedule | SOLID | HTTP schedule create/update/list; adversarial invalid cadence/scope cases; DB schedule rows. Regression: `test_ai_system_governance_schedule_phase53.py`. |
| Phase 54 Governance recurrence | SOLID | HTTP recurrence expansion/review generation; adversarial duplicate/no-op cases; DB generated review rows. Regression: `test_ai_system_governance_recurrence_phase54.py`. |
| Phase 55 Governance constraints | SOLID | HTTP constraint resolution; adversarial invalid/unsupported constraints; DB constraint rows. Regression: `test_ai_system_governance_constraints_phase55.py`. |
| Phase 56 Governance sequence | SOLID | HTTP sequencing/reorder behavior; adversarial invalid sequence changes; DB sequence ordering rows. Regression: `test_ai_system_governance_sequence_phase56.py`. |
| Phase 57-60 Guardrail policy foundation | SOLID | HTTP guardrail CRUD, precedence, policy sets, contracts; adversarial invalid precedence and cross-org assignment; DB guardrail/policy-set/assignment/audit rows. Regressions: `test_ai_system_governance_guardrails_phase57.py` through `test_ai_system_governance_contracts_phase60.py`. |
| Phase 61 Risk assessments engine | SOLID | HTTP create/detail/list/snapshot/contract endpoint; adversarial invalid type/level/likelihood, cross-org owner/system/get/list, read-only audit behavior; DB assessment/snapshot/audit rows. Regression: `test_ai_system_risk_assessments_phase61.py`. |
| Phase 62 Risk scoring profiles | SOLID | HTTP profile CRUD/selection/scoring behavior; adversarial invalid dimensions and org isolation; DB profile/version rows. Regression: `test_ai_system_risk_scoring_profiles_phase62.py`. |
| Phase 63 Risk dimension templates | SOLID | HTTP template CRUD/seed/use; adversarial invalid dimension/template access; DB template rows. Regression: `test_ai_system_risk_dimension_templates_phase63.py`. |
| Phase 64 Risk classification | SOLID | HTTP classification create/recompute/list; adversarial invalid category/status and org isolation; DB classification rows. Regression: `test_ai_system_risk_classification_phase64.py`. |
| Phase 65 Classification review signals | SOLID | HTTP review/signal creation paths; adversarial invalid review/status cases; DB review/signal/audit rows. Regression: `test_ai_system_risk_classification_review_signals_phase65.py`. |
| Phase 66 Signal prioritization | SOLID | HTTP prioritized signal reads; adversarial cross-org access; DB signal ordering evidence and no-audit read-only check. Regression: `test_ai_system_signal_prioritization_phase66.py`. |
| Phase 67 Candidate actions | SOLID | HTTP candidate summary/explain endpoints; adversarial cross-org AI system/assessment and missing record cases; DB signal rows and no-audit read-only check. Regression: `test_ai_system_candidate_actions_phase67.py`. |
| Phase 68 Recommendation snapshots | SOLID | HTTP preview/snapshot endpoints; adversarial read-only preview no rows/audit; DB snapshot rows. Regression: `test_ai_system_recommendation_snapshots_phase68.py`. |
| Phase 69 Recommendation action dispositions | SOLID | HTTP disposition apply/dismiss/status behavior; adversarial invalid transition/cross-org cases; DB disposition/audit rows. Regression: `test_ai_system_recommendation_action_dispositions_phase69.py`. |
| Phase 70-87 Autopilot | SOLID | HTTP policies, intents, approvals, quorum, simulations, runner admissions/sessions/handshakes, regression gate, safety, noop runner events/observability/client compatibility/readiness/closure; adversarial safety, approval, and admission guards; DB policy/intent/session/event/audit rows. Regressions: `test_ai_system_autopilot_*phase70.py` through `phase87.py`. |
| Phase 511-530 Policy resolution/diff gating/diagnostic exports | SOLID | HTTP policy resolution simulation, diffs, reason codes, diff gating, preset compare/version/pinning/assignment diagnostics, export diff gating, and compare reports; adversarial invalid compare/scope/gating cases; DB report/export/diff rows. Regressions: `test_ai_system_governance_policy_*phase511.py` through `test_ai_system_governance_preset_assignment_*phase530.py`. |
| T1-7 LLM tracing | SOLID after retired-system fix | HTTP trace poll and summary; adversarial unauthorized/cross-org/retired system rejection; DB LLM event/audit/event rows. Regression: `test_llm_observability_t1_7_t1_10.py`. Fix: `ea0e229`. |
| T1-8 Hallucination detection | SOLID | HTTP hallucination check; adversarial invalid score/missing system; DB LLM event, alert, governance event, audit rows. Regression: `test_llm_observability_t1_7_t1_10.py`. |
| T1-9 Cost monitoring | SOLID after retired-system fix | HTTP cost readings and spike detection; adversarial negative/invalid cost and retired system; DB cost events, alerts, audit rows. Regression: `test_llm_observability_t1_7_t1_10.py`. Fix: `ea0e229`. |
| T1-10 RAG monitoring | SOLID | HTTP RAG evaluation; adversarial invalid retrieval/context values; DB retrieval events, audit/event rows. Regression: `test_llm_observability_t1_7_t1_10.py`. |
| T1-11 Fairness runner/core push | SOLID | HTTP/core push through monitoring integration; adversarial threshold breach and metric validation; DB monitoring readings/signals/alerts. Regression: `test_llm_observability_t1_11_12_13.py`. |
| T1-12 Drift runner/core push | SOLID | HTTP/core push through monitoring integration; adversarial drift breach and bad metric cases; DB monitoring readings/signals/alerts. Regression: `test_llm_observability_t1_11_12_13.py`. |
| T1-13 LLM monitoring integration | SOLID | HTTP config/readings/key rotation/dashboard integration; adversarial wrong key, inactive config, cross-org access; DB configs/readings/audit/event rows. Regressions: `test_llm_observability_t1_11_12_13.py`, `test_ai_monitoring_a66.py`. |

## Remaining Weak/Broken Items

No Worktree A feature remains known weak or broken after the local fixes above.

Repository-wide full-suite caveat: real external provider tests remain unexecutable in this environment without `GROQ_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and related Azure deployment settings. The initial full-suite collection also requires `SECRET_KEY`.

