# Production Secrets Management

This document describes the **mechanism**, not the values. No real secret
value belongs in this file, in any file in this repo, in a commit message,
or in `DEVELOPMENT_LOG*.md`. (There was a near-miss with `.env.walkthrough2`
during development — this doc exists to make that a process failure that
can't recur, not a one-off save.)

## Principle: three separate secret scopes, never shared

| Scope | Where it lives | Who/what can read it |
|---|---|---|
| Local dev | developer's own `.env` (gitignored) | that developer's machine only |
| Demo/staging (`demo.adarshkumar.app`) | OpenBao dev instance on `127.0.0.1:8220` + demo `.env` | the demo host only |
| Production | a real secrets manager (see below) | production runtime + CI deploy job only, via short-lived credentials |

**A production secret value must never be typed into a file that a human or
an agent could `git add`.** That includes README updates, log files,
walkthrough notes, and scratch scripts. If a secret needs to be recorded
for a human to hand off, it goes in a password manager entry or a secret
manager, never in the repo.

## What "a real secrets manager" means here

The demo's OpenBao **dev-mode** instance is explicitly not production-safe:
dev mode stores everything unsealed, in-memory-backed, with a root token,
and does not survive a restart. Production needs one of:

- **OpenBao/Vault in production mode** — persistent storage backend (e.g.
  Raft or a cloud KMS-backed backend), auto-unseal via cloud KMS, real
  ACL policies scoped per service, audit logging enabled. This is the
  natural upgrade path since the codebase already integrates with
  Vault/OpenBao (see `app/services/secrets_service.py` and the
  `VAULT_ADDR` / `VAULT_TOKEN` / `VAULT_TRANSIT_KEY_NAME` settings in
  `app/core/config.py`) — it's the same interface, pointed at a hardened
  instance instead of dev mode.
- **Cloud-native alternative** (AWS Secrets Manager, GCP Secret Manager,
  Azure Key Vault) if the production host ends up on that cloud — trades
  the self-hosted OpenBao operational burden for a managed service.

Either choice is a human decision (see `docs/runbooks/deploy.md`), not
something this pipeline presumes.

## CI/CD secrets (GitHub Actions)

GitHub Actions secrets are the mechanism for anything the **deploy
workflow** needs at deploy time (not application runtime secrets — those
come from the production secrets manager above, fetched by the running
app, not baked into CI).

Required repository or environment secrets (values TBD by a human, never
committed):

- `PRODUCTION_DATABASE_URL` — connection string for the production
  Postgres instance. Only used by the migration-safety-gate step at
  deploy time, never printed to logs.
- `PRODUCTION_DEPLOY_HOST` / `PRODUCTION_DEPLOY_SSH_KEY` (or the
  equivalent for whatever hosting target is chosen — API token for a
  PaaS, etc.)
- `PRODUCTION_VAULT_ADDR` / `PRODUCTION_VAULT_TOKEN` (or
  AppRole/OIDC-based auth, preferred over a static token if the target
  platform supports OIDC federation — e.g. GitHub Actions OIDC → AWS/GCP
  short-lived credentials, no long-lived secret stored at all).

These should be set as **GitHub Environment secrets** on a `production`
environment (Settings → Environments → production), with required
reviewers enabled, rather than plain repository secrets — this makes the
`environment: production` gate in `deploy.yml` meaningful (a human must
approve the run) and scopes the secrets so they're unreadable from other
workflows/branches.

## Rotation discipline

Any secret that appears in `DEVELOPMENT_LOG_V5.md` history (Razorpay live
key ID, AWS access key ID referenced around the SES integration) should be
treated as **compromised-by-exposure-in-git-history** and rotated before
go-live, regardless of whether the paired secret value was also present.
This is flagged for human action — rewriting git history or rotating live
payment/AWS credentials is exactly the kind of account-level action this
pass does not take unilaterally. See the report handed back with this
change for the specific finding.

## Local dev hygiene

- `.env` is gitignored; only `.env.example` (placeholders only) is
  committed. This was verified as correctly set up as of this pass.
- Before any commit, diff what's staged: `git diff --cached` — don't rely
  on `.gitignore` alone to save you from `git add -A` accidents.
