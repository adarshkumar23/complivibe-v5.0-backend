# Secrets migration: Fernet -> OpenBao/Infisical (vault)

**MANUAL, PRODUCTION-ONLY RUNBOOK. Do not run this against production
without following every step below in order. This document describes a
procedure for a human operator to execute; it was not executed against
production, staging, or any shared environment by the author of this
runbook -- only against a disposable local SQLite DB and a throwaway local
OpenBao dev server, as evidence that the code is correct.**

## What this migrates

Five tables hold Fernet-encrypted columns, each currently encrypted with a
per-feature key derived from either `FERNET_SECRET_KEY` (or `SECRET_KEY` as a
fallback) or a feature-specific `*_ENCRYPTION_KEY` setting:

| Table                          | Column(s)                                            | Legacy key source              |
|---------------------------------|-------------------------------------------------------|---------------------------------|
| `oidc_configs`                  | `client_secret_enc`                                    | `FERNET_SECRET_KEY` (raw or SHA-256(`SECRET_KEY`)) |
| `mlops_integrations`            | `config_json`                                          | `MLOPS_CONFIG_ENCRYPTION_KEY` or SHA-256(`SECRET_KEY`) |
| `openmetadata_integrations`     | `config_json`                                          | `OPENMETADATA_CONFIG_ENCRYPTION_KEY` or SHA-256(`SECRET_KEY`) |
| `organization_ai_configurations`| `groq_api_key_encrypted`, `azure_api_key_encrypted`    | `FERNET_SECRET_KEY` (raw or SHA-256(`SECRET_KEY`)) |
| `org_email_configs`             | `config_json`, `aws_access_key_id_enc`, `aws_secret_key_enc` | `FERNET_SECRET_KEY` / `EMAIL_CONFIG_ENCRYPTION_KEY` |

After migration, every one of those columns holds a vault transit-engine
ciphertext (`vault:v<version>:...`) instead of a Fernet token (`gAAAAA...`).

`app/services/secrets_service.py` is the compatibility layer: it detects
which format a value is in and decrypts either one, but only ever *writes*
new ciphertext via vault. Once this migration has run, all application code
paths keep working unchanged (they already call through `SecretsService` /
the per-service wrappers that delegate to it) -- this runbook exists purely
to re-encrypt the *existing* rows so the legacy Fernet code path becomes
unused.

## Prerequisites

1. A real, operator-managed OpenBao (or Vault-compatible) cluster reachable
   from the production backend, with:
   - The `transit` secrets engine enabled.
   - A transit key created (name must match `VAULT_TRANSIT_KEY_NAME`,
     default `complivibe-secrets`): `bao secrets enable transit && bao write -f transit/keys/complivibe-secrets`
   - A token with `encrypt`/`decrypt` capability on that transit key, scoped
     to nothing else (least privilege). Do NOT use a root token.
2. `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_TRANSIT_KEY_NAME` set in the
   production backend's environment (alongside the existing
   `FERNET_SECRET_KEY`/`SECRET_KEY`/`*_ENCRYPTION_KEY` settings -- **do not
   remove those yet**, they're still needed to decrypt any row this
   migration hasn't reached, and as a safety net until you've verified 100%
   migration).
3. A **verified, recent database backup** you can restore from.
4. A maintenance window or low-traffic period. The migration script commits
   once at the end of a full pass; it does not lock tables, but a
   concurrent write to a row it's mid-processing could theoretically be
   overwritten by the migration's own commit. Prefer running it when the 5
   tables above are not being actively written (config/integration setup
   screens are low-traffic by nature).

## Procedure

1. **Dry run first, always**:
   ```
   VAULT_ADDR=... VAULT_TOKEN=... python -m scripts.migrate_secrets_to_vault --dry-run
   ```
   Review the printed counts (`scanned`, `migrated`, `already_vault`,
   `empty`, `errors`). Investigate any `errors` before proceeding --
   `SecretFormatError` on a row means its ciphertext matches neither vault
   nor legacy-Fernet format (data corruption or a key mismatch) and needs
   manual investigation before continuing; `SecretsBackendError` means vault
   itself was unreachable and nothing was migrated.

2. **Take/confirm a fresh backup.**

3. **Run for real**:
   ```
   VAULT_ADDR=... VAULT_TOKEN=... python -m scripts.migrate_secrets_to_vault
   ```
   This is idempotent -- if it fails partway (e.g. vault becomes
   unreachable), re-running it later only re-processes rows still in
   Fernet format; anything already migrated to vault format is left
   untouched (verified in this branch's evidence run: a second run reported
   `migrated: 0`, `already_vault: <N>`, with byte-identical ciphertext).

4. **Verify**: spot-check a handful of rows across each of the 5 tables --
   confirm the column values now start with `vault:v` and that the
   corresponding feature (SSO login, email sending, AI drafting, MLOps
   sync, OpenMetadata sync) still works end-to-end in a real request.

5. **Audit trail**: every encrypt/decrypt this script performs writes an
   `AuditLog` row (`action` = `secret.encrypt` / `secret.decrypt`,
   `entity_type` = `secret`, `metadata_json` includes `secret_name` and
   `success`, never the plaintext). Query these to confirm coverage:
   ```sql
   select action, metadata_json->>'secret_name', count(*)
   from audit_logs
   where action like 'secret.%' and created_at > now() - interval '1 hour'
   group by 1, 2;
   ```

6. **Do not remove `FERNET_SECRET_KEY`/`*_ENCRYPTION_KEY` from the
   environment immediately.** Keep them for at least one full deploy cycle
   after migration, in case any row was missed (new writes always go
   through vault regardless, so this is purely a safety net for reads of
   old rows). Once you've confirmed via the audit log / a full table scan
   that zero rows remain in legacy Fernet format, those settings can be
   retired.

## Rollback

There is no automatic rollback. If something goes wrong mid-migration:
- The script only commits once, at the end of a full pass, so a crash
  mid-run leaves the DB in its pre-run state (nothing partially written).
- If a full pass completed but something downstream is broken, restore the
  DB backup taken in step 2. Vault-side, no state needs to be rolled back
  (the transit key can simply be left in place and reused).

## What was actually verified (this branch, evidence only -- not production)

- A real, standalone OpenBao v2.5.5 binary (no Docker) was run in `-dev`
  mode locally, with the `transit` engine enabled and a real
  `complivibe-secrets` key created.
- A disposable SQLite DB was seeded with one row per table above, each with
  a **real** Fernet ciphertext produced using each service's original exact
  key-derivation algorithm (including a real `FERNET_SECRET_KEY` value, to
  match how this repo's own `.env` is configured).
- `scripts/migrate_secrets_to_vault.py` was run against that DB: all 8
  seeded secret columns were re-encrypted to `vault:v1:...` format, 0
  errors.
- A real decrypt round-trip through `SecretsService` after migration
  recovered the original plaintext for every migrated column.
- 18 real `AuditLog` rows were written (one encrypt + one decrypt per
  secret processed), all `success: true`.
- The script was run a **second time** against the now-migrated DB:
  `migrated: 0`, `already_vault: 8`, and the ciphertext bytes were
  confirmed byte-for-byte identical to the first run's output -- proving no
  double-encryption on repeat runs.
- The dev-only OpenBao server used for this evidence run (and for the
  automated test suite, via `tests/conftest.py`) is provisioned by
  `scripts/setup_dev_vault.sh` / an auto-downloaded binary under the
  gitignored `.dev_vault/` directory. **This is never used for production.**
