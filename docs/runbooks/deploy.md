# Production Deploy Runbook (Backend)

## Status: pipeline built, NOT activated

`ci.yml` runs on every push/PR to `main` and is real today. `deploy.yml`
exists but its `deploy` job deliberately fails with an explicit error —
there is no production target configured. Nothing in this repo will
deploy anywhere until a human completes the steps below. This is by
design: domain choice, hosting-account creation, production DB
provisioning, and secret values are account-level, hard-to-reverse
decisions that were explicitly out of scope for automated execution.

## What already exists and is real

- Single alembic head confirmed at `0300_obligation_embedding_json_always_present`
  (verified with `alembic heads` on this branch — see report).
- `RATE_LIMIT_ENABLED` defaults to `True` in `app/core/config.py` and is
  only skipped when `APP_ENV=="test"` (`app/main.py:123`). No production
  code path disables it.
- httpOnly session cookie + double-submit CSRF cookie (`_set_auth_cookies`
  in `app/api/v1/auth.py`), `secure=True` whenever `APP_ENV=="production"`.
- `requirements.txt` lockfile (from the prior security-fix pass, commit
  `3c1ad97`).

## Evidence already found in this codebase suggesting an intended domain

`app/core/config.py` already has these **defaults** (not secrets, just
config defaults baked into code before this pass):
```
WEBHOOK_URL: str = "https://complivibe.in/api/webhook/razorpay"
FRONTEND_URL: str = "https://app.complivibe.in"
```
`DEVELOPMENT_LOG_V5.md` (already committed on `main`, predates this pass)
also references `https://complivibe.in/api/webhook/razorpay` as the
Razorpay webhook target. This is **evidence of an earlier intent**, not a
live decision made by this pass — a human still needs to confirm this is
still the domain to use for real production traffic before anything is
pointed at it. Treat it as a strong hint, not a green light.

## ⚠️ Security finding surfaced during this pass (needs human action)

`DEVELOPMENT_LOG_V5.md` (commit `b2de574` and earlier, already on `main`)
contains what appear to be **live-looking credential fragments**,
committed in plain text:
- A Razorpay live key ID (`rzp_live_...`)
- An AWS access key ID (`AKIA...`) tied to `adarsh@complivibe.in` / SES

Only the *ID* halves are present (no paired secret was found in that
file), which limits blast radius, but access-key IDs alone are still
enumerable/sensitive and, per the `.env.walkthrough2` near-miss precedent
already in project memory, the safe assumption is to treat anything that
touched git history as potentially exposed. **This pass did not rotate
keys or rewrite git history** — both are account-level/destructive
actions outside the authorized scope. Recommended human action before
go-live:
1. Rotate the Razorpay live API key pair and the AWS SES access key in
   their respective consoles.
2. Decide whether to scrub `DEVELOPMENT_LOG_V5.md` history (git history
   rewrite — coordinate with anyone else with a clone) or accept the
   exposure as already-mitigated by rotation and leave history intact.
3. Going forward, use `docs/runbooks/secrets_management.md` — no secret
   values in any file, ever.

## Step-by-step: what a human needs to do to actually go live

1. **Confirm the domain.** Either use `complivibe.in` / `app.complivibe.in`
   (matches existing code defaults and prior webhook config) or pick a
   different one. Either way this is a DNS + Cloudflare change this pass
   did not make.
2. **Provision production Postgres.** A new instance/database, separate
   from `complivibe_demo` (matching the requirement that prod be genuinely
   separate from the temporary tunnel demo). Enable `pgvector`. Do NOT
   reuse the demo DB.
3. **Provision production OpenBao/Vault in production mode** (not dev
   mode) — see `docs/runbooks/secrets_management.md` for what "production
   mode" means concretely (persistent backend, auto-unseal, real ACLs).
4. **Choose a hosting target for the backend process.** Options to weigh:
   another gunicorn+uvicorn process on this same host behind a *new*,
   separate Cloudflare Tunnel route (cheapest, fastest, but keep it on a
   distinct port/service unit from the demo's `127.0.0.1:8000` — do not
   let prod and demo share a process or port); or a managed platform
   (Fly.io, Render, ECS, etc.) if isolation from this host is wanted. This
   choice determines what `deploy.yml`'s real deploy step looks like.
5. **Create the GitHub `production` Environment** (Settings → Environments)
   with required reviewers, and add the secrets listed in
   `docs/runbooks/secrets_management.md` (`PRODUCTION_DATABASE_URL`,
   `PRODUCTION_VAULT_ADDR`/`PRODUCTION_VAULT_TOKEN`, deploy credentials for
   whatever target was chosen in step 4).
6. **Replace the placeholder `deploy` job body in `.github/workflows/deploy.yml`**
   with the real migration + deploy commands (a commented example is
   already in the file). Keep the `migration-safety-gate` and
   `wait-for-ci` jobs as hard prerequisites — do not remove them.
7. **Run `alembic heads` manually against the new production DB one more
   time** right before the very first `alembic upgrade head` in prod, even
   though CI and the deploy workflow both already gate on this — belt and
   suspenders for a database that, unlike CI's ephemeral one, you can't
   just throw away if something's wrong.
8. **Update cookie/CORS config for the real domain**: set
   `BACKEND_CORS_ORIGINS` to the real frontend origin, confirm
   `APP_ENV=production` so `_set_auth_cookies` sets `secure=True`, and
   decide whether frontend and backend will share an apex domain (e.g.
   `app.complivibe.in` frontend + `api.complivibe.in` backend needs the
   auth cookie's `domain=` explicitly set to `.complivibe.in` — currently
   `_set_auth_cookies` does not set a `domain=` at all, which is fine for
   the current same-origin-via-Next.js-proxy architecture in
   `app/api/proxy/[...path]/route.ts` on the frontend, but would break
   auth if the frontend ever calls the backend directly cross-subdomain).
   This is a one-line addition to `_set_auth_cookies` once the final
   domain topology is decided — deliberately not made here since the
   topology isn't decided yet.
9. **First real deploy**: trigger `deploy.yml` via `workflow_dispatch`,
   typing `deploy` to confirm, and watch the `production` Environment
   approval gate.

## What this pass explicitly did NOT do

- Did not create a Vercel/hosting account or project.
- Did not point any DNS record at anything.
- Did not provision a production Postgres or OpenBao instance.
- Did not create or rotate any real secret value.
- Did not merge this branch to `main`, and did not push it anywhere.

## Update 2026-07-14: demo.adarshkumar.app promoted to real production infra

A later pass (this one) took a different path than "provision a brand-new,
separate production stack" above: the user explicitly asked to harden the
existing `demo.adarshkumar.app` deployment on this VPS (`complivibe-v3-0-1`)
into genuinely durable infrastructure instead, same domain, same DB. What
changed:

- Backend, frontend, and Vault now run as real systemd services
  (`complivibe-backend`, `complivibe-frontend`, `complivibe-vault`), not
  manually-started terminal processes. All three proved to auto-restart after
  a `SIGKILL`.
- Vault/OpenBao is now persistent (`file` storage backend, `complivibe-vault.service`,
  `127.0.0.1:8230`) with an `ExecStartPost` auto-unseal script reading key
  shares from a root-only file (`/etc/complivibe-vault/unseal.keys`) — replaces
  the old in-memory dev-mode instance on `127.0.0.1:8220` (left running,
  untouched, as a scratch/dev target only).
- Daily DB backups (`complivibe-backup.timer` → `scripts/backup_demo_db.sh`)
  and a 5-minute stack health check (`complivibe-health-monitor.timer` →
  `scripts/monitor_stack_health.sh`) both actually pass now — the previous
  versions of these systemd units pointed at a stale `/home/ubuntu/complivibe`
  (pre-v4.0) codebase and had been silently failing.
- `RATE_LIMIT_ENABLED=true` and `APP_ENV=production` were already correct in
  the live environment; carried forward into `/etc/complivibe/backend.env`.

**Still not wired (deferred, needs a human with real credentials):**
`SENTRY_DSN`, `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET`,
`AWS_SES_ACCESS_KEY_ID`/`AWS_SES_SECRET_ACCESS_KEY` — all present as empty
placeholders in `.env.example` and `/etc/complivibe/backend.env`. Dropping in
real values later is a one-line edit + `sudo systemctl restart complivibe-backend`,
no code change. The Razorpay/AWS values specifically must be **freshly-rotated**
per the exposure finding above, not the old ones.
