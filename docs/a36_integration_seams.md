# A3.6 External Engine Integration Seams
# CompliVibe v5.0 — Authoritative Field Reference
# Last verified: 2026-06-27

## IMPORTANT
These are the ACTUAL field names in the
production schema. Any prior documentation
referring to different field names is superseded
by this document.

## Seam 1 — compliance_policies table
The external A3.6 engine reads from this table.
NEVER rename these columns:

  id                UUID   PK
  organization_id   UUID   tenant scope
  title             VARCHAR  policy name
                    (NOTE: field is 'title' not 'name')
  content_url       TEXT   policy document reference
                    (NOTE: field is 'content_url' not 'content')
  status            VARCHAR  lifecycle state

## Seam 2 — controls table
NEVER rename these columns:

  id                UUID   PK
  organization_id   UUID   tenant scope
  title             VARCHAR  control name
                    (NOTE: field is 'title' not 'name')
  description       TEXT   control description
  status            VARCHAR  operational status

## Seam 3 — compliance_policy_control_links table
NEVER rename or restructure this table.
  (NOTE: full table name is 'compliance_policy_control_links'
   not 'policy_control_links')

  policy_id   UUID FK -> compliance_policies.id
  control_id  UUID FK -> controls.id

## Seams 4-7 — Code contracts (confirmed intact)

Seam 4 — require_permission():
  Location: app/core/deps.py
  Signature: require_permission(permission_code: str)
    -> Callable[..., Membership]
  NEVER change this signature.

Seam 5 — AuditService.write_audit_log():
  Location: app/services/audit_service.py
  Signature: write_audit_log(self, *, action,
    entity_type, organization_id, actor_user_id=None,
    entity_id=None, before_json=None,
    after_json=None, metadata_json=None,
    ip_address=None, user_agent=None)
  NEVER change this signature.

Seam 6 — seed_service.py structural pattern:
  Location: app/services/seed_service.py
  Pattern: SeedService with ensure_* methods
  NEVER change this structural pattern.

Seam 7 — app/api/v1/router.py include pattern:
  Location: app/api/v1/router.py
  Pattern: consistent include_router() calls
  NEVER break this pattern.

## Reserved (never create in core)
  Table name:  policy_mapping_suggestions
  Permission:  policy_suggestions:view

## Known Historical Migration Exceptions
The following early v5.0 migrations (written
before the no-ENUM / no-ARRAY rules were
strictly enforced) contain rule violations.
They CANNOT be altered without breaking the
migration chain. They are permanent exceptions.

  0092_key_risk_indicators.py     — contains ENUM
  0093_risk_appetite_framework.py — contains ENUM
  0101_policy_template_library.py — contains ARRAY

All migrations from 0102 onward follow the
no-ENUM / no-ARRAY rules correctly.
These three files are grandfathered.
