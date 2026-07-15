from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class EntityGraphNodeOut(BaseModel):
    entity_type: str = Field(description="Node type, e.g. 'risk', 'control', 'vendor'.")
    entity_id: uuid.UUID
    depth: int = Field(description="Shortest hop distance from the anchor (anchor excluded).")
    via_edge_types: list[str] = Field(
        default_factory=list,
        description="Logical edge types by which this node was reached.",
    )
    reached_via_cycle: bool = Field(
        description="True if a cycle was detected on a path to this node."
    )


class EntityGraphTraverseResponse(BaseModel):
    anchor_type: str
    anchor_id: uuid.UUID
    organization_id: uuid.UUID
    max_depth: int
    max_nodes: int
    depth_reached: int
    truncated: bool = Field(
        description="True if the node cap was hit; nodes is a bounded, explicitly-flagged "
        "subset rather than a silent partial result."
    )
    cycle_detected: bool
    edge_specs_used: int
    node_count: int
    nodes: list[EntityGraphNodeOut]

    @classmethod
    def from_result(cls, result) -> "EntityGraphTraverseResponse":
        return cls(
            anchor_type=result.anchor_type,
            anchor_id=result.anchor_id,
            organization_id=result.organization_id,
            max_depth=result.max_depth,
            max_nodes=result.max_nodes,
            depth_reached=result.depth_reached,
            truncated=result.truncated,
            cycle_detected=result.cycle_detected,
            edge_specs_used=result.edge_specs_used,
            node_count=len(result.nodes),
            nodes=[
                EntityGraphNodeOut(
                    entity_type=n.entity_type,
                    entity_id=n.entity_id,
                    depth=n.depth,
                    via_edge_types=n.via_edge_types,
                    reached_via_cycle=n.reached_via_cycle,
                )
                for n in result.nodes
            ],
        )
