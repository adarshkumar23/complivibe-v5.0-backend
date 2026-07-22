# Access Model — Stage 1c Build Plan (ordered, staged)

**Status:** PLAN ONLY. No code written. Execute stage by stage against **scratch** after review.
**Touches billing (LIVE in prod).** Safe order is mandatory: **grandfather before any gate.**
**Anchors (verified):** migration head `0328`; gate deps `app/core/billing_deps.py`; plans `app/platform/services/billing_service.py` (`DEFAULT_PLANS`, `ensure_default_plans`, `start_trial`); register `app/api/v1/auth.py:108` + `app/platform/services/onboarding_service.py:133`; scheduler `app/core/pbc_scheduler.py` (`register_pbc_scheduler`, `scheduler.add_job`); audit `app/services/audit_service.py` (`write_audit_log`).

**Global test rule (standing):** every stage's tests use the dedicated `complivibe_test_user` on a scratch PG DB (never live `complivibe_user`), and each behavioral test must be proven **failing-first** with the fix stashed (weak-identity-map / dashless-UUID traps). Tear down scratch stacks by exact PID/port, never `pkill -f`.

---

## Dependency order (why this sequence)

```
1c-1 Foundation ──► must land ENTIRELY before 1c-4 (grandfather before gate)
  │   (schema + plan rows + grandfather + start_free)
  ├─► 1c-2 Trial codes      (independent of gating; needs trial plan row from 1c-1)
  ├─► 1c-3 Capacity caps    (needs record_caps in free plan from 1c-1)
  └─► 1c-4 Gating B+C  ◄──── HARD DEPENDENCY on 1c-1 grandfather
        └─► 1c-5 Trial lifecycle (needs gate from 1c-4 for lazy downgrade)
```
1c-2 and 1c-3 can be built/tested in parallel with each other after 1c-1. **1c-4 must never precede 1c-1's grandfather step.**

---

## STAGE 1c-1 — Foundation (schema + plans + grandfather). NO gating yet.

### Built
1. **Migration `0329_access_model_foundation`** (child of `0328`), additive only:
   - Drop/recreate `ck_organizations_subscription_plan` to add `'free'`:
     `subscription_plan IN ('trial','starter','growth','enterprise','usage_flex','free')`.
     (`'trial'` already legal — no change needed for the new trial row.)
   - **No new columns**: `record_caps` rides inside existing `subscription_plans.features` JSONB; `subscription_status` CHECK untouched (`free`/`trial` both use `'active'`, already allowed).
   - Migration does **not** insert plan rows (that's `ensure_default_plans`) and does **not** grandfather (separate explicit step 3 — kept out of the schema migration so it can be verified/aborted independently).
2. **Extend `DEFAULT_PLANS`** (`billing_service.py`) — single source of truth (note: `ensure_default_plans` **overwrites** `features`/`max_*` on every call, so this dict must be exactly right):
   - Add `free` row: `status`-agnostic; `features` = all 13 new domain flags **False**, existing premium flags False, `api_access:False`, `audit_log_days:7`, `record_caps:{"policies":5,"controls":5,"evidence":5,"risks":5}`, `max_*` per matrix.
   - Add `trial` row: **enterprise-equivalent** — all 13 new flags + all existing premium flags **True**, `record_caps:{}` (uncapped), `audit_log_days:730`, `max_*:None`.
   - Add the 13 new flags to `starter/growth/enterprise/usage_flex` per the locked matrix (design doc §1.2). `record_caps:{}` on all paid plans.
3. **GRANDFATHER (must run before 1c-4 exists):**
   - **Pre-flight (prod, read-only, do FIRST):** `SELECT id, name, subscription_plan, subscription_status, trial_ends_at FROM organizations;` — capture the real state; do **not** rely on memory.
   - Data step (idempotent): pin every pre-cutover org to full access:
     `UPDATE organizations SET subscription_plan='enterprise', subscription_status='active' WHERE created_at < :cutover;` (or by captured ids). Enterprise = all flags True + no caps → zero future access loss when gates land.
   - Delivered as a **standalone script** (`scripts/grandfather_existing_orgs.py`), not baked into the schema migration, so it's separately auditable/abortable and re-runnable.
4. **`BillingService.start_free(org_id)`** — new method: `plan='free'`, `status='active'`, `trial_ends_at=None`, flush.
5. **Registration switch:** replace `start_trial(...)` with `start_free(...)` at `app/api/v1/auth.py:108` **and** `onboarding_service.py:133`. (Optionally flip model defaults `organization.py:23-24` to `free`/`active` for safety-by-default on any uncovered path — low-risk, include.)

### Test (scratch PG)
- Run migration up **and** down cleanly on scratch; confirm CHECK now admits `free`.
- `ensure_default_plans()` on a fresh DB creates 5 rows (free/trial/starter/growth/enterprise) with exact feature maps incl. `record_caps` and 13 flags.
- **Grandfather:** seed 2 orgs on `starter/trial` (old defaults) → run script → both become `enterprise/active`, trial_ends_at preserved.
- **Registration:** `POST /auth/register` → new org is `free/active`, `trial_ends_at IS NULL` (assert **not** starter/trial).
- **No behavior change yet:** no endpoint returns 402/403 it didn't before (no gates exist).

### Blast-radius guard
- Purely additive schema; `free`/`trial` unused by any existing row until explicitly set.
- Grandfather runs **before** gating so no existing org can lose access. Idempotent + read-only pre-flight.
- `ensure_default_plans` drift-sync means prod plan rows self-heal to the new maps on first call — verify the maps in code review before deploy (no hand-editing prod rows; they'd revert).

---

## STAGE 1c-2 — Trial-code system

### Built
1. **Model + migration `0330_trial_codes`** (child of `0329`): table `trial_codes` —
   `id` UUID PK; `code_hash` String(64) UNIQUE (SHA-256 hex); `code_prefix` String(12) (non-secret, support); `label` String(64) null; `trial_days` Integer default 14; `is_active` Boolean default True; `redeemed_by_org_id` UUID FK→organizations SET NULL; `redeemed_by_user_id` UUID FK→users SET NULL; `redeemed_at` DateTime(tz) null; `created_at` DateTime(tz) server_default now(). Indexes: `UNIQUE(code_hash)`, `(is_active, redeemed_at)`, `(redeemed_by_org_id)`.
2. **Generation script** `scripts/generate_trial_codes.py` (mirrors `setup_razorpay_plans.py` shape): mint 1000 codes `CV-XXXXX-XXXXX-XXXXX` (Crockford base32, no ambiguous chars) via `secrets`; store **hashed** (`sha256(code.strip().upper())`) + `code_prefix`; write the 1000 **plaintext** codes to one out-of-band CSV (the only copy). Idempotent by `label` (skip/`--force`) so a re-run can't mint another 1000.
3. **Redeem endpoint** `POST /api/v1/billing/redeem-trial-code` (in `platform/routers/billing.py`), authenticated + owner/admin (reuse existing billing permission). Logic in one txn:
   - Hash input → lookup.
   - **Eligibility (one-per-lifetime):** org must be `subscription_plan=='free'` **and** `trial_ends_at IS NULL`; else `409 already_trialed` / `not_eligible`.
   - **Atomic claim:** `UPDATE trial_codes SET redeemed_at=now(), redeemed_by_org_id=:o, redeemed_by_user_id=:u WHERE code_hash=:h AND is_active AND redeemed_at IS NULL RETURNING id`; 0 rows → `404 invalid_or_used_code` (don't distinguish invalid vs used → no enumeration).
   - On success: `start_trial(org_id)` (modified 1c-1-adjacent: sets `plan='trial'`, `status='active'`, `trial_ends_at=now+trial_days`). **Change `start_trial` here** (plan `starter`→`trial`, status `trial`→`active`, accept `trial_days`).
   - `write_audit_log('trial_code_redeemed', org, user, code_prefix)` — never plaintext/hash.
   - Return `get_billing_status`.

### Test (scratch PG)
- Generate N codes → rows hashed, plaintext only in CSV, prefix stored.
- Redeem valid code on a Free org → org becomes `trial/active`, `trial_ends_at=+14d`, code `redeemed_at` set, audit row written.
- **Second redeem of same code** → 404/409, org unchanged (atomic-claim proof: concurrent double-redeem test → exactly one wins).
- **Second trial on same org** (already has `trial_ends_at`) → blocked `already_trialed`, even after manual downgrade to free.
- Failing-first: run redeem test with the atomic-claim `WHERE redeemed_at IS NULL` stashed → prove double-redeem succeeds without it.

### Blast-radius guard
- New table only; no existing table touched. `start_trial` change affects only *future* redemptions (register no longer calls it after 1c-1). Existing trialing orgs already carry `trial_ends_at`; the lazy/sweep logic (1c-5) handles them.

---

## STAGE 1c-3 — Capacity caps (Category A)

### Built
- **`require_capacity(resource: str)`** dependency factory in `app/core/billing_deps.py`: resolve org → `ensure_default_plans` → load plan → `cap = features.get('record_caps',{}).get(resource)`; if `cap` is an int, `COUNT` existing **non-deleted** org rows for that resource (respect each domain's soft-delete/status filter); if `count >= cap` → `402 {"error":"record_cap_reached","resource","cap","upgrade_url"}`; if `cap` absent/None → allow.
- Attach to the **4 create endpoints** (router layer, uniform — covers `controls` inline-ORM create too):
  `compliance_policies.py:164`, `controls.py:135`, `evidence.py:195`, `risks.py:304`.

### Test (scratch PG)
- Free org: create 5 of each resource OK; **6th → 402 record_cap_reached** (each of the 4 independently).
- Trial org and enterprise org: create 10+ of each, no cap (`record_caps:{}`).
- Cap counts only top-level `POST ""` rows — sub-creates (policy versions, evidence file uploads, links) do **not** count toward the cap.
- Deleting one Free record frees a slot (count-based, not high-water-mark).

### Blast-radius guard
- Only the 4 create paths change; reads and all other writes untouched.
- Grandfathered/paid/trial orgs have `record_caps:{}` → dependency is a no-op for them (proven by the trial/enterprise test).
- Known accepted race: concurrent creates could yield 6 not 5 (documented; per-org `FOR UPDATE` counter deferred — not needed for a Free cap).

---

## STAGE 1c-4 — Gating rollout (Categories B + C). LAST — only after 1c-1 grandfather is live.

### Built (use the FINAL gating map exactly)
- **Category C — router-level `require_feature`:** add `dependencies=[require_feature("<flag>")]` to each locked router (same shape as `platform/routers/siem.py:68`). Flags: `ai_governance_module`, `governance_autopilot`, `resilience_module`, `advanced_analytics`, `board_reporting`, `advanced_reporting`, `control_monitoring_module`, `advanced_risk`, `integrations_module`, `privacy_advanced` (whistleblower+legal only — see note), `audit_management`, plus existing `ai_policy_drafting`, `ai_risk_recommendations`, `sso_enabled`, `scim_enabled`, `siem_export`, and the specialized single-module flags (carbon/ip_assets/pam/sod/offboarding/access-certs/trust-center-admin/questionnaires/ip-allowlist/custom-roles).
- **Category B — write-endpoint gating:** add `Depends(require_feature("<flag>"))` to **mutation** endpoints only (POST/PUT/PATCH/DELETE); GETs stay RBAC-only. Domains: frameworks/obligations (`framework_activation`), issues+tasks/workflow (`workflow_management`), attestations (`attestation_management`), exceptions/linking/control-library/templates/risk-read-config (fold under existing bundles), **breach_notifications** (`privacy_basic` = True for Free-view / write-gated), vendors/TPRM (`vendor_management`), reg-alerts/deadlines (view open, manage gated).
- **`require_feature` already chains `require_active_subscription`** → locked/expired orgs get 402 before 403.
- **Do NOT touch** patent/machine scoped-key routers (`patent_ingest_p2/p4`, `patent_exports_p2`, `patent_ingest_p9`, `shadow_ai_signature`, `mlops_ingest`) — controlled by not issuing scoped keys to Free/trial (go-live policy, see below). P3 `policy_derivation` **is** gated (Category C, `ai_governance_module`).
- **Category D — assert ungated:** add a test that iterates D routers and confirms none acquired a gate.

### Test (scratch PG) — the full tier matrix
- **Free org:** can hit all D endpoints; can READ Category B; A-create capped at 5; **blocked (403) on every C router** and on B **writes**. `/api/webhook/razorpay`, `/auth`, `/billing`, `/health`, `trust_center_public` reachable.
- **Trial org:** full access everywhere (enterprise-equiv flags) — no 403 on any C router.
- **Enterprise (grandfathered prod) org:** unaffected — full access; explicit regression proving existing orgs didn't lose anything.
- **Starter/growth:** access per their flag matrix (spot-check a C flag that differs, e.g. `governance_autopilot` False for growth).
- Negative: confirm no D router (esp. webhook/login/billing/public trust center) returns 402/403 for a Free org.

### Blast-radius guard
- **Hard ordering:** this stage is gated on 1c-1 grandfather being deployed — CI/checklist assertion that all prod orgs are `enterprise/active` before merge.
- Router-level for C = fewest edits, lowest per-endpoint review risk.
- The D-ungated assertion test prevents a stray gate breaking payments/login.
- `check_feature_access` returns False on a missing plan row → the 1c-1 seed of `free`+`trial` rows must be confirmed present before gating (any org on an unseeded plan_code would be locked out of everything).

---

## STAGE 1c-5 — Trial lifecycle (expiry → Free)

### Built
- **Lazy downgrade (authoritative)** in `require_active_subscription` (`billing_deps.py`): if `subscription_plan=='trial'` and `trial_ends_at < now` → transition in place: `plan='free'`, `status='active'`, **keep `trial_ends_at`** (blocks re-redeem per one-per-lifetime), flush, then continue as Free. Replaces today's `402 trial_expired` dead-end.
- **Nightly sweep (backstop)** `expire_trials` via `scheduler.add_job` in `app/core/pbc_scheduler.py`: daily, transition all `plan=='trial' AND trial_ends_at < now` orgs → Free (so dormant orgs downgrade without traffic; analytics stay accurate). Reuse `scheduler_lock`/`scheduler_logger` patterns already in that file.
- **Pre-expiry warnings:** sweep (or a companion job) emails via `EmailService` at T-3d / T-1d before `trial_ends_at` (respect existing email send-caps).

### Test (scratch PG)
- Set a trial org's `trial_ends_at` to the past → next gated request lazily downgrades it to `free/active`; **data (policies/controls/etc.) retained**; C routers now 403, B-writes now gated, A-caps now apply (features re-lock correctly).
- Run `expire_trials` job directly against a dormant expired-trial org (no request) → downgraded to Free.
- Re-redeem after expiry → blocked (`trial_ends_at` still set).
- Warning job: org at T-2d gets one warning, not duplicated on re-run.

### Blast-radius guard
- Lazy path is idempotent and only fires for `plan=='trial'` past expiry — never touches paid/enterprise/free orgs.
- Sweep uses the existing scheduler lock (no double-run across workers).
- Grandfathered prod orgs are `enterprise`, never `trial` → untouched by both mechanisms.

---

## GO-LIVE steps (SEPARATE from scratch build — prod config, do NOT bundle into stages)

These are **not** part of the scratch implementation and must be done deliberately against prod:

1. **Razorpay keys** — supply `RAZORPAY_KEY_ID/KEY_SECRET/WEBHOOK_SECRET` and run `scripts/setup_razorpay_plans.py` to replace placeholder plan IDs. Independent of the tier logic; billing endpoints exist but can't transact until this lands. (Free/trial flow works without it; only paid upgrade needs it.)
2. **Grandfather on prod** — run `scripts/grandfather_existing_orgs.py` against prod **before** deploying the 1c-4 gating build (the safe-order lynchpin).
3. **Generate + distribute the 1000 trial codes** — run `generate_trial_codes.py` in prod, secure the CSV out-of-band.
4. **Scoped-key issuance policy** — enforce that patent/machine scoped keys are issued only to paid orgs (the control that "gates" the scoped-key routers, since `require_feature` can't). Confirm the key-issuance path checks org plan.
5. **Prod migration** — apply `0329`/`0330` via the established pre-flight (pip-freeze the venv, not git-diff) per the prod-deploy runbook.

---

## Stage sign-off checklist (review gate before executing each)

- [ ] 1c-1 approved → build; **do not start 1c-4 until grandfather verified on scratch (and later prod).**
- [ ] Final feature-flag names locked (13 new + 5 existing) — confirm exact strings before 1c-1 (they become API contract in `features` JSON).
- [ ] Category B bundle-flag assignment confirmed (which write endpoints map to which of the 13 flags) — needed before 1c-4.
- [ ] `privacy_advanced` split decision (breach → B-view/write-gated vs C) reflected in the map before 1c-4.
- [ ] Prod org SELECT captured and grandfather target (all pre-cutover vs named ids) confirmed.
