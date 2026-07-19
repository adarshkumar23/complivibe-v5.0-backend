# Shadow-AI signature detection — graft notes and tracked follow-ups

Built 2026-07-19 on top of `2985550`. Ports the novel capabilities of the
`shadow-ai-discovery-engine` patent repo into core as an **additive-parallel**
subsystem, the same pattern used for P2's governance-graph vs. core's
entity-graph.

## What was grafted

| Capability | Tables | Endpoints |
|---|---|---|
| Signature-scored detection | `shadow_ai_signature_registry`, `shadow_ai_telemetry_events`, `shadow_ai_signature_detections` | telemetry ingest, rescan, list/get detection, review |
| Decay tracking | (columns on `shadow_ai_signature_detections`) | decay |
| IdP scan (tier 2) | `shadow_ai_idp_connections`, `shadow_ai_idp_sync_logs` | idp scan |
| Federated detection | `shadow_ai_federated_observations`, `shadow_ai_federated_submissions` | federated submit, candidates |
| Suppression | `shadow_ai_suppressed_detections` | suppressions |

Migrations `0314` (tables) and `0315` (permission backfill), chained on `0313`.
Permission codes `shadow_ai_signature:read/write/review/admin` (208 → 212).

## What was NOT grafted, and why

The upstream repo has 20 tables. Only the 8 above serve the four named
capabilities. Deliberately excluded because core already owns the concern:

* `ai_systems` — core's real, populated inventory is the promotion target.
  The upstream `i007` stub could never retrofit it (NOT NULL unique
  `source_detection_id`), so that migration is dropped entirely rather than
  ported.
* `audit_logs` — core's `AuditService` is used instead.
* `vendors`, `vendor_assessments`, `vendor_dpa_records`, `vendor_ai_contamination`
  — core has a full vendor/TPRM domain.
* `questionnaire_responses` — core has `vendor_questionnaire_responses` and
  `inbound_questionnaire_*`.
* `regulation_nodes`, `regulation_articles` — core has frameworks/obligations.
* `zero_day_candidates`, `connector_tokens`, `connector_heartbeats` — outside
  the four named capabilities; core has `cloud_evidence_connectors` and the
  `patent_scoped_keys` pattern for the connector concerns.

## Reconciliation applied

* **Table rename.** Upstream `shadow_ai_detections` collides with core's live
  table under an incompatible schema, so it is `shadow_ai_signature_detections`
  here. Every other table is namespaced `shadow_ai_*` for the same reason.
* **AuditService.** All call-sites use core's frozen instance signature
  `AuditService(db).write_audit_log(*, action, entity_type, organization_id,
  actor_user_id, ...)`. Upstream called a non-existent `.log()` staticmethod.
* **Permissions.** Real `require_permission` on every endpoint, replacing the
  upstream always-allow stub. Codes are deliberately distinct from the
  `ai_systems:*` codes governing core's separate feature.
* **Migration chain.** Upstream started at `down_revision = None` (a second
  Alembic root). Re-authored as a linear `0313 → 0314 → 0315`.
* **UUID.** No rework was required — contrary to the integration audit, the
  repo has **zero** `BigInteger` usage and was already UUID-native. (The
  BigInteger finding belonged to P2 and was carried over in error.)

## Tracked follow-ups — product decisions, not code gaps

### 1. Two Shadow-AI detection results for the same tool (UX)

Core's existing feature and this one can each hold a row for, say, "ChatGPT" —
one a coarse human/scanner report, one a scored inference. That is the intended
outcome of a graft, but the UI will eventually need to decide whether to merge
them in the presentation layer, cross-link them, or show two lists. **No code
should resolve this until the product decision is made.** Same treatment as the
KRI/appetite write-permission gap and the compliance-bot delivery question.

### 2. The patent scoring formula does not damp an uncorroborated signal

Characterised by test, not assumed. The formula divides by the summed weight of
*contributing* signals only:

```
ConfidenceScore = Σ(weight[i] × score[i]) / Σ(weight[i])   # contributing i only
```

So a single perfect keyword match on the lowest-weighted axis (0.10) scores
**1.0 — identical to full four-tier corroboration**. The weights rank signals
against each other within a scan; they do not express "one signal is weaker
evidence than four". A lone questionnaire mention therefore lands in the HIGH
band.

This is a property of the patent-invariant algorithm, which the brief says must
not be modified, so it is preserved verbatim and asserted in
`test_patent_benchmark_weighted_multi_tier_aggregation`. If the product wants
corroboration to actually raise confidence, that is a **patent-claim change**,
not an implementation fix, and needs to go back to the patent author.

### 3. No scheduler wiring

`recompute_detections`, `apply_decay` and `record_idp_scan` are reachable only
via their endpoints. They are deliberately **not** registered in
`pbc_scheduler.py` yet — the scheduler's duplicate-execution defect was only
just fixed (`2985550`), and adding jobs is a separate decision. This is the same
"built but never triggered" category the FEATURE_INVENTORY walk flagged; it is
recorded here so it is visible rather than silent.

### 4. Federated pooling is single-instance

`shadow_ai_federated_observations` aggregates across tenants **within one
deployment**. Cross-deployment federation (the upstream repo's submission-token
design) is not ported; it needs a trust and privacy decision first.
