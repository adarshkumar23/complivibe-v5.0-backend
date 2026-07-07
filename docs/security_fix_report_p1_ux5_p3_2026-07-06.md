# Security fix report — P1 pricing refresh, UX5 share-link lockout, P3 spend-cap decision

Date: 2026-07-06  
Worktrees: `cv-p2-B`, `cv-p2-D`  
Status: fixed, committed, not pushed

---

## FIX 1 — P1: platform-admin gate for POST /pricing/refresh (cv-p2-B)

### Problem
`competitor_pricing_entries/versions` is a single global table, but `POST /pricing/refresh` was gated only by the org-scoped `pricing:manage` permission. Because every self-registered customer's owner role has `pricing:manage`, any customer could overwrite the platform-wide pricing snapshot that every other customer sees.

### Decision
Block customer-owners from touching shared pricing. Reuse the existing `User.is_superuser` flag as the minimal platform-admin marker (it is already used for platform-staff endpoints such as `/admin/rate-limits`).

### Changes
- `app/api/v1/pricing.py`
  - Removed `require_permission("pricing:manage")`.
  - Added `_require_platform_admin()` that checks `current_user.is_superuser` and returns `403` otherwise.
  - `GET /pricing` remains public and unaffected.
- `app/platform/services/competitor_pricing_service.py`
  - `create_snapshot()` now accepts `actor_is_superuser` and records it in the `pricing.snapshot_created` audit metadata.
- `tests/unit/test_pricing_p1.py`
  - Verifies a regular org owner is rejected (`403`).
  - Verifies the same user promoted to `is_superuser=True` can refresh successfully (`201`).
  - Verifies the audit log contains `actor_is_superuser: true`.

### Verification
```text
pytest tests/unit/test_pricing_p1.py -v
======================= 7 passed, 11 warnings in 17.85s =======================
```

Key HTTP-level results:
- Regular org owner → `403` "Platform administrator privileges required"
- Superuser → `201`
- `GET /api/v1/pricing` → `200` for everyone

### Commit
- `a3f0abc fix(P1): gate POST /pricing/refresh to platform admins only`

---

## FIX 2 — UX5: brute-force protection for public share-link passwords (cv-p2-D)

### Problem
The password-check endpoint for shared summary links processed 25 rapid wrong-password attempts in ~9 ms each with no throttling or lockout, and the password comparison was not constant-time.

### Changes
- `app/platform/routers/report_sharing.py`
  - Added `@rate_limiter.limiter.limit("10/minute")` to `POST /shared/{token}/verify`, matching the slowapi pattern already used elsewhere (auth, ingest, SCIM, etc.).
- `app/models/shared_report_link.py`
  - Added `failed_password_attempt_count` and `locked_until` columns.
- `alembic/versions/0246_shared_link_password_lockout.py`
  - New migration adding the two columns.
- `app/platform/services/report_share_service.py`
  - Password comparison now uses `hmac.compare_digest`.
  - Tracks failed attempts per token.
  - After 5 failures, the token is locked for 15 minutes and a `429` with `Retry-After` is returned.
  - Successful authentication resets the failure window.
  - Lockout activation is audited as `report.share_password_lockout`.
- `tests/unit/test_experience_summary_ux5_p2d.py`
  - Added test proving lockout after threshold, correct password works before threshold, and 2-3 typos do not lock out legitimate users.

### Verification
```text
pytest tests/unit/test_experience_summary_ux5_p2d.py -v
======================== 3 passed, 7 warnings in 17.19s ========================
```

Key HTTP-level results:
- 2 wrong guesses → `200` `valid: false` (no lockout)
- Correct password before threshold → `200` `valid: true`
- 6th rapid wrong guess → `429` with `Retry-After`
- Correct password during lockout → `429`

### Commit
- `dafb763 fix(UX5): brute-force protection for shared report link passwords`

---

## DOCUMENT — P3: spend cap is an intentional soft warning (cv-p2-B)

### Decision
The usage spend cap is intentionally a **soft warning**, not a hard stop. Customers must never be blocked from using the product mid-work because of a billing cap. The only automatic side effect of a breached cap is that usage is not synced to the payment processor until the cap is raised or usage drops.

### Changes
- `app/platform/services/usage_billing_service.py`
  - Added explicit comments documenting the deliberate soft-cap behavior.
  - Added `_spend_cap_alert()` helper that produces a clear, human-readable warning message.
- `app/platform/schemas/billing.py`
  - `UsageBillingDashboardRead` and `UsageBillingSyncResponse` now expose `spend_cap_alert: str | None`.
- `tests/unit/test_usage_pricing_p3.py`
  - Confirms the alert is surfaced in both the dashboard and the sync-blocked response, and contains the phrase "soft warning".

### Verification
```text
pytest tests/unit/test_usage_pricing_p3.py -v
... 3 passed (run together with pricing tests: 7 passed, 11 warnings)
```

### Commit
- `dfc6fd4 doc(P3): spend cap is an intentional soft warning, not a hard stop`

---

## Full regression suite

Both worktrees ran the full unit suite to completion with exit code 0.

| Worktree | Command | Result |
|---|---|---|
| cv-p2-B | `pytest tests/unit -q --tb=short` | `EXIT:0` (1,348 tests collected) |
| cv-p2-D | `pytest tests/unit -q --tb=short` | `EXIT:0` (1,341 tests collected) |

Integration tests (`tests/integration/test_postgres_migration_smoke.py`) are documented as a manual/CI PostgreSQL gate and were not run in this session.

---

## Merge readiness

- `cv-p2-B` now contains commits `a3f0abc` and `dfc6fd4`.
- `cv-p2-D` now contains commit `dafb763`.
- No commits have been pushed.
- No production data was touched.
- No new ENUM/ARRAY types introduced.
- Migration ID is well under 63 bytes: `0246_shared_link_lockout` (24 bytes).
- `AuditService.write_audit_log` is used on every state change.

Both worktrees are ready for the merge plan `A → B → C → D` (with B/C renumbered).
