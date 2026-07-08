"""Genuine risk-to-risk dependency/cascade tracking.

Deliberately separate from RiskGraphService (which builds a risk<->control/
vendor/evidence/obligation/policy *coverage* graph off `/risks/{id}/graph`
-- that endpoint stays exactly as-is). This service is pure risk-to-risk:
which risks cascade into / trigger / compound other risks, so a compliance
or risk professional can see, when a risk's score changes, which other
risks might be affected.
"""

from __future__ import annotations

import uuid
from collections import deque

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.risk_dependency import RiskDependency


class RiskDependencyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------
    def _get_risk_or_404(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
        risk = self.db.execute(
            select(Risk).where(Risk.id == risk_id, Risk.organization_id == org_id)
        ).scalar_one_or_none()
        if risk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
        return risk

    def _all_edges(self, org_id: uuid.UUID) -> list[RiskDependency]:
        return list(
            self.db.execute(
                select(RiskDependency).where(RiskDependency.organization_id == org_id)
            ).scalars().all()
        )

    def _downstream_reachable(self, org_id: uuid.UUID, start_risk_id: uuid.UUID) -> set[uuid.UUID]:
        """BFS forward (upstream -> downstream) over existing edges, returning every risk
        id reachable from start_risk_id (exclusive of start itself unless revisited)."""
        edges = self._all_edges(org_id)
        adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}
        for edge in edges:
            adjacency.setdefault(edge.upstream_risk_id, []).append(edge.downstream_risk_id)

        visited: set[uuid.UUID] = set()
        queue: deque[uuid.UUID] = deque([start_risk_id])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def create_dependency(
        self,
        *,
        org_id: uuid.UUID,
        upstream_risk_id: uuid.UUID,
        downstream_risk_id: uuid.UUID,
        relationship_type: str,
        rationale: str | None,
        created_by_user_id: uuid.UUID | None,
    ) -> RiskDependency:
        if upstream_risk_id == downstream_risk_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A risk cannot depend on itself (upstream_risk_id == downstream_risk_id)",
            )

        # Both risks must exist and be org-scoped.
        self._get_risk_or_404(org_id, upstream_risk_id)
        self._get_risk_or_404(org_id, downstream_risk_id)

        existing = self.db.execute(
            select(RiskDependency).where(
                RiskDependency.organization_id == org_id,
                RiskDependency.upstream_risk_id == upstream_risk_id,
                RiskDependency.downstream_risk_id == downstream_risk_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A dependency edge already exists between these two risks",
            )

        # Cycle detection: if downstream_risk_id can already reach upstream_risk_id via
        # existing edges, adding upstream -> downstream would close a cycle. A risk
        # cascading back into itself through a chain isn't meaningful for this graph.
        if downstream_risk_id == upstream_risk_id or upstream_risk_id in self._downstream_reachable(
            org_id, downstream_risk_id
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "This dependency would create a cycle: downstream_risk_id already has a "
                    "path back to upstream_risk_id through existing dependencies"
                ),
            )

        dependency = RiskDependency(
            organization_id=org_id,
            upstream_risk_id=upstream_risk_id,
            downstream_risk_id=downstream_risk_id,
            relationship_type=relationship_type,
            rationale=rationale,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(dependency)
        self.db.flush()
        return dependency

    def delete_dependency(self, *, org_id: uuid.UUID, risk_id: uuid.UUID, dependency_id: uuid.UUID) -> RiskDependency:
        dependency = self.db.execute(
            select(RiskDependency).where(
                RiskDependency.id == dependency_id,
                RiskDependency.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if dependency is None or (
            dependency.upstream_risk_id != risk_id and dependency.downstream_risk_id != risk_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk dependency not found")

        self.db.delete(dependency)
        self.db.flush()
        return dependency

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_dependencies(self, *, org_id: uuid.UUID, risk_id: uuid.UUID) -> list[RiskDependency]:
        self._get_risk_or_404(org_id, risk_id)
        return list(
            self.db.execute(
                select(RiskDependency).where(
                    RiskDependency.organization_id == org_id,
                    (RiskDependency.upstream_risk_id == risk_id) | (RiskDependency.downstream_risk_id == risk_id),
                )
            ).scalars().all()
        )

    def directly_downstream_risk_ids(self, *, org_id: uuid.UUID, risk_id: uuid.UUID) -> list[uuid.UUID]:
        """Risks directly dependent on risk_id (risk_id is their upstream) -- used to
        flag which risks might be affected when risk_id's score changes."""
        rows = self.db.execute(
            select(RiskDependency.downstream_risk_id).where(
                RiskDependency.organization_id == org_id,
                RiskDependency.upstream_risk_id == risk_id,
            )
        ).scalars().all()
        return list(rows)

    def dependency_graph(self, *, org_id: uuid.UUID, risk_id: uuid.UUID) -> dict:
        """Connected component of pure risk-to-risk dependency edges reachable from
        risk_id (in either direction), with each node's current score/severity surfaced
        so a user can see the cascade at a glance."""
        root = self._get_risk_or_404(org_id, risk_id)
        edges = self._all_edges(org_id)

        undirected_adjacency: dict[uuid.UUID, set[uuid.UUID]] = {}
        for edge in edges:
            undirected_adjacency.setdefault(edge.upstream_risk_id, set()).add(edge.downstream_risk_id)
            undirected_adjacency.setdefault(edge.downstream_risk_id, set()).add(edge.upstream_risk_id)

        component_ids: set[uuid.UUID] = {risk_id}
        queue: deque[uuid.UUID] = deque([risk_id])
        while queue:
            current = queue.popleft()
            for neighbor in undirected_adjacency.get(current, set()):
                if neighbor not in component_ids:
                    component_ids.add(neighbor)
                    queue.append(neighbor)

        component_risks: list[Risk] = []
        if component_ids:
            component_risks = list(
                self.db.execute(
                    select(Risk).where(Risk.organization_id == org_id, Risk.id.in_(component_ids))
                ).scalars().all()
            )

        nodes = [
            {
                "risk_id": r.id,
                "title": r.title,
                "status": r.status,
                "severity": r.severity,
                "category": r.category,
                "inherent_score": r.inherent_score,
                "residual_score": r.residual_score,
            }
            for r in component_risks
        ]
        component_edges = [
            edge
            for edge in edges
            if edge.upstream_risk_id in component_ids and edge.downstream_risk_id in component_ids
        ]
        edge_payload = [
            {
                "id": edge.id,
                "upstream_risk_id": edge.upstream_risk_id,
                "downstream_risk_id": edge.downstream_risk_id,
                "relationship_type": edge.relationship_type,
            }
            for edge in component_edges
        ]

        return {
            "root_risk_id": root.id,
            "nodes": nodes,
            "edges": edge_payload,
            "summary": {
                "total_nodes": len(nodes),
                "total_edges": len(edge_payload),
            },
        }
