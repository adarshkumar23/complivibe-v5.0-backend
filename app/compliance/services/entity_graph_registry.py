"""Entity-graph edge registry (Step 2 of the unified cross-entity graph).

This is a *read-only* registry: a declarative map from each physical, FK-enforced
edge table already in the schema to a single logical edge type the unified graph
exposes. It follows the pattern already established by ``risk_graph_service.py``
(which hard-codes the same set of link tables) and ``data_lineage_edges`` -- it
does NOT introduce a new generic edge table or touch any existing table. See
``docs/entity_graph_design.md`` for the full argument (Option B: keep the ~30
tables as source of truth, add a traversal layer on top).

Design decisions baked in here (resolved from the doc's open questions):

* **Node key** = ``(entity_type, entity_id)`` -- matching ``entity_risk_scores``.
* **Duplicate seams** are resolved *in this registry only*, never by renaming a
  physical table. For each logically-duplicated seam we register ONE ``EdgeSpec``
  as ``canonical`` (the table live cross-domain code actually reads today) and
  map the other(s) as ``deprecated_but_present`` so traversal does not silently
  drop real edges that still exist in those tables:
    - **policy <-> risk**: canonical ``policy_risk_links`` (the user-facing
      link router + ``PolicyRiskLinkService.list_*`` read path); deprecated
      ``policy_risk_mappings`` (a mitigation-strength derivative the same
      service keeps in sync).
    - **control <-> obligation**: canonical ``control_obligation_mappings``
      (the table ``risk_graph_service.build`` -- the live cross-entity graph --
      actually joins on); deprecated ``common_control_mappings`` (a 3-way
      control/framework/obligation inheritance mapping whose control<->obligation
      projection we still want reachable). Suggestion/recommendation tables
      (``obligation_control_recommendations`` et al.) are *proposals*, not
      confirmed edges, and are intentionally excluded.
    - **issue <-> policy**: canonical ``issue_policy_links``; deprecated
      ``policy_issue_links``.
* **Incident node = ``issues``** (not ``data_incidents``): ``issues`` owns the
  cross-domain edge tables (``issue_control_links``, ``issue_policy_links``,
  ``policy_issue_links``), and the Phase 1 DORA listener materialises an
  operational incident as an ``Issue``. ``data_incidents`` has zero edges into
  controls/policies/risks, so it is not a graph node in v1.

Every ``EdgeSpec`` is validated against the live SQLAlchemy metadata at import
time (:func:`validate_registry`), so a typo in a table or column name fails
loudly instead of silently dropping edges from the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SeamStatus(str, Enum):
    """Provenance of an edge spec within a (possibly duplicated) logical seam."""

    CANONICAL = "canonical"
    # A duplicate physical table for a seam whose canonical table is elsewhere.
    # Still traversed (so real edges are not dropped) unless the caller opts out.
    DEPRECATED_BUT_PRESENT = "deprecated_but_present"
    # A seam with only one physical table -- nothing to disambiguate.
    SOLE = "sole"


# Whitelisted "row is live" predicates. Kept as a closed enum (never free SQL)
# so the generated CTE cannot be injected through and every predicate column is
# validated to exist on its table.
class ActiveFilter(str, Enum):
    NONE = "none"
    STATUS_ACTIVE = "status_active"          # status = 'active'
    LINK_STATUS_ACTIVE = "link_status_active"  # link_status = 'active'
    NOT_DELETED = "not_deleted"              # deleted_at IS NULL
    IS_ACTIVE_TRUE = "is_active_true"        # is_active = true


# Which physical column each active-filter predicate reads (for validation).
_ACTIVE_FILTER_COLUMN: dict[ActiveFilter, str | None] = {
    ActiveFilter.NONE: None,
    ActiveFilter.STATUS_ACTIVE: "status",
    ActiveFilter.LINK_STATUS_ACTIVE: "link_status",
    ActiveFilter.NOT_DELETED: "deleted_at",
    ActiveFilter.IS_ACTIVE_TRUE: "is_active",
}

# The SQL fragment each active filter renders to (identifiers are validated
# registry column names, never user input).
_ACTIVE_FILTER_SQL: dict[ActiveFilter, str | None] = {
    ActiveFilter.NONE: None,
    ActiveFilter.STATUS_ACTIVE: "{t}.status = 'active'",
    ActiveFilter.LINK_STATUS_ACTIVE: "{t}.link_status = 'active'",
    ActiveFilter.NOT_DELETED: "{t}.deleted_at IS NULL",
    ActiveFilter.IS_ACTIVE_TRUE: "{t}.is_active = true",
}


@dataclass(frozen=True)
class EdgeSpec:
    """One logical edge, read from one physical FK-enforced table.

    ``directed`` = True means the edge is only walked source -> target (cascade,
    supply-chain parent->sub, lineage upstream->downstream). ``directed`` = False
    (an association) is walked both ways, so blast-radius reachability works from
    either endpoint.
    """

    edge_type: str
    table: str
    source_type: str
    source_fk: str
    target_type: str
    target_fk: str
    directed: bool
    active_filter: ActiveFilter = ActiveFilter.NONE
    seam_status: SeamStatus = SeamStatus.SOLE
    org_column: str = "organization_id"
    notes: str = ""

    def active_filter_sql(self, table_alias: str) -> str | None:
        template = _ACTIVE_FILTER_SQL[self.active_filter]
        return None if template is None else template.format(t=table_alias)


# ---------------------------------------------------------------------------
# The registry. One row per physical edge table. Grouped by seam for clarity.
# ---------------------------------------------------------------------------
EDGE_REGISTRY: list[EdgeSpec] = [
    # -- Risk-centric associations ------------------------------------------
    EdgeSpec("mitigated_by", "risk_control_links", "risk", "risk_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    EdgeSpec("risk_evidenced_by", "risk_evidence_links", "risk", "risk_id",
             "evidence", "evidence_item_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    EdgeSpec("asset_bears_risk", "data_asset_risk_links", "data_asset", "data_asset_id",
             "risk", "risk_id", directed=False),
    EdgeSpec("ai_system_bears_risk", "ai_system_risk_links", "ai_system", "ai_system_id",
             "risk", "risk_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    # -- Control-centric associations ---------------------------------------
    EdgeSpec("policy_governs_control", "compliance_policy_control_links", "policy", "policy_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE,
             notes="PROTECTED SEAM -- never rename compliance_policy_control_links."),
    EdgeSpec("control_evidenced_by", "evidence_control_links", "control", "control_id",
             "evidence", "evidence_item_id", directed=False,
             active_filter=ActiveFilter.LINK_STATUS_ACTIVE),
    EdgeSpec("issue_affects_control", "issue_control_links", "issue", "issue_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.NOT_DELETED),
    EdgeSpec("matter_involves_control", "legal_matter_control_links", "legal_matter", "matter_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    EdgeSpec("ai_system_uses_control", "ai_system_control_links", "ai_system", "ai_system_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    EdgeSpec("vendor_provides_control", "vendor_control_links", "vendor", "vendor_id",
             "control", "control_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    # -- control <-> obligation seam (canonical + deprecated) ---------------
    EdgeSpec("control_satisfies_obligation", "control_obligation_mappings", "control", "control_id",
             "obligation", "obligation_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE,
             seam_status=SeamStatus.CANONICAL,
             notes="Canonical control<->obligation seam (used by risk_graph_service.build)."),
    EdgeSpec("control_satisfies_obligation", "common_control_mappings", "control", "control_id",
             "obligation", "obligation_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE,
             seam_status=SeamStatus.DEPRECATED_BUT_PRESENT,
             notes="Deprecated dup: 3-way control/framework/obligation inheritance map; "
                   "we project its control<->obligation edge so real edges are not dropped."),
    # -- Obligation / policy / evidence / issue -----------------------------
    EdgeSpec("asset_subject_to_obligation", "data_asset_obligation_links", "data_asset", "data_asset_id",
             "obligation", "obligation_id", directed=False),
    EdgeSpec("ropa_subject_to_obligation", "ropa_framework_links", "processing_activity", "processing_activity_id",
             "obligation", "obligation_id", directed=False),
    EdgeSpec("ai_system_evidenced_by", "ai_system_evidence_links", "ai_system", "ai_system_id",
             "evidence", "evidence_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    EdgeSpec("matter_evidenced_by", "legal_matter_evidence_links", "legal_matter", "matter_id",
             "evidence", "evidence_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE),
    # -- policy <-> risk seam (canonical + deprecated) ----------------------
    EdgeSpec("policy_addresses_risk", "policy_risk_links", "policy", "policy_id",
             "risk", "risk_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE,
             seam_status=SeamStatus.CANONICAL,
             notes="Canonical policy<->risk seam (user-facing link router + list reads)."),
    EdgeSpec("policy_addresses_risk", "policy_risk_mappings", "policy", "policy_id",
             "risk", "risk_id", directed=False,
             active_filter=ActiveFilter.NOT_DELETED,
             seam_status=SeamStatus.DEPRECATED_BUT_PRESENT,
             notes="Deprecated dup: mitigation-strength derivative kept in sync by "
                   "PolicyRiskLinkService; mapped so real edges are not dropped."),
    # -- issue <-> policy seam (canonical + deprecated) ---------------------
    EdgeSpec("issue_relates_to_policy", "issue_policy_links", "issue", "issue_id",
             "policy", "policy_id", directed=False,
             active_filter=ActiveFilter.STATUS_ACTIVE,
             seam_status=SeamStatus.CANONICAL),
    EdgeSpec("issue_relates_to_policy", "policy_issue_links", "policy", "policy_id",
             "issue", "issue_id", directed=False,
             active_filter=ActiveFilter.NOT_DELETED,
             seam_status=SeamStatus.DEPRECATED_BUT_PRESENT),
    # -- Directed cascade / hierarchy edges ---------------------------------
    EdgeSpec("risk_cascades_to", "risk_dependencies", "risk", "upstream_risk_id",
             "risk", "downstream_risk_id", directed=True,
             notes="Self-referential risk cascade (cascades_to/triggers/compounds)."),
    EdgeSpec("vendor_supplies", "vendor_supply_chain_links", "vendor", "parent_vendor_id",
             "vendor", "sub_vendor_id", directed=True,
             active_filter=ActiveFilter.IS_ACTIVE_TRUE),
    EdgeSpec("obligation_equivalent_to", "cross_framework_obligation_mappings", "obligation", "source_obligation_id",
             "obligation", "target_obligation_id", directed=False,
             notes="Cross-framework obligation equivalence (semantically undirected)."),
    EdgeSpec("lineage_flows_to", "data_lineage_edges", "data_lineage_node", "upstream_node_id",
             "data_lineage_node", "downstream_node_id", directed=True),
    EdgeSpec("geopolitical_cascaded_risk", "vendor_geopolitical_exposure", "vendor", "vendor_id",
             "risk", "cascaded_risk_id", directed=True,
             active_filter=ActiveFilter.NOT_DELETED,
             notes="Vendor geopolitical exposure that cascaded into a risk (Phase 1 listener). "
                   "cascaded_risk_id is nullable; NULL rows are filtered by the FK-not-null guard."),
    EdgeSpec("concentration_cascaded_risk", "vendor_concentration_risk_detections", "vendor", "top_vendor_id",
             "risk", "risk_id", directed=True,
             notes="Vendor concentration detection whose top vendor drives a register risk. "
                   "Both FKs nullable; NULL rows filtered by the FK-not-null guard."),
]


# Node types the graph currently spans (for documentation / callers).
NODE_TYPES: frozenset[str] = frozenset(
    {spec.source_type for spec in EDGE_REGISTRY}
    | {spec.target_type for spec in EDGE_REGISTRY}
)


class RegistryValidationError(RuntimeError):
    """Raised when an EdgeSpec references a table/column absent from metadata."""


def validate_registry(registry: list[EdgeSpec] | None = None) -> None:
    """Assert every EdgeSpec's table and referenced columns exist in the ORM.

    This is the guard that stops a typo from *silently* dropping a whole edge
    table out of the graph -- import fails instead. Imported lazily so this
    module has no hard import-time dependency on the full model graph beyond
    what the app already loads.
    """

    import app.models  # noqa: F401  -- register all mappers
    from app.db.base import Base

    specs = EDGE_REGISTRY if registry is None else registry
    tables = Base.metadata.tables
    errors: list[str] = []
    for spec in specs:
        tbl = tables.get(spec.table)
        if tbl is None:
            errors.append(f"{spec.edge_type}: table '{spec.table}' not in metadata")
            continue
        cols = set(tbl.columns.keys())
        for col_label, col in (
            ("source_fk", spec.source_fk),
            ("target_fk", spec.target_fk),
            ("org_column", spec.org_column),
        ):
            if col not in cols:
                errors.append(f"{spec.edge_type}: {col_label} '{col}' not on '{spec.table}'")
        active_col = _ACTIVE_FILTER_COLUMN[spec.active_filter]
        if active_col is not None and active_col not in cols:
            errors.append(
                f"{spec.edge_type}: active_filter column '{active_col}' not on '{spec.table}'"
            )
    if errors:
        raise RegistryValidationError(
            "Entity-graph edge registry is out of sync with the schema:\n  - "
            + "\n  - ".join(errors)
        )
