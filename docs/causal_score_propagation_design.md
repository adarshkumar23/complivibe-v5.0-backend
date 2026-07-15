# Causal Score Propagation — Design Doc

Status: **DESIGN ONLY — awaiting review before any code is written** (same gate as Phases 1–3).
Head at design time: `alembic heads` → `0304_compound_insights` (single head). Branch `main`, commit `87c19b6`.

Goal: make a score **change** traceable to its real cause — e.g. *"your compliance score dropped 4 points
because Control X failed, which dropped Control-Health's implemented ratio (−3 pts) and, via GDPR's
control coverage, contributed to the framework view (−1 pt)."*

All facts below are grep/audit-confirmed against the current tree (citations inline), not assumed.

---

## 0. Sizing verdict up front — confirm 2–3 prompts, with one honest caveat

**Confirmed: the core is genuinely small and rides on existing infra — ~1 build prompt + a checkpoint,**
because the org scores are **deterministic weighted aggregations whose snapshots already persist the exact
inputs and weights** (`score_snapshots.breakdown_json`), so decomposing a delta is *pure arithmetic over
data that already exists* — not statistical causal inference. And there is already a working driver-attribution
engine to generalize (`BoardScorecardService._score_change_summary`).

**But three realities of the as-built Phase 1/2 (not visible in the original hypothetical roadmap) make the
*full* motivating example a bit more than a trivial event-bus read** (details in §5):
1. Score snapshots are **materialized in a batch job, not per-change** — so "the change" is snapshot-to-snapshot, and the specific entity cause is reconstructed from `domain_events` in that window, not read off a single event.
2. The event cascade **does not reach the org-level score** — it terminates at `EntityRiskScore` with no re-emit, and `ScoreSnapshot` changes emit no event and share no `correlation_id` with the triggering entity change. So the cause→score link is *reconstructed* (arithmetic + graph + event-window), not pre-linked by `correlation_id`.
3. The **per-framework "GDPR score" is computed on-the-fly and never persisted** — so that specific leg of the example has no history to diff without a small new snapshot type.

Net: **2–3 prompts holds for the persisted score families (compliance/governance/risk-posture/control-health,
entity, board).** Fully realizing the "…lowered your GDPR score" leg needs a small persisted per-framework
snapshot type — recommend either adding that as the one net-new bit, or scoping v1 to persisted scores and
approximating the framework leg via the graph (§5). Not a blow-up; a scoping call to make.

---

## 1. Audit — how scores are computed today (grep-confirmed)

**Almost every score is a pure weighted aggregation of live DB counts.** Two families are persisted over time
(diffable), the rest are recomputed per request. Three surfaces already do *partial* attribution — the
"extend, don't rebuild" candidates.

### 1a. Org-level scores — `app/services/scoring_service.py` (persisted → `score_snapshots`)
Six snapshot types; each `compute_*` returns `{score, grade, inputs_json, breakdown_json, recommendations_json}`.
All deterministic (`methodology()`, `:680-714`, states "deterministic and based only on CompliVibe records").
Exact formulas (verbatim locations):
- **Control Health** (`:150-158`): `(implemented_ratio*0.55 + passing_ratio*0.45 − needs_review_ratio*0.2 − open_high_critical_issue_ratio*0.3) * 100`
- **Evidence Readiness** (`:254`): `verified_ratio*100 − expired_ratio*35 − needs_review_ratio*20`
- **Risk Posture** (`:339-345`): `100 − critical_high_ratio*50 − without_owner_ratio*25 − without_controls_ratio*25 + accepted_or_mitigated_ratio*10`
- **Task Hygiene** (`:428`): `(completion_ratio*0.6 + max(0,1−overdue_ratio)*0.25 + max(0,1−urgent_ratio)*0.15) * 100`
- **Compliance Readiness** (`:461-465`): `control_health*0.4 + evidence_readiness*0.4 + risk_posture*0.2`
- **Governance Health** (`:503`): `average(control_health, evidence_readiness, risk_posture, task_hygiene)` (each 0.25)

**Critical enabler:** each snapshot's `breakdown_json` stores the **input ratios AND the weights** used
(`:168-179`, `:267`, `:354-360`, `:466-477`). So a diff of two snapshots' `breakdown_json` yields *each term's
exact contribution to the score delta* by arithmetic. `score_delta` (`:641`) already computes `latest−previous`
but **attributes it to nothing**. Snapshots are written by `materialize_snapshots` (`:537`, batch/scheduled/manual,
supports `dry_run`). Model `score_snapshots` (`app/models/score_snapshot.py`): `snapshot_type, score, grade,
inputs_json, breakdown_json, recommendations_json, calculated_at`, org+timestamp mixins, indexed
`(org, snapshot_type, calculated_at)`.

### 1b. Existing PARTIAL attribution — the extend candidates
- **`BoardScorecardService._score_change_summary`** (`board_scorecard_service.py:427-512`) — the *only* real
  "why did the score move" engine. Diffs the current vs previous persisted `BoardScorecardSnapshot`, builds a
  `drivers` list ("control effectiveness dropped N pts", "framework coverage improved N pts", "N more open
  critical/high risks") and a narrative. **Limitation:** hardcoded 3 drivers, threshold-gated (≥0.5 pt),
  narrative-only — *no per-driver quantified contribution to the delta.* This is the pattern to generalize.
- **`RiskScoringService.compute_breakdown`** (`risk_scoring_service.py:161-216`) — per-factor `contribution` +
  `contribution_pct` (static composition of a single risk score; the `/{risk_id}/score-breakdown` endpoint).
- **`EntityRiskScoreService`** — `component_risks_json` persists per-risk `weighted_contribution`
  (`:270-311`); `staleness()` (`:366-412`) already emits reasons like *"risk X inherent_score changed from A to
  B since this score was computed"* — drift reasoning, structurally close to change attribution.

### 1c. On-the-fly scores (NO history to diff)
Framework readiness / control coverage / evidence-verified % (`compliance_dashboard_service.py:102-206`,
`control_coverage_pct = mapped_obligation_count/obligation_count*100`), SOC2 readiness, trust-center coverage,
AI-governance maturity. **These are recomputed per request and never snapshotted** — a "change" is not
reconstructable from stored state. (The dashboard does track *that* data changed via
`_underlying_data_changed_since` `:164`, reading audit-log action prefixes — but not by how much or to what.)

### 1d. Event flow feeding scores (from the bus audit)
`domain_events` (Phase 1, `0303`) carries `organization_id, entity_type, entity_id, previous_value, new_value,
correlation_id, occurred_at`, indexed `ix_domain_events_org_type_occurred (organization_id, event_type,
occurred_at)` — *exactly* the shape for a windowed "what changed between T1 and T2" query. Score-relevant emits:
`CONTROL_STATUS_CHANGED`, `EVIDENCE_STATUS_CHANGED`, `EVIDENCE_EXPIRED`, `RISK_SCORE_UPDATED` (re-emitted with the
parent `correlation_id`, `risk_recalculation_listener.py:146-164`), `VENDOR_SCORE_UPDATED`. **Coverage is
partial:** control status ✓, evidence ✓, risk score ✓ — but issue changes, risk status transitions
(accepted/mitigated), owner assignment, and control↔risk link changes emit **no** event, so some score-input
moves have no corresponding `domain_events` row.

---

## 2. Attribution mechanism — reconstruct on-demand from existing data (recommended), not new score-site instrumentation

Two layers, deterministic-first (mirroring Phase 3's "code decides, AI only narrates"):

**Layer 1 — arithmetic delta decomposition (the reliable backbone).** Given two `ScoreSnapshot`s of a type,
diff their `breakdown_json`. Because `score = Σ wᵢ·rᵢ`, the contribution of each term to the change is exactly
`wᵢ·(rᵢ_new − rᵢ_old)`, and composites decompose recursively (Compliance = 0.4·ΔCH + 0.4·ΔER + 0.2·ΔRP, each
sub-Δ further into its ratio terms). This is pure arithmetic over data that already exists — it **always** works
for the persisted families and needs no events or graph. Output: a ranked list *"this −4 pt move is −3 from
Control-Health (implemented_ratio 0.72→0.61) and −1 from Risk-Posture (critical_high_ratio rose)."*

**Layer 2 — entity-cause enrichment (best-effort, where events exist).** For the top-moved term(s), query
`domain_events` for the org in `[snapshot_prev.calculated_at, snapshot_curr.calculated_at]` filtered to the
event types that feed that term (e.g. Control-Health ← `CONTROL_STATUS_CHANGED`), giving the concrete entity
change(s) with before/after. Then use **Phase 2's `EntityGraphTraversalService`** (org-scoped, depth-capped) to
connect that entity to the score's scope — e.g. Control X → its obligations/frameworks — producing the chain
*"Control X → failed → obligations it satisfied → GDPR coverage."* Where an input has no event (issues, risk
status), fall back to the dashboard's existing `_underlying_data_changed_since` signal ("underlying data changed
in this window") rather than inventing a cause.

**Recommendation: reuse (Layer 1 snapshots + Layer 2 `domain_events` + Phase 2 graph), NOT new instrumentation
at score-calc sites.** Tradeoffs:
- *Reuse (recommended):* zero new write-path code, no touching the batch materializer or listeners, everything
  needed already persists. Cost is per-query recompute — trivial (diff two JSON blobs + one indexed
  `domain_events` window query + a bounded graph traversal). The arithmetic backbone is exact; only the
  entity-cause layer is best-effort, and it degrades gracefully.
- *New instrumentation at score sites:* would mean the batch materializer computes+stores an attribution when it
  writes each snapshot. More code on the write path, a new table, and it still can't attribute inputs that emit
  no events. No accuracy gain over on-demand for Layer 1 (same arithmetic), so not worth it in v1.

---

## 3. What gets stored/shown — on-demand computed, no new table (v1)

**Recommend on-demand computation, persisting nothing new** — consistent with Phase 2 "no projection in v1" and
Phase 1 "in-process bus, not a queue": don't over-build ahead of demonstrated need. The raw materials already
persist (`score_snapshots` with `breakdown_json`, append-only `domain_events`, `entity_risk_scores` history);
an explanation is a **view** over them, computed when asked.

- New service `ScoreChangeAttributionService` (generalizing `board_scorecard_service._score_change_summary`) +
  a read endpoint, e.g. `GET /api/v1/scoring/snapshots/{snapshot_type}/explain-change`
  (auto-picks the latest two snapshots, or accepts `from`/`to` snapshot ids), org-scoped, permission-gated with
  a dedicated new code (e.g. `score_attribution:read`).
- Response: `{ snapshot_type, from, to, score_delta, contributions: [ {component, weight, ratio_before,
  ratio_after, points_delta} … ranked ], likely_causes: [ {component, event_type, entity_type, entity_id,
  entity_label, before, after, occurred_at, graph_path: [...] } … ] }` — deterministic contributions always
  present; `likely_causes` best-effort.

**Future extension (documented, not built), if a queryable "why" history is later demanded:** hook
`materialize_snapshots` to persist the Layer-1 attribution alongside each new snapshot (a compact
`score_change_attribution` row keyed to the snapshot). That's the natural change-point (snapshots are the one
place org scores actually change), but it adds a table + write path — deferred exactly like Phase 2's projection.

---

## 4. Tenant scoping & audit trail

- **Strict org scoping, reusing proven guarantees.** `score_snapshots` and `domain_events` are `organization_id`
  columns filtered on every query; the graph leg uses `EntityGraphTraversalService(..., organization_id=org_id)`
  whose org filter is enforced at every hop (Phase 2 proved 0 cross-tenant bleed under concurrency). No
  cross-org explanation is representable.
- **Audit trail:** the on-demand explanation is a **read** — it mutates nothing — so it warrants no
  `AuditService.write_audit_log` entry, consistent with how other read/breakdown endpoints behave. `write_audit_log`
  (unchanged signature, `from app.services.audit_service import AuditService`) becomes appropriate only in the
  *future* persist-at-materialize variant (§3), or if a significant score drop is surfaced as an alert (§6). Flagging
  this rather than forcing a contrived audit write on a read.

---

## 5. Honest sizing impact — what Phase 1/2 as-built changes vs the original estimate

**Easier than the roadmap assumed:**
- The org scores are deterministic weighted sums with `breakdown_json` already persisting ratios+weights → the
  delta decomposition (the hard-sounding "causal attribution") is arithmetic, not inference. This is the bulk of
  the value and it's cheap.
- `BoardScorecardService._score_change_summary` is a working, tested template to generalize (not a blank page).
- `domain_events`'s `(org, event_type, occurred_at)` index makes the windowed cause query a one-liner; the graph
  service is ready.

**Harder / caveats the hypothetical framing missed (all surfaced by the real audits):**
1. **Snapshot vs event granularity.** Scores materialize in a batch (`materialize_snapshots`), not per change, so
   the honest unit is snapshot→snapshot; the specific cause is the top `domain_events` in that window. If snapshots
   are sparse (daily), multiple changes aggregate — correct but coarser than "the one event."
2. **The cascade doesn't reach the org score.** `EntityScoreInvalidationListener` is terminal (no re-emit), and
   `ScoreSnapshot` changes fire no event and carry no `correlation_id` back to the triggering entity change. So the
   cause→score link cannot be read off `correlation_id`; it is *reconstructed* (arithmetic which-input-moved +
   graph which-entity-feeds-it + event-window which-entity-changed). Doable, but it's genuine reconstruction logic,
   not a bus read — the single biggest reason this is "a bit more than trivial."
3. **Partial event coverage of score inputs.** Control-status/evidence/risk-score emit events; issue changes, risk
   status transitions, owner assignment, and link changes do not — so Layer 2 is best-effort per input, with a
   graceful "underlying data changed" fallback for uncovered inputs.
4. **Framework-level scores aren't persisted.** The literal "…lowered your GDPR score" leg has no history to diff.
   Options: (a) add a small `framework_readiness` snapshot type to `ScoringService`/`score_snapshots` (the one
   net-new persisted thing — modest), or (b) v1 covers persisted scores and expresses the framework leg as a graph
   path ("Control X → obligations → GDPR framework") without a numeric framework delta. Recommend (b) for v1, (a)
   as a fast follow if a numeric per-framework delta is wanted.

**Verdict: 2–3 prompts confirmed** for Layer 1 + Layer 2 over the persisted score families; the only thing that
could nudge it is choosing to add the per-framework snapshot type (§5.4a). No hidden blow-up.

---

## 6. Proposed build sequence (after approval — no code yet)

1. `ScoreChangeAttributionService` — **Layer 1** arithmetic decomposition over two `ScoreSnapshot.breakdown_json`
   (generalize `_score_change_summary` into quantified per-component `points_delta`). Pure, unit-testable, no PG
   needed. Covers compliance/governance/risk-posture/control-health/evidence/task-hygiene.
2. **Layer 2** enrichment — windowed `domain_events` query (indexed) per moved component + `EntityGraphTraversalService`
   path from the changed entity to its frameworks/obligations; graceful fallback for uncovered inputs. Org-scoped.
3. Read endpoint `GET /scoring/snapshots/{type}/explain-change` + `score_attribution:read` permission
   (owner/admin + the four read roles, no scope creep), org-scoped from membership.
4. Tests: arithmetic decomposition exactness (a −4 pt move attributes to the right components summing to −4);
   real-PG windowed-cause + graph-path attribution for a control-failure → compliance-drop scenario; tenant
   isolation; `complivibe_test_user`.
5. **Deferred/documented (not built):** persist-at-materialize attribution history (§3); the numeric per-framework
   snapshot type (§5.4a); surfacing a significant score drop as a Phase-3 compound-insight/alert (natural tie-in —
   a score-drop attribution is exactly the shape Phase 3 already notifies on, and could reuse that path with an
   audit entry + notification).

---

## Sources searched (web, verified live)
- Causal attribution / change-explanation / event-sourcing-for-"why-changed" patterns and the caveat that
  change-score *analysis* isn't statistical causal inference (here it's deterministic arithmetic decomposition):
  [Azure Event Sourcing pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing),
  [Attribution-scores & causal counterfactuals (arXiv 2303.02829)](https://arxiv.org/abs/2303.02829),
  [Why observability needs causality](https://www.nofire.ai/blog/why-observability-needs-causality),
  ["change scores" don't estimate causal effects (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9557845/).

## Internal audit citations (this tree, commit 87c19b6)
- Org scores/formulas: `app/services/scoring_service.py:150-158,254,339-345,428,461-465,503,537,641,680-714`; `app/models/score_snapshot.py`.
- Existing attribution: `board_scorecard_service.py:427-512`; `risk_scoring_service.py:161-216`; `entity_risk_score_service.py:270-311,366-412`.
- On-the-fly framework scores: `compliance_dashboard_service.py:102-206`, `_underlying_data_changed_since:164`.
- Event flow: `app/core/event_bus.py:12-22,25-41,93-115`; `risk_recalculation_listener.py:146-164`; `entity_score_invalidation_listener.py:11-57`; `app/models/domain_event.py:24-54`.
- Graph traversal (Phase 2): `app/compliance/services/entity_graph_traversal_service.py`.
