from typing import Any, Literal

from pydantic import BaseModel, Field


# ---- ingest (satellite) ----
class ObligationDerivationRequest(BaseModel):
    ai_system_id: str
    derived_obligations: list[str] = []
    derived_controls: list[str] = []
    graph_path: Any = None
    methodology_version: str
    trigger_reason: Literal["event", "scheduled"]
    derivation_hash: str


class BatchObligationDerivationRequest(BaseModel):
    derivations: list[ObligationDerivationRequest] = Field(min_length=1)


class NodeStructureItem(BaseModel):
    node_type: str
    node_key: str
    properties: dict = {}


class EdgeStructureItem(BaseModel):
    source_node_type: str
    source_node_key: str
    target_node_type: str
    target_node_key: str
    edge_type: str
    is_active: bool = True
    weight: float = 1.0
    properties: dict = {}


class GraphStructureRequest(BaseModel):
    nodes: list[NodeStructureItem] = []
    edges: list[EdgeStructureItem] = []
    structure_hash: str


# ---- human knowledge-graph ----
class ManualEdgeCreateRequest(BaseModel):
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float = 1.0
    properties: dict = {}
