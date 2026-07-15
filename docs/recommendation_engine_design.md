# Cross-Domain Compound-Exposure Recommendation Engine — Design Doc

Status: **DESIGN ONLY — awaiting review before any code is written** (same gate as Phases 1 & 2).
Head at design time: `alembic heads` → `0303_domain_events` (single head). Branch `main`, commit `5b7da8e`.

Goal: surface *compounding* exposures — e.g. "this control failed its test **AND** the vendor it
depends on has a stale assessment **AND** there's an open high-severity risk pointing at both" — as **one
synthesized insight**, instead of three separate, unconnected alerts. Detection reads the Phase 2 entity
graph; the AI layer only writes prose.

All facts below are grep/audit-confirmed against the current tree (citations inline), not assumed.

---

## 0. Locked architecture decisions (restated, not re-litigated)

1. **Hybrid, code-decides / AI-explains.** Deterministic code detects compound patterns by querying the
   Phase 2 entity graph and the real status/severity columns; **AI only generates the human-readable
   narrative for a pattern code has already confirmed.** AI never decides what is risky. Consistent with
   the platform's "no AI inference in compliance-critical logic" rule (Governance Autopilot etc.).
2. **Surface inside the existing Proactive Insights presentation — no new UI page.** (See §6 for an
   important audit finding: there is no single backend surface literally named "Proactive Insights"; §6
   proposes the faithful interpretation and flags it for confirmation.)
3. **Start conservative.** Only the clearest, highest-confidence compounds at first; **no per-org
   threshold configurability yet** (future work, documented in §3, not built).
4. **AI model = `openai/gpt-oss-120b` on Groq** for the narrative layer. §9 audits the *currently
   configured* model string and raises a separate urgent finding.

---

## 1. Pattern definition — a config-driven `PatternSpec` registry

Following the spirit of Phase 2's `EdgeSpec` registry (`app/compliance/services/entity_graph_registry.py`):
a compound pattern is a **declarative spec**, validated at import, that says (a) what connected shape to
match in the graph, (b) what real-field predicates each matched node must satisfy, (c) how severe the
resulting insight is, and (d) a narrative hint for the AI/template layer.

### 1a. Proposed shape

```python
@dataclass(frozen=True)
class NodePredicate:
    role: str                      # logical name in the match, e.g. "failed_control"
    entity_type: str               # a Phase 2 graph node type: control|vendor|risk|evidence|issue|ai_system|...
    conditions: list[Condition]    # ALL must hold (conjunction) on the node's real record
    min_count: int = 1             # cardinality: >=1 by default; >=2 expresses fan-out (Pattern E)

@dataclass(frozen=True)
class Condition:
    # whitelisted operators only (never free SQL), validated against the entity's real columns:
    field: str                     # a real column, e.g. "status", "severity", "risk_tier"
    op: str                        # "in" | "eq" | "lt" | "gt" | "age_days_gt" | "derived_eq"
    value: object                  # e.g. ["high","critical"]  or  30 (days)

@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str                # stable slug + dedup namespace, e.g. "failed_control_stale_vendor_open_risk"
    title: str
    insight_severity: str          # severity assigned WHEN matched: "critical" | "high"
    anchor: NodePredicate          # detection starts here (the node an event touches, or a swept candidate)
    legs: list[LegSpec]            # other required nodes + how they connect to the anchor/each other
    max_depth: int                 # graph hop ceiling (feeds EntityGraphTraversalService.traverse)
    narrative_template_hint: str   # deterministic fallback template + steer for the AI layer
    dedup_scope: list[str]         # roles whose (type,id) form the dedup key (see §5)

@dataclass(frozen=True)
class LegSpec:
    predicate: NodePredicate
    reached_via: list[str]         # allowed Phase 2 edge_type(s) connecting this leg into the match,
                                   # e.g. ["vendor_provides_control"], ["mitigated_by"]
    from_role: str                 # which already-matched role this leg attaches to (anchor by default)
```

Predicates express severity/staleness using the **real** vocabularies audited in §3 (e.g. control
`status == "failed"`, risk `severity in {high,critical}`, vendor assessment `age_days_gt 30`). The
`reached_via` edge-type list ties the spec to Phase 2 edges, so a match is only real if the nodes are
**actually connected in the graph**, not merely co-resident in the org. Like `EdgeSpec`, each spec is
validated at import against `entity_graph_registry.NODE_TYPES` and the ORM columns, so a typo fails loudly.

### 1b. Concrete example patterns (REAL entity/edge types only)

Edge types are verbatim from the Phase 2 registry; field values are verbatim from §3.

**Pattern A — Failed control + stale vendor + open high-severity risk** *(the headline example; initial rollout)*
- anchor `failed_control`: `control` where `status == "failed"` (or a `control_test_runs.result == "failed"` within 90d).
- leg `stale_vendor`: `vendor` reached via `vendor_provides_control`; has a `vendor_assessments` row with
  `status in {draft,in_progress,under_review}` AND `due_date` age > 30 days (overdue ≥ 30d).
- leg `open_high_risk`: `risk` reached via `mitigated_by`; `severity in {high,critical}` AND
  `status in {identified,assessing,treatment_planned,in_treatment,monitored}` (i.e. not accepted/mitigated/archived).
- `max_depth = 2`, `insight_severity = "critical"`.

**Pattern B — Expired evidence for a control that mitigates an open high-severity risk** *(initial rollout)*
- anchor `at_risk_control`: `control` with `status in {implemented,needs_review}`.
- leg `expired_evidence`: `evidence` reached via `control_evidenced_by`; `freshness_status == "expired"`.
- leg `open_high_risk`: `risk` reached via `mitigated_by`; `severity in {high,critical}` AND open (as above).
- `max_depth = 2`, `insight_severity = "high"`. "Your only evidence for a control mitigating a critical risk has expired."

**Pattern C — Active high-severity incident on a failed control with a stale vendor behind it** *(initial rollout)*
- anchor `active_incident`: `issue` where `status in {open,investigating,mitigating}` AND `severity in {high,critical}`.
- leg `failed_control`: `control` reached via `issue_affects_control`; `status in {failed,needs_review}`.
- leg `stale_vendor`: `vendor` reached via `vendor_provides_control` (from that control); overdue assessment ≥ 30d.
- `max_depth = 2`, `insight_severity = "critical"`.

**Pattern D — Production high-risk AI system carrying an open critical risk whose control failed** *(phase-in later)*
- anchor `prod_high_risk_ai`: `ai_system` with `lifecycle_status == "production"` AND an
  `eu_ai_act_classifications.article_category in {prohibited,high_risk_annex1,high_risk_annex3}`.
- leg `open_high_risk`: `risk` reached via `ai_system_bears_risk`; `severity in {high,critical}` AND open.
- leg `failed_control`: `control` reached via `mitigated_by` (from the risk) or `ai_system_uses_control`;
  `status == "failed"`.
- `max_depth = 3`, `insight_severity = "critical"`.

**Pattern E — Concentration: a high-tier stale vendor underpins controls for ≥2 open high-severity risks** *(phase-in later)*
- anchor `stale_high_vendor`: `vendor` with `risk_tier in {high,critical}` AND overdue assessment ≥ 30d.
- leg `open_high_risks`: `risk` reached via `vendor_provides_control` → `mitigated_by`, `min_count = 2`,
  each `severity in {high,critical}` AND open.
- `max_depth = 2`, `insight_severity = "critical"`. Demonstrates cardinality (`min_count`) and reuses the
  `concentration_cascaded_risk`/`vendor_supplies` edges if we later want nth-party depth.

**Initial conservative set = A, B, C.** D and E are documented and spec-expressible now, enabled after the
first set proves quiet in production.

---

## 2. Detection trigger — recommend **both**, with AI/persistence always OUT of the publisher transaction

Available infrastructure (audited):
- **Phase 1 event bus** (`app/core/event_bus.py`): `EventType` constants exist for
  `CONTROL_STATUS_CHANGED`, `EVIDENCE_STATUS_CHANGED`, `EVIDENCE_EXPIRED`, `VENDOR_ASSESSMENT_STALE`,
  `RISK_SCORE_UPDATED`, `VENDOR_SCORE_UPDATED`, `DORA_REGISTER_GAP_DETECTED`,
  `GEOPOLITICAL_SIGNAL_CRITICAL`, `OT_ICS_FINDING_INGESTED`. Listeners register in
  `app/core/startup.py::register_event_listeners`; dispatch is SAVEPOINT-isolated and **flush-only**
  (listeners must not commit and must not block on external calls — that's the publisher's transaction).
- **APScheduler** (`app/core/pbc_scheduler.py`): ~29 cron/interval jobs via `scheduler.add_job(...)`, each
  wrapped by `SchedulerJobLogger.run_logged(...)` with its own committed session. There is already a
  `vendor_assessment_staleness_sweep` (cron 03:15).

**Recommendation: run detection on a schedule as the workhorse, and use the event bus only to flag
candidate anchors for fast re-evaluation — never to run the graph traversal + AI inline in a listener.**

Reasoning / tradeoffs:
- **Reactive-only is insufficient** because the *conjunction* often becomes true through the passage of
  time, not a state change: a vendor assessment crossing 30 days overdue, or evidence crossing `valid_until`,
  emits no synchronous "node changed" event at the moment the compound forms. A scheduled sweep is the only
  thing that reliably catches time-formed compounds.
- **Scheduled-only is too slow** for the highest-severity compounds (a control failing *now* next to an
  already-stale vendor and open critical risk should surface in minutes, not at 03:00).
- **Never do detection+AI inside an event listener.** Graph traversal is a read (cheap-ish, §Phase 2 perf
  ~100-600 ms) but the Groq call is a 30 s-timeout external call; running it inside the publisher's
  SAVEPOINT-isolated, flush-only transaction would hold a DB transaction open across a network call and
  violates the Phase 1 listener contract. So:
  - A new **`CompoundPatternCandidateListener`** subscribes to `CONTROL_STATUS_CHANGED`,
    `VENDOR_ASSESSMENT_STALE`, `RISK_SCORE_UPDATED`, `EVIDENCE_EXPIRED`, `EVIDENCE_STATUS_CHANGED`. Its only
    job (flush-only, cheap) is to record the touched `(entity_type, entity_id)` as a **detection candidate**
    (a lightweight durable marker row, or an in-memory/again-durable queue) — no traversal, no AI.
  - A **short-interval APScheduler job** (`compound_insight_reactive_drain`, every ~5 min) processes queued
    candidates: for each, run the deterministic graph detection, then persist + AI-narrate + notify **in its
    own committed session, outside any request transaction.**
  - A **nightly APScheduler job** (`compound_insight_full_sweep`, cron ~03:30, after the staleness sweeps at
    03:15) re-evaluates all patterns org-by-org as the completeness backstop and auto-resolves cleared insights.
- Dedup (§5) makes the reactive drain and the nightly sweep idempotent — double-detection is harmless.

Net: **event bus for latency (candidate flagging), scheduler for the actual work and completeness.**

---

## 3. Confidence / severity gating — concrete conservative threshold, with reasoning

Audited reality (values verbatim; note most vocabularies live in Pydantic `pattern=` regexes / derived
service logic, NOT DB enums):
- **Control** `status` ∈ `not_started|in_progress|implemented|needs_review|failed|not_applicable|archived`
  (`app/schemas/control.py:28`). A *failed control test* = `control_test_runs.result == "failed"`
  (`app/schemas/control_test.py:49`; values are `passed/failed`, not `pass/fail`).
- **Risk** `severity` is **derived**, only ∈ `low|medium|high|critical` via `RiskService.score_to_severity`
  (`app/services/risk_service.py:43-50`: ≤4 low, ≤9 medium, ≤16 high, else critical). "Open" is not a
  literal — non-terminal = `status ∉ {accepted,mitigated,archived}`.
- **Vendor** staleness has **no built-in grace window**: the codebase treats *overdue = `due_date < today`*
  (N=0) in `vendor_assessment_service.is_overdue` (`:104`). `risk_tier` ∈ `critical|high|medium|low|not_assessed`.
- **Evidence** `freshness_status` derived (`evidence_service.py:24-35`): `expired` (past `valid_until`),
  `expiring_soon` (≤ **30 days**), `current`, `unknown`.
- **Issue** (incident) has real CheckConstraints: `severity ∈ {critical,high,medium,low}`,
  `status ∈ {open,investigating,mitigating,resolved,closed}` (`app/models/issue.py:14-30`).

**Proposed conservative starting gate (initial patterns A/B/C):**
1. **Every severity/status leg must be at the TOP of its real vocabulary**, not "medium-or-above":
   risk `severity ∈ {high,critical}`; issue `severity ∈ {high,critical}`; control at the unambiguous
   `status == "failed"` (not the softer `needs_review`) for the "failed" role.
2. **Vendor "stale" tightened to ≥ 30 days overdue** (`due_date < today − 30d`), even though the codebase's
   own threshold is N=0. Rationale: 30 days is the platform's existing "materially stale" horizon
   (`evidence_service` uses `timedelta(days=30)`; several review windows use 30d), so it's a principled,
   already-in-use number — and it prevents flagging a vendor one day past due next to an unrelated hot risk.
3. **Full conjunction only** — all legs must match; no partial/2-of-3 compounds surfaced initially.
4. **Graph-connected only** — legs must be linked by the spec's `reached_via` edge types within `max_depth`,
   not merely co-existing in the org.
5. Resulting **insight severity = `critical`** for the 3-leg patterns (A/C), `high` for B.

Why this is genuinely conservative (data-shape argument): an org typically holds thousands of graph edges
and many *medium* risks, but very few nodes sit simultaneously at the **top** of every severity axis while
also being **graph-connected**. Requiring `failed` + `severity∈{high,critical}` + `≥30d-overdue` +
edge-confirmed conjunction makes a match rare *by construction* → low volume, high signal. Loosening any leg
to "medium-or-above" would flood the surface. **Per-org tunable thresholds are explicitly deferred** (a
future `pattern_thresholds` config keyed by `organization_id`); v1 ships one hard-coded conservative gate.

---

## 4. Narrative generation contract (Groq) — strict structured I/O with a deterministic fallback

The code-confirmed pattern is the **source of truth and is persisted first**; the AI text is enrichment
layered on top and can never suppress a real detection.

### 4a. Exactly what is sent to Groq
A structured JSON description of the **already-confirmed** pattern — labels + the real attribute values code
already read (the model is *told* the severity; it never computes it):
```json
{
  "pattern_id": "failed_control_stale_vendor_open_risk",
  "insight_severity": "critical",
  "nodes": [
    {"role":"failed_control","entity_type":"control","label":"<control.title>","status":"failed","criticality":"high"},
    {"role":"stale_vendor","entity_type":"vendor","label":"<vendor.name>","assessment_days_overdue":47,"risk_tier":"high"},
    {"role":"open_high_risk","entity_type":"risk","label":"<risk.title>","severity":"critical","status":"in_treatment"}
  ],
  "relationships": [
    {"from":"stale_vendor","edge":"vendor_provides_control","to":"failed_control"},
    {"from":"open_high_risk","edge":"mitigated_by","to":"failed_control"}
  ]
}
```
Only human-facing labels/titles + non-sensitive attributes are sent; no raw IDs, secrets, or full records.
System prompt pins role ("explain, don't assess"), tone, and forbids inventing facts beyond the payload.

### 4b. Exactly what is expected back (bounded, structured)
Enforced with Groq **Structured Outputs** — `response_format: {"type":"json_schema","json_schema":{...,"strict":true}}`
(constrained decoding; per Groq docs this "never errors or produces invalid JSON" and guarantees schema
adherence). Schema:
```json
{
  "headline":            "string (<= 120 chars)",
  "summary":             "string (<= 600 chars)",
  "recommended_actions": ["string (<= 140 chars)", "... up to 3"]
}
```
`temperature` low (≤ 0.3). Because `gpt-oss-120b` is a **reasoning** model, budget `max_completion_tokens`
well above the visible output (reasoning tokens count) and read only the final message content.

### 4c. Validation + fallback (never fail to surface a real pattern)
Order of operations, so an AI problem is always survivable:
1. Persist the code-confirmed insight row **first** (status `open`, `narrative_source` initially `template`).
2. Build the **deterministic templated narrative** from the same structured payload (per-pattern
   `narrative_template_hint`, e.g. *"Control '{control}' has FAILED. The vendor '{vendor}' that provides it
   is {days} days overdue for reassessment, and open {sev} risk '{risk}' depends on this control. Review all
   three together."*). This is always attached.
3. Attempt the Groq call through the existing `AIProviderService` chain (Groq → Azure fallback). On success
   **and** post-parse server-side validation (schema shape already guaranteed by strict mode; additionally
   enforce length caps, non-empty, strip control chars / prompt-injection echoes), replace the templated
   text and set `narrative_source = "ai"`, record `provider_used`/`used_byo_credentials`.
4. If Groq times out (30 s), Azure also fails (HTTP 502 from the chain), the response is empty/malformed, or
   validation fails → **keep the templated narrative** (`narrative_source = "template"`). Log at WARN. The
   insight is already surfaced and notified regardless.

This mirrors the platform's existing resilience posture but upgrades it: today the JSON-producing provider
methods rely on prompt-only JSON + regex parsing + a 2-attempt retry (`ai_provider_service.py`), which is
brittle — the new narrative path should use strict `json_schema` structured outputs instead (see §9).

---

## 5. Deduplication & noise control

**Dedup key** = a stable hash over the organization and the *identity of the matched node set* for a pattern:
```
dedup_key = sha256( organization_id | pattern_id | sorted( f"{role}:{entity_type}:{entity_id}" for role in dedup_scope ) )
```
`dedup_scope` is per-pattern (usually all matched roles). Stored as a **unique** column
`compound_insights.dedup_key` (unique within org). Rules:
- **Create-once:** if an `open`/`acknowledged` insight with the same `dedup_key` exists, do **not** insert a
  new row and do **not** re-notify. Optionally bump `last_detected_at` + `detection_count`.
- **Notify on first surfacing only** — the None→`open` transition triggers the human notification (§7); later
  re-detections (from unrelated events touching the same nodes) are silent.
- **Auto-resolve** on the nightly sweep: if a previously-open insight's underlying conjunction no longer
  holds (control no longer failed, vendor reassessed, risk mitigated), set `status = "resolved"`,
  `resolved_at = now`. A later genuine re-formation is a new surfacing (new notify), which is correct.
- **Re-notify cooldown** (optional, conservative): suppress re-notification for the same `dedup_key` within
  a cooldown window even across resolve→reopen, to avoid flapping. Start simple (notify-on-create); add
  cooldown only if flapping is observed.

Because the node-set identity (not a timestamp) drives the key, the same compound re-detected by the reactive
drain and the nightly sweep collapses to one insight.

---

## 6. Integration with "Proactive Insights" — audit finding + faithful interpretation (needs one confirmation)

**Audit finding (important):** there is **no single backend feature named "Proactive Insights"** — no
`proactive_insights` table/model/router/service (grep-negative across models, routers, docs, git log). What
exists is several **independent, single-domain** recommendation subsystems, each with its own table and its
own DB `CheckConstraint`-enforced type vocabulary:
- `compliance_risk_recommendations` (`ComplianceRiskRecommendation`) — has a JSON payload
  (`context_snapshot_json`), narrative (`title`/`rationale`), a `pending/accepted/dismissed/snoozed`
  lifecycle, `provider_used`, but **no severity column and no dedup key**; types
  `∈ {gap_identified,treatment_change,new_risk,risk_retirement}` (`ck_comp_risk_rec_type`).
- `ai_risk_recommendations` (`AIRiskRecommendation`) — has `priority ∈ {critical,high,medium,low}`
  (severity-like) and text-equality dedup, but **no JSON payload**; categories
  `∈ {technical_control,process_control,documentation,audit,decommission}`.

Neither table carries the full set a compound insight needs — **{severity, matched-node JSON, dedup key,
narrative, detection lifecycle}** — and both enforce their type list via a DB check constraint that a new
"compound" value would require a migration to widen, semantically polluting a single-domain table with a
cross-domain concept.

**Recommendation:** introduce a **new dedicated table `compound_insights`** (cross-domain by nature, clean
field set) and surface it *through the existing insights presentation* rather than a new page — i.e. extend
the current Proactive Insights UI section with a "Connected Exposures" card type fed by a **new list endpoint
that mirrors the existing recommendation-endpoint conventions** (status filter + `accept`/`acknowledge` /
`dismiss` / `snooze`, `require_permission`, org-scoped via `get_current_organization`). A new *table +
endpoint* is not a new *UI surface*; it reuses the existing page, honoring decision #2.

Proposed `compound_insights` columns (mirrors `compliance_risk_recommendations` conventions where possible):
`id`, `organization_id`, `pattern_id`, `severity`, `status` (`open|acknowledged|dismissed|resolved`),
`dedup_key` (unique per org), `title`, `narrative_headline`, `narrative_summary`,
`recommended_actions_json`, `matched_nodes_json` (role → {entity_type, entity_id, label, key attrs}),
`narrative_source` (`ai|template`), `provider_used`, `used_byo_credentials`, `first_detected_at`,
`last_detected_at`, `detection_count`, `acknowledged_by/at`, `dismissed_by/at`, `resolved_at`,
`created_at`, `updated_at`. New permission `compound_insights:read` / `:write` (dedicated, not reused).

**One confirmation needed for review:** decision #2 assumed a single existing "Proactive Insights
page/endpoint." Since the backend has several recommendation surfaces, please confirm the intended host — my
recommendation is the new `compound_insights` table surfaced in the same frontend Insights page. (Flagging
rather than silently reinterpreting a locked decision.)

---

## 7. Audit trail — and a correction to the "audit log notifies a human" premise

Every **newly surfaced** compound insight writes a real audit entry via the unchanged API
(`from app.services.audit_service import AuditService`; `write_audit_log` is keyword-only, required
`action`, `entity_type`, `organization_id`):
```python
AuditService(db).write_audit_log(
    action="compound_insight.surfaced",
    entity_type="compound_insight",
    entity_id=insight.id,
    organization_id=org_id,
    actor_user_id=None,   # system-generated
    after_json={"pattern_id": pattern_id, "severity": severity, "matched_nodes": [...]},
    metadata_json={"source": "reactive"|"sweep", "provider_used": ..., "narrative_source": ...},
)
```
**Correction (audited):** `write_audit_log` does **not** itself notify a human — after flushing the `AuditLog`
row it only calls `_dispatch_search_indexing` (Meilisearch), gated to a small `TRACKED_ENTITY_TYPES`
allowlist, and swallows failures (`app/services/audit_service.py:43-78`). So the audit entry satisfies the
**trail** requirement, but the **human notification** must be a **separate call at the surfacing call site**.
Design: on the None→`open` transition, also invoke the platform's existing notification mechanism (the same
path existing alerts use — e.g. the `ControlMonitoringAlert(status="open")` row that
`vendor_staleness_listener` already creates, or the notifications/inbox service). *The exact notification
service to reuse is the one open dependency to confirm during build* — it is not `write_audit_log`.

---

## 8. Tenant scoping — reuse Phase 2's proven isolation

Every step is single-org:
- Detection anchors are always within one `organization_id`; the graph walk uses
  `EntityGraphTraversalService.traverse(..., organization_id=org_id, ...)`, whose org filter is enforced **in
  the recursive term at every hop** — Phase 2 proved a shared vendor cannot bridge orgs, including **0
  cross-request bleed under 48-way concurrency**.
- Every leg's record fetch (control/vendor/risk/evidence/issue) filters `organization_id = org_id`.
- `dedup_key` includes `organization_id`; the `compound_insights` row is `OrganizationOwnedMixin`; the list
  endpoint scopes to `get_current_organization`. No cross-org pattern or insight is representable.

---

## 9. Groq model-string audit — SEPARATE URGENT FINDING (act regardless of Phase 3 timing)

**Current state (audited):** the Groq provider chain hard-codes a single model string —
```
app/ai_governance/services/ai_provider_service.py:386   "model": "llama-3.3-70b-versatile"
```
inside `_call_groq_messages`. There is **no `GROQ_MODEL` setting** (`app/core/config.py` defines only
`GROQ_API_KEY`), so the model is not env-overridable. This one literal is the sole Groq model reference in
`app/`. The Azure fallback carries no hard-coded model (it's deployment-name driven).

**`llama-3.3-70b-versatile` is a deprecated Groq model** (confirmed via Groq's own docs and current
listings: Groq's guidance is to move general-purpose/reasoning workloads to `openai/gpt-oss-120b` /
`gpt-oss-20b`; `qwen3-32b`, `qwen3.6-27b`, `llama-4-scout`, `kimi-k2-instruct` are **preview/eval-only** and
unsuitable for anything depended on). When Groq stops serving the deprecated model, **every** Groq call
(policy drafting, risk recommendations, inline suggestions, refinement) will start erroring and fall through
to Azure — or 502 if Azure isn't configured for that org.

**Urgent recommendation (independent of the recommendation engine):**
1. Change the string to **`openai/gpt-oss-120b`** now.
2. Make it a **setting** — add `GROQ_MODEL: str = "openai/gpt-oss-120b"` to `config.py` and read it in
   `_call_groq_messages`, so future deprecations are a config change, not a code change.
3. Because `gpt-oss-120b` is a **reasoning** model: raise `max_tokens`/`max_completion_tokens` (currently
   1200) to leave room for reasoning tokens, and adopt **`response_format` structured outputs** for the
   existing JSON-producing methods (`generate_inline_suggestions`, `generate_risk_recommendations`) to
   replace today's brittle prompt-only-JSON + regex + 2-retry parsing — the same strict-JSON mechanism §4
   specifies for the new narrative layer.

This is a pre-existing production risk surfaced by the audit; recommend fixing it as its own small change
before/independent of building the recommendation engine.

---

## 10. Proposed build sequence (after approval — no code yet)

1. **Fix the Groq model string** (§9) as a standalone urgent change: `openai/gpt-oss-120b` + `GROQ_MODEL`
   setting + structured outputs on existing JSON methods.
2. `PatternSpec` registry (patterns A/B/C) + import-time validation against `NODE_TYPES`/ORM columns.
3. Deterministic detector: anchor → `EntityGraphTraversalService.traverse` → leg predicate evaluation →
   conjunction confirm; pure read, org-scoped; unit-tested against a hand-built graph like Phase 2's.
4. `compound_insights` table + service + list/lifecycle endpoint (new `compound_insights:*` permission);
   dedup + auto-resolve (§5); audit log + separate notification (§7).
5. Triggers: `CompoundPatternCandidateListener` (flag-only) + `compound_insight_reactive_drain` (≈5 min) +
   `compound_insight_full_sweep` (nightly) — all detection+AI+notify outside any request transaction (§2).
6. Narrative layer: strict `json_schema` Groq call with templated fallback (§4).
7. Frontend: extend the existing Insights page with the "Connected Exposures" card (no new page).
8. Deferred/documented-not-built: per-org threshold config (§3), patterns D/E, nth-party depth via
   `vendor_supplies`/`concentration_cascaded_risk`, a graph-projection-backed detector if sweep cost grows.

---

## Sources searched (web, verified live — not cached)
- Groq supported/production models, `openai/gpt-oss-120b` specs & pricing, deprecation guidance:
  [Groq Models doc](https://console.groq.com/docs/models),
  [Groq API 2026 overview](https://console.groq.com/docs/overview),
  [Groq pricing 2026 (CloudZero)](https://www.cloudzero.com/blog/groq-pricing/),
  [Portkey Groq model list](https://portkey.ai/models/groq).
- Structured-output reliability (json_schema `strict`, constrained decoding, retries):
  [Groq Structured Outputs doc](https://console.groq.com/docs/structured-outputs),
  [Groq API cookbook — structured output](https://deepwiki.com/groq/groq-api-cookbook/3-structured-output-generation).

## Internal audit citations (this tree, commit 5b7da8e)
- Groq model string: `app/ai_governance/services/ai_provider_service.py:386`; chain `_run_provider_chain:330-366`; no `GROQ_MODEL` in `app/core/config.py`.
- Event bus / types / SAVEPOINT dispatch: `app/core/event_bus.py:12-22,93-115`; registration `app/core/startup.py:4-22`.
- Scheduler: `app/core/pbc_scheduler.py` (`register_pbc_scheduler`, `add_job`, existing `vendor_assessment_staleness_sweep`).
- AuditService: `app/services/audit_service.py:15-28` (signature), `:43-78` (search-index only, no notify).
- Insights surfaces: `compliance_risk_recommendations` (`app/models/compliance_risk_recommendation.py`, `ck_comp_risk_rec_type`), `ai_risk_recommendations` (`app/models/ai_risk_recommendation.py`).
- Real field vocabularies (§3): `app/schemas/control.py:28`, `app/schemas/control_test.py:49`, `app/services/risk_service.py:43-50`, `app/services/vendor_assessment_service.py:104`, `app/services/evidence_service.py:24-35`, `app/models/issue.py:14-30`.
- Entity graph edges/nodes: `app/compliance/services/entity_graph_registry.py`; traversal `entity_graph_traversal_service.py` (org filter per hop, Phase 2 §5/§6b).
