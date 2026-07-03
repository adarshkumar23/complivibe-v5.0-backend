# Router Collision Audit Findings

## Background

A full audit of `app/api/v1/router.py` was performed to identify every
`APIRouter` mounted at an overlapping HTTP path. The audit found **18
duplicate endpoint registrations** across 6 path groups under `/api/v1/compliance`.
For each group, the router that was registered **first** in
`app/api/v1/router.py` was the live implementation; the later registration
was unreachable for the colliding paths and produced structurally different
response shapes depending on import order.

The fix strategy was:

* Keep the **first-registered (currently live)** router unchanged.
* Remove only the colliding endpoint definitions from the **later-registered
  (shadowed)** router so the duplicate path disappears.
* If a shadowed router became entirely dead because every one of its
  endpoints collided, its `include_router()` registration was removed.
* Unique, non-colliding endpoints on the shadowed router were preserved so
  no test coverage or live functionality was lost.

## Audit Method

A script parsed every `api_router.include_router(...)` call in
`app/api/v1/router.py`, resolved each imported router module, extracted the
router's `prefix` and every `@router.<method>("...")` decorator, and built a
map keyed by `(HTTP method, full path)`. Any key with more than one handler
was flagged as a collision.

No collisions were found outside `/api/v1/compliance` after correcting for
sub-string router-variable matches (e.g. `router` vs `systems_router`).

## Collisions Fixed

### 1. `/compliance/attestation-campaigns`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `POST /compliance/attestation-campaigns` | `compliance_policy_attestations.router` | `employee_attestations.router` |
| `GET /compliance/attestation-campaigns` | `compliance_policy_attestations.router` | `employee_attestations.router` |
| `GET /compliance/attestation-campaigns/{campaign_id}` | `compliance_policy_attestations.router` | `employee_attestations.router` |
| `POST /compliance/attestation-campaigns/{campaign_id}/attest` | `compliance_policy_attestations.router` | `employee_attestations.router` |

**Why compliance router is live:** It is registered at line 215, before
`employee_attestations` at line 275. Existing tests in
`test_attestations_exceptions_sprint3_p1.py` rely on its response shape
(`AttestationSummaryResponse` with `content_hash`, `declined_count`, etc.).

**Unique endpoints preserved on `employee_attestations.router`:**
`/attestation-campaigns/dashboard`, `PATCH /{campaign_id}`,
`DELETE /{campaign_id}`, `GET /{campaign_id}/completion`,
`POST /{campaign_id}/reminders`, `POST /{campaign_id}/exempt/{user_id}`,
`POST /{campaign_id}/remind/{user_id}`, `/attestation-records/me`,
`/attestation-records/user/{user_id}`, and
`/policies/{policy_id}/attestation-summary`.

**Files changed:**

* `app/api/v1/employee_attestations.py` — removed the 4 colliding endpoint
  definitions.

### 2. `/compliance/policy-exceptions`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `GET /compliance/policy-exceptions/{exception_id}` | `compliance_policy_exceptions.router` | `policy_exceptions.router` |
| `POST /compliance/policy-exceptions/{exception_id}/approve` | `compliance_policy_exceptions.router` | `policy_exceptions.router` |
| `POST /compliance/policy-exceptions/{exception_id}/reject` | `compliance_policy_exceptions.router` | `policy_exceptions.router` |

**Why compliance router is live:** It is registered at line 216, before
`policy_exceptions` at line 283.
`test_attestations_exceptions_sprint3_p1.py` relies on the v2 approve/reject
payload (`expiry_date`) and `expired` sweep behavior.

**Unique endpoints preserved on `policy_exceptions.router`:**
`POST /policy-exceptions`, `GET /policy-exceptions`,
`GET /policy-exceptions/dashboard`, `PATCH /{exception_id}`,
`DELETE /{exception_id}`, and `/policies/{policy_id}/exception-summary`.

**Files changed:**

* `app/api/v1/policy_exceptions.py` — removed the 3 colliding endpoint
  definitions.

### 3. `/compliance/audit-findings`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `GET /compliance/audit-findings/summary` | `compliance_audit_findings.router` | `audit_findings.router` |
| `GET /compliance/audit-findings/{finding_id}` | `compliance_audit_findings.router` | `audit_findings.router` |

**Why compliance router is live:** It is registered at line 221, before
`audit_findings` at line 280.
`test_pbc_audit_findings_sprint3_p4.py` relies on the v2 response shape
(from `app.compliance.schemas.pbc_audit_findings.AuditFindingResponse`).

**Note on merging:** Both routers implement real, different features, but
almost all of those features live on **non-colliding** paths
(e.g. v1's `POST /`, `/{id}/transition`, `/{id}/link-risk`,
`/bulk-transition`, `/{id}/create-issue`; v2's
`/audits/{audit_id}/findings`, `/{id}/remediation`, `/{id}/resolve`,
`/{id}/close`, `/{id}/accept-risk`). The only colliding paths were
`/summary` and `/{finding_id}`. Those two v1 endpoints were unreachable in
practice and are removed; all other endpoints from both implementations
remain mounted and reachable.

**Files changed:**

* `app/api/v1/audit_findings.py` — removed the 2 colliding endpoint
  definitions.

### 4. `/compliance/policy-templates`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `GET /compliance/policy-templates` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/categories` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/clones` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/frameworks` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/slug/{slug}` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/{template_id}` | `compliance_policy_templates.router` | `policy_templates.router` |
| `GET /compliance/policy-templates/{template_id}/stats` | `compliance_policy_templates.router` | `policy_templates.router` |
| `POST /compliance/policy-templates/{template_id}/clone` | `compliance_policy_templates.router` | `policy_templates.router` |

**Why compliance router is live:** It is registered at line 217, before
`policy_templates` at line 282. All of `policy_templates.router`'s endpoints
were shadowed, so the entire router registration was removed.

**Files changed:**

* `app/api/v1/router.py` — removed `policy_templates` from the
  `app.api.v1` import block and removed its `include_router()` call.
* `app/api/v1/policy_templates.py` — left in place; no longer mounted.

### 5. `/compliance/issues/{issue_id}/policy-links`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `GET /compliance/issues/{issue_id}/policy-links` | `policy_issue_links.router` | `issues.router` |

**Why `policy_issue_links.router` is live:** It is registered at line 284,
before `issues` at line 309.
`test_policy_issue_links_a35.py` relies on this endpoint.

**Unique endpoints preserved on `issues.router`:** the colliding path was
only one of many issue endpoints; all others (CRUD, transitions, RCA,
suggestions, SLA, control-links, etc.) remain mounted.

**Files changed:**

* `app/api/v1/issues.py` — removed the colliding `GET /{issue_id}/policy-links`
  endpoint definition.

### 6. `/compliance/policies/{policy_id}/violation-rate`

| Collision path | Live router (kept) | Shadowed router (fixed) |
|---|---|---|
| `GET /compliance/policies/{policy_id}/violation-rate` | `compliance_policy_issue_links_v2.router` | `compliance_policies.router` |

**Why `compliance_policy_issue_links_v2.router` is live:** It is registered
at line 219, before `compliance_policies` at line 270. Both
`test_policy_issue_links_sprint3_p3.py` and
`test_issue_links_a66_a67.py` exercise this endpoint and pass through the v2
handler (`PolicyIssueLinkService.get_policy_violation_rate`).

**Unique endpoints preserved on `compliance_policies.router`:** all policy
CRUD, versions, approvals, control links, and summaries remain mounted.

**Files changed:**

* `app/api/v1/compliance_policies.py` — removed the colliding
  `GET /{policy_id}/violation-rate` endpoint definition and the now-unused
  `PolicyViolationRateRead` import.

## Verification

After the changes, the collision audit script reports **0 remaining
endpoint collisions** and the following test files still pass:

* `tests/unit/test_employee_attestations_a31.py`
* `tests/unit/test_attestations_exceptions_sprint3_p1.py`
* `tests/unit/test_policy_exceptions_a32.py`
* `tests/unit/test_audit_portal_findings_a43_a44.py`
* `tests/unit/test_pbc_audit_findings_sprint3_p4.py`
* `tests/unit/test_policy_templates_a33.py`
* `tests/unit/test_policy_templates_risk_links_sprint3_p2.py`
* `tests/unit/test_policy_issue_links_a35.py`
* `tests/unit/test_policy_issue_links_sprint3_p3.py`
* `tests/unit/test_issue_links_a66_a67.py`
* `tests/unit/test_issue_log_a61.py`

## Scope Notes

* No router source files were deleted; only duplicate endpoint definitions
  or fully-shadowed `include_router()` registrations were removed.
* No production database was touched. Tests run against the project's
  disposable SQLite test DB (`sqlite+pysqlite:///./test.db`).
