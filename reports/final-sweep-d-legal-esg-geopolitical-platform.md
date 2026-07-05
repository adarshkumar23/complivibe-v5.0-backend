# Final Sweep D: Legal, ESG, Geopolitical, Platform

Worktree: `/home/ubuntu/complivibe-v4.0/complivibe-sweep-d`  
Branch: `final-sweep-d`  
Base refreshed to main: `66f779d Document local dev vault setup`  
Alembic head/current: `0244_fair_bayesian (head)`  
Real env copied from backend: `.env` includes `VAULT_ADDR=http://127.0.0.1:8210` and `VAULT_TOKEN=dev-root-token`.

## Verification Summary

This sweep used real HTTP requests through the FastAPI test client, direct SQLAlchemy DB assertions for side effects, adversarial same-class cross-tenant tests, and full regression runs. Three read-only subagents audited separate slices inside this worktree only; their high-confidence findings were reproduced and fixed where scoped.

Final test evidence:

- Focused security regression set: passed.
- Broad D-slice suite: passed.
- Failed observability dependency rerun after installing declared runtime packages: passed.
- Final full suite: `python -m pytest tests/ -q --disable-warnings` passed.
- Only skip: existing PostgreSQL migration smoke test skipped because `POSTGRES_TEST_DATABASE_URL` is not set.

No migrations were added. No hard deletes were used. `AuditService.write_audit_log` call sites were preserved.

## Fixes Made

1. Legal matters now validate `owner_user_id` against active membership in the current organization on create and update.
   - Before: Org A could create/update a Legal Matter owned by Org B's user ID.
   - After: HTTP 422 and no row mutation; regression test asserts DB state.

2. SCIM active/deprovision handling is tenant-local.
   - Before: one org's SCIM deactivate toggled global `users.is_active/status`, disabling the same shared user in other orgs.
   - After: SCIM toggles the org membership first and only disables the global user when no other active memberships remain.

3. Billing status and `rate-limits/my-limits` now require membership in the requested org.
   - Before: a valid JWT plus another org's `X-Organization-ID` could read tenant billing/rate-limit data.
   - After: both return 403 for non-member org headers.

4. OIDC discovery and JWKS fetches reject internal/private URL targets before network fetch.
   - Before: admin-configured discovery/JWKS URLs were SSRF candidates.
   - After: `assert_public_http_url` guards discovery and callback-time JWKS fetches; regressions cover loopback URLs.

5. SAML SSO no longer accepts unsigned forged assertions through the regex fallback.
   - Before: any posted XML/string containing an email could authenticate if SSO was active.
   - After: unsigned fallback returns no email and callback rejects it. Remaining caveat: this is not full cryptographic SAML validation; see residual risks.

6. DORA ICT register now validates cross-tenant references and completes the requested chain.
   - Before: `owner_id` was checked only against global users and `vendor_id` was not validated; DORA gaps created a Risk only.
   - After: owner must be an active org member, vendor must belong to the org, and a DORA gap creates one idempotent Risk plus one idempotent Issue row with audit evidence.

## Feature Verdicts

### Legal / IP / Provenance

| Feature | Verdict | Evidence |
| --- | --- | --- |
| Legal Matter Management | SOLID after fix | HTTP CRUD/link/close happy path passes; cross-org risk link returns 404; cross-org owner create/update now returns 422 with no DB row/mutation; audit rows verified. |
| IP/Model Licensing Registry | SOLID | HTTP create/list/read/update paths pass; linked AI system references are same-org validated; cross-org reference tests pass. |
| C2PA Content Provenance | SOLID | Verify/read flows pass; tenant-scoped record read returns 404 cross-org; invalid provenance input rejected. |
| Training Data Rights Management | SOLID | HTTP dataset rights flows pass; linked AI system same-org validation and adversarial cross-org tests pass. |
| Synthetic Data Governance | SOLID | HTTP synthetic dataset governance flows pass; source dataset linkage is org-scoped; no orphan/cross-org source accepted. |

### ESG

| Feature | Verdict | Evidence |
| --- | --- | --- |
| ESG Disclosure Templates | SOLID | Template seed/generate flow passes through real HTTP; readonly denial and DB-backed idempotency tests pass. |
| XBRL Export | SOLID | Export job creation passes; invalid datapoints and SSRF taxonomy targets rejected; report lookup is tenant-scoped. |
| Carbon Accounting | SOLID | Reading ingest/dashboard/correction flows pass; DB rows verified; org-scoped idempotent correction logic reviewed. |
| Connector Marketplace | WEAK | Org enablement is tenant-scoped and tested. Catalog mutation remains globally effective while gated by ordinary org connector write permission; this needs product/security authority decision for platform-admin gating. |

### Geopolitical / Workforce

| Feature | Verdict | Evidence |
| --- | --- | --- |
| Geopolitical Risk Monitoring | SOLID | Signal ingest/list/summary/vendor exposure paths pass; vendor and business unit filters reject cross-org references. |
| OT/ICS Convergence Monitoring | SOLID | Agent/asset/finding ingest/resolve paths pass; linked data assets and findings are org-scoped; cross-org resolve returns 404. |
| AI-Usage Policy Compliance | SOLID | Bulk run/gap/summary tests pass; archived systems excluded from bulk/gaps. Static review noted stale single-read possibility after archive, but no cross-tenant read/write was found in this slice. |
| Training & Awareness Analytics | SOLID | Record ingest/summary passes; assigned user and BU must be active same-org references; cross-org tests pass. |

### Platform / Security / Administration

| Feature | Verdict | Evidence |
| --- | --- | --- |
| Organizations | SOLID | Register/current org flows and org header scoping covered by auth/org tests. |
| Users & Memberships | SOLID | Membership creation/list/update permissions pass; cross-org membership assumptions rejected via RBAC dependencies. |
| Roles & Custom Roles | SOLID | Custom role CRUD/assignment tests pass; dedicated permission checks preserved. |
| Authentication | SOLID | Register/login/me/RBAC/audit tests pass; inactive users blocked. |
| SSO (SAML) | WEAK after partial fix | Unsigned forged assertion acceptance is fixed and regression-tested. Full signed assertion validation against configured certificate/issuer/audience/timestamps remains a required hardening item. |
| SSO (OIDC) | SOLID | Discovery/config/login/callback validation tests pass; invalid state/nonce/claims/signature rejected; internal discovery/JWKS URL regressions pass. |
| SCIM Provisioning | SOLID after fix | Token lifecycle and org isolation pass; shared-user deprovision now leaves other org membership active and global user active, with DB assertions. |
| Sessions | SOLID | Session/IP allowlist tests pass. |
| Audit Logs | SOLID | Auth, legal, DORA, billing, and chain tests assert audit rows. |
| Rate Limits | SOLID after fix | Admin defaults/override/my-limits pass; non-member org header now gets 403. |
| SIEM Export | SOLID | Config/export tests pass. |
| IP Allowlist | SOLID | Session/IP allowlist coverage passes. |
| Email Outbox & Templates | SOLID | SES/email template/preference tests pass. |
| Webhooks | SOLID | SSRF checks are enforced on create/update and delivery-time revalidation; webhook/offboarding tests pass. |
| Onboarding | SOLID | Onboarding workflow tests pass. |
| Offboarding | SOLID | Reassignment/offboarding tests pass; SCIM deprovision still triggers offboarding when appropriate. |
| Billing & Subscriptions | SOLID after fix | Plan/status/subscribe/invoices/webhook tests pass; non-member status read now gets 403. |
| Scheduler Admin | SOLID | Scheduler admin tests pass. |
| Security Scan Ingestion | SOLID | C1/C2 ingest tests pass. |
| Trust Center | SOLID | Static review found tenant scoping around policy publishing; related platform tests pass. |
| Non-Human Identity | SOLID | Owner/member validation tests pass. |
| PAM | SOLID | Session/owner scoping tests pass. |
| Access Certification | SOLID | Certification target/user scoping tests pass. |
| SoD | SOLID | Permission fix remains covered; static review noted non-member detect returns empty rather than 404, but no cross-tenant write/read leak was reproduced. |

## Cross-Feature Chains

| Chain | Verdict | Evidence |
| --- | --- | --- |
| Sanctions hit -> vendor risk tier -> concentration recompute | SOLID | Existing chain test passed; DB-backed vendor risk tier and concentration recompute assertions pass. |
| DORA finding -> risk register/issue entry | SOLID after fix | DORA critical gap now creates real Risk and Issue rows, with idempotency and audit assertions. |
| T1-3 nth-party flag -> T1-4 criticality re-score | SOLID | Chain test passed; nth-party context changes criticality read/re-score output without cross-org leakage. |
| T4-17 policy gap -> AI system flagged | SOLID | AI-usage compliance tests pass for gap computation and archived exclusion. |
| Whistleblower report -> investigator workflow | SOLID | Platform/admin angle reconfirmed: investigator permission routing works through Users/Memberships; list/reply/status and cross-org invisibility tests pass. |

## Residual Risks / Not Fixed

- SAML SSO remains WEAK until full `python3-saml` validation is wired for issuer, audience, ACS/destination, timestamps, and configured certificate signature verification. This sweep blocked the live forged unsigned assertion bug, but did not implement the complete SAML validation stack.
- Connector catalog writes remain a product/security decision: catalog entries are global, but ordinary org connector write permission can mutate schema/status affecting other org enablements. The safe direction is a platform-admin-only permission model plus regression tests.
- AI usage single-system latest-check reads may return stale historical checks after an AI system is archived. Bulk/gap paths exclude archived systems and no cross-tenant leak was found.

## Changed Files

- `app/services/legal_matter_service.py`
- `app/auth/services/scim_service.py`
- `app/auth/services/sso_service.py`
- `app/auth/services/oidc_config_service.py`
- `app/auth/services/oidc_service.py`
- `app/platform/routers/billing.py`
- `app/platform/routers/rate_limits.py`
- `app/compliance/services/dora_service.py`
- Regression tests in `tests/unit/test_*`

## Final Status

Ready for review. Do not merge without reviewer acknowledgement of the residual SAML and connector catalog risks.
