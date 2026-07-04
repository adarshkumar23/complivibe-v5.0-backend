# Opus Bug Hunt Log — 2026-07-04

Comprehensive find-and-fix pass across all CompliVibe backend domains.
Method: real HTTP against local dev server (port 8010, own uvicorn instance),
fresh test orgs `BugHunt Opus Org A/B` (hunter1/hunter2@bughunt-opus.io).

Baseline: full suite run started at session start (result recorded below when complete).
Alembic head at start: f37a755f8aa6 (single head). Git HEAD at start: 0479c18.

Baseline result: full suite passes except exactly the 4 known Groq/Azure
provider-selection flakes (test_real_groq_platform_default_policy_draft,
test_generate_recommendations_real_groq_persists_rows,
test_refine_draft_real_calls_revision_history_and_org_scoping,
test_inline_suggestions_real_calls_for_policy_control_risk_and_status_updates).

Parallelization note: per user request, domains 2–13 were delegated to four
fork subagents in isolated git worktrees (branches to be merged back here);
this session continues Domain 1 (AI Governance) directly.

## Findings

### 1. AI Governance — ISO 42001 tracker + NIST RMF updates wipe notes/evidence; accept foreign evidence_id
- **Root cause:** `ISO42001Service.update_tracker` and `NISTRMFService.update_subcategory`
  unconditionally assigned `notes`/`evidence_id` from the request payload, whose schema
  defaults omitted fields to `None` — so a status-only update silently nulled previously
  saved notes and evidence links. Additionally, `evidence_id` was persisted without any
  existence or org-scoping check.
- **Evidence:** `POST /ai-governance/iso42001/conformity-tracker/4.1/update {"status":"in_progress","notes":"AIMS scope drafted, pending review"}` → notes saved; follow-up `{"status":"implemented"}` → `"notes": null` (data loss). `POST .../4.2/update {"status":"implemented","evidence_id":"00000000-0000-0000-0000-000000000001"}` → 200 with nonexistent evidence persisted.
- **Fix:** pass the payload's `model_fields_set` through so omitted fields are preserved
  (explicit `null` still clears); validate `evidence_id` exists in the caller's org (422
  `evidence_id not found in organization`, matching vendor_mitigation_service precedent).
  Applied to both ISO 42001 and NIST RMF paths. Regression tests added.
- **Files:** app/ai_governance/services/iso42001_service.py, app/ai_governance/services/nist_rmf_service.py, app/ai_governance/routers/iso42001.py, app/ai_governance/routers/ai_systems.py, tests/unit/test_iso42001_nist_rmf_a59_a60.py
- **Commit:** 666f30e

### 2. AI Governance — guardrails with mistyped constraint keys are silently inert
- **Root cause:** `GuardrailService.create_guardrail` accepted any `constraint_value`
  dict, but the built-in policy engine only enforces exact keys (`max_usd`,
  `allowed_regions`, `allowed_user_roles`, `prohibited_actions`,
  `allowed_data_categories`). A financial_limit guardrail created with
  `{"max_amount": 1000}` passed every check.
- **Evidence:** created guardrail `{"guardrail_type":"financial_limit","constraint_value":{"max_amount":1000},"violation_action":"block_and_alert"}` → 201; `POST /systems/{id}/guardrails/check {"action_context":{"amount":5000}}` → `{"decision":"permit","blocked":false}`. With `max_usd` the same check correctly blocks.
- **Fix:** per-type required-key + shape validation on create/update with specific 422
  messages. Also noted (not fixed): `GuardrailService.update_guardrail` has no API route
  (dead code) — validation added there anyway for future use.
- **Files:** app/ai_governance/services/guardrail_service.py, tests/unit/test_partD_ai_guardrail_and_signals.py
- **Commit:** b025cce

### 3. AI Governance — third-party assessment completion silently downgrades EU AI Act risk tier
- **Root cause:** `ThirdPartyAIService.complete_assessment` unconditionally wrote
  `tier_map[risk_level]` onto the linked `ai_system.risk_tier`. EU AI Act
  classification also writes that field; a later favorable vendor assessment
  clobbered the regulatory tier (parallel-subsystems disagreement pattern).
- **Evidence:** `POST /systems/{id}/eu-act-classification {"article_category":"high_risk_annex3"}` → system `risk_tier: high`; then completed a fully-favorable vendor model assessment (`overall_risk_level: low`) → system `risk_tier: minimal`.
- **Fix:** completion now only escalates (severity: unassessed < minimal < limited <
  high < prohibited), never downgrades, and the system-tier change gets its own
  `ai_system.risk_tier_escalated` audit log entry (previously unaudited).
- **Files:** app/ai_governance/services/third_party_ai_service.py, tests/unit/test_model_cards_aibom_a61_a62_a63.py
- **Commit:** 7bd7f4e

### 4. AI Governance — shadow AI detection state machine allows duplicate registration and inconsistent transitions
- **Root cause:** `ShadowAIService.register_as_system` only rejected `dismissed`
  detections; `dismiss_detection`/`review_detection` had no state checks. Re-register
  of a `registered` detection created a duplicate AI system per call; dismissing a
  registered detection produced status=dismissed with a live `registered_system_id`.
  `review_detection` also wrote no audit log for its state change.
- **Evidence:** `POST /shadow-ai/detections/{id}/register` twice → two distinct AI systems (201 both times); `POST .../dismiss` after register → 200, status flipped to dismissed.
- **Fix:** registered detections are terminal (re-register/dismiss/review → 422 naming
  the linked system); review transition restricted to new/under_review and audited.
- **Files:** app/ai_governance/services/shadow_ai_service.py, tests/unit/test_ai_inventory_a51_a52_a53.py
- **Commit:** 7119bd5

## Continuation — Codex session on 2026-07-04

Orientation:
- `pwd`: `/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend`
- `DATABASE_URL`: confirmed local dev database at `localhost:5432/complivibe`
- `git log --oneline -30`: start HEAD `7119bd5`; recent commits matched the already-fixed list plus the four AI governance fixes above
- Alembic head: `0202_oidc_sso_support` (single head)
- Baseline: `.venv/bin/python -m pytest tests/ -q --disable-warnings` failed only the four known Groq/Azure provider-selection flakes:
  `test_real_groq_platform_default_policy_draft`,
  `test_generate_recommendations_real_groq_persists_rows`,
  `test_refine_draft_real_calls_revision_history_and_org_scoping`,
  `test_inline_suggestions_real_calls_for_policy_control_risk_and_status_updates`

### 5. AI Governance / TPRM — third-party AI assessment patch lacks audit, permits cross-org assessed_by, and leaks null-column 500s
- **Root cause:** `ThirdPartyAIService.update_assessment` mutated draft/in-progress
  assessments without `AuditService.write_audit_log`. The update schema also exposed
  `assessed_by` but did not verify that the supplied user was an active member of the
  caller's organization. Finally, explicit `null` values for non-null columns were
  accepted by Pydantic and reached the database, producing generic 500s.
- **Evidence before fix:** real HTTP against local server on port 8020:
  `PATCH /api/v1/ai-governance/third-party-assessments/395a1def-cb6b-40ac-a6c4-093b5b5b9e67 {"model_version":"2.0","status":"in_progress"}` -> 200 with updated fields, but SQL audit query returned only `['third_party_ai.created']`.
  `PATCH /api/v1/ai-governance/third-party-assessments/9e38ca8e-1a31-4d48-8776-07eeba6d77d1 {"assessed_by":"69702f8a-d926-4c59-a2b3-3c74a6b6414b"}` where that user belongs to another org -> 200 and response persisted the foreign user ID.
  `PATCH /api/v1/ai-governance/third-party-assessments/{id} {"data_egress_type":null}` -> `500 Internal Server Error`.
- **Fix:** update route now passes the actor user into the service; service rejects
  explicit `null` for non-null update fields with specific 422s, validates
  `assessed_by` against active membership in the caller org, and writes
  `third_party_ai.updated` audit logs with before/after deltas.
- **Evidence after fix:** real HTTP `PATCH ... {"model_version":"2.0","status":"in_progress"}` -> 200 and audit query returned `third_party_ai.updated` with before `{"status":"draft","model_version":null}` and after `{"status":"in_progress","model_version":"2.0"}`. Foreign `assessed_by` now returns 422 `assessed_by must be an active member of the organization`; `{"data_egress_type":null}` now returns 422 `data_egress_type cannot be null`.
- **Files:** app/ai_governance/services/third_party_ai_service.py, app/ai_governance/routers/third_party_ai.py, tests/unit/test_model_cards_aibom_a61_a62_a63.py
- **Tests:** `.venv/bin/python -m pytest tests/unit/test_model_cards_aibom_a61_a62_a63.py -q --disable-warnings` -> `7 passed`
- **Commit:** TBD

### 6. Privacy & Data Protection — DPA PATCH/create can attach foreign tenant related records
- **Root cause:** `DPAService.link_processing_activity` validated the activity belonged
  to the caller org, but `DPAService.update_dpa` accepted `processing_activity_ids`
  through PATCH and only normalized UUID syntax. `DPAService.create_dpa` and
  `update_dpa` also accepted `vendor_id`/`subprocessor_id` without any application-level
  org scoping; those DPA columns are plain UUIDs, so the database could not protect the
  relationship.
- **Evidence before fix:** real HTTP against local server on port 8020:
  with org A DPA `c6eefc53-d402-4351-9f9d-c6b094945a62` and org B ROPA activity
  `f38f1641-ded8-4d9b-a669-f2fa2f5a19f1`, the dedicated
  `POST /api/v1/privacy/dpas/{dpa_id}/link-activity` returned 404
  `Processing activity not found`, but
  `PATCH /api/v1/privacy/dpas/{dpa_id} {"processing_activity_ids":["f38f1641-ded8-4d9b-a669-f2fa2f5a19f1"]}`
  returned 200 and persisted the foreign activity ID. Separately,
  `POST /api/v1/privacy/dpas` in org A with org B `vendor_id`
  `559a5ff4-02c3-431d-9e09-3274f672e8e5` returned 201 and persisted the foreign vendor ID.
- **Fix:** DPA create/update now require supplied `vendor_id`, `subprocessor_id`, and
  every `processing_activity_id` to exist in the caller organization. The direct link
  endpoint and PATCH path now share the same activity scoping behavior.
- **Evidence after fix:** real HTTP create with a foreign `vendor_id` returns 404
  `Vendor not found`; real HTTP PATCH with a foreign `processing_activity_ids` value
  returns 404 `Processing activity not found`.
- **Files:** app/privacy/services/dpa_service.py, tests/unit/test_dpa_breach_extension_d92_d89.py
- **Tests:** `.venv/bin/python -m pytest tests/unit/test_dpa_breach_extension_d92_d89.py -q --disable-warnings` -> `5 passed`
- **Commit:** TBD

### 7. Data Observability — data assets can be owned/custodied by users from another tenant
- **Root cause:** `DataAssetService.create_asset` and `update_asset` accepted
  `owner_id`/`custodian_id` as raw user UUIDs. The database foreign key only proves the
  user exists globally, not that the user is an active member of the asset's
  organization.
- **Evidence before fix:** real HTTP against local server on port 8020:
  `POST /api/v1/data-observability/assets` in org A with `owner_id`
  `689f8ea5-3ca5-4bfb-806a-e5029223b5cb` from org B returned 201 and response
  persisted that foreign owner on asset `e182b7b1-9c20-450b-93f9-540aa760404d`.
- **Fix:** validate supplied `owner_id` and `custodian_id` against active user +
  active membership in the caller organization on create and update. Explicit `null`
  for non-null scalar update fields now returns a clear 422 before database flush.
- **Evidence after fix:** real HTTP create with foreign `owner_id` returns 422
  `owner_id must be an active organization user`; real HTTP PATCH with foreign
  `custodian_id` returns 422 `custodian_id must be an active organization user`.
- **Files:** app/data_observability/services/data_asset_service.py, tests/unit/test_data_catalog_classify_c73_c74.py
- **Tests:** `.venv/bin/python -m pytest tests/unit/test_data_catalog_classify_c73_c74.py -q --disable-warnings` -> `4 passed`
- **Commit:** TBD
