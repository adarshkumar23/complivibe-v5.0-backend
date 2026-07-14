# Interconnection Phase 1 — Domain Event Bus (Design Doc)

Status: **DRAFT — awaiting review before any code is written (Step 2).**
Head at design time: `alembic heads` → `0302_raise_api_general_rate_limit_default` (single head). Branch `main`.

---

## 0. Headline finding — this is an EXTEND, not a greenfield build

A working in-process pub/sub event bus **already exists** and is wired into app startup:

- `app/core/event_bus.py` — `EventBus` singleton, `EventType` constants, `EventPayload` dataclass, `subscribe`/`emit`/`clear_listeners`. `emit()` already dispatches synchronously and wraps **each** listener in its own `try/except` + `logger.exception` (per-handler isolation — requirement #5 is partially met today).
- `app/core/startup.py` → `register_event_listeners()` — the central wiring point, called once from `create_application()` in `app/main.py` (before the PBC scheduler starts).
- Two real subscribers already run on it: `RiskRecalculationListener` and `EntityScoreInvalidationListener` (`app/compliance/services/`).
- Real emit sites already exist: `control_service.py`, `evidence_service.py`, `api/v1/evidence.py`, and a cascade re-emit inside the recalculation listener.

**Decision: extend this bus into the full substrate the task asks for, rather than build a parallel one.** Replacing it would duplicate infrastructure and orphan working, tested code — and it already matches the recommended architecture (in-process, synchronous, no new external dependency). What it lacks is: event **persistence**, the richer **schema** (generic payload, `occurred_at`, `triggered_by_user_id`, `correlation_id`), and robust **failure isolation under DB errors**. This doc specifies those additions.

> Note: do not confuse the internal `EventBus` with `WebhookService.emit(...)` (`app/services/risk_service.py`, `issue_service.py`), which is **outbound customer webhooks** — a different, unrelated mechanism.

---

## 1. Event schema

Two representations, one logical event:

### 1a. Persisted record — new `domain_events` table (model `DomainEvent`)

Persisting events (recommended) gives us an auditable, replayable event stream that is **separate from** the audit log (see §4). Columns follow existing conventions (UUID PKs, `organization_id` FK w/ `ondelete=CASCADE`, `*_json` JSONB-with-variant, `sa.DateTime(timezone=True)`):

| column | type | notes |
|---|---|---|
| `id` | `Uuid` PK | `default=uuid4` (UUIDPrimaryKeyMixin) |
| `organization_id` | `Uuid` FK→organizations, NOT NULL, indexed | **strict tenant scope — non-negotiable** (OrganizationOwnedMixin) |
| `event_type` | `str` NOT NULL, indexed | namespaced, e.g. `vendor.assessment_stale` |
| `entity_type` | `str` NOT NULL | e.g. `vendor`, `control`, `dora_ict_entry` |
| `entity_id` | `Uuid` NOT NULL | the subject entity |
| `payload_json` | `JSON().with_variant(JSONB,"postgresql")`, NOT NULL, default `{}` | event-specific data (incl. legacy `previous_value`/`new_value`) |
| `occurred_at` | `DateTime(tz)` NOT NULL | when the originating action happened (defaults to now) |
| `triggered_by` | `str` NOT NULL | actor category label: `"user"` / `"system"` (kept for back-compat) |
| `triggered_by_user_id` | `Uuid` FK→users `ondelete=SET NULL`, **nullable** | the acting user; NULL for system/scheduler triggers |
| `correlation_id` | `Uuid` NOT NULL, indexed | traces a cascade of related events (see §1c) |
| `created_at` / `updated_at` | timestamps | TimestampMixin |

Indexes: `ix_domain_events_org_type` on `(organization_id, event_type)`, `ix_domain_events_correlation` on `(correlation_id)`, `ix_domain_events_org_entity` on `(organization_id, entity_type, entity_id)`.
Migration `0303_domain_events` (DDL modelled on `0298`; `sa.JSON()` + `server_default=sa.text("'{}'")`, explicit `ck_`/`ix_` names).

### 1b. Runtime carrier — extend the existing `EventPayload` dataclass

`EventPayload` must keep carrying the live `db: Session` (that field is **not** persisted — it's the in-process transaction the handlers share). Extend it additively so the two existing listeners keep working unchanged:

```python
@dataclass(slots=True)
class EventPayload:
    org_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    event_type: str
    previous_value: Any                       # kept — existing listeners read these
    new_value: Any                            # kept
    triggered_by: str                         # "user" | "system"
    db: Session
    # NEW (all defaulted so existing call sites still construct):
    payload: dict = field(default_factory=dict)          # generic JSONB body
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    triggered_by_user_id: uuid.UUID | None = None
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
```

`previous_value`/`new_value` are retained (five call sites + two listeners use them); the persisted `payload_json` is `{"previous_value":…, "new_value":…, **payload}` so nothing is lost. Go-forward events use the generic `payload` dict.

### 1c. `correlation_id` propagation

Generated once at the **root** emit (the originating HTTP action / scheduler tick). Any cascade re-emit **copies the parent's `correlation_id`** (e.g. `RiskRecalculationListener` re-emitting `risk.score_updated` passes `correlation_id=payload.correlation_id`). This lets one query reconstruct an entire cascade: `SELECT * FROM domain_events WHERE correlation_id = ? ORDER BY occurred_at`.

### 1d. New `EventType` constants (added, none removed)

```
vendor.assessment_stale          # Step-3 migration target #1
dora.ict_register_changed        # Step-3 migration target #2
geopolitical.signal_critical     # Step-3 migration target #3
ot_ics.finding_ingested          # Step-3 migration target #4
```

---

## 2. Delivery model — in-process synchronous (unchanged), now persisted

Recommendation: **keep in-process synchronous pub/sub** — it matches the standing "no Celery, FastAPI-lifespan scheduler, no new external infra without approval" rule and matches what the bus does today. **Do not** introduce a queue/broker now.

Emit sequence (the new `emit()`):
1. Publisher completes its own state change + `db.flush()`, then calls `EventBus.emit(...)`.
2. `emit()` **persists a `DomainEvent` row** using `payload.db` (same transaction as the triggering action — so if the whole request rolls back, the event row rolls back too: correct, the action didn't really happen).
3. `emit()` dispatches each subscriber synchronously with per-handler isolation (§5).
4. Control returns to the publisher; its result is unaffected by any subscriber.

**Migration path to a real queue (designed for, not built now):** because every event is a durable row with `correlation_id` and an implicit "processed" semantics, a future async worker could poll `domain_events` for undispatched rows and dispatch out-of-process — without changing publishers. We add **no** `status`/`dispatched_at` column now (YAGNI); if/when a queue is approved, that's a one-column additive migration. This is a note on extensibility, not a Step-2 deliverable.

---

## 3. Subscriber model — central registry, zero domain↔domain imports

The existing pattern already prevents circular imports; we formalize it as **the** rule:

- **Shared vocabulary lives in core**: `EventType`, `EventPayload`, `EventBus` in `app/core/`. Everyone imports *down* into core; nobody imports *across* domains.
- **Publishers** (`app/<domain>/…`) import only `app.core.event_bus` and call `EventBus.get_instance().emit(...)`. A publisher **never** imports the subscriber's domain.
- **Subscribers** are `*Listener` classes in their own domain, each exposing `handle(self, payload)` and `register(self, bus)` (matching `RiskRecalculationListener`). A subscriber may import its own domain's sink services (e.g. `RiskService`) at runtime inside `handle()` — that dependency is the subscriber's, not the publisher's.
- **Wiring** is centralized in `app/core/startup.py::register_event_listeners()` — the one place that imports domain listener classes. Direction is strictly `core → domains`, so no cycle is possible.

Net effect: the publisher (e.g. vendor-assessment) and the subscriber (Risk+Alert creation) become fully decoupled — exactly ADR-009's "cross-pillar references flow through the service layer only," now enforced by a seam instead of by discipline.

---

## 4. Audit integration — the bus triggers audit, it does not replace it

Two **distinct** records, both required:

1. **`domain_events` row** — "an event of type X was published." Written by `emit()`. This is the event stream, for tracing/replay.
2. **`audit_logs` row(s)** — "a real state change happened." Written **by the subscriber** via `AuditService(db).write_audit_log(...)`, exactly as inline code does today (`RiskRecalculationListener` already does this; every migrated connection keeps its existing `write_audit_log` calls verbatim).

The event row is **not** a substitute for the audit log. Emitting does not itself write an audit log (emits are cheap/frequent; the `domain_events` row is their record). Any subscriber that changes downstream state MUST still produce its `write_audit_log` entry — this is a migration invariant verified in Step 4 (same audit `action` strings appear after migration as before).

Note: `AuditService.write_audit_log(...)` is keyword-only, param names `organization_id` / `actor_user_id`, `flush()`es but does **not** commit.

---

## 5. Failure handling — one broken subscriber never breaks anything else

Requirement: a throwing subscriber must not block the publisher **or** sibling subscribers. Today's `try/except` per listener covers Python exceptions but has a real gap: **if a handler raises a DB error (e.g. `IntegrityError`) on the shared session, the session enters "pending rollback" and every *subsequent* handler's query fails too.** Catching the exception isn't enough — the session is poisoned.

**Fix (Step 2): wrap each handler dispatch in a SAVEPOINT** (`db.begin_nested()`), the standard SQLAlchemy isolation primitive:

```python
def emit(self, event_type, payload):
    self._persist_event(payload)          # DomainEvent row, best-effort, logged on failure
    for listener in self._listeners.get(event_type, []):
        try:
            with payload.db.begin_nested():   # SAVEPOINT per handler
                listener(payload)
        except Exception:
            logger.exception("Event listener failed event_type=%s", event_type)
            # savepoint rolled back; session is clean for the next handler
```

Guarantees:
- Publisher's original action is **never** rolled back by a subscriber (the publisher's writes are outside these savepoints; the publisher owns the outer commit).
- A failing handler rolls back **only its own** partial writes; siblings run on a clean session.
- The `domain_events` row is persisted **before** dispatch, so a failed handler still leaves a durable, correlatable record for replay/debugging.

Caveat to resolve in Step 2: the two existing listeners currently call `db.commit()` **inside** `handle()`. Committing inside a `begin_nested()` block interacts with savepoints. Resolution: move the outer `commit()` responsibility to the caller/emit boundary (the publisher's endpoint already commits), and have listeners `flush()` not `commit()` — OR keep listener commits but have `emit` use savepoints only around the handler body. This is the one non-trivial refactor and will be validated by the "throwing subscriber doesn't poison siblings" test before any connection is migrated.

**Tenant scoping enforcement (requirement):** `organization_id` is NOT NULL on `domain_events` and is the *single source of truth* for a handler's scope. The convention (already followed by both listeners) is mandatory: **every handler query filters by `payload.org_id`; handlers never derive scope from ambient state or trust `entity_id` alone.** Because dispatch is in-process on a shared session, this is enforced by-convention-plus-test rather than structurally — Step 2 includes an explicit test that an org-A event does not let a handler mutate org-B rows. (Honest framing: true structural cross-tenant enforcement would require per-handler scoped sessions, which is out of scope for an in-process bus and not warranted at current scale.)

---

## 6. Migration inventory (all cross-domain point-to-point connections found)

Full inventory from a codebase sweep (not memory). Two structural shapes: **(A)** routed through `RiskService.create_risk_from_service` (auto-audits `risk.created`, runs appetite check, fires `risk.critical` webhook); **(B)** inline `Risk(...)` + `check_appetite_breach` (skips the auto `risk.created` audit).

| # | Source (trigger) | Target effect(s) | Shape | Audited |
|---|---|---|---|---|
| 1 | DORA ICT register create/update — `dora_service.py:48/244/294` | Risk + `ControlMonitoringAlert` + Issue | A | yes |
| 2 | Vendor assessment staleness — `vendor_assessment_service.py:130` (+ daily sweep) | Risk + `ControlMonitoringAlert` | A | yes |
| 3 | Geopolitical GDELT signal — `geopolitical_risk_service.py:324` | `vendor.risk_tier="critical"` + Risk | A | yes |
| 4 | OT/ICS finding ingest — `ot_ics_service.py:407/454` | Risk (finding) + Risk (segment concentration) | A | yes |
| 5 | Bias/fairness test failure — `ai_depth_service.py:49` | system bias status + Issue + `AIRiskSignal` | — | yes |
| 6 | SDF designation confirm — `sdf_designation_service.py:126` | `OrganizationObligationState` applicability + `AuditSchedule` | — | yes |
| 7 | Sanctions screening match — `sanctions_screening.py:~480` | `vendor.risk_tier` + concentration recompute + supply-chain alerts | A(via 9) | yes |
| 8 | Bribery risk inconsistency — `bribery_risk_scoring.py:346` | `vendor.risk_tier="high"` + Risk | A | yes |
| 9 | Vendor concentration recompute — `vendor_concentration_risk_service.py:222` | Risk | A | yes |
| 10 | AI risk assessment finalize — `ai_risk_assessment_service.py:~465` | Risk (inline) + appetite check | B | breach only |
| 11 | MLOps adapter event — `mlops_adapter_service.py:~210` | Risk (inline) | B | breach only |
| 12 | Audit finding "accept risk" — `audit_finding_service.py:650` | Risk (inline) | B | yes |
| 13 | Compliance recommendation accepted — `compliance_risk_recommendation_service.py:296` | Risk (inline) | B | breach only |
| 14 | Security integration report — `integrations/security/base_service.py:207` | Issue (`security_incident`) | — | via Issue |
| 15 | DORA resilience test results — `resilience_testing_service.py:~185` | Issue(s) per finding | — | via Issue |
| 16 | AI human-oversight downgrade — `ai_depth_service.py:155` | Issue (critical) | — | yes |
| 17 | Third-party AI assessment complete — `third_party_ai_service.py:264` | `AISystem.risk_tier` escalation | — | yes |

Six real cross-domain "sinks": `create_risk_from_service`, `ControlMonitoringAlert`, `IssueService.create_issue`, `SignalService.emit_signal`, `OrganizationObligationState`, `AuditScheduleService`.

### Step-3 migration picks (recommended 4 — prove the pattern, don't boil the ocean)

**#2 vendor staleness, #1 DORA, #3 geopolitical, #4 OT/ICS** — all shape-A (route through the already-audited `create_risk_from_service`), all match the task's named examples, and each has a clean HTTP trigger to prove "identical Risk+Alert result via the bus" in Step 4. Each becomes: source **publishes** its new `EventType`; a new `*Listener` in the appropriate domain **subscribes** and performs the exact Risk/Alert/Issue creation that is inline today — byte-for-byte the same sink calls and the same `write_audit_log` actions.

Explicitly **not** migrating now: the shape-B inline builders (#10–13) and the Issue/Signal sinks (#5,14,15,16). They're the natural follow-on once the pattern is proven; #10–13 also carry a latent bug (they skip the standard `risk.created` audit) that a later pass can unify through the bus.

---

## 7. Step 2/3/4 plan (build only after approval)

- **Step 2:** `DomainEvent` model + `0303_domain_events` migration; extend `EventPayload`; add `_persist_event` + savepoint isolation to `emit()`; resolve the listener-commit caveat (§5). Tests: (a) publish→subscriber fires; (b) throwing subscriber doesn't break publisher or siblings (incl. a DB-error handler, proving the savepoint fix); (c) org-scoping test (org-A event doesn't touch org-B); (d) `domain_events` row persisted with correct fields + correlation propagation.
- **Step 3:** migrate #2, #1, #3, #4 onto publish/subscribe. No behavior change — same sinks, same audits.
- **Step 4:** full regression suite + per-connection real-HTTP evidence that the migrated path yields an identical Risk/Alert/Issue result and identical audit `action`s vs. pre-migration.

---

## Open questions for review

1. **Scope of Step 3** — confirm the 4 picks (#2/#1/#3/#4), or swap any (e.g. include the SDF→obligations #6 to prove a non-Risk sink)?
2. **Listener commit refactor (§5 caveat)** — OK to move commit ownership to the emit/endpoint boundary and make listeners `flush()`-only? This touches the 2 existing listeners.
3. **Persistence** — confirm we persist every event to `domain_events` (recommended), vs. persist only a subset / stay in-memory.
4. **`previous_value`/`new_value`** — keep on the dataclass for back-compat (recommended), or fold into `payload` now and update the 2 listeners + 5 call sites?
