# Consolidated Fix Report — Parts A–D

This report covers the multi-wave bug-fix effort on the CompliVibe backend
performed across this session, building on the pre-existing Wave 2 Fixes
1–5 checkpoint. It documents every fix, its root cause, the files changed,
the real evidence used to verify it, and the final scope/test-suite status.

Git commits for this session, in order:

```
4158b84  Checkpoint: Wave 2 Fixes 1-5 (pre-existing, verified as sanity check)
107ff62  Fix 6/7/8: Auditor Portal scope inheritance, scheduler admin crash, AI draft content loss
7aec057  Fix A: remove remaining router collision on /compliance/policy-exceptions base path
51cc064  Fix B: confirm TPRM answer_text scoring + fix scoring-rule endpoint discoverability
99f81ab  Fix C/D: issue resolution_note silent loss + systemic enum-error enrichment
7432309  Part D items 1-5: guardrail enforcement, signal emission, unique_actors, residual clamp, entity risk
3253d04  Part D items 6-10: schedule scoping, vendor-assessment complete, template versioning, SoD symmetry
```

---

## Part A — Fixes 6, 7, 8

### Fix 6 — Auditor Portal scoping non-functional (HIGH)

**Root cause:** `AuditorPortalService.create_invitation` validated
`scoped_framework_ids` only against the organization's global framework
list (`_validate_framework_ids`), never against the parent engagement's own
`scope_framework_ids`. There was no inheritance logic either — an
invitation with no explicit `scoped_framework_ids` defaulted to an empty
list rather than the engagement's own scope. Net effect: any invitation
could be scoped arbitrarily wide (up to "every framework in the org"),
completely defeating the "framework-based" scoping the feature claims to
provide.

**Fix:** `app/compliance/services/auditor_portal_service.py` —
framework-based scoping now inherits the engagement's `scope_framework_ids`
by default, and any explicit `scoped_framework_ids` must be a subset of the
engagement's own scope (422 otherwise).

**Evidence:** Created an engagement scoped to Framework A only.
- Explicit invitation request for Framework B → `422` rejected.
- Default (no `scoped_framework_ids`) invitation → inherited `[A]` only.
- Linked one control under Framework A's obligation, another under
  Framework B's. Hit `GET /audit-portal/controls` with the invitation's
  real token → returned **exactly 1 control** (the in-scope one).
- Re-verified live on Postgres (`complivibe_e2e`).

### Fix 7 — Scheduler admin endpoint crashes (HIGH)

**Root cause:** `apscheduler.job.Job.next_run_time` is not set as an
attribute on a `Job` object until the scheduler has actually started and
computed trigger fire times. `SchedulerAdminService.get_job_status`
accessed `job.next_run_time` directly, raising `AttributeError` → 500 in
the (very real, always-hit-once) window right after app startup.

**Fix:** `app/compliance/services/scheduler_admin_service.py` — switched to
`getattr(job, "next_run_time", None)`.

**Evidence:** Reproduced the crash with a real, unstarted
`BackgroundScheduler` + `CronTrigger`; confirmed `AttributeError` before the
fix and `None` (no crash) after. Live `GET /admin/scheduler/jobs` → `200`
immediately after cold Postgres-backed startup (the exact race window of
the original bug). Added a regression test using a real APScheduler job
object rather than the pre-existing `_FakeJob` test double (which always
set `next_run_time` and so never exercised the bug).

### Fix 8 — AI draft apply doesn't persist content (HIGH)

**Root cause:** `PolicyDraftingService.accept_draft` used
`description=description or row.draft_output` — if the caller supplied any
non-empty `description`, the actual AI-generated draft body
(`row.draft_output`) was discarded entirely and never persisted anywhere.
No `content` column exists on `CompliancePolicy` (and none was added, to
respect the locked `content_url`/`title`/`status` seam fields).

**Fix:** `app/compliance/services/policy_drafting_service.py` — the draft
body is now always persisted as a real `CompliancePolicyVersion` snapshot
via the existing policy-versioning system, regardless of whether a
caller-supplied `description` is also present. Router now returns
`policy_version_id`.

**Evidence:** Accepted a draft **with** a caller-supplied description (the
exact bug condition) — confirmed the full AI-generated text present in
`content_snapshot_json.content` on the new policy version. Verified on
SQLite and Postgres.

---

## Part B — Fixes A, B

### Fix A — Duplicate router collision audit (CRITICAL)

The prior session's audit (documented in
`docs/router_collision_audit_findings.md`) found and fixed 18 collisions
across 6 path groups via **static parsing** of `include_router()` calls.
This session performed an **independent re-audit using runtime
introspection** of the live `app.main.app` route table — walking FastAPI's
`_IncludedRouter`/`original_router` tree and accumulating each level's
`include_context.prefix` — which is immune to the blind spots of static
parsing.

**Finding:** 2 collisions the static-parse audit missed: `GET`/`POST
/compliance/policy-exceptions` (the *base* list/create paths) were still
dual-registered between `app.compliance.routers.policy_exceptions` (v2,
live) and `app.api.v1.policy_exceptions` (dead). The earlier pass only
checked the `/{exception_id}`-suffixed paths on this router and incorrectly
listed the base list/create endpoints as "unique, preserved."

**Fix:** `app/api/v1/policy_exceptions.py` — removed the dead
`create_policy_exception`/`list_policy_exceptions` handlers and their
now-unused imports.

**Evidence:** Independent runtime scan confirmed **0 remaining collisions
across 1613 unique `(method, path)` routes**. Live request/response
confirmed `POST`/`GET /compliance/policy-exceptions` now consistently
return the v2 schema, on both SQLite and Postgres.

### Fix B — TPRM questionnaire scoring false-negative (HIGH)

**Root cause investigation:** The scoring logic itself
(`QuestionnaireScoringService._effective_answer_text`, which prefers
`answer_text` and falls back to `answer_value`) was already correct in the
current codebase — this had evidently already been fixed in an earlier
pass. The genuine remaining bug was **discoverability**: the scoring-rule
configuration endpoint was mounted at `/compliance/scoring-rules`, breaking
the naming convention every sibling questionnaire endpoint follows
(`/compliance/questionnaire-templates`, `/compliance/questionnaire-responses`,
`/compliance/inbound-questionnaires`) — genuinely unreachable by guessing
under any `/questionnaire*` path.

**Fix:** `app/api/v1/scoring_rules.py` — renamed router prefix to
`/compliance/questionnaire-scoring-rules`.

**Evidence:** Submitted a questionnaire answer using **only** the
documented `answer_text` field (no `answer_value`) — SQLite: 100/100 across
10 high-risk answers; Postgres: 15/100 for one answer, confirming the score
was never silently zero. Confirmed the renamed scoring-rules endpoint
reachable on Postgres. Added a permanent regression test
(`test_a52_scoring_uses_answer_text_only_field_not_just_answer_value`).

---

## Part C — Fixes C, D

### Fix C — Silent notes/free-text field loss

Full grep-based audit (an Explore agent scanned ~74 candidate
service functions accepting `*_notes`/`*_reason`/`*_comment` params across
the whole `app/` tree) of the pattern: a Pydantic schema accepts a
free-text field, but the service layer never assigns it to the persisted
row.

**Findings — 4 of 5 previously-known instances already fixed** (verified
live, not assumed):
- DSR `response_notes` — persisted at `dsar_service.py:381`. ✅
- Consent `withdrawal_reason` — persisted at `consent_service.py:223`. ✅
- Customer commitment `fulfillment_notes` — persisted at
  `customer_commitment_service.py:369`. ✅
- Frameworks applicability wrong-named field — not reproducible; router
  uses `.model_dump()`, guaranteeing schema/service field-name consistency. ✅

**1 genuine bug found and fixed:** Issue `resolution_note` on status
transitions (`app/compliance/services/issue_service.py`,
`transition_issue`). The assignment `row.resolution_note = ...` only
happened inside the `resolved → closed` branch — a caller supplying a
resolution note on any other transition (`open → investigating`,
`investigating → resolved`, etc.) had it silently discarded.

**Fix:** `resolution_note` is now persisted whenever supplied, on any
transition, while still only being *required* on the `resolved → closed`
transition (unchanged behavior there).

**Evidence:** Real before/after evidence across two different transitions
(`open→investigating`, `investigating→mitigating`) with distinct note text
each time, confirmed retrievable via `GET`. Reproduced the pre-fix bug via
`git stash` to confirm the assertion genuinely failed on the old code.
Verified on SQLite and Postgres.

Also chased and ruled out several false-positive leads without touching
working code: control-recommendation `apply_notes` on the
`map_existing_control` path (persisted via a trailing common code block the
initial audit agent missed), vendor archive `reason`, DPIA/DPA
`review_notes`/`risk_assessment_notes`.

### Fix D — Undocumented enum rejection (systemic fix)

**Root cause investigation:** This codebase has almost no true Pydantic
`Literal`/`Enum` fields. Two distinct mechanisms account for essentially
all "enum-like" validation in the codebase:

1. **~150 hand-rolled checks** of the form `if value not in ALLOWED_SET:
   raise HTTPException(..., detail="Invalid X")` scattered across services
   in every domain (AI Governance, Data Observability, Controls,
   Governance Automation, Frameworks, Reports, Retention, Privacy,
   Compliance, etc.) — each with its own hand-written, non-enriched error
   message.
2. **~285 Pydantic `Field(pattern="^(a|b|c)$")` fields** whose default
   FastAPI 422 error only echoes the raw regex string, not a clean list of
   valid values.

**Fix — single systemic mechanism covering both, applied globally rather
than patching each field:**

- `app/core/validation.py` (new) — `InvalidChoiceError` +
  `validate_choice()`. A global `@app.exception_handler(InvalidChoiceError)`
  in `app/main.py` always returns `{detail, field, value, valid_options}`.
  Mechanically swept ~134 hand-rolled "not in" checks across the whole
  codebase onto this shared path (via a scripted regex transform, verified
  by full-suite compile + test run), preserving each call site's original
  status code (400 vs 422) via an explicit `status_code` kwarg.
- A second global `@app.exception_handler(RequestValidationError)` in
  `app/main.py` post-processes Pydantic's own validation errors: for
  `string_pattern_mismatch` errors on simple alternation patterns
  (`^(a|b|c)$`), and for `enum`/`literal_error` types, it extracts and
  attaches a `valid_options` list to that specific error entry — covering
  all ~285 pattern-based fields uniformly with zero per-field changes.

**Evidence:** Verified against 4 real endpoints spanning all 4 named
domains (AI Governance EU AI Act classification, Data Observability/
Governance retention policy, Controls test definitions, Governance
Automation rules), on both SQLite and Postgres — every case returns a
`valid_options` list. Permanent regression test:
`tests/unit/test_enum_validation_enrichment.py`.

---

## Part D — 10 smaller confirmed findings

| # | Finding | Resolution | Files |
|---|---|---|---|
| 1 | AI Governance `data_scope` guardrail was a hardcoded no-op in `BuiltInPolicyEngine.evaluate` (fell through to `permit` unconditionally) despite the DB `CheckConstraint` treating it as a first-class guardrail type | Implemented real enforcement — `allowed_data_categories` allowlist check against `action_context.data_categories` — matching the exact pattern of the other 5 guardrail types (financial_limit, geographic_scope, user_scope, action_scope, approval_required) | `app/platform/policy_engine/builtin_engine.py` |
| 2 | Risk-signal auto-creation on monitoring threshold breach only fired for `bias_parity_gap` (hardcoded check); `output_drift` breaches never created any signal | Both metric types now map to their matching `AIRiskSignal.signal_type` (`bias_signal` / `output_distribution_shift`) | `app/ai_governance/services/ai_monitoring_service.py` |
| 3 | Data Observability `access/summary.unique_actors` only counted distinct `actor_id`, silently ignoring rows where only `actor_external` (machine/ETL ingest) was populated — always undercounting for machine-ingest-heavy orgs | Sums distinct `actor_id` + distinct `actor_external` (disjoint identifier spaces on the same log table) | `app/data_observability/services/access_monitoring_service.py` |
| 4 | Risk `residual_score` could exceed `inherent_score` for `factor_based` risks — logically impossible. Root cause: residual is derived from `likelihood * impact`, which is a completely different, unrelated basis from the factor-based weighted `inherent_score` formula | Clamped `residual_score` to never exceed `inherent_score` in all 3 auto-derivation call sites (risk creation, control link/unlink recompute, event-driven recalculation listener — `RiskScoringService.compute_residual` now takes `inherent_score` and clamps against it) plus the manual PATCH path (`RiskService.calculate_scores` result clamped at the `app/api/v1/risks.py` call site) | `app/api/v1/risks.py`, `app/compliance/services/risk_scoring_service.py`, `app/compliance/services/risk_recalculation_listener.py` |
| 5 | Entity risk scoring for `business_unit` entities returned a fake "Business unit model not yet implemented" placeholder label, even though the real `BusinessUnit` model (with a `name` field) has existed since migration 0176; the underlying risk-linkage query already worked correctly behind a stale `hasattr()` defensive check that was always-true dead code | Real `BusinessUnit` name lookup wired in, matching the pattern used for vendor/framework/asset entity types; removed the dead `hasattr` branch | `app/compliance/services/entity_risk_score_service.py` |
| 6 | Frameworks applicability-answer schema allegedly silently drops a wrong-named field | **Confirmed already correct** — no bug found. The router does `[item.model_dump() for item in payload.answers]` before calling the service, guaranteeing field-name consistency by construction. No fix needed. | — |
| 7 | Audit & Assurance `GET /audit-schedules/{id}/history` validated the schedule belonged to the org, but the actual `AuditEngagement` query had **no schedule filter at all** — it returned every engagement in the org regardless of which schedule (if any) created it, leaking unrelated engagements | Added migration `0199` (`audit_engagements.source_schedule_id`, nullable FK → `audit_schedules.id`, `ON DELETE SET NULL`); wired through `AuditEngagementService.create_engagement` (new optional kwarg) and the schedule auto-create sweep job; `get_schedule_history` now filters by `source_schedule_id` | `alembic/versions/0199_audit_engagement_source_schedule_link.py`, `app/models/audit_engagement.py`, `app/compliance/services/audit_engagement_service.py`, `app/compliance/services/audit_schedule_service.py` |
| 8 | TPRM `POST /vendors/{id}/assessments/{id}/complete` took **no request body at all** — `overall_rating`/`findings_summary` could never be set at completion time, only via a separate PATCH before completing | Added `VendorAssessmentCompleteRequest` (optional `overall_rating`, `findings_summary`) and wired it through; audit log now records the final rating/findings | `app/schemas/vendor_assessment.py`, `app/api/v1/vendors.py` |
| 9 | Policy Management: template apply (`POST /policy-templates/{id}/apply`) wrote the template body only into the new policy's `notes` field — same silent-loss-of-real-content pattern as the AI-draft-apply bug (Fix 8) | Now creates a real `CompliancePolicyVersion` via the existing versioning system, identical fix pattern to Fix 8; response now includes `policy_version_id` | `app/compliance/services/policy_template_service.py`, `app/compliance/routers/policy_templates.py`, `app/compliance/schemas/policy_template_library.py` |
| 10 | Policy Management: policy exceptions enforced segregation-of-duties (requester ≠ approver) on **approve** but had no equivalent check on **reject** — asymmetric enforcement let a requester unilaterally reject (close out) their own exception | Added the same `requested_by == actor` check to `reject_exception_v2` (409 Conflict, matching approve's error style) | `app/compliance/services/policy_exception_service.py` |

**Test fallout from item 10:** two pre-existing tests
(`test_a32_approval_rejection_flow_and_immutability`,
`test_a32_dashboard_and_policy_summary_metrics`) exercised the exact
previously-buggy same-actor-reject path and needed updating to use a
distinct approver — this is expected: they were asserting the old buggy
behavior. Updated to match the existing approve-path pattern in the same
test file (which already used a separate `approver_headers` actor). Added
a new dedicated regression test,
`test_verify_sod_applies_symmetrically_to_reject_not_just_approve`.

---

## Verification summary

**Real evidence, not assumptions, for every fix.** Every item in this
report was verified with an actual HTTP request/response (or, for the
router-collision audit, an independent runtime route-table scan), and for
several items the pre-fix bug was independently reproduced (via `git
stash`) to confirm the fix genuinely changed observable behavior rather
than being a no-op.

**Test suite:** run after every part. Zero new failures at every
checkpoint. The only failures ever seen were 4 pre-existing,
network-dependent tests hitting the real Groq API
(`test_real_groq_platform_default_policy_draft` and 3 siblings in
`test_copilot_draft_sprint2_p1.py` / `test_compliance_risk_recs_sprint2_p3.py`)
— confirmed via `git stash` baseline comparison to fail identically without
any of this session's changes (Groq's live API was intermittently falling
back to Azure during this session, unrelated to any code change here).

**Database scope:** every fix verified on the disposable SQLite test DB
(`tests/` suite) **and** re-verified against a live server backed by the
real disposable Postgres database `complivibe_e2e` (confirmed via `SELECT
current_database()` before every Postgres session). Migration `0199` was
additionally confirmed to apply cleanly on Postgres via `alembic upgrade
head`. The production `complivibe` database was never touched at any
point in this session.

**Scope:** no files were touched outside
`/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend`.

---

## What's resolved vs. what may still remain open

**Resolved this session:** All items explicitly listed in Parts A, B, C,
and D of the original task — Fixes 6/7/8, Fix A (router collisions, both
the originally-known 3 and 2 additional ones found this session), Fix B
(TPRM scoring + discoverability), Fix C (silent field loss — 1 new genuine
instance beyond the 4 already-fixed), Fix D (systemic enum-error
enrichment, applied far more broadly than the 4 named domains), and all 10
Part D smaller findings.

**Not covered by this session** (out of the original scope given to this
effort, or explicitly noted as unresolved during it):
- The full "new customer simulation" walkthrough (16-agent scorecard
  exercise) queued after this fix effort — not yet started.
- Any bugs outside the specific findings list handed to this session. The
  systemic Fix D sweep covered every hand-rolled enum check and
  pattern-restricted field found via grep across the whole `app/` tree at
  the time of the sweep, but a codebase of this size may still have
  isolated instances following slightly different code shapes that a
  regex-based sweep wouldn't catch — the global exception handlers will
  automatically cover any of those the moment they're touched, but
  existing untouched call sites using non-standard phrasing were not
  individually audited beyond the patterns identified.
