# Runbook: re-issue per-subsystem inbound ingest keys (migration 0317)

## What changed
Six inbound machine-ingest subsystems used to authenticate their `X-CompliVibe-Key`
against **one shared key** — the OpenMetadata / data-lineage integration key. A key
leaked from any one (e.g. a PAM push agent) authenticated all of the others for that
org. Migration `0317_subsystem_ingest_keys` gives each subsystem its **own** key:

| subsystem | `key_type` | inbound endpoint(s) |
|-----------|-----------|---------------------|
| Data lineage (OpenLineage/OpenMetadata push) | `lineage` | `POST /data-observability/lineage/openmetadata/ingest` |
| Cookie scanner | `cookies` | `POST /privacy/cookie-registry/scan-report` |
| Consent events | `consent` | `POST /privacy/consent/inbound` |
| Security ingest | `security` | `POST /integrations/security/ingest/*` |
| Access monitoring | `access_monitoring` | `POST /data-observability/access-monitoring/ingest` |
| PAM sessions | `pam` | `POST /pam/sessions` |

## Why re-issuance is required (no silent break avoidance)
The old shared key's **raw value is unrecoverable** (only its SHA-256 hash was ever
stored, inside the encrypted OpenMetadata config). The migration therefore does **not**
backfill — copying the old hash into every subsystem row would recreate the exact
sharing this closes. **Until new keys are issued and distributed, inbound ingest for an
affected org returns HTTP 401.** This is a deliberate, breaking cutover; distribute new
keys before or immediately after deploy.

## Steps
1. **Deploy** the code + run `alembic upgrade head` (creates `subsystem_ingest_keys`).
2. **Dry run** to see which orgs need re-issuance (those with an active OpenMetadata
   integration — the set that used the shared key):
   ```
   python -m scripts.reissue_subsystem_ingest_keys --dry-run
   ```
3. **Mint** the new keys, capturing to a protected file:
   ```
   python -m scripts.reissue_subsystem_ingest_keys --apply > /secure/reissued_keys.txt
   ```
   Output is `organization_id<TAB>key_type<TAB>api_key`. Each `api_key` is shown **once**.
4. **Distribute** each subsystem's new key to the corresponding push agent/script for
   that org, over a secure channel. Update the agent to send the new key as
   `X-CompliVibe-Key`.
5. **Delete** `/secure/reissued_keys.txt`.

## Ongoing self-service
Admins can provision or rotate any single subsystem key themselves (raw key returned
once), without this script:
```
POST /api/v1/integrations/ingest-keys        {"key_type": "pam"}      # requires org:update
GET  /api/v1/integrations/ingest-keys                                  # lists provisioned types (no secret)
```
`POST /data-observability/lineage/openmetadata/configure` continues to (re)issue the
`lineage` key as before.

## Rotation / revocation
Re-running the script, or re-POSTing to `/integrations/ingest-keys`, rotates a key in
place (old value stops working immediately). There is one active key per (org, key_type).
