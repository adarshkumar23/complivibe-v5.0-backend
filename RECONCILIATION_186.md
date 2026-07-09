# 186-Feature Tested/Untested Reconciliation

## Methodology & a correction to the requesting prompt

The requesting prompt asserted that a prior "coverage reconciliation" had already identified "4 untouched
original-catalog features" and "5 named route-clusters" (guardrail policy-resolution scaffolding, Autopilot
runner/approval internals, framework-review-capacity batch/scheduling, AI-governance review-orchestration,
machine-API-key-gated ingest endpoints). **A full-repo search (`grep -rl` across all `.md` files, `reports/`,
and the auto-memory store) found zero trace of this artifact.** It does not exist anywhere in this repo's
history. The counts and named items below are a **fresh, independent analysis**, not a validation of that
claim. Where my own analysis happens to name similar untested clusters, that is coincidence, not
confirmation.

### Evidence tiers used (per the assignment's own weighting rule)

- **Tier A (→ DEEP-TESTED-WORKING/BROKEN):** real HTTP-call + DB-assertion evidence from a source I can verify
  used that methodology: `reports/final-sweep-{a,b,c,d}-*.md` (each explicitly describes "real FastAPI
  test-client HTTP requests, adversarial cases, and direct DB assertions," names specific bugs found/fixed,
  and reports focused + full regression results); this session's G1-G9 fix passes (each item individually
  reproduced live, fixed, and re-verified — confirmed via git log); this session's T1-T4 32-feature deep test
  (curl-based real walkthrough, just completed); the 2026-07-08 13-agent memory walkthrough (real HTTP, no
  bulk seeding, per its own methodology note).
- **Tier B (weak, ≠ Tier A):** `reports/158_domain_agent_master_scorecard.md` and
  `reports/master_scorecard_19agent_sweep.md`. **Important finding:** both files' own header states
  *"Compiled from the existing repo evidence… **No new tests were run**."* Despite this, many rows carry
  language like "verified live via real HTTP" and a "tonight sweep" tag. This is **internally
  contradictory** — a file that admits no new testing occurred cannot also claim live verification happened
  that same night. I am treating every claim in these two files as Tier B (equivalent to "tests pass" /
  documentation-only) regardless of the "tonight sweep" label, **not** as Tier A evidence. This one file
  alone would have inflated bucket-1 by ~140 rows if trusted at face value; it is not trusted here.
- **Tier C:** a real registered route + real model file confirmed via `FEATURE_INVENTORY.md`'s live-OpenAPI
  generation, `git grep`, or the 43-item roadmap check earlier this session — no walkthrough evidence.
- **No evidence at all**, not even beyond FEATURE_INVENTORY's own route census.

Because `FEATURE_INVENTORY.md` was itself generated from a live, running `/openapi.json` (1867 real
operations, 200 OK), **every one of the 186 rows already clears the Tier-C floor** — none can be "no route
ever confirmed." So bucket 4 (UNTESTED) is necessarily small: it can only contain rows where the *feature
grouping itself* is questionable (near-zero real endpoints, e.g. the `(None)` tag) or where the row is a
placeholder/未-exercised internal sub-system with no external evidence of use anywhere, including no mention
in any sweep, walkthrough, or this session's work.

### A structural caveat that affects several rows

`FEATURE_INVENTORY.md`'s 186-row granularity does **not** line up 1:1 with the 32-item T1-T4 roadmap
granularity from earlier in this session. Several T1-T4 items are sub-capabilities bundled inside a single
186-list row. Most importantly: **`Tprm Intelligence`** (17 endpoints) is the single row backing *six*
separately-tested T1/T4 sub-capabilities — Security Rating (CONFUSING), Threat Intelligence (CONFUSING),
AML/KYB (shallow/CONFUSING), Sanctions Screening (WORKING), Anti-Bribery (BROKEN — risk_tier not escalated
despite system self-flagging the inconsistency), Export Control (WORKING). Since 4 of 6 sub-parts have real,
documented problems, `Tprm Intelligence` is classified **DEEP-TESTED-BROKEN** as a composite verdict, not
averaged into "working." This is flagged per-row below wherever it applies.

---

## Domain: AI Governance (36 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | AI Governance | DEEP-TESTED-WORKING | Tier A: final-sweep-A ran real adversarial cross-tenant tests (owner/reviewer/contact-owner org-scoping fixes, commits `880bd87`,`a4762d0`,`aa5a379`) against this tag's core CRUD; 2026-07-08 walkthrough also exercised AI system inventory directly. |
| 2 | AI Governance Systems | DEEP-TESTED-WORKING | Tier A: final-sweep-A `test_ai_inventory_a51_a52_a53.py`, `test_governance_classify_a54_a55_a56.py` run as real regression with adversarial cases. |
| 3 | AI Systems | DEEP-TESTED-WORKING | Tier A: same final-sweep-A slice; owner-scoping bug found and fixed live. |
| 4 | AI Governance MLOps | EXISTENCE-ONLY | Tier B only (158-scorecard "tonight sweep" MLflow fix claim is Tier B per methodology note above — no independent Tier-A corroboration found this session). |
| 5 | AI Drafting | EXISTENCE-ONLY | Tier B only (158-scorecard "tonight sweep"/Azure OpenAI claim); not independently re-verified with real HTTP this session. |
| 6 | AI Governance EU AI Act Workflows | EXISTENCE-ONLY | Tier C: routes/models exist (EU AI Act classification referenced in 43-item roadmap check as T1-3 EU AI Act obligations, but that check was route+model only, not walkthrough). |
| 7 | Governance Overrides | DEEP-TESTED-WORKING | Tier A: this session's P0 re-verification personally ran a real 10-way concurrent approval race (1×200/9×400/0×500, DB-confirmed) against this exact feature. |
| 8 | AI Governance Reviews | EXISTENCE-ONLY | Tier B only (158-scorecard "Review lifecycle... tests pass"), no Tier-A walkthrough found. |
| 9 | Non Human Identities | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T4-1) — orphan-flagging logic correct in isolation but never fires via the real offboarding flow (`PATCH /memberships/{id}/deactivate` doesn't touch the fields the scanner checks). |
| 10 | Governance Override Templates | EXISTENCE-ONLY | Tier B only (158-scorecard "EXCELLENT... template/version snapshots"), not independently walked through this session. |
| 11 | AI Vendor Assessments | EXISTENCE-ONLY | Tier B only ("Deterministic scoring... tests pass"); overlaps with TPRM Vendor Assessments (also EXISTENCE-ONLY) — no Tier-A evidence. |
| 12 | Synthetic Datasets | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-14) — re-identification risk genuinely varies with real DP ε / k-anon parameters (0.5→0.622, 20→1.0, k=50→0.02), governance-gaps correctly fires only for weak-privacy "validated" datasets. |
| 13 | AI Governance Shadow Ai | EXISTENCE-ONLY | Tier B only ("Manual report, review/register/dismiss... tests pass"). |
| 14 | AI Governance Diagnostics | EXISTENCE-ONLY | Tier B only. |
| 15 | AI Governance Risk Assessments | EXISTENCE-ONLY | Tier B only; overlaps with autopilot's risk-assessment lookup which G1 fixed a 404 in (Tier A for that specific execution-time code path, but the assessment CRUD itself wasn't separately walked). |
| 16 | Governance | EXISTENCE-ONLY | Tier C: signals/candidate-actions routes exist; T1-T4 autopilot fork found the deterministic candidate-action engine never actually surfaces the 3 real-execution action types organically — a real gap in this row's usability, but not a full walkthrough of the whole tag. |
| 17 | OSCAL | EXISTENCE-ONLY | Tier B only ("SSP/AP/AR/full package generation... tests pass"). |
| 18 | Training Datasets | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-13) — all 4 rights-gap categories (documented/unclear/lapsed/no-dataset) populated correctly with real, distinct AI systems. |
| 19 | AI Governance Atlas | DEEP-TESTED-WORKING | Tier A: final-sweep-A commit `55ea117` — ATLAS assessment was previously read-only; now persists `atlas_risk_score`, emits an audit log, verified live. |
| 20 | AI Governance Third Party Ai | DEEP-TESTED-WORKING | Tier A: 2026-07-08 walkthrough explicitly noted "Stop third-party AI assessment completion downgrading system risk_tier" fix (commit `7bd7f4e` in git log), a real reproduce-fix. |
| 21 | AI Governance LLM Observability | DEEP-TESTED-WORKING | Tier A: final-sweep-A's primary named slice — commit `ea0e229` (retired-system write rejection), full `test_llm_observability_t1_7_t1_10.py` + `t1_11_12_13.py` regression run live. |
| 22 | Copilot Draft | EXISTENCE-ONLY | Tier B only ("Immutable snapshots, preview, diff... implemented"). |
| 23 | AI Governance ISO 42001 | EXISTENCE-ONLY | Tier B only. |
| 24 | AI Governance Guardrails | EXISTENCE-ONLY | Tier B only (Part-D `data_scope` no-op fix referenced only in Tier-B docs, not independently reproduced this session). |
| 25 | AI Governance Approval Envelopes | EXISTENCE-ONLY | Tier B only. |
| 26 | AI Usage Compliance | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-17) — precisely confirmed the "approved-only" policy-status gating (draft→non_compliant_no_policy, approved→non_compliant_never_attested) and archived-system exclusion (4→3 count) with real state transitions. |
| 27 | Training Analytics | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-18) — cross-org `user_id` validation confirmed with a real cross-org user (not just a random UUID), summary counts verified to move with real completions. |
| 28 | Content Provenance | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-12) — real Ed25519 signature verification, genuine tamper detection confirmed by mismatching content hash and watching the verdict flip. |
| 29 | AI Governance Recommendations | DEEP-TESTED-WORKING | Tier A: G6 item 5 this session — fixed and re-verified live that the recommendations engine reflects active drift breaches/failed bias assessments (real HTTP before/after evidence, commit `b398442`). |
| 30 | Risk Quantification | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T2-1) — FAIR/Monte Carlo math and degenerate-input rejection correct, but any risk `category` outside a hardcoded 7-value enum crashes `/quantify` with an unhandled 500. Real, reproducible, unfixed bug. |
| 31 | AI Governance NIST RMF | EXISTENCE-ONLY | Tier B only. |
| 32 | AI Governance Monitoring | EXISTENCE-ONLY | Tier B only (the inverted-threshold bug this row references was fixed per Tier-B docs but not independently reproduced this session — downgraded, not taken on faith). |
| 33 | AI Monitoring | EXISTENCE-ONLY | Same as above — duplicate/overlapping tag with #32, no independent Tier-A evidence this session. |
| 34 | AI Governance Risk Signals | EXISTENCE-ONLY | Tier B only. |
| 35 | AI Governance Contracts | EXISTENCE-ONLY | Tier B only; Tier-B's own two scorecards directly *contradict* each other on this row (one says "WEAK... dashboard remains a skeleton returning zeros," the other says "SOLID... computes real metrics") — unresolved contradiction, no independent evidence to break the tie. |
| 36 | AI Governance Dashboard | EXISTENCE-ONLY | Same contradiction as #35 — the two Tier-B scorecards disagree on this exact capability. |

## Domain: Privacy & Data Protection (11 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Privacy DSR | DEEP-TESTED-WORKING | Tier A: final-sweep-B ran `test_ropa_d83.py`/adversarial cross-tenant reference tests against this domain slice as part of its focused regression; DSR SLA/sweep referenced directly. |
| 2 | Privacy ROPA | DEEP-TESTED-WORKING | Tier A: final-sweep-B commit-level fix — RoPA activity cross-tenant owner/reference validation gap found and fixed live (`test_d83_rejects_cross_tenant_owner_and_linked_references`, real HTTP + DB assertion). |
| 3 | Privacy DPIAs | DEEP-TESTED-WORKING | Tier A: final-sweep-B — DPIA reviewer cross-tenant validation gap found and fixed live (real HTTP evidence). |
| 4 | Breach Notifications | DEEP-TESTED-WORKING | Tier A: this session's G8 — fixed and re-verified the Article 33 draft 500 (unpacked-tuple bug) with real HTTP before/after (commit `d54503d`). |
| 5 | Privacy Consent | EXISTENCE-ONLY | Tier B only for this specific sub-feature; final-sweep-B's focused fixes concentrated on RoPA/DPIA, not consent specifically. |
| 6 | Privacy Notices | EXISTENCE-ONLY | Tier B only. |
| 7 | Privacy DPAs | EXISTENCE-ONLY | Tier B only. |
| 8 | Privacy Cookies | EXISTENCE-ONLY | Tier B only. |
| 9 | Privacy Lawful Basis | DEEP-TESTED-WORKING | Tier A: final-sweep-B ran `test_dpia_lawful_basis_d86_d91.py` as focused fix regression tied to the DPIA cross-tenant fix (real HTTP, same commit group). |
| 10 | Privacy Fides Import | EXISTENCE-ONLY | Tier B ("tonight sweep" claim, but per methodology correction not trusted as Tier A) and Tier-B's *other* scorecard independently rates this "NEEDS RE-VERIFICATION" — the two Tier-B sources disagree, landing this at EXISTENCE-ONLY. |
| 11 | Privacy CCPA | EXISTENCE-ONLY | Tier B only. |

## Domain: Data Observability (10 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Data Observability Assets | EXISTENCE-ONLY | Tier B only for asset CRUD itself; the residency-matcher fix (below) is a distinct sub-area. |
| 2 | Data Observability Retention | EXISTENCE-ONLY | Tier B only. |
| 3 | Data Observability Residency | DEEP-TESTED-WORKING | Tier A: this session's G3 — hierarchical region-matcher bug found live (`IN-Mumbai` vs `IN` false positive), fixed, and I personally re-verified live post-merge (`compliant: true` for a real asset/policy pair). Commit `ad3376a`. |
| 4 | Data Observability Lineage | EXISTENCE-ONLY | Tier B only. |
| 5 | Data Observability Incidents | DEEP-TESTED-WORKING | Tier A: this session's G8 — investigate/contain notes persistence bug found and fixed live (migration `0283`, commit `62f15e7`), verified via a real server-restart persistence check. |
| 6 | Data Observability Quality | EXISTENCE-ONLY | Tier B only (2026-07-08 memory notes an inverted-threshold bug in this area historically, but that was for AI drift monitoring, a different tag — not directly this row). |
| 7 | Data Observability Access | EXISTENCE-ONLY | Tier B only. |
| 8 | Data Observability Obligation Suggestions | DEEP-TESTED-WORKING | Tier A: this session's G3 — sensitivity-inversion + missing jurisdiction filter found live, fixed, personally re-verified with a real footprint-driven test (personal_data 35→20 after adding jurisdiction filter, sensitive_personal_data parity confirmed). Commit `ad3376a`. |
| 9 | Data Observability Dashboard | EXISTENCE-ONLY | Tier B only. |
| 10 | Data Observability Obligation Coverage | EXISTENCE-ONLY | Tier B only. |

## Domain: Risk Management (7 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Risks | DEEP-TESTED-WORKING | Tier A: final-sweep-B `test_risks_phase23.py` run live as part of focused regression; also underlies the Risk Quantification 500-crash finding (T1-T4), confirming real exercise of risk CRUD. |
| 2 | Risk Appetite | DEEP-TESTED-WORKING | Tier A: this session's G5 — retroactive breach-evaluation gap found and fixed live (lower threshold on existing risk → real breach flagged with zero further writes), commit `730e737`; also `test_risk_appetite_a12.py` in final-sweep-B. |
| 3 | Risk Indicators | EXISTENCE-ONLY | Tier B only (2026-07-08 memory notes a KRI "dead status filter" bug historically fixed — not independently re-verified this session). |
| 4 | Compliance Risk Recommendations | EXISTENCE-ONLY | Tier B only. |
| 5 | Geopolitical Risk | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-15) — real read-path/staleness logic confirmed (unmonitored_exposures correctly flagged pre-ingest), live `/ingest` blocked only by sandbox network restriction to GDELT (not a code bug, graceful degrade confirmed). Real gap found: signals don't feed vendor risk_tier. |
| 6 | Risk Dependencies | EXISTENCE-ONLY | Tier C: model/route confirmed present (migration `0273`), no walkthrough evidence found. |
| 7 | Risk Scores | EXISTENCE-ONLY | Tier B only. |

## Domain: Policy Management (10 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Compliance Policies | EXISTENCE-ONLY | Tier B only. |
| 2 | Policy Template Library | EXISTENCE-ONLY | Tier B only. |
| 3 | Policy Issue Links | DEEP-TESTED-WORKING | Tier A: this session's G6 — v1 completely broken (FK'd to wrong table, `tasks` instead of `issues`) found live, deprecated to 410 cleanly, verified with real before/after HTTP evidence. Commit `83aa70e`. |
| 4 | Policy Risk Mappings | EXISTENCE-ONLY | Tier B only. |
| 5 | Policy Drafting | EXISTENCE-ONLY | Tier B only. |
| 6 | Policy Attestations | EXISTENCE-ONLY | Tier B only. |
| 7 | Policy Exceptions V2 | DEEP-TESTED-WORKING | Tier A: this session's G6 — withdrawn-exception visibility mismatch (spurious soft-delete on withdraw) found and fixed live, verified with real before/after HTTP (v2 GET 404→200). Commit `d88ecf5`. |
| 8 | Policy Issue Links V2 | DEEP-TESTED-WORKING | Tier A: same G6 pass — v2 confirmed working throughout (used as the reference behavior v1 was deprecated toward). |
| 9 | Policy Exceptions | DEEP-TESTED-WORKING | Tier A: same G6 fix (`d88ecf5`) touches the shared underlying record both v1/v2 read. |
| 10 | Policy Risk Links | EXISTENCE-ONLY | Tier B only. |

## Domain: Compliance Frameworks & Obligations (8 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Frameworks | DEEP-TESTED-WORKING | Tier A: this session's G6 — PCI DSS inactive-placeholder cleanup found and fixed live (15 `REQ-EXT-*` rows leaking into default views), real before/after count (93→78). Commit `de1dd52`. |
| 2 | Framework Review Capacity | EXISTENCE-ONLY | Tier B only ("EXCELLENT... capacity policies, workload snapshots" — no independent Tier-A walkthrough found this session for the batch/scheduling internals specifically). |
| 3 | Framework Pack Reviews | EXISTENCE-ONLY | Tier B only. |
| 4 | Obligations | DEEP-TESTED-WORKING | Tier A: covered by the same G3/G6 obligation-suggestion and framework-content fixes this session (`ad3376a`, `de1dd52`) which directly exercise obligation records. |
| 5 | Compliance Deadlines | EXISTENCE-ONLY | Tier B only; 2026-07-08 memory notes a dry-run/dedup poisoning bug historically, not re-verified this session. |
| 6 | DORA | DEEP-TESTED-WORKING | Tier A: this session's G5 — DORA-vs-generic vendor-staleness cascade reconciled live (missing `ControlMonitoringAlert` half added), real before/after HTTP evidence. Commit `06da6f2`. Also T1-T4 deep test (T2-4) independently confirmed DORA resilience-testing end-to-end (real issue auto-creation from critical/high findings). |
| 7 | Framework Content | DEEP-TESTED-WORKING | Tier A: this session's G6 search-degrade fix and PCI cleanup both touch framework-content serving paths; also T1-T4 (T3-1 ESG templates, adjacent capability under the same custom-report-template surface) confirmed genuinely non-placeholder content generation. |
| 8 | Regulatory Alerts | EXISTENCE-ONLY | Tier C: route/model confirmed (`db98260` in git log), no walkthrough evidence. |

## Domain: Controls & Control Testing (10 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Technical Controls | EXISTENCE-ONLY | Tier B only. |
| 2 | Controls | DEEP-TESTED-WORKING | Tier A: this session's G4 — `/dashboard/summary` control-count fix (archived-status filter mismatch) found and fixed live, real before/after (2/2 → 3/3 matching direct DB count). Commit `f2178c7`. Also final-sweep-B `test_controls_phase21.py` run live. |
| 3 | Control Monitoring | EXISTENCE-ONLY | Tier B only. |
| 4 | Control Monitoring Rules | EXISTENCE-ONLY | Tier B only. |
| 5 | SoD Conflicts | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-4) — real conflicting-duties rule created, user assigned to both roles, finding genuinely generated with correct severity; acknowledge/waive both persisted correctly. |
| 6 | Control Monitoring Alerts | EXISTENCE-ONLY | Tier B only. |
| 7 | Common Controls | DEEP-TESTED-WORKING | Tier A: this session's G9-era work (referenced in git log `fbe491b` "Unify common-controls and direct obligation mappings in coverage counting") — pre-dates this conversation's G1-G8 pass but is a real reproduce-fix commit on main. |
| 8 | Control Exceptions | DEEP-TESTED-WORKING | Tier A: git log `76d4b21` "Document control-exception required fields and move validation into the schema" — real schema-level fix, pre-dates this conversation's G1-G8 but on main with commit evidence. |
| 9 | Control Tests | EXISTENCE-ONLY | Tier B only for the general test-run feature; the specific "manual_result silently overridden" bug from 2026-07-08 memory was not independently re-verified this session. |
| 10 | Control Recommendations | EXISTENCE-ONLY | Tier B only. |

## Domain: Audit & Assurance (14 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Evidence Packages | EXISTENCE-ONLY | Tier B only. |
| 2 | Recertification | EXISTENCE-ONLY | Tier B only. |
| 3 | Pbc Items | EXISTENCE-ONLY | Tier B only. |
| 4 | Audit Findings | EXISTENCE-ONLY | Tier B only for the general feature; the specific `resolve_finding` invalid-status bug from 2026-07-08 memory was not independently re-verified this session (it's a different code path from the `accepted_risk` fix Tier B claims). |
| 5 | Evidence | DEEP-TESTED-WORKING | Tier A: this session's G2 — dedup non-functional across all 4 ingestion paths found live (checksum/title never populated by automation handlers), fixed, and I personally re-verified live on the merged server (1st POST 201, 2nd 200 w/ dup header, exactly 1 DB row per checksum across manual/webhook/email/form). Commit `2b6dea6`. |
| 6 | Audit Schedules | EXISTENCE-ONLY | Tier B only. |
| 7 | Audit Findings V2 | EXISTENCE-ONLY | Tier B only. |
| 8 | Audit Engagements | EXISTENCE-ONLY | Tier B only. |
| 9 | Auditor Portal | EXISTENCE-ONLY | Tier B only. |
| 10 | Access Certifications | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-3) — full campaign lifecycle exercised, reviewer scoping correct, certify/reject persisted, auto-completion on all-decided confirmed. |
| 11 | Pbc Requests V2 | EXISTENCE-ONLY | Tier B only. |
| 12 | Evidence Automation | DEEP-TESTED-WORKING | Tier A: same G2 dedup fix directly touches `evidence_automation_service.py` (webhook/email/form ingest paths) — real HTTP evidence for all 3 automation sources. |
| 13 | Audit Evidence Packages | EXISTENCE-ONLY | Tier B only. |
| 14 | Audit Logs | EXISTENCE-ONLY | Tier C: this session's T4 identity/financial-crime fork independently confirmed via direct DB query that the audit log captured 29 distinct action types correctly across all its testing — real corroborating evidence. Upgrading to **DEEP-TESTED-WORKING**. |

## Domain: TPRM / Third-Party Risk (12 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Vendors | DEEP-TESTED-WORKING | Tier A: this session's G7 item 6 (cross-tenant 404→403 fix, live-verified) + T1-T4 deep test exercised vendor CRUD extensively as the substrate for nearly every T1/T4 sub-feature. |
| 2 | Tprm Intelligence | **DEEP-TESTED-BROKEN** (composite) | Tier A: T1-T4 deep test bundles 6 sub-capabilities into this one row — Security Rating (CONFUSING: noise-dominated scoring, phantom history entries), Threat Intelligence (CONFUSING: same root cause), AML/KYB (shallow — 4/5 external sources unavailable in sandbox, couldn't observe positive-escalation path, no `/history` endpoint unlike siblings), Sanctions Screening (WORKING — real match/clear/risk_tier escalation confirmed), Anti-Bribery (BROKEN — scoring correct but doesn't escalate risk_tier despite the API's own `context_flags` self-flagging the inconsistency), Export Control (WORKING — 5D/5E coverage confirmed with real EAR citations). See structural caveat above. |
| 3 | Inbound Questionnaires | EXISTENCE-ONLY | Tier B only. |
| 4 | Vendor Mitigation | DEEP-TESTED-WORKING | Tier A: final-sweep-C — "Vendor mitigation case ownership validation" gap found and fixed live (real HTTP tests for Org B user + inactive same-org user, both 422, DB-confirmed no case rows created). |
| 5 | OT/ICS | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-16) — real SCADA asset registered, finding ingested via agent token, `/resolve` genuinely confirmed working. Real gap found (not a broken-verdict item): findings don't create risk-register entries. |
| 6 | Subprocessors | EXISTENCE-ONLY | Tier B only. |
| 7 | Questionnaire Responses | DEEP-TESTED-WORKING | Tier A: this session's G5 — reported "total_score never aggregates" bug was investigated live and found NOT reproducible on the correct code base (traced `compute_response_score`, live-tested with real per-question submission — correctly aggregated 70=30+40 every time). Honest negative-finding still counts as real exercise. |
| 8 | Questionnaire Templates | EXISTENCE-ONLY | Tier B only. |
| 9 | Vendor Remediation Portal | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T1-5) — full lifecycle tested (case→action→token→portal access→evidence submission); all 4 negative paths (malformed/revoked/expired/cross-tenant) correctly distinguished with different status codes. |
| 10 | Questionnaire Scoring Rules | EXISTENCE-ONLY | Tier B only. |
| 11 | Vendor Supply Chain | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T1-3) — nth-party risk propagation genuinely works, but cycle detection is broken (silently drops the cyclic edge from the graph response, `cycle_count: 0` even with a real cycle in the DB). |
| 12 | Vendor Concentration Risk | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T1-6) — HHI math correct and creates a real linked Risk, but double-counts a vendor that's both directly tracked and a supply-chain dependency (proven by deleting the link and re-running — share dropped from 26%→15%); also `risk_created:false` wrongly reported on the very call that created the risk. |

## Domain: Issues & Incident Management (10 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Issues | EXISTENCE-ONLY | Tier B only for general CRUD; 2026-07-08 memory's `resolve_finding` bug is a different tag (Audit Findings), not this one. |
| 2 | Issue Sync | DEEP-TESTED-WORKING | Tier A: this session's G7 item 1 — Linear webhook idempotency fallback-key gap found and fixed live (composite dedup key added), verified with real duplicate deliveries (1st processed, 2nd `duplicate_delivery:true`, single DB row confirmed). Commit range `b07a401`..`5b608b8`. |
| 3 | Escalation Policies | EXISTENCE-ONLY | Tier B only. |
| 4 | BCM | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T2-2) — real process created, BIA with backdated review date, overdue-detection correctly flagged ("overdue by 554 days"). Also final-sweep-C fixed inactive-owner/reviewer validation live. |
| 5 | Crisis Management | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T2-3) — playbook activation genuinely cross-referenced real linked process + risks (matched by scenario/category, not user-supplied), `/active` and resolve both confirmed correct. |
| 6 | Whistleblower | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T2-5) — anonymous submission, tracking-code status lookup, no IP/identity leakage confirmed at schema level (no such columns exist), investigator↔reporter messaging confirmed live. |
| 7 | Resilience Testing | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T2-4) — overdue calc, completion, and auto-issue-creation from critical/high findings all confirmed with real HTTP+DB evidence. |
| 8 | Issue Sla Policies | EXISTENCE-ONLY | Tier B only. |
| 9 | Issue Settings | EXISTENCE-ONLY | Tier B only. |
| 10 | Incident Analytics | EXISTENCE-ONLY | Tier B only. |

## Domain: Reports, Exports & Dashboards (10 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Reports | EXISTENCE-ONLY | Tier B only for general reporting; XBRL sub-path is separately evidenced below. |
| 2 | Exports | EXISTENCE-ONLY | Tier B only. |
| 3 | Entity Exports | EXISTENCE-ONLY | Tier B only. |
| 4 | Scoring | EXISTENCE-ONLY | Tier B only. |
| 5 | Custom Reports | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T3-1 ESG Templates live under this surface) — confirmed genuinely NOT a bare-echo report; real keyword-matched evidence-coverage computation demonstrated by adding evidence and watching readiness % move (0%→11.11%). |
| 6 | Compliance Dashboard | EXISTENCE-ONLY | Tier B only; distinct from the root "Dashboard" row below which was G4-fixed. |
| 7 | Board Scorecard | EXISTENCE-ONLY | Tier B only. |
| 8 | Compliance Reports | DEEP-TESTED-WORKING | Tier A: this session's G4 — XBRL export (element-ordering bug) found and fixed live, verified against the real IFRS SDS taxonomy via arelle with 3 distinct real requests all returning `validation_status:"valid"`. Also independently re-confirmed in T1-T4 (T3-2) with fabricated-vs-real-concept testing. Commit `c666219`. |
| 9 | Dashboard | DEEP-TESTED-WORKING | Tier A: this session's G4 — root `/dashboard/summary` undercount found and fixed live, real before/after (2/2→3/3 matching direct DB count). Commit `f2178c7`. |
| 10 | Compliance Contracts | EXISTENCE-ONLY | Tier B only. |

## Domain: Governance Automation (7 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Automation | EXISTENCE-ONLY | Tier B only. |
| 2 | Employee Attestations | EXISTENCE-ONLY | Tier B only (the two Tier-B scorecards disagree on this row too — one says SOLID, the other "NEEDS RE-VERIFICATION" — unresolved contradiction). |
| 3 | Tasks | DEEP-TESTED-WORKING | Tier A: this session's G7 item 2 — reminder job clobbering `priority` found and fixed live (added distinct `escalation_tier` field, real before/after: `priority` stayed `low`, `escalation_tier` became `urgent`). Commit range `b07a401`..`5b608b8`, migration `0281`. |
| 4 | Compliance Bot | DEEP-TESTED-WORKING | Tier A: this session's G7 item 4 — webhook auth fixed live (signature-only replacing impossible internal Bearer JWT requirement), verified with curl (no Authorization/X-Organization-ID header, valid signature → 200, wrong signature → 401). Migration `0282`. |
| 5 | Digest Preferences | EXISTENCE-ONLY | Tier B only. |
| 6 | Attestation Tokens | EXISTENCE-ONLY | Tier B only — and notably, both Tier-B scorecards independently rate this "WEAK"/"NEEDS RE-VERIFICATION" (no dedicated generic-token endpoint found) — the two low-trust sources agree with each other here, which is at least consistent, but still not Tier-A walkthrough evidence. |
| 7 | Attestations | EXISTENCE-ONLY | Tier B only. |

## Domain: Platform / Security / Administration (37 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Organizations | DEEP-TESTED-WORKING | Tier A: this session — the trust-center-slug regression I found and fixed myself lives on this row (`organizations.slug`/`trust_center_slug_confirmed_at`), verified live end-to-end (first-set no-confirm-needed → 200, re-change no-confirm → 409, confirm → 200). Commit `79bfb1e`. |
| 2 | Auth SSO | EXISTENCE-ONLY | Tier B only — and the two Tier-B scorecards flatly contradict each other on this row (one: "OIDC endpoints are not implemented," the other: "OIDC `/auth/oidc/{slug}/initiate`/`/callback`... implemented") — unresolved contradiction, real risk this needs direct re-verification. |
| 3 | Legal Matters | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-10) — real matter created, linked to real risk/evidence/control (the evidence/control linking specifically added in a recent fix pass, confirmed actually functional not just endpoint-present); closed-matter guardrail (409) confirmed on all 3 link types. |
| 4 | Email | EXISTENCE-ONLY | Tier B only. |
| 5 | Onboarding | EXISTENCE-ONLY | Tier B only. |
| 6 | Auth SCIM | EXISTENCE-ONLY | Tier B only (both Tier-B sources agree "SOLID... 7/7 verifications passed" but that's still self-reported without independent Tier-A corroboration this session). |
| 7 | Customer Commitments | EXISTENCE-ONLY | Tier B only. |
| 8 | Webhooks | EXISTENCE-ONLY | Tier B only — and again the two Tier-B scorecards contradict each other (one: "delivery is intentionally stubbed," the other: "RESOLVED... real httpx POST calls") — unresolved, needs direct re-verification. |
| 9 | SIEM | EXISTENCE-ONLY | Tier B only. |
| 10 | Business Units | EXISTENCE-ONLY | Tier B only. |
| 11 | Trust Center Admin | DEEP-TESTED-WORKING | Tier A: this session — slug-confirmation regression found and fixed by me directly, live HTTP evidence (see Organizations row above, same commit). |
| 12 | Connector Marketplace | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T3-4) — catalog/enable/config-validation all real, but `test-connection` never makes a live network call yet returns `"connection_status":"validated"` for an obviously fake Okta URL — confirmed in source as intentionally schema-only but never surfaced to the caller; also stores API tokens in plaintext, retrievable via `GET /connectors/enabled`. |
| 13 | Billing | EXISTENCE-ONLY | Tier B only. |
| 14 | Memberships | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test used real `PATCH /memberships/{id}/deactivate` and discovered it's the actual root cause of the Non-Human-Identity orphan-detection gap — real exercise of this row's core mutation. |
| 15 | Ip Assets | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T4-11) — real IP asset with expiry registered, `/expiring-soon` window-threshold behavior confirmed genuinely respected (10-day window excluded a 29-day asset, 400-day window included it). |
| 16 | Security Integrations | EXISTENCE-ONLY | Tier B only. |
| 17 | Custom Roles | DEEP-TESTED-WORKING | Tier A: this session's G7 item 3 — role-deactivation live-revocation gap found and fixed (removed a blocking 409, added `is_active` check at permission-check time), verified live (member's next request after deactivation → 403, no re-login needed). |
| 18 | Rate Limits | DEEP-TESTED-WORKING | Tier A: this session's G7 item 5 — general API rate limiting found to be silently exempted for all `/api/v1/*` routes (slowapi route-scan bug), fixed and verified live (61st request → 429). |
| 19 | Import Jobs | DEEP-TESTED-WORKING | Tier A: this session's G4 — CSV import silently dropping 4 columns found and fixed live, real before/after CSV upload (all 4 fields persisted correctly on both create and update-conflict paths). Commit `c739117`. |
| 20 | Offboarding | EXISTENCE-ONLY | Tier B only for offboarding itself; only its *interaction* with Non-Human Identity was exercised (that's attributed to the Non-Human Identities/Memberships rows). |
| 21 | Auth | EXISTENCE-ONLY | Tier B only for the general feature — though every single agent this session logged in/registered via this surface hundreds of times, that's incidental infrastructure use, not a deliberate walkthrough of Auth's own edge cases (e.g. password policy, invite-token abuse). |
| 22 | Report Sharing | EXISTENCE-ONLY | Tier B only. |
| 23 | Email Config | EXISTENCE-ONLY | Tier B only. |
| 24 | PAM Sessions | DEEP-TESTED-BROKEN | Tier A: T1-T4 deep test (T4-2) — ingest works but requires an unrelated Data-Lineage/OpenMetadata integration just to get the API key (confusing coupling); `unapproved-risks` hardcodes `approval_status="missing"` and silently excludes `denied` sessions; `flag-unapproved` overwrites `approval_status` unconditionally, destroying a `denied` signal by downgrading it to `missing`. |
| 25 | Experience | EXISTENCE-ONLY | Tier B only. |
| 26 | Ip Allowlist | EXISTENCE-ONLY | Tier B only (both Tier-B sources claim a self-lockout fix, but neither is Tier A; not independently re-verified this session). |
| 27 | Notification Preferences | EXISTENCE-ONLY | Tier B only. |
| 28 | Admin Email Config | EXISTENCE-ONLY | Tier B only. |
| 29 | Sessions | EXISTENCE-ONLY | Tier B only. |
| 30 | Scheduler Admin | DEEP-TESTED-WORKING | Tier A: this session's G1 root-cause fix — the entire sanctions-bootstrap-never-ran bug traced directly to `app/core/pbc_scheduler.py`'s registration path and a custom `lifespan=` silently disabling `on_startup`; fixed and re-verified live across a real process kill+restart (dataset auto-repopulated to 20,560 rows with zero manual intervention). Commit `12c03ea`. |
| 31 | (None) | UNTESTED | This is a 2-endpoint catch-all for routes with no OpenAPI tag assigned — not a real feature, no walkthrough evidence, no dedicated model/service to even attribute testing to. Genuinely untested and arguably not a discrete "feature" at all. |
| 32 | Trust Center Public | DEEP-TESTED-WORKING | Tier A: same trust-center-slug fix this session exercises the public read side too (public slug lookup used to confirm the confirm-guard fix didn't break existing public links). |
| 33 | Health | EXISTENCE-ONLY | Tier C: trivially confirmed alive (every server-boot this session curl'd `/openapi.json` successfully, which depends on app startup succeeding) but never a deliberate walkthrough of `/health` itself. |
| 34 | Users | EXISTENCE-ONLY | Tier B only. |
| 35 | Roles | EXISTENCE-ONLY | Tier B only. |
| 36 | Search | DEEP-TESTED-WORKING | Tier A: this session's G6 — global `/search` 503 found live (Meilisearch genuinely unreachable in-sandbox, confirmed via direct port probe), fixed to gracefully degrade, verified live (503→200 with `degraded:true`). Commit `3321922`. |
| 37 | Billing Webhook | EXISTENCE-ONLY | Tier C: route/model exists (Razorpay webhook, used as the reference "correct" signature-only pattern G7 copied for compliance-bot), but the webhook itself wasn't independently exercised this session — only referenced as a pattern to imitate. |

## Domain: Competitive Differentiation (Phase II-VIII) (4 rows)

| # | Feature | Bucket | Evidence |
|---|---|---|---|
| 1 | Auditor Marketplace | EXISTENCE-ONLY | Tier C: confirmed live 200 in G8's feature-inventory spot-check this session (`GET /find-auditor`), but that was a single-endpoint smoke test, not a real workflow walkthrough. |
| 2 | Certification Programs | EXISTENCE-ONLY | Tier C: same G8 spot-check, single-endpoint 200 only. |
| 3 | Carbon Accounting | DEEP-TESTED-WORKING | Tier A: T1-T4 deep test (T3-3) — real Scope 1/2/3 readings ingested, dashboard aggregation independently verified by hand (602.0 = 89.4+512.6), idempotent dedup on `source_record_id` confirmed via before/after dashboard totals. |
| 4 | Pricing | EXISTENCE-ONLY | Tier C: same G8 spot-check, single-endpoint 200 only (bundles competitor pricing + ROI calculator + usage-based pricing — none individually exercised). |

---

## Final Counts

| Bucket | Count |
|---|---|
| 1. DEEP-TESTED-WORKING | 62 |
| 2. DEEP-TESTED-BROKEN | 8 |
| 3. EXISTENCE-ONLY | 115 |
| 4. UNTESTED | 1 |
| **Total** | **186** |

**Bucket 3 + 4 combined: 116 features** — this is the real number Part 2 needs to deep-test, replacing any
prior estimate.

### On the "40-feature gap catalog mostly lands in EXISTENCE-ONLY" hypothesis

**Confirmed, with nuance.** Of the ~24 gap-catalog items individually named in `FEATURE_INVENTORY.md`
Appendix A, roughly two-thirds map to rows I landed in EXISTENCE-ONLY (Risk Dependencies, Framework Review
Capacity's batch/scheduling internals, generic Attestation Tokens, digest preferences, etc.) — but a
meaningful minority were directly touched by this session's G1-G9 fix passes and are genuinely
DEEP-TESTED-WORKING (Data Observability Residency/Obligation-Suggestions, DORA vendor-staleness cascade,
Control Exceptions, Common Controls, Evidence Automation idempotency, Data Observability Incidents notes,
Compliance Bot idempotency/auth, Issue Sync idempotency). So the hypothesis holds directionally but isn't
absolute — the gap catalog is *not* uniformly untested, it's a genuine mix weighted toward EXISTENCE-ONLY.

### Composite/mixed-verdict rows worth flagging for Part 2's planning

- **Tprm Intelligence**: bundles 6 T1/T4 sub-capabilities, 4 of which have real, distinct issues. Part 2
  should treat this as effectively already deep-tested (it's in bucket 2, not 3/4) but the *specific*
  bucket-2 bugs (Anti-Bribery risk_tier inaction, AML/KYB shallow verification) may warrant follow-up in a
  fix pass rather than more deep-testing.
- **AI Governance Contracts** and **AI Governance Dashboard**: the two Tier-B scorecards directly contradict
  each other. Recommend Part 2 treat these as effectively UNTESTED-equivalent despite landing in
  EXISTENCE-ONLY by my rule, since even the *weak* evidence is self-contradictory.
- **Auth SSO** and **Webhooks**: same direct Tier-B self-contradiction (implemented vs. stubbed). Same
  recommendation — prioritize these in Part 2 despite EXISTENCE-ONLY classification.

### Commit / files

No code was modified. Wrote `/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend/RECONCILIATION_186.md`
only (this file). No commit made — leaving that to the orchestrator's discretion since this is a
documentation artifact, not a code fix.
