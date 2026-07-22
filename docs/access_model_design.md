# Access Model Design — Free / Trial / Paid Tiers (Stage 1b)

**Status:** DESIGN ONLY. No code, no migration written. Review before Stage 1c build.
**Date:** 2026-07-22
**Touches:** billing — LIVE in prod. Blast-radius section is mandatory reading before any build.

---

## 0. Grounding facts (verified against the real codebase)

These shape every decision below; they are not assumptions.

| Fact | Location | Consequence |
|---|---|---|
| Org tier state already exists: `subscription_plan` (String(20), CHECK), `subscription_status` (String(20), CHECK), `trial_ends_at`, `subscription_ends_at` | `app/models/organization.py:23-30` | REUSE. No new org column needed for tier. |
| Plan catalog `subscription_plans` with `features` JSONB + `max_*` columns | `app/models/subscription_plan.py` | EXTEND. Add `free` (and `trial`) rows. |
| Gate deps `require_active_subscription` (402) + `require_feature(name)` (403) | `app/core/billing_deps.py:20-74` | REUSE as the entitlement gate. |
| `check_feature_access` reads `plan.features[feature]`; **returns False if `subscription_plan` has no matching plan row** | `billing_service.py:437-461` | Any org whose `subscription_plan` lacks a `subscription_plans` row is denied *everything*. Critical for grandfathering. |
| **`max_users/max_frameworks/max_ai_systems/max_dsr_per_month` are STORED but NEVER ENFORCED** (only read by the public ROI calculator + plan-list serialization) | grep across `app/` | The 5-record caps are **new work**, not reuse. |
| `start_trial()` sets `subscription_plan="starter"`, `status="trial"`, `trial_ends_at=now+14d` | `billing_service.py:219-227` | Today "trial" == starter entitlements. Must change for the locked flow. |
| Register calls `start_trial()` — new orgs land on **starter/trial**, not free | `app/api/v1/auth.py:108`; also `OnboardingService` at `onboarding_service.py:133` | Both call sites must change to land on Free. |
| `subscription_plan` CHECK = `('trial','starter','growth','enterprise','usage_flex')`; **`'trial'` is allowed but has no plan row** | migration `0251:55-60` | Adding `'free'` needs a CHECK migration. `'trial'` is already legal — we can add a real `trial` plan row with no CHECK change. |
| Only 5 features gated today (`sso_enabled`, `scim_enabled`, `siem_export`, `ai_policy_drafting`, `ai_risk_recommendations`) across 6 routers | multiple | Gating the rest of the domain map is the bulk of the work. |
| VARCHAR(20) on `subscription_plan`/`plan_code` | migrations 0173/0251 | `"free"` (4) and `"trial"` (5) fit. No length change needed. |

---

## 1. Free Plan Definition

### 1.1 Plan matrix (locked: Free = real plan, `plan_code="free"`, `status="active"`)

Five plan rows after this work: **free, trial, starter, growth, enterprise** (usage_flex unchanged). `trial` becomes a *real* row so trial orgs get their own entitlement set independent of the paid ladder.

**Design decision surfaced for review:** what does a **trial** grant? Locked docs say trial should showcase more than Free. Recommendation: **trial = full product** (mirrors enterprise feature flags, but time-boxed 14 days, no record caps). This makes the trial a genuine "try everything" and the drop-to-Free at expiry a real downgrade. Alternative (mirror `growth`) is noted but not recommended — it under-sells.

### 1.2 The `features` map per plan

Existing flags kept as-is; **new domain-bundle flags** added (section 2.2 defines each). `None` = unlimited/allowed (matches existing `check_feature_access` semantics: `None`→True, bool→value). Record caps live under a new nested `record_caps` key (section 1.3).

```
                              free      trial     starter   growth    enterprise
--- existing flags ---
sso_enabled                   False     True      False     True      True
scim_enabled                  False     True      False     False     True
siem_export                   False     True      False     True      True
ai_policy_drafting            False     True      False     True      True
ai_risk_recommendations       False     True      False     True      True
api_access                    False     True      True      True      True
audit_log_days                7         730       90        365       730
support                       none      email     email     priority  dedicated_csm
--- new domain-bundle flags (view/write gates; see 2.2) ---
vendor_management             False     True      True      True      True
audit_management              False     True      True      True      True
attestation_management        False     True      True      True      True
workflow_management           False     True      True      True      True
questionnaire_management      False     True      True      True      True
framework_activation          False     True      True      True      True
advanced_reporting            False     True      False     True      True
board_reporting               False     True      False     True      True
advanced_analytics            False     True      False     True      True
ai_governance_module          False     True      False     True      True
governance_autopilot          False     True      False     False     True
resilience_module             False     True      False     True      True
privacy_advanced              False     True      True      True      True
--- limits (kept for ROI calc + future enforcement) ---
max_users                     3         None      5         25        None
max_frameworks                1         None      3         10        None
max_ai_systems                0         None      2         10        None
max_dsr_per_month             0         None      10        100       None
```

**Free semantics (locked):** capped create (5 each) on the four core domains; **view-only** on standard domains (reads open via RBAC, writes gated by the domain flag = False); premium domains **fully locked** (all endpoints gated, flag = False). Note `api_access=False` for Free (Free is UI-only).

> **`starter` note:** Under the locked model, paid `starter` should behave like a real paid tier (full writes on core/standard domains, no 5-record cap). Its domain flags above are set True accordingly. The 5-record cap applies to **Free only** (section 1.3).

### 1.3 5-record caps — enforcement (NEW mechanism)

The existing `max_*` columns are dead (never enforced). Do **not** try to overload them. Instead:

- Store caps in the plan's `features` JSON under a nested key:
  ```
  "record_caps": {"policies": 5, "controls": 5, "evidence": 5, "risks": 5}
  ```
  Free = 5 each; every other plan = `record_caps: {}` (absent key → uncapped).
- New shared dependency factory in `app/core/billing_deps.py`:
  `require_capacity(resource: str)` → resolves org → loads plan → reads `features["record_caps"].get(resource)`; if an int, `COUNT` existing **non-deleted** org rows for that resource; if count ≥ cap, raise **HTTP 402** `{"error":"record_cap_reached","resource":..,"cap":..,"upgrade_url":..}`.
- **Placement (cleanest seam):** add `Depends(require_capacity("policies"))` etc. to the four bare-collection create endpoints — the **router layer**, uniformly:
  - `app/api/v1/compliance_policies.py:164` `create_policy`
  - `app/api/v1/controls.py:135` `create_control` (note: constructs ORM inline — router-layer dep covers it; a service-layer check would miss it)
  - `app/api/v1/evidence.py:195` `create_evidence`
  - `app/api/v1/risks.py:304` `create_risk`
- **Count scope:** count top-level org rows only (the `POST ""` resource), respecting soft-delete/status filters each domain already uses. Sub-creates (`/{id}/versions`, file uploads, links) are NOT counted.
- **Race note:** two concurrent creates could both pass a count-then-insert check. Acceptable for a Free cap (worst case: 6 not 5). If strictness matters, wrap in `SELECT ... FOR UPDATE` on a per-org counter — deferred, not needed for v1.

### 1.4 Migration (CHECK constraint) — described, not written

One migration, additive:
1. **Extend org plan CHECK** — drop/recreate `ck_organizations_subscription_plan` to add `'free'`:
   `subscription_plan IN ('trial','starter','growth','enterprise','usage_flex','free')`.
   (`'trial'` already present — no change needed for the new trial plan row.)
2. **No** column changes (VARCHAR(20) fits `free`/`trial`; `features`/`max_*` already exist).
3. **No** new columns on `subscription_plans` — `record_caps` rides inside existing `features` JSONB.
4. Plan rows themselves are **not** inserted by the migration — `ensure_default_plans()` seeds/drift-syncs them from `DEFAULT_PLANS` (which we extend). Confirm `ensure_default_plans` is called on the redemption/gate paths (it is — `check_feature_access` calls it first).

Identifier lengths confirmed OK: `free`=4, `trial`=5 ≤ VARCHAR(20); flag names are JSON keys (unbounded).

---

## 2. Gating Rollout Plan

### 2.1 Pattern (confirmed)

Gating a domain = attach `require_feature("<flag>")` to that domain's write (or all) endpoints. Two shapes:

- **View-only domain (Free reads, can't write):** add the dep to **mutation endpoints only** (POST/PUT/PATCH/DELETE). GETs stay behind existing `require_permission` (RBAC) only. Example — vendors:
  ```python
  # app/api/v1/vendors.py  (illustrative shape, not to build yet)
  @router.post("", ...)
  def create_vendor(..., _f: Organization = Depends(require_feature("vendor_management")),
                         _p: Membership = Depends(require_permission("vendors:write"))):
      ...
  # GET endpoints: unchanged (RBAC only) -> Free can view
  ```
- **Fully-locked domain (Free can't even read):** attach at the **router level** via `APIRouter(dependencies=[require_feature("<flag>")])` (same shape already used at `app/platform/routers/siem.py:68`). Covers every endpoint incl. GET.

`require_feature` already chains `require_active_subscription`, so a locked-out or expired org gets 402 before the 403 feature check — desired.

### 2.2 Domain → flag mapping (the bulk of the work — review this table)

**Category A — Core capped (no feature flag; `require_capacity` instead).** Free = read + 5-cap create; paid = uncapped.
| Domain | Routers |
|---|---|
| Policies / Controls / Evidence / Risks | `compliance_policies.py`, `controls.py`+`common_controls.py`+`technical_controls.py`+`control_*`, `evidence.py`+`evidence_*`, `risks.py`+`risk_*` |

**Category B — Standard, view-only for Free (gate WRITE endpoints; flag False for Free, True trial+all paid).**
| Flag | Domain | Routers |
|---|---|---|
| `vendor_management` | Vendors / third-party / supply chain | `vendors.py`, `subprocessors.py`, `vendor_concentration_risk.py`, `vendor_mitigation.py`, `vendor_remediation_portal.py`, `vendor_supply_chain.py` |
| `audit_management` | Audit & assurance | `audit_engagements.py`, `audit_findings.py`, `audit_schedules.py`, `pbc_items.py`, `compliance/routers/audit_*`, `pbc_requests.py`, `auditor_portal.py` |
| `attestation_management` | Attestations / certifications | `attestations.py`, `attestation_tokens.py`, `employee_attestations.py`, `access_certifications.py`, `recertification.py`, `certification_programs.py`, `compliance/routers/policy_attestations.py` |
| `workflow_management` | Tasks / SLA / escalation / issues | `tasks.py`, `sla_policies.py`, `escalation_policies.py`, `issues.py`, `issue_settings.py`, `issue_sync.py` |
| `questionnaire_management` | Inbound questionnaires (NOT public trust center) | `inbound_questionnaires.py`, `questionnaire_responses.py`, `questionnaire_templates.py`, `trust_center_admin.py`, `customer_commitments.py` |
| `framework_activation` | Framework activation/content | `frameworks.py`, `framework_content.py`, `framework_pack_reviews.py`, `obligations.py`, `oscal.py` (activation gated; also honors `max_frameworks` later) |
| `privacy_advanced` | Breach / whistleblower / legal | `breach_notifications.py`, `whistleblower.py`, `legal_matters.py` |

**Category C — Premium, fully locked for Free (router-level gate; flag False Free & often False starter).**
| Flag | Domain | Routers |
|---|---|---|
| `ai_governance_module` | Entire AI-governance package | `app/ai_governance/routers/*` (ai_systems, ai_reviews, guardrails, eu_act, iso42001, nist_rmf, atlas, shadow_ai, mlops*, monitoring, llm_observability, third_party_ai, governance_graph, recommendations, risk_signals, contracts, policy_derivation, diagnostics), plus `app/api/v1/ai_*` (ai_governance, ai_systems, ai_drafting, ai_usage_compliance, ai_vendor_assessments, content_provenance, synthetic_datasets, training_*, non_human_identities) |
| `governance_autopilot` | Autopilot / governance overrides | `governance.py`, `governance_overrides.py`, `governance_override_templates.py`, `automation.py` |
| `resilience_module` | DORA / BCM / crisis / OT-ICS / geopolitical | `dora.py`, `bcm.py`, `crisis_management.py`, `resilience_testing.py`, `ot_ics.py`, `geopolitical_risk.py`, `incident_analytics.py` |
| `board_reporting` | Board scorecard | `compliance/routers/board_scorecard.py` |
| `advanced_analytics` | Graph / insights / score explanation | `entity_graph.py`, `compound_insights.py`, `score_explanation.py`, `risk_quantification.py` |
| `advanced_reporting` | Custom reports / exports / report sharing | `custom_reports.py`, `exports.py`, `platform/routers/report_sharing.py` |
| `siem_export` *(exists)* | SIEM | `platform/routers/siem.py` |
| `sso_enabled` *(exists)* | SSO | `auth/routers/sso.py` |
| `scim_enabled` *(exists)* | SCIM | `auth/routers/scim.py` |
| `ai_policy_drafting` *(exists)* | Policy AI drafting | `compliance/routers/policy_drafting.py`, `copilot_draft.py` |
| `ai_risk_recommendations` *(exists)* | Risk AI recs | `compliance/routers/compliance_risk_recommendations.py` |

**Category D — Never gated (stay open to Free / public / infra):**
`auth.py` (login/register), `billing.py`, `webhooks.py` (`/api/webhook/razorpay`), `health.py`, `trust_center_public.py`, `roi_calculator.py`, `pricing.py`, `dashboard.py`/`compliance_dashboard.py` (read summaries), `users.py`/`memberships.py`/`organizations.py`/`roles.py` (org self-admin), `experience.py`, `onboarding.py`, `sessions.py`, `ip_allowlist.py`, `admin_email_config.py`/`email_config.py`, `search.py` (read), `regulatory_alerts.py`/`compliance_deadlines.py` (read), `patent_ingest_*`/`patent_exports_*` (scoped-key auth, orthogonal to tiers).

> Category C is the largest touch surface. Recommend building it **router-level** (one `dependencies=[...]` per router) to minimize per-endpoint edits and review risk. Category B is per-endpoint (writes only) — more surgical, more edits.

---

## 3. Trial-Code System Design

### 3.1 New table `trial_codes`

Single table, new migration. No ENUM (CHECK/plain columns per standing rule). UUID PK mixin.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID PK | no | mixin |
| `code_hash` | `String(64)` | no | **SHA-256 hex** of the plaintext code, UNIQUE. Lookup key. |
| `code_prefix` | `String(12)` | no | first chars of plaintext (e.g. `CV-AB12`) for support/debug — non-secret |
| `label` | `String(64)` | yes | batch/campaign tag (e.g. `launch-2026-07`) |
| `trial_days` | `Integer` | no | default 14; lets future batches vary length |
| `is_active` | `Boolean` | no | default True; lets ops disable a code without deleting |
| `redeemed_by_org_id` | UUID FK→organizations (SET NULL) | yes | set on redemption |
| `redeemed_by_user_id` | UUID FK→users (SET NULL) | yes | set on redemption |
| `redeemed_at` | `DateTime(tz)` | yes | NULL = unused (single-use gate) |
| `created_at` | `DateTime(tz)` | no | `server_default now()` |

Constraints/indexes: `UNIQUE(code_hash)`, index on `(is_active, redeemed_at)` for redemption lookup, index on `redeemed_by_org_id`.
Single-use is enforced by `redeemed_at IS NULL` + atomic claim (3.2), not just the unique constraint.

### 3.2 Redemption flow

**Endpoint:** `POST /api/v1/billing/redeem-trial-code` (add to `platform/routers/billing.py`).
**Auth:** authenticated user + org context; require an owner/admin membership (reuse `require_permission("billing_...")` — pick/seed a `billing:manage` or reuse the existing billing subscribe permission). Body: `{"code": "<plaintext>"}`.

**Validation & effect (all in one transaction, audited):**
1. Hash input (`sha256(code.strip().upper())`) → `code_hash`.
2. **Eligibility guard (anti-farming):** org must currently be `subscription_plan == "free"` **and** `trial_ends_at IS NULL` (never trialed). If `trial_ends_at` is already set (trial used, even if expired & dropped back to free) → 409 `already_trialed`. If org is on a paid plan → 409 `not_eligible`.
3. **Atomic claim** to avoid double-redeem races:
   `UPDATE trial_codes SET redeemed_at=now(), redeemed_by_org_id=:org, redeemed_by_user_id=:user WHERE code_hash=:h AND is_active=true AND redeemed_at IS NULL RETURNING id`.
   0 rows → 404/409 `invalid_or_used_code` (don't distinguish invalid vs used, to avoid enumeration).
4. On success: call **`BillingService.start_trial(org_id)`** (modified — section 3.4) which sets `plan="trial"`, `status="active"`, `trial_ends_at = now + trial_days`.
5. `write_audit_log` (action `trial_code_redeemed`, org, user, code_prefix — never the plaintext or hash).
6. Return `get_billing_status(org)`.

### 3.3 Generation (1000 codes)

Script `scripts/generate_trial_codes.py` (mirrors `scripts/setup_razorpay_plans.py` shape).

- Generate 1000 codes with `secrets.token_urlsafe` formatted human-friendly, e.g. `CV-XXXXX-XXXXX-XXXXX` (Crockford base32, no ambiguous chars). ~20 chars, fits any distribution channel.
- **Storage recommendation: HASHED.** Store only `sha256` + `code_prefix`. Rationale: a `trial_codes` table leak with plaintext = 1000 free 14-day trials mintable by an attacker; hashing makes the DB copy useless (same reasoning as API/ingest keys elsewhere in this codebase). Trade-off: plaintext exists **only** at generation time.
- Script writes the 1000 plaintext codes to a **single out-of-band file** (`scratchpad`/secure CSV: `code,label`) for distribution, and inserts the hashed rows. Print a reminder that the CSV is the only copy.
- Idempotency: re-running with the same batch `label` should skip existing (check by `label` count) or require `--force`, so an accidental re-run doesn't mint another 1000.

### 3.4 `start_trial` change

Change `BillingService.start_trial` (`billing_service.py:219-227`):
- `subscription_plan = "trial"` (was `"starter"`) — trial now maps to the real `trial` plan row.
- `subscription_status = "active"` (was `"trial"`) — **decision:** keep it a normal `active` status so `require_active_subscription` passes cleanly and there's no separate "trial" status branch to reconcile. Trial-ness is expressed by `subscription_plan=="trial"` + `trial_ends_at`. *(Alternative: keep `status="trial"`; then `check_feature_access`'s `status in (active,trial)` still passes. Either works; `active` is simpler. Flag for review.)*
- Accept optional `trial_days` param (default `settings.TRIAL_DAYS`) so codes can set length.
- **Do not** call `start_trial` from register/onboarding anymore (section 4).

### 3.5 Expiry → drop back to Free

Locked: at expiry the org returns to Free. Two coordinated mechanisms:
- **Lazy (authoritative):** in `require_active_subscription`, if `subscription_plan=="trial"` and `trial_ends_at < now`, transition in-place → `plan="free"`, `status="active"`, keep `trial_ends_at` (so re-redeem is blocked), flush, then continue as a Free org. This guarantees correctness on next request without waiting for a job, and replaces today's 402 `trial_expired` dead-end.
- **Sweep (backstop):** a daily APScheduler job `expire_trials` (reuse existing scheduler infra) transitions any `plan=='trial' AND trial_ends_at < now` orgs, so dormant orgs downgrade even without traffic and analytics stay accurate.

---

## 4. Registration Flow Change

New orgs must land on **Free, active, no trial** (locked). Change both org-creation call sites:

1. `app/api/v1/auth.py:108` — replace `BillingService(db).start_trial(organization.id)` with a new `BillingService.start_free(organization.id)`.
2. `app/platform/services/onboarding_service.py:133` — same replacement.

New method `BillingService.start_free(org_id)`:
```
org.subscription_plan  = "free"
org.subscription_status = "active"
org.trial_ends_at       = None
```
Model defaults (`plan="starter"`, `status="trial"`) remain but are now always overwritten by `start_free` at both creation paths — consider (later, non-blocking) changing the model defaults to `free`/`active` so any un-covered creation path is safe-by-default. Not required for this stage.

Result: `register → Free (active) → redeem code → start_trial → 14-day trial → expiry → Free`. Matches locked flow exactly.

---

## 5. Risks / Blast Radius (billing is LIVE in prod)

### 5.1 What breaks existing orgs if we're careless

The danger is **not** the schema (adding `free` to a CHECK is additive/safe). The danger is **gating**: the moment `require_feature(...)` lands on Categories B/C, every existing org is evaluated against its *current* plan's flags.

- Today, orgs created via register/onboarding are on **`plan="starter"`, `status="trial"`** (start_trial). `starter` has most premium flags **False**. So the instant Category C gates deploy, those orgs **lose access** to AI-gov, autopilot, resilience, board, analytics, advanced reporting — even though they have it today (ungated).
- Any org whose `subscription_plan` has **no matching `subscription_plans` row** is denied *everything* by `check_feature_access` (returns False on missing plan). If any prod org sits on `plan='trial'` today (legal per CHECK, but no row exists until we add it), adding the `trial` row *fixes* them; but until seeded they're exposed.

### 5.2 Prod org state — VERIFY before build (do not assume)

Session memory suggests the live demo org was upgraded to **enterprise**, and PulseHealth exists on seed data. **This must be confirmed against the live DB, not memory**, before gating ships:

```sql
SELECT name, subscription_plan, subscription_status, trial_ends_at FROM organizations;
```

Whatever it returns drives 5.3. If any prod org is on `starter`/`trial`/`free` or an unseeded plan, it MUST be grandfathered first.

### 5.3 Grandfathering (mandatory, ship-order-critical)

**Sequence is non-negotiable:** the Free plan + `trial` plan seed + grandfather data-migration must ship **before or in the same release as** any `require_feature` gate. Never gate first.

1. **Seed rows first:** ship `DEFAULT_PLANS['free']` and `DEFAULT_PLANS['trial']` + the CHECK migration; deploy; confirm `ensure_default_plans()` created both rows. No behavior change yet (no new gates).
2. **Grandfather migration:** pin every **pre-existing** org to a full plan so gating can't strip access:
   ```sql
   UPDATE organizations
   SET subscription_plan='enterprise', subscription_status='active'
   WHERE created_at < :cutover;   -- i.e. all orgs that predate the access model
   ```
   (Or target the 2 known prod orgs by id.) Enterprise = all flags True + no caps → zero access loss. Document that this is a deliberate grandfather, not a billing entitlement.
3. **Then** ship gating (Categories B/C) + `require_capacity` (Category A). New self-registered orgs get Free via `start_free`; existing orgs are safely on enterprise.
4. `start_free`/`start_trial` changes and register-flow change ride with step 3 (they only affect *new* orgs and *new* redemptions).

### 5.4 Other blast-radius notes

- **`ensure_default_plans` drift-sync is aggressive:** it overwrites `features`/`max_*`/prices on every call from `DEFAULT_PLANS` (billing_service.py:170-200). So the `DEFAULT_PLANS` dict is the single source of truth — the free/trial flag matrix (section 1.2) must be exactly right there; no hand-editing plan rows in prod (they'd be reverted).
- **Trial status semantics:** if we keep `start_trial` setting `status="active"` (recommended), the existing 402 `trial_expired` branch in `require_active_subscription` becomes reachable only for legacy `status=="trial"` orgs — reconcile it with the lazy-downgrade logic (3.5) so no org gets a hard 402 dead-end.
- **Race on caps:** Free 5-cap is count-then-insert (5.1 note) — worst case 6 rows. Acceptable; documented.
- **Public/webhook paths must stay open:** confirm none of the Category D routers accidentally inherit a gate (esp. `/api/webhook/razorpay`, `trust_center_public`, `health`, `auth`) — a stray router-level gate there would break payments/login.
- **RBAC still applies underneath:** `require_feature` is additive to `require_permission`. A Free user still needs the RBAC permission to read a domain; gating only removes the *entitlement*. No RBAC changes in this stage.

---

## 6. Reuse / Extend / Build summary

| Piece | Verdict |
|---|---|
| Org tier columns (`subscription_plan`/`status`/`trial_ends_at`) | **REUSE** as-is |
| `require_feature` / `require_active_subscription` gate | **REUSE** as the entitlement gate |
| `subscription_plans` + `features` JSON | **EXTEND**: add `free`+`trial` rows, add domain-bundle flags + `record_caps` |
| `DEFAULT_PLANS` | **EXTEND** with free/trial + new flags (source of truth) |
| Razorpay integration | **REUSE** (unchanged; still needs live keys separately) |
| `start_trial` | **MODIFY**: plan→`trial`, status→`active`, param days; drop from register |
| Register / Onboarding | **MODIFY**: call new `start_free` |
| CHECK constraint | **MIGRATE**: add `'free'` |
| 5-record caps | **BUILD NEW**: `require_capacity` dep + `record_caps` in features (existing `max_*` are dead, don't reuse) |
| Trial codes | **BUILD NEW**: `trial_codes` table + redeem endpoint + hashed generation script |
| Trial expiry → Free | **BUILD NEW**: lazy downgrade in gate + `expire_trials` sweep job |
| Grandfathering | **BUILD NEW**: seed-first, then pin existing orgs to enterprise, then gate |

### Open decisions for reviewer sign-off
1. **Trial entitlement level** — full/enterprise-equivalent (recommended) vs growth-equivalent.
2. **Trial status value** — `active` (recommended, simpler) vs keep `trial`.
3. **`starter` behaviour** — confirm starter is uncapped and gets Category B write access (matrix assumes yes).
4. **Grandfather target** — all pre-cutover orgs → enterprise (recommended) vs only the 2 named prod orgs.
5. **Category C granularity** — router-level lock (recommended, fewer edits) vs per-endpoint.
6. **Anti-farming rule** — block re-redeem once `trial_ends_at` is ever set (recommended) vs allow N trials.
```
