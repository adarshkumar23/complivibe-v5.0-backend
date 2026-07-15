# Governance Autopilot — Cross-Domain Graph-Aware Reasoning (Design Doc)

Status: **DESIGN ONLY — awaiting review before any code is written.** Given Autopilot's safety history,
this design is written to be read more carefully than any prior phase's, and it deliberately recommends
expanding Autopilot's *reasoning* without expanding its *authority*.
Head at design time: `alembic heads` → `0304_compound_insights` (single head). Branch `main`, commit `e5df769`.

Goal: let Autopilot's candidate-action engine reason across the connected picture (Phase 1 event bus +
Phase 2 graph + Phase 3 compound insights + Phase 4 causal attribution) instead of domain-local signals alone.

---

## 0. Headline recommendation, and the one piece I recommend NOT building

**Recommendation: v1 graph-aware reasoning is SUGGESTION-ONLY.** New cross-domain candidate sources may
enrich *what Autopilot proposes and how it explains it*, but cross-domain-sourced candidates route to
**human approval regardless of their low-risk action type** — they do **not** become auto-executable in v1.
This is the textbook safe pattern for the situation the task describes (expanded blast radius): *the agent
proposes, a human disposes, while trust is built* ([Microsoft], [Strata]). It means this phase's larger
reasoning surface touches **zero** new autonomous authority.

**The piece I explicitly recommend NOT building (yet):** auto-execution of cross-domain-sourced actions.
Even though the only actions these sources can emit are individually low-risk (`send_reminder`,
`flag_stale_evidence`, `refresh_signals`), the *combination* of "wider blast radius" + "auto-execute" is
exactly where expanded reasoning would meet autonomous authority. Defer it behind its own future opt-in,
enabled only after the suggestion-only behavior is proven in production. Everything below is designed so
that deferral is the default and enabling auto-exec later is a deliberate, isolated switch — never a silent
consequence of "smarter" reasoning.

---

## 1. Audit — how Autopilot actually works today (grep-confirmed; engine in `app/services/ai_system_risk_assessment_service.py`)

Auto-execution authority is already very narrow, with multiple independent walls:
- **Candidates are deterministic, signal-derived** (`_candidate_actions_from_prioritized_signals:3865`), never
  model-generated. Real-execution signals come from `_build_real_execution_signal_candidates:3180`
  (staleness/structural checks; `GOVERNANCE_SIGNAL_ASSESSMENT_STALE_THRESHOLD_DAYS = 30`).
- **Risk tier is server-computed and never client-trusted** (`classify_candidate_action_risk_tier:3834`;
  `# SECURITY: risk_tier must never be trusted from client input`, `:6266`). `low_keys =
  {flag_stale_evidence, send_reminder, refresh_signals}`; `high_keys` + `destructive_tokens`
  (delete/remove/purge/revoke/destroy/close) force `high`; default is `high`.
- **Only `risk_tier == "low"` can auto-execute.** `medium` and `high` both route to human approval
  (`_should_auto_execute_action:7227` appends `risk_tier_not_low` / `high_risk_requires_human_approval`).
- **Confidence is a fixed internal `0.5`** (`AUTOPILOT_DEFAULT_CONFIDENCE_SCORE = 0.5`; client value
  discarded, `:6274` `# a self-declared 1.0 could otherwise force auto-execution`) vs a **`0.95`** default
  threshold — so nothing auto-executes unless an org lowers its threshold to ≤ 0.5.
- **The auto-execute gate requires ALL of:** `risk_tier=="low"`, `confidence>=threshold`,
  `automation_allowed==True` (every template ships `False`), policy `allowed_by_policy` and not
  `requires_human_approval`, org `autopilot_auto_execute_enabled==True`, and a registered real-execution
  runner (only 3 exist).
- **Opt-in defaults OFF** (`organization_governance_setting.autopilot_auto_execute_enabled=False`, threshold
  `0.95`, `reversal_window_hours=24`); policy `mode` default `suggest_only`; capability flags default `False`.
- **No owner/admin to notify ⇒ auto-execution is blocked (409)** (`:7145`) — it never executes silently.
- **Reversal** is window-bound (`reversal_deadline_at = now + window`, default 24h) with stored before/after
  inverse snapshots, row-locked, double-reversal/expiry-rejected (`reverse_autopilot_execution:7389`).
- **Circuit breaker** (`_run_autopilot_circuit_breaker:7259`) runs after every auto-exec and every reversal;
  trips on reversal-rate > 0.2 (n≥3/24h), reversal-rate ≥ 1.0 (n≥2), or a 1h volume spike (≥3× baseline,
  floor 10); tripping flips org `autopilot_auto_execute_enabled=False` + a loud email.
- **Self-approval block (the prior-bug area) is clean in `app/`.** The historical `enforce_requester_self_block=False`
  parameter is **gone from shipping code** (survives only in `.claude/worktrees/agent-*` snapshots). Current
  self-block is inline (`vote_approve_execution_approval:11669` — `if block_requester_self_approval and voter
  is not None: if requester==voter: raise`), backed by a DB unique-vote constraint
  (`uq_gov_ap_exec_appr_votes_org_appr_voter_*`). No `skip_*/enforce_*/override_*` flags remain on any approval fn.

**Two real gaps the audit surfaced (worth fixing this phase, since blast radius grows):**
(a) there is **no `governance_autopilot_execution.executed` audit-log entry** — an auto-exec is only captured
under the intent-created audit row + the execution row + the email; and (b) a **circuit-breaker trip writes no
audit log**. Both should be closed to satisfy constraint #3 ("complete audit trail") as authority-adjacent
surface expands.

---

## 2. Concrete new cross-domain candidate SOURCES (real Phase 1–4 data)

The safe move is to add new *signal sources*, each of which maps **only to the existing low-risk action
types** — never a new action type. Three concrete ones:

**Source A — Compound insight → notify the responsible owners (Phase 3).**
A surfaced `compound_insights` row (e.g. pattern A: failed control + ≥30d-stale vendor + open high risk) is
already a *code-confirmed* cross-domain exposure. Autopilot proposes a **`send_reminder`** to the owners of the
matched nodes (control owner, vendor owner) pointing at the compound insight. Deterministic (the insight was
detected deterministically in Phase 3), reuses the existing `send_reminder` runner.

**Source B — Graph-confirmed stale dependency → flag it (Phase 2 + staleness).**
When a vendor with a ≥30d-overdue assessment is graph-connected (via `EntityGraphTraversalService`,
`vendor_provides_control` → `mitigated_by`) to a control mitigating an open high/critical risk, Autopilot
proposes **`flag_stale_evidence`** on that dependency (a flag/annotation), or a `send_reminder` to the vendor
owner. Reuses existing low-risk runners; the graph link is the new, org-scoped input.

**Source C — Causal score-drop attribution → nudge the attributed owner (Phase 4).**
When `ScoreExplanationService` attributes a score drop to a *specific* entity with event coverage (e.g.
evidence readiness dropped, attributed to a real expired evidence item), Autopilot proposes a
**`send_reminder`** to that entity's owner to refresh it. The cause entity is deterministic (Phase 4 Layer 2
returns a real triggering entity, never a fabricated one — path-only framework legs are excluded here).

All three emit only `send_reminder` / `flag_stale_evidence` / `refresh_signals`. **No new action type, no new
runner, no new destructive capability.** They widen *inputs*, not *outputs*.

---

## 3. Risk classification of each new source's actions

| Source | Emitted action type(s) | Risk tier (per `classify_candidate_action_risk_tier`) | v1 disposition |
|---|---|---|---|
| A — compound insight | `send_reminder` | **low** | **human approval (suggestion-only)** |
| B — graph-confirmed stale dep | `flag_stale_evidence`, `send_reminder` | **low** | **human approval (suggestion-only)** |
| C — score-drop attribution | `send_reminder` | **low** | **human approval (suggestion-only)** |

The *action* is low-risk in every case (a reminder is a reminder no matter what prompted it). **But per the
task's "default to caution" rule, and because the trigger is now cross-domain (wider blast radius), v1 routes
all cross-domain-sourced candidates to human approval regardless of the low classification** (§0). So even the
low-risk classification does not make them auto-executable in v1 — a second, source-based gate keeps them
human-disposed. If any future source were ever to emit a non-low action, the existing action-derived
classifier already forces approval; the source allowlist (§4) prevents it from arising at all.

---

## 4. Confidence & cross-domain corroboration — and the hard safeguard (capability ≠ authority)

**Q: could richer cross-domain input ever make a HIGH-risk action auto-executable where simpler logic kept it
human-gated? → Hard NO, enforced by four independent walls:**

1. **Source action allowlist (new, generation-time).** A cross-domain source may only emit a candidate whose
   `action_key` is in `CROSS_DOMAIN_SOURCE_ALLOWED_ACTIONS = {send_reminder, flag_stale_evidence,
   refresh_signals}` — asserted where the candidate is built. A cross-domain source *physically cannot* propose
   `close_risk`/`delete_*`/etc. (It's the same "no actions by default; enable explicitly" principle — [Microsoft].)
2. **Action-derived risk classification stays the sole authority.** Risk tier is computed from the
   action_key/action_type (`classify_candidate_action_risk_tier`), **never** from the trigger, confidence, or
   any reasoning signal — unchanged. Cross-domain corroboration is *not an input to it*.
3. **The auto-execute gate reads no reasoning signal.** `_should_auto_execute_action` keeps reading only
   {risk_tier, confidence, automation_allowed, policy, opt-in}. Cross-domain corroboration must **not** be
   plumbed into `confidence_score` (which feeds the gate); it lives in a *separate* `human_review_context`
   field used only to rank/annotate for humans. This is the crux: **corroboration raises human-review priority,
   never auto-execute eligibility.**
4. **v1 source gate (§0/§3).** Cross-domain-sourced candidates are approval-routed regardless of low tier, so
   even walls 1–3 are backed by "these don't auto-execute at all in v1."

**On confidence specifically:** do **not** compute a higher confidence from "confirmed by both a compound
insight AND a graph traversal." Corroboration is real and useful — but it belongs in the *human-facing
explanation and prioritization*, not in the number that gates autonomy. Letting corroboration raise the
auto-execute confidence is precisely the mechanism by which "more sophisticated reasoning" could erode the
boundary; the design forbids that plumbing and a test must assert the auto-execute gate is *independent of any
cross-domain field*.

---

## 5. Circuit breaker — applies unchanged (source-agnostic), plus close the audit gaps

The breaker measures reversal-rate and volume on `GovernanceAutopilotExecution` rows **regardless of what
generated them**. That is exactly the right property: a spike or high reversal rate from cross-domain-sourced
executions trips it identically. **No threshold change is warranted** — the thresholds bound *outcomes*
(reversals/volume), not sources, so a new source is automatically covered. Recommended additions (small, safe):
- **Tag each execution with its `candidate_source`** (`domain_local` | `compound_insight` | `graph_dependency`
  | `score_attribution`) for observability and post-hoc analysis — informational only, never read by any gate.
- **Fix the two audit gaps (§1):** add `governance_autopilot_execution.executed` and
  `governance_autopilot_circuit_breaker.tripped` audit-log entries (unchanged `AuditService.write_audit_log`
  signature). Since v1 is suggestion-only, cross-domain candidates don't execute yet — but these fixes should
  land regardless, and are prerequisites before any future cross-domain auto-exec opt-in.

---

## 6. Self-approval / authorization audit of every new path (the prior-bug class)

The new code is **candidate GENERATION only** — it feeds the *existing* `create_execution_intent` →
`_should_auto_execute_action` / approval-routing path unchanged. Explicit commitments:
- **Zero new boolean safety flags.** The new sources introduce no `skip_*/enforce_*/override_*/allow_*` param.
  They call the same gate and (in v1) always land in approval routing. A test asserts the new sources add no
  new parameter to any authorization/gate function.
- **No new approval/execution entry point.** Cross-domain candidates do not touch `vote_approve_execution_approval`
  or `_auto_execute_candidate_action` with any new argument; the self-block, distinct-approver DB constraint,
  and quorum logic are reused verbatim.
- **Harden the one structural soft-spot the audit found.** `vote_approve_execution_approval` currently *skips*
  the self-block when `voter_user_id is None` (`:11674`). It's unreachable via the authenticated API, but it is
  the exact structural analogue of the prior bug (a condition that silently disables a safety check). This phase
  should **reject `voter_user_id is None` outright** rather than skip the check — a one-line defense-in-depth
  hardening worth doing now that Autopilot's blast radius is the whole connected system.

---

## 7. Tenant scoping

Every cross-domain input is strictly `organization_id`-scoped, reusing proven isolation:
- Graph traversal via `EntityGraphTraversalService(..., organization_id=org_id)` — org-filtered at every hop
  (Phase 2: 0 cross-tenant bleed under concurrency).
- `compound_insights`, `score_snapshots`/`domain_events` (Phase 4) — all org-scoped queries.
No cross-domain candidate can be generated from another org's data.

---

## 8. Independent kill-switch — YES, recommended

Add a **separate** `autopilot_graph_reasoning_enabled` org setting (**default False**), independent of the base
`autopilot_auto_execute_enabled`. This gives three independent switches, most-restrictive-wins:
1. base Autopilot opt-in (existing, default off),
2. **graph-aware reasoning opt-in (new, default off)** — disables *only* the new cross-domain candidate
   generation without touching base Autopilot,
3. the circuit breaker (existing org-wide auto-exec kill).
So an operator can kill the new graph-aware behavior instantly and in isolation if it misbehaves, while leaving
the proven domain-local Autopilot running — and, because v1 is suggestion-only, worst case is "too many
proposed reminders for humans to review," never an unwanted auto-execution.

---

## Concerns / what I would NOT proceed with
- **Do not auto-execute cross-domain-sourced actions in v1** (§0) — defer behind its own future opt-in.
- **Do not feed cross-domain corroboration into the auto-execute confidence/gate** (§4) — it must live only in
  human-review context, or the low-risk-only boundary can be eroded.
- Proceed with: the three new suggestion-only sources, the independent kill-switch, the source allowlist +
  the `voter_user_id is None` hardening + the two audit-log gap fixes. Nothing here expands autonomous authority.

## Sources searched (web, verified live)
- Safe autonomous-agent scope/authority separation, defense-in-depth, deterministic escalation, HITL as a
  governance (not just trust) control, "agent proposes / human disposes" during rollout:
  [Microsoft — Defense in depth for autonomous AI agents](https://www.microsoft.com/en-us/security/blog/2026/05/14/defense-in-depth-autonomous-ai-agents/),
  [Strata — Human-in-the-Loop 2026](https://www.strata.io/blog/agentic-identity/practicing-the-human-in-the-loop/),
  [NIST — defense-in-depth glossary](https://csrc.nist.gov/glossary/term/defense_in_depth).

## Internal audit citations (this tree, commit e5df769)
- Engine/gate: `app/services/ai_system_risk_assessment_service.py` — `classify_candidate_action_risk_tier:3834`,
  `_should_auto_execute_action:7227`, `create_execution_intent:7471`, `_auto_execute_candidate_action:7127`,
  `_run_autopilot_circuit_breaker:7259`, `reverse_autopilot_execution:7389`, `vote_approve_execution_approval:11669`,
  constants `:207-217`; capability matrix `:408-574`.
- Opt-in/policy: `app/models/organization_governance_setting.py:22-24`, `app/schemas/organization.py:45-47`,
  `app/models/governance_autopilot_policy.py`, `app/models/governance_autopilot_approval_policy.py:24-30`.
- Notification/audit: `_queue_autopilot_notification:6980`; audit strings in `app/api/v1/ai_governance.py`.
