# Phase 2 TPRM Intelligence Report

Date: 2026-07-05

Branch: `phase2-tprm-goal`

Scope: T1-3 through T1-6 in this worktree only. No push was performed.

## Commits

- `855c40d` - Add nth-party vendor risk propagation flags
- `5dccabd` - Add vendor criticality weighted scoring
- `51ee5e1` - Add vendor concentration risk detection
- `b07e35f` - Add public vendor remediation portal

## Design Decisions

- Supply-chain visibility uses the existing dedicated vendor-to-vendor supply-chain model, not the GDPR/privacy subprocessor table. The subprocessor API remains a Privacy/GDPR processor concept; nth-party operational dependency visibility belongs in `vendor_supply_chain_links`, `vendor_supply_chain_alerts`, and durable first-party vendor risk flags.
- Vendor criticality scoring is separate from manual vendor risk-score creation. It adds organization-configurable business-criticality drivers and updates the cached vendor tier with audit evidence.
- Vendor remediation portal follows the Auditor Portal token pattern: random plaintext token returned once, SHA-256 hash stored, scoped expiring bearer access, public endpoints without a CompliVibe account, and persisted expiry/revocation state.
- Concentration risk creates a Risk Register entry through `RiskService.create_risk_from_service`, not by duplicating risk creation logic.

## Files Changed

- `alembic/versions/0228_t13_supply_chain_flags.py`
- `alembic/versions/0228_vendor_criticality_scoring.py`
- `alembic/versions/0229_vendor_concentration_risk.py`
- `alembic/versions/0230_vendor_remediation_portal.py`
- `app/api/v1/risks.py`
- `app/api/v1/router.py`
- `app/api/v1/vendor_concentration_risk.py`
- `app/api/v1/vendor_remediation_portal.py`
- `app/api/v1/vendors.py`
- `app/compliance/services/vendor_remediation_portal_service.py`
- `app/models/__init__.py`
- `app/models/vendor.py`
- `app/models/vendor_concentration_risk.py`
- `app/models/vendor_criticality.py`
- `app/models/vendor_remediation_portal_token.py`
- `app/schemas/vendor.py`
- `app/schemas/vendor_concentration_risk.py`
- `app/schemas/vendor_criticality.py`
- `app/schemas/vendor_remediation_portal.py`
- `app/services/risk_service.py`
- `app/services/seed_service.py`
- `app/services/vendor_concentration_risk_service.py`
- `app/services/vendor_criticality_service.py`
- `app/services/vendor_supply_chain_service.py`
- `tests/unit/test_tprm_intelligence_satellite.py`
- `tests/unit/test_vendor_concentration_risk_t1_6.py`
- `tests/unit/test_vendor_criticality_scoring_t1_4.py`
- `tests/unit/test_vendor_remediation_portal_t1_5.py`
- `PHASE2_TPRM_INTELLIGENCE_REPORT.md`

## Permission Codes Added

- `vendor_criticality:read`
- `vendor_criticality:manage`
- `vendor_concentration_risk:read`
- `vendor_concentration_risk:manage`
- `vendor_remediation_portal:read`
- `vendor_remediation_portal:manage`

Existing dedicated supply-chain codes confirmed and reused only for supply-chain endpoints:

- `vendor_supply_chain:read`
- `vendor_supply_chain:manage`

## Web Research Sources

- NIST Cybersecurity Framework 2.0, GV.SC-04: suppliers are known and prioritized by criticality.
  `https://www.nist.gov/cyberframework`
- NIST SP 800-161 Rev. 1: C-SCRM risk should be contextualized for critical operations and enterprise risk exposure.
  `https://csrc.nist.gov/pubs/sp/800/161/r1/upd1/final`
- FFIEC IT Examination Handbook, Outsourcing Technology Services: outsourcing/service-provider risk management guidance.
  `https://ithandbook.ffiec.gov/it-booklets/outsourcing-technology-services`
- U.S. DOJ/FTC 2023 Merger Guidelines, Guideline 1: HHI concentration convention and `1800` highly concentrated threshold.
  `https://www.justice.gov/atr/merger-guidelines/applying-merger-guidelines/guideline-1`
- Interagency Guidance on Third-Party Relationships: Risk Management: higher-risk/critical third-party activities and subcontractor oversight.
  `https://www.federalregister.gov/documents/2023/06/09/2023-12340/interagency-guidance-on-third-party-relationships-risk-management`

## Feature Evidence

### T1-3 Supply Chain Visibility

- Migration/model/service/router/schema present: `0218_vendor_supply_chain.py`, `0228_t13_supply_chain_flags.py`, `vendor_supply_chain` model/service/router/schema, and vendor read fields.
- Graph traversal is depth-limited and cycle-aware.
- A->B->C->A cycle was verified not to crash.
- Nth-party degraded security signal on C propagated a durable first-party flag to A:
  - `nth_party_risk_flag: true`
  - `nth_party_risk_severity: high`
  - `nth_party_risk_signal_type: security_rating_degraded`
- Audit rows verified for:
  - `vendor_supply_chain.link_created`
  - `vendor_supply_chain.alert_created`
  - `vendor_supply_chain.nth_party_flag_updated`

Verifier: independent T1-3 verifier reported PASS with real HTTP/TestClient evidence.

Focused command:

```bash
.venv/bin/pytest -q tests/unit/test_tprm_intelligence_satellite.py::test_t1_3_supply_chain_graph_detects_cycle_and_rejects_bad_links tests/unit/test_tprm_intelligence_satellite.py::test_t1_3_supply_chain_propagates_nth_party_signal_to_first_party
```

Result: `2 passed`.

### T1-4 Criticality-Weighted Risk Scoring

- Migration/model/service/router/schema present.
- Missing profile returns computed default:
  - `revenue_dependency_pct: 0.00`
  - `data_volume_tier: none`
  - `operational_criticality: low`
  - `substitutability_score: 1`
  - `criticality_score: 10`
  - `criticality_tier: low`
- Settings and profiles use dedicated `vendor_criticality:*` permissions.
- State changes write audit logs.

Manual formula verification:

```text
weights = .4/.3/.2/.1
revenue 60% -> 60/20 = 3.0
data high -> 4
operational critical -> 5
substitutability -> 5
weighted score = (3*.4 + 4*.3 + 5*.2 + 5*.1) / 1.0 = 3.9
0-100 projection = round(3.9/5*100) = 78
tier = critical
```

Verifier: independent T1-4 verifier reported PASS with HTTP evidence for default profile, settings update, profile update, score `78`, tier `critical`, and audit actions.

Focused command:

```bash
.venv/bin/pytest -q tests/unit/test_vendor_criticality_scoring_t1_4.py tests/unit/test_vendor_risk_scoring_phase95.py
```

Result: `8 passed`.

### T1-5 Public Vendor Remediation Portal

- Migration/model/service/router/schema present.
- Internal token endpoints use only `vendor_remediation_portal:*` permissions.
- Public endpoints require only `Authorization: Bearer <portal_token>`.
- Plaintext token is returned once; only SHA-256 hash is stored.
- Wrong token returns `401`.
- Expired token returns `410` with `Portal token expired` and persists token status `expired`.
- Revoked token returns `403`.
- Scoped actions prevent access to unscoped/internal actions.
- Vendor evidence submission creates evidence, updates action/case state, and writes audit rows.

Verifier: independent T1-5 verifier reported PASS with real HTTP/DB evidence for no-account portal access, invalid/expired/revoked tokens, scoped actions, evidence side effects, and audits.

Focused commands:

```bash
.venv/bin/pytest -q tests/unit/test_vendor_remediation_portal_t1_5.py
.venv/bin/pytest -q tests/unit/test_trust_ai_mitigation_a56_a57_a58.py
```

Results: `4 passed` and `3 passed`.

### T1-6 Concentration Risk

- Migration/model/service/router/schema present.
- Endpoints use dedicated `vendor_concentration_risk:*` permissions.
- HHI threshold is `1800`, stored with source metadata.
- Breach creates one Risk Register entry through `RiskService.create_risk_from_service`.
- Recompute without new data does not create a duplicate risk because the detection stores `risk_id`.
- Audit rows verified for `risk.created` and `vendor_concentration_risk.recomputed`.

Verifier: independent T1-6 verifier reported PASS with standalone HTTP/DB evidence:

- First recompute:
  - `status: breach`
  - `hhi_score: 3877`
  - `threshold_hhi_score: 1800`
  - `risk_created: True`
  - one generated Risk Register row
  - one `risk.created` audit
- Second recompute:
  - `risk_created: False`
  - `state_changed: False`
  - generated risk count remained `1`

Focused command:

```bash
.venv/bin/pytest -q tests/unit/test_vendor_concentration_risk_t1_6.py tests/unit/test_vendors_phase93.py tests/unit/test_risks_phase23.py tests/unit/test_partD_residual_clamp.py
```

Result: `16 passed`.

## Consolidated Verification

Phase 2 focused mandatory-edge-case suite:

```bash
.venv/bin/pytest -q tests/unit/test_tprm_intelligence_satellite.py::test_t1_3_supply_chain_graph_detects_cycle_and_rejects_bad_links tests/unit/test_tprm_intelligence_satellite.py::test_t1_3_supply_chain_propagates_nth_party_signal_to_first_party tests/unit/test_vendor_criticality_scoring_t1_4.py tests/unit/test_vendor_remediation_portal_t1_5.py tests/unit/test_vendor_concentration_risk_t1_6.py
```

Result: `11 passed`.

Full regression suite:

```bash
.venv/bin/pytest -q
```

Result: completed with two failures, both outside the changed Phase 2 surface:

- `tests/unit/test_copilot_draft_sprint2_p1.py::test_refine_draft_real_calls_revision_history_and_org_scoping`
- `tests/unit/test_copilot_draft_sprint2_p1.py::test_inline_suggestions_real_calls_for_policy_control_risk_and_status_updates`

Both failures assert `provider_used == "groq"` but the configured provider path returned `azure`. This branch changed no Copilot, draft, AI provider, Groq, or Azure files (`git diff --name-only 535f98f..HEAD | rg 'copilot|draft|llm|groq|azure|ai_drafting|suggest'` returned no matches). The failures are therefore recorded as unrelated to Phase 2 changes.

## Alembic

`alembic heads` result:

```text
0230_vendor_remediation_portal (head)
```

Single head confirmed after linearizing migrations:

`0228_t13_supply_chain_flags -> 0228_vendor_criticality_scoring -> 0229_vendor_concentration_risk -> 0230_vendor_remediation_portal`

## Guardrails

- No new ENUM or ARRAY types were added.
- No hard deletes were introduced.
- State changes write `AuditService.write_audit_log`.
- Migration IDs are under 63 bytes.
- No new third-party libraries were added; `THIRD_PARTY_LICENSES.md` did not require changes.
- Work remained in `/home/ubuntu/complivibe-v4.0/complivibe-worktree-phase2-goal`.
- No push was performed.
