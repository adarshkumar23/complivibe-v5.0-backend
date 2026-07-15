# Unified Cross-Entity Graph — Design Doc

Status: **DRAFT — awaiting review before any code is written.** No code in this phase.
Head at design time: `alembic heads` → `0303_domain_events` (single head). Branch `main`, commit `5658faa`.
Scope: design a unified graph spanning risks, controls, vendors, AI systems, policies, obligations, incidents — as one connected structure that **extends** existing edges, not a rebuild.

---

## 0. Headline findings — this is an EXTEND, and two stated premises are wrong

A codebase audit (grep-confirmed, not memory — see §1) changes the framing in three ways:

1. **A de-facto cross-entity graph already exists** and is the thing to extend: `app/compliance/services/risk_graph_service.py` — `RiskGraphService.build(risk_id, org_id, depth, db)` already walks risk→control→vendor/evidence/policy/obligation with **typed edges**, depth-capped at 2, pure-Python BFS. Plus a real self-referential cascade graph (`risk_dependencies`: `cascades_to`/`triggers`/`compounds`) and ~30 FK-enforced two-entity edge tables.

2. **There is NO "Trust Graph."** `trust_graph`/`TrustGraph` returns zero hits. The only "trust" surface is **Trust Center** (public disclosure pages) — unrelated to graphs. The design must not pretend to extend something that doesn't exist; the real per-entity risk-rollup substrate is `entity_risk_scores` (polymorphic `entity_type`+`entity_id`, no FK) — see §1.

3. **There is NO recursive-CTE traversal today.** Zero `WITH RECURSIVE` in `app/`. Risk propagation is Python BFS (`collections.deque` + `visited` set) in `risk_dependency_service.py` and `risk_graph_service.py`. So "recursive CTE already used for risk propagation" is not accurate — introducing recursive CTEs (§3) would be **new**, and that's a deliberate design choice with tradeoffs, not a continuation.

**Decision preview (full argument in §2): keep the ~30 existing edge tables as the FK-enforced source of truth (the standing "never rename/restructure integration seams" rule forbids collapsing them), and build a NEW unifying traversal layer on top — optionally backed by a derived, event-bus-maintained `graph_edges` projection used as a read cache, never as a second source of truth.**

---

## 1. Inventory — every existing graph-like structure (grep-confirmed)

388 tables, 307 migrations. No graph library, no SQL CTE traversal — all Python BFS.

### 1a. Self-referential / true graphs (node→same-node-type)
| Graph | Table | Edge column(s) | Traversal | Org-scoped |
|---|---|---|---|---|
| Risk cascade | `risk_dependencies` (`RiskDependency`) | `relationship_type` ∈ {`cascades_to`,`triggers`,`compounds`}, `upstream_risk_id`→`downstream_risk_id` | `risk_dependency_service.py:46` BFS + cycle-guard-on-create `:101` | yes |
| Vendor supply chain | `vendor_supply_chain_links` | `vendor_id`→`vendor_id` | — | yes |
| Cross-framework obligation equivalence | `cross_framework_obligation_mappings` | `obligation_id`↔`obligation_id` | — | yes |
| Data lineage | `data_lineage_nodes` + `data_lineage_edges` | `upstream_node_id`→`downstream_node_id`, `source_method` edge-type | — | yes |

### 1b. Two-entity edge tables (~30; all ORM models w/ FK + audit cols, org-scoped)
Risk-centric: `risk_control_links`, `risk_evidence_links`, `data_asset_risk_links`, `ai_system_risk_links`, `vendor_geopolitical_exposure.cascaded_risk_id`, `vendor_concentration_risk_detections.risk_id`.
Control-centric: `compliance_policy_control_links` **(the protected seam — never rename)**, `evidence_control_links`, `issue_control_links`, `legal_matter_control_links`, `ai_system_control_links`, `vendor_control_links`.
Obligation/policy/evidence/issue: `control_obligation_mappings`, `common_control_mappings`, `data_asset_obligation_links`, `ropa_framework_links`, `ai_system_evidence_links`, `legal_matter_evidence_links`, `policy_risk_links`, `policy_risk_mappings`, `issue_policy_links`, `policy_issue_links` (→`tasks`), `eu_act_annex_mappings`, `openscap_rule_mappings`.
Recommendation/suggestion edges: `obligation_control_recommendations`, `obligation_control_suggestions`, `finding_control_suggestions`, `sdf_designation_suggestions`, etc.

### 1c. Polymorphic rollup (the real precedent for a generic edge shape)
- `entity_risk_scores` (`entity_risk_score.py`) — `entity_type`+`entity_id` (**no FK**), aggregates risk onto ANY entity type. Proves the codebase already tolerates a controlled polymorphic pattern for a *derived* rollup — directly relevant to the projection option in §2.

### 1d. Cascade-trace edges (Phase 1)
- `domain_events.correlation_id` (indexed `ix_domain_events_correlation`) — every event in one cascade shares a `correlation_id` (`risk_recalculation_listener.py:147` re-emits carrying the parent id). This is a temporal cascade edge, complementary to the structural edges above.

### 1e. Duplicate seams to reconcile (flagged, not part of this phase)
- **policy↔risk**: `policy_risk_links` **and** `policy_risk_mappings` — two independent edge tables for the same pair.
- **control↔obligation**: `control_obligation_mappings`, `common_control_mappings`, plus suggestion/recommendation tables.
The unifying layer must map each of these to a single logical edge type (see §2) and pick one as canonical for traversal, without renaming either physical table.

---

## 2. Node/edge model — recommendation: unifying layer over existing tables (Option B), with an optional derived projection

### The two options
- **Option A — one generic `graph_edges(entity_type, entity_id, …, other_entity_type, other_entity_id, edge_type, metadata_json)` that subsumes the ~30 tables.** Rejected as the source of truth. Reasons: (a) it's a **polymorphic association**, which **cannot carry foreign keys** — you lose the referential integrity and `ondelete=CASCADE` the current tables enforce, and gain orphaned-edge risk ([Hashrocket], [GitLab]); (b) it flattens away per-edge columns the current tables need — `status`, `linked_by_user_id`/`unlinked_by_user_id`, soft-delete `deleted_at`, unique constraints; (c) it **violates the standing rule** never to rename/restructure integration seams (`COMPLIANCE_POLICY_CONTROL_LINKS` et al.). This is the same "don't orphan working, integrity-checked code" instinct that paid off in Phase 1.
- **Option B — keep the ~30 tables as source of truth; add a new read/traversal layer.** Recommended.

### Recommended architecture (Option B, two parts)

**Part 1 — an edge registry (code, no schema change).** A single declarative map that names every logical edge the graph exposes and how to read it from the existing tables:
```
EdgeSpec(edge_type="mitigated_by",
         source=("risk", "risks"), target=("control", "controls"),
         table="risk_control_links", source_fk="risk_id", target_fk="control_id",
         org_column="organization_id", directed=True, active_filter="deleted_at IS NULL")
```
One `EdgeSpec` per physical edge table (~30 rows of config). This is the *only* place that knows table names, so the protected seams are read, never touched. Duplicate seams (§1e) are resolved here by choosing one `EdgeSpec` as canonical per logical edge.

**Part 2 (optional, for performance) — a derived `graph_edges` projection table.** A single **append/upsert, org-scoped, polymorphic** table (`organization_id, source_type, source_id, target_type, target_id, edge_type, active, source_table, updated_at`) that is a **cache/materialization** of the registry's reads — *not* a source of truth. Because it is rebuilt from FK-enforced tables, the classic polymorphic orphan problem is bounded (a stale edge is self-healing on the next projection update). This gives uniform, index-friendly traversal (one table, one recursive query) while the real tables keep FK integrity + audit. `entity_risk_scores` is precedent that a controlled polymorphic derived table is acceptable house style.

**Recommendation:** ship Part 1 first (pure read layer, zero migration, can traverse via a UNION-ALL view over the existing tables). Add Part 2 only if §6 sizing shows real-time UNION traversal is too slow — and keep it strictly derived.

---

## 3. Traversal — recursive CTE with hard safeguards (new capability)

"If this vendor has a breach, what's at risk across my whole posture" = a bounded multi-hop reachability query from an anchor node. Today that's Python BFS capped at depth 2 (`risk_graph_service.py:129`). To span the whole graph we need deeper traversal; recommended engine is a **PostgreSQL recursive CTE** over either the UNION-ALL edge view (Part 1) or the `graph_edges` projection (Part 2), with **all** of these guards:

- **Depth guard** — carry a `depth` column, `WHERE depth < :max_depth` (default 4, see §6). Independent of PG's `max_recursive_depth`≈1000 default hard stop.
- **Cycle detection** — PostgreSQL 14+ `CYCLE edge_id SET is_cycle USING path` clause (or manual `path uuid[]` + `NOT (next_id = ANY(path))`). Required because this is a general graph (the risk cascade, vendor supply chain, and obligation-equivalence graphs all admit cycles) — `UNION ALL` without a visited-set would loop ([sqlfordevs], [PostgreSQL docs]).
- **Fan-out / result cap** — `LIMIT` on total visited nodes (e.g. 5,000) so a hyper-connected control can't produce a runaway result; return a "truncated" flag rather than a partial-but-unmarked set.
- **Directionality** — the CTE honors `EdgeSpec.directed`; "what's downstream of this vendor" walks forward edges, "what depends on this control" walks reverse. Undirected views (e.g. supply chain) traverse both.

Cross-check: keep the existing Python BFS (`risk_dependency_service`, `risk_graph_service`) working unchanged; the CTE is an additive traversal path for the whole-posture query, validated to return the same neighborhoods as the Python BFS at depth ≤ 2.

---

## 4. Event-bus integration — the graph projection is a derived, eventually-consistent bus subscriber

This is the natural next use of Phase 1's bus, and it's what makes the projection safe.

- The `graph_edges` projection (§2 Part 2) is **maintained by an event-bus listener**, not by every edge-writing call site. When an edge table changes, its domain publishes an event; a new `GraphProjectionListener` upserts/deactivates the corresponding projection row (org-scoped, inside the same SAVEPOINT-isolated dispatch Phase 1 built).
- Two ways to source those events, recommended in order: (a) **reuse existing events** where they already fire on edge changes (e.g. the vendor/DORA/geopolitical cascades already emit); (b) add a **generic `graph.edge_changed`** event type emitted by the link-service layer for edges that have no event yet. Prefer (a); only add (b) where there's a real gap, to avoid a blanket new emit on every join-table write.
- **Projection is derived, never authoritative.** If a listener fails, Phase 1's isolation logs it and the projection is stale, not corrupt; a periodic reconciler (re-read registry → diff → fix) closes drift. Reads that need strict correctness can fall back to the UNION-ALL registry view.
- Cascade edges: `correlation_id` chains stay in `domain_events` and can overlay the structural graph ("which structural edges did this incident actually propagate along") without being copied into `graph_edges`.

Open question for review: do we want the projection at all in v1, or ship the registry read-layer only and defer the projection+listener until sizing demands it? (Leaning: registry-only first — §7.)

---

## 5. Tenant scoping — org-scoped at every hop; shared nodes must never bridge orgs

Every edge table already carries `organization_id` (§1). The rule for the unifying layer:

- **Every `EdgeSpec` declares its `org_column`; the traversal filters `organization_id = :anchor_org` at the anchor AND at every recursive step** — not just the seed. The projection table is `organization_id`-scoped and every query is org-filtered.
- **The shared-node hazard is real and specifically guarded.** A vendor (or person, or obligation) referenced by two orgs does not create a bridge, because each org owns its **own** edge rows — org A's `vendor_control_links` and org B's are disjoint row sets, and the recursive step never joins across `organization_id`. Research on multi-tenant knowledge-graph traversal found **up to ~95% of benign queries leaked cross-tenant** precisely through "organic entity connections, shared vendors, and personnel that naturally exist across tenant boundaries" ([IJSRM], [Memgraph]) — so the org filter must live **in the recursive term itself**, and the design is tested with an org-A anchor that must never reach an org-B row even when both reference the same vendor id.
- Defense in depth: the projection can additionally store the pair `(source_org, target_org)` and assert `source_org = target_org` on every row, so a mis-projected cross-org edge is a constraint violation, not a silent leak.

---

## 6. Performance — rough sizing and the real-time vs precomputed line

Assumptions (demo/mid-market scale; to be re-measured on real volumes with the new `complivibe_test_user`, never a live role): per org, low-thousands of core entities, ~30 edge tables averaging low-thousands of rows each → tens of thousands of edges per org.

- **Real-time recursive CTE is fine at depth ≤ 4 with the fan-out cap**, on the projection (single indexed table) or even the UNION-ALL view for smaller orgs. Index: `(organization_id, source_type, source_id, active)` and the reverse `(organization_id, target_type, target_id, active)`.
- **Move to precompute when** any of: depth > 4 routinely; "whole-posture blast radius" run interactively per page-load; orgs with >~100k edges; or fan-out caps get hit often. Precompute options, in order: (a) the `graph_edges` projection (already recommended) collapses ~30 UNIONs into one scan; (b) a cached per-anchor neighborhood (short TTL, invalidated by the same bus events); (c) only if truly needed, a materialized reachability/closure table (expensive to maintain — defer hard).
- The existing depth-2 Python BFS stays as the cheap, always-correct path for the common "one entity's immediate neighborhood" view.

---

## 7. Suggested build sequence (after approval — no code yet)

1. **Edge registry (Part 1)** + a UNION-ALL edge view + recursive-CTE traversal service with all §3 guards + §5 org filtering. Tests: whole-posture query returns correct multi-hop set; matches Python BFS at depth ≤ 2; **cross-tenant anchor cannot reach another org's rows via a shared vendor**; cycle/depth/fan-out guards proven. Zero migration; protected seams read-only.
2. **`graph_edges` projection (Part 2) + `GraphProjectionListener`** on the bus, only if §6 sizing calls for it — derived, org-scoped, reconciler-backed.
3. Reconcile the duplicate seams (§1e) *in the registry only* (choose canonical), never by renaming tables.

---

## Open questions for review
1. **Projection in v1?** Registry read-layer only first (recommended), or build the `graph_edges` projection + listener now?
2. **Depth default** — 4 a good ceiling for the whole-posture query, with a truncation flag beyond it?
3. **Duplicate seams** — OK to pick `policy_risk_links` (vs `policy_risk_mappings`) and `control_obligation_mappings` (vs `common_control_mappings`) as canonical for traversal, leaving both physical tables intact?
4. **Node identity** — is `(entity_type, entity_id)` the node key (matching `entity_risk_scores`), and do we enumerate the node types now: risk, control, vendor, ai_system, policy, obligation, incident/issue, evidence, data_asset, legal_matter?
5. **Incidents** — the goal lists "incidents"; today the closest is `issues` / `data_incidents`. Confirm which is the incident node.

## Sources searched
- Polymorphic association FK/integrity tradeoffs: [Hashrocket](https://hashrocket.com/blog/posts/modeling-polymorphic-associations-in-a-relational-database), [GitLab Docs](https://docs.gitlab.com/development/database/polymorphic_associations/)
- Recursive CTE cycle detection / depth guards: [PostgreSQL WITH Queries](https://www.postgresql.org/docs/current/queries-with.html), [sqlfordevs — cycle detection](https://sqlfordevs.com/cycle-detection-recursive-query)
- Graph vs relational edge-storage tradeoffs: [Neo4j](https://neo4j.com/blog/graph-database/graph-database-vs-relational-database/), [Memgraph](https://memgraph.com/blog/graph-database-vs-relational-database)
- Multi-tenant graph isolation / shared-node cross-tenant leakage: [IJSRM — Graph-Based Multi-Tenant Security](https://ijsrm.net/index.php/ijsrm/article/view/3360/3744), [Memgraph — multi-tenancy](https://memgraph.com/blog/why-multi-tenancy-matters-in-graph-databases)
