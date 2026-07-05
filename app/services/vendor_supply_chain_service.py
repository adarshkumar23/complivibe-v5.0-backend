from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.vendor_supply_chain import VendorSupplyChainAlert, VendorSupplyChainLink
from app.services.audit_service import AuditService
from app.services.vendor_concentration_risk_service import VendorConcentrationRiskService
from app.services.vendor_service import VendorService

MAX_GRAPH_DEPTH = 10


class VendorSupplyChainService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.vendor_service = VendorService(db)

    def create_link(
        self,
        *,
        organization_id: uuid.UUID,
        parent_vendor_id: uuid.UUID,
        sub_vendor_id: uuid.UUID,
        relationship_type: str,
        description: str | None,
        actor_user_id: uuid.UUID,
    ) -> VendorSupplyChainLink:
        if parent_vendor_id == sub_vendor_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A vendor cannot depend on itself")
        self.vendor_service.require_vendor_in_org(organization_id, parent_vendor_id)
        self.vendor_service.require_vendor_in_org(organization_id, sub_vendor_id)
        normalized_type = (relationship_type or "supplier").strip().lower().replace(" ", "_")
        if len(normalized_type) < 2 or len(normalized_type) > 80:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="relationship_type must be 2-80 characters")
        existing = self.db.execute(
            select(VendorSupplyChainLink).where(
                VendorSupplyChainLink.organization_id == organization_id,
                VendorSupplyChainLink.parent_vendor_id == parent_vendor_id,
                VendorSupplyChainLink.sub_vendor_id == sub_vendor_id,
                VendorSupplyChainLink.relationship_type == normalized_type,
                VendorSupplyChainLink.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active vendor supply-chain link already exists")
        row = VendorSupplyChainLink(
            organization_id=organization_id,
            parent_vendor_id=parent_vendor_id,
            sub_vendor_id=sub_vendor_id,
            relationship_type=normalized_type,
            description=description,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vendor supply-chain link conflicts with an existing link") from exc
        self._refresh_concentration_risk(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            trigger="vendor_supply_chain.link_created",
        )
        return row

    def deactivate_link(self, *, organization_id: uuid.UUID, link_id: uuid.UUID, actor_user_id: uuid.UUID) -> VendorSupplyChainLink:
        row = self.db.execute(
            select(VendorSupplyChainLink).where(
                VendorSupplyChainLink.organization_id == organization_id,
                VendorSupplyChainLink.id == link_id,
                VendorSupplyChainLink.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active vendor supply-chain link not found")
        row.is_active = False
        row.deactivated_at = datetime.now(UTC)
        row.deactivated_by_user_id = actor_user_id
        self.db.flush()
        self._reconcile_alerts_after_link_change(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        self._refresh_concentration_risk(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            trigger="vendor_supply_chain.link_deactivated",
        )
        return row

    def _refresh_concentration_risk(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        trigger: str,
    ) -> None:
        """Keep T1-6 concentration detection current with T1-3 supply-chain changes.

        No-ops for organizations that have never opted into concentration monitoring
        (no detection row yet) so this stays cheap and side-effect-free by default.
        """
        outcome = VendorConcentrationRiskService(self.db).recompute_if_tracked(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        if outcome is None:
            return
        detection, risk_created, state_changed = outcome
        if not state_changed:
            return
        AuditService(self.db).write_audit_log(
            action="vendor_concentration_risk.recomputed",
            entity_type="vendor_concentration_risk_detection",
            entity_id=detection.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "status": detection.status,
                "hhi_score": detection.hhi_score,
                "risk_id": str(detection.risk_id) if detection.risk_id else None,
            },
            metadata_json={"source": trigger, "risk_created": risk_created},
        )

    def _reconcile_alerts_after_link_change(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        """Close nth-party alerts (and clear flags) whose propagation path no longer exists.

        Without this, deactivating a supply-chain link leaves a permanent, unexplainable
        nth-party risk flag on the first-party vendor even though the vendor that
        triggered it is no longer reachable in the graph at all.
        """
        open_alerts = self.db.execute(
            select(VendorSupplyChainAlert).where(
                VendorSupplyChainAlert.organization_id == organization_id,
                VendorSupplyChainAlert.status == "open",
            )
        ).scalars().all()
        if not open_alerts:
            return
        now = datetime.now(UTC)
        audit = AuditService(self.db)
        affected_parent_ids: set[uuid.UUID] = set()
        for alert in open_alerts:
            still_reachable_parents = self._upstream_vendor_ids(
                organization_id=organization_id,
                triggering_vendor_id=alert.triggering_vendor_id,
                max_depth=MAX_GRAPH_DEPTH,
            )
            if alert.parent_vendor_id in still_reachable_parents:
                continue
            alert.status = "resolved"
            alert.resolved_at = now
            self.db.flush()
            audit.write_audit_log(
                action="vendor_supply_chain.alert_resolved",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                before_json={"status": "open"},
                after_json={"status": "resolved", "resolved_at": now.isoformat(), "reason": "supply_chain_path_removed"},
                metadata_json={"source": "vendor_supply_chain.link_deactivated"},
            )
            affected_parent_ids.add(alert.parent_vendor_id)
        for parent_id in affected_parent_ids:
            parent_vendor = self.vendor_service.require_vendor_in_org(organization_id, parent_id)
            self._recompute_nth_party_flag(
                organization_id=organization_id,
                parent_vendor=parent_vendor,
                actor_user_id=actor_user_id,
                trigger="vendor_supply_chain.link_deactivated",
            )

    def resolve_vendor_signal(
        self,
        *,
        organization_id: uuid.UUID,
        triggering_vendor_id: uuid.UUID,
        signal_type: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[VendorSupplyChainAlert]:
        """Close open alerts for a signal that has recovered (e.g. rating back above threshold).

        Called by the signal-producing endpoints when a fresh measurement is healthy, so a
        first-party vendor's nth-party flag doesn't stay stuck on a stale finding forever.
        """
        open_alerts = self.db.execute(
            select(VendorSupplyChainAlert).where(
                VendorSupplyChainAlert.organization_id == organization_id,
                VendorSupplyChainAlert.triggering_vendor_id == triggering_vendor_id,
                VendorSupplyChainAlert.signal_type == signal_type,
                VendorSupplyChainAlert.status == "open",
            )
        ).scalars().all()
        if not open_alerts:
            return []
        now = datetime.now(UTC)
        audit = AuditService(self.db)
        resolved: list[VendorSupplyChainAlert] = []
        affected_parent_ids: set[uuid.UUID] = set()
        for alert in open_alerts:
            alert.status = "resolved"
            alert.resolved_at = now
            self.db.flush()
            audit.write_audit_log(
                action="vendor_supply_chain.alert_resolved",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                before_json={"status": "open"},
                after_json={"status": "resolved", "resolved_at": now.isoformat(), "reason": "signal_recovered"},
                metadata_json={"source": "vendor_supply_chain.signal_recovered"},
            )
            resolved.append(alert)
            affected_parent_ids.add(alert.parent_vendor_id)
        for parent_id in affected_parent_ids:
            parent_vendor = self.vendor_service.require_vendor_in_org(organization_id, parent_id)
            self._recompute_nth_party_flag(
                organization_id=organization_id,
                parent_vendor=parent_vendor,
                actor_user_id=actor_user_id,
                trigger="vendor_supply_chain.signal_recovered",
            )
        return resolved

    def _recompute_nth_party_flag(
        self,
        *,
        organization_id: uuid.UUID,
        parent_vendor: Vendor,
        actor_user_id: uuid.UUID | None,
        trigger: str,
    ) -> None:
        """Set the vendor's durable nth-party flag from its current open alerts, not a blind write.

        Picks the highest-severity remaining open alert so a lower-severity signal arriving
        later can never silently downgrade a still-open critical finding, and clears the flag
        entirely once no open alerts remain.
        """
        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        remaining = self.db.execute(
            select(VendorSupplyChainAlert).where(
                VendorSupplyChainAlert.organization_id == organization_id,
                VendorSupplyChainAlert.parent_vendor_id == parent_vendor.id,
                VendorSupplyChainAlert.status == "open",
            )
        ).scalars().all()
        if remaining:
            worst = max(remaining, key=lambda a: severity_rank.get(a.severity, 0))
            new_flag, new_severity, new_signal_type = True, worst.severity, worst.signal_type
            worst_triggering_vendor_id: uuid.UUID | None = worst.triggering_vendor_id
        else:
            new_flag, new_severity, new_signal_type = False, None, None
            worst_triggering_vendor_id = None

        if (
            parent_vendor.nth_party_risk_flag == new_flag
            and parent_vendor.nth_party_risk_severity == new_severity
            and parent_vendor.nth_party_risk_signal_type == new_signal_type
        ):
            return

        before = {
            "nth_party_risk_flag": parent_vendor.nth_party_risk_flag,
            "nth_party_risk_severity": parent_vendor.nth_party_risk_severity,
            "nth_party_risk_signal_type": parent_vendor.nth_party_risk_signal_type,
            "nth_party_risk_updated_at": parent_vendor.nth_party_risk_updated_at.isoformat() if parent_vendor.nth_party_risk_updated_at else None,
        }
        parent_vendor.nth_party_risk_flag = new_flag
        parent_vendor.nth_party_risk_severity = new_severity
        parent_vendor.nth_party_risk_signal_type = new_signal_type
        parent_vendor.nth_party_risk_updated_at = datetime.now(UTC)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="vendor_supply_chain.nth_party_flag_updated",
            entity_type="vendor",
            entity_id=parent_vendor.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "nth_party_risk_flag": new_flag,
                "nth_party_risk_severity": new_severity,
                "nth_party_risk_signal_type": new_signal_type,
                "triggering_vendor_id": str(worst_triggering_vendor_id) if worst_triggering_vendor_id else None,
            },
            metadata_json={"source": trigger},
        )

    def build_graph(self, *, organization_id: uuid.UUID, root_vendor_id: uuid.UUID, depth: int) -> dict[str, Any]:
        root = self.vendor_service.require_vendor_in_org(organization_id, root_vendor_id)
        if depth < 1 or depth > MAX_GRAPH_DEPTH:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"depth must be between 1 and {MAX_GRAPH_DEPTH}")
        vendors_by_id: dict[uuid.UUID, Vendor] = {root.id: root}
        edges: list[VendorSupplyChainLink] = []
        cycles: list[list[uuid.UUID]] = []
        queue: deque[tuple[uuid.UUID, int, list[uuid.UUID]]] = deque([(root.id, 0, [root.id])])
        visited_edges: set[uuid.UUID] = set()
        while queue:
            current_id, current_depth, path = queue.popleft()
            if current_depth >= depth:
                continue
            links = self.db.execute(
                select(VendorSupplyChainLink).where(
                    VendorSupplyChainLink.organization_id == organization_id,
                    VendorSupplyChainLink.parent_vendor_id == current_id,
                    VendorSupplyChainLink.is_active.is_(True),
                )
            ).scalars().all()
            for link in links:
                if link.id in visited_edges:
                    continue
                visited_edges.add(link.id)
                edges.append(link)
                if link.sub_vendor_id not in vendors_by_id:
                    vendor = self.vendor_service.require_vendor_in_org(organization_id, link.sub_vendor_id)
                    vendors_by_id[vendor.id] = vendor
                if link.sub_vendor_id in path:
                    cycle_start = path.index(link.sub_vendor_id)
                    cycle = path[cycle_start:] + [link.sub_vendor_id]
                    if cycle not in cycles:
                        cycles.append(cycle)
                    continue
                queue.append((link.sub_vendor_id, current_depth + 1, path + [link.sub_vendor_id]))
        alerts = self.db.execute(
            select(VendorSupplyChainAlert).where(
                VendorSupplyChainAlert.organization_id == organization_id,
                VendorSupplyChainAlert.parent_vendor_id == root_vendor_id,
                VendorSupplyChainAlert.status == "open",
            )
        ).scalars().all()
        return {
            "root_vendor_id": str(root.id),
            "depth": depth,
            "nodes": [self._vendor_node(vendor) for vendor in vendors_by_id.values()],
            "edges": [self._link_payload(link) for link in edges],
            "data_quality_findings": [self._cycle_finding(cycle, vendors_by_id) for cycle in cycles],
            "open_alerts": [self._alert_payload(alert) for alert in alerts],
        }

    def propagate_vendor_signal(
        self,
        *,
        organization_id: uuid.UUID,
        triggering_vendor_id: uuid.UUID,
        signal_type: str,
        severity: str,
        explanation: str,
        source_entity_type: str | None = None,
        source_entity_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        max_depth: int = MAX_GRAPH_DEPTH,
    ) -> list[VendorSupplyChainAlert]:
        triggering_vendor = self.vendor_service.require_vendor_in_org(organization_id, triggering_vendor_id)
        created: list[VendorSupplyChainAlert] = []
        ancestor_ids = self._upstream_vendor_ids(
            organization_id=organization_id,
            triggering_vendor_id=triggering_vendor_id,
            max_depth=max_depth,
        )
        audit = AuditService(self.db)
        for parent_vendor_id in ancestor_ids:
            existing = self.db.execute(
                select(VendorSupplyChainAlert).where(
                    VendorSupplyChainAlert.organization_id == organization_id,
                    VendorSupplyChainAlert.parent_vendor_id == parent_vendor_id,
                    VendorSupplyChainAlert.triggering_vendor_id == triggering_vendor_id,
                    VendorSupplyChainAlert.signal_type == signal_type,
                    VendorSupplyChainAlert.status == "open",
                )
            ).scalar_one_or_none()
            text = f"{triggering_vendor.name} triggered {signal_type}: {explanation}"
            if existing is not None:
                before = {
                    "severity": existing.severity,
                    "explanation": existing.explanation,
                    "source_entity_type": existing.source_entity_type,
                    "source_entity_id": str(existing.source_entity_id) if existing.source_entity_id else None,
                }
                existing.severity = severity
                existing.explanation = text
                existing.source_entity_type = source_entity_type
                existing.source_entity_id = source_entity_id
                self.db.flush()
                audit.write_audit_log(
                    action="vendor_supply_chain.alert_updated",
                    entity_type="vendor_supply_chain_alert",
                    entity_id=existing.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    before_json=before,
                    after_json={
                        "parent_vendor_id": str(existing.parent_vendor_id),
                        "triggering_vendor_id": str(triggering_vendor_id),
                        "signal_type": signal_type,
                        "severity": severity,
                    },
                    metadata_json={"source": "vendor_supply_chain.propagation"},
                )
                created.append(existing)
            else:
                alert = VendorSupplyChainAlert(
                    organization_id=organization_id,
                    parent_vendor_id=parent_vendor_id,
                    triggering_vendor_id=triggering_vendor_id,
                    signal_type=signal_type,
                    severity=severity,
                    explanation=text,
                    source_entity_type=source_entity_type,
                    source_entity_id=source_entity_id,
                )
                self.db.add(alert)
                self.db.flush()
                audit.write_audit_log(
                    action="vendor_supply_chain.alert_created",
                    entity_type="vendor_supply_chain_alert",
                    entity_id=alert.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    after_json={
                        "parent_vendor_id": str(alert.parent_vendor_id),
                        "triggering_vendor_id": str(triggering_vendor_id),
                        "signal_type": signal_type,
                        "severity": severity,
                    },
                    metadata_json={"source": "vendor_supply_chain.propagation"},
                )
                created.append(alert)

            parent_vendor = self.vendor_service.require_vendor_in_org(organization_id, parent_vendor_id)
            self._recompute_nth_party_flag(
                organization_id=organization_id,
                parent_vendor=parent_vendor,
                actor_user_id=actor_user_id,
                trigger="vendor_supply_chain.propagation",
            )
        return created

    def _upstream_vendor_ids(
        self,
        *,
        organization_id: uuid.UUID,
        triggering_vendor_id: uuid.UUID,
        max_depth: int,
    ) -> list[uuid.UUID]:
        if max_depth < 1 or max_depth > MAX_GRAPH_DEPTH:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"max_depth must be between 1 and {MAX_GRAPH_DEPTH}")

        ordered: list[uuid.UUID] = []
        seen: set[uuid.UUID] = {triggering_vendor_id}
        queue: deque[tuple[uuid.UUID, int, list[uuid.UUID]]] = deque([(triggering_vendor_id, 0, [triggering_vendor_id])])
        while queue:
            current_id, current_depth, path = queue.popleft()
            if current_depth >= max_depth:
                continue
            links = self.db.execute(
                select(VendorSupplyChainLink).where(
                    VendorSupplyChainLink.organization_id == organization_id,
                    VendorSupplyChainLink.sub_vendor_id == current_id,
                    VendorSupplyChainLink.is_active.is_(True),
                )
            ).scalars().all()
            for link in links:
                parent_id = link.parent_vendor_id
                if parent_id in path or parent_id in seen:
                    continue
                seen.add(parent_id)
                ordered.append(parent_id)
                queue.append((parent_id, current_depth + 1, path + [parent_id]))
        return ordered

    @staticmethod
    def _vendor_node(vendor: Vendor) -> dict[str, Any]:
        return {"id": str(vendor.id), "name": vendor.name, "vendor_type": vendor.vendor_type, "risk_tier": vendor.risk_tier, "status": vendor.status}

    @staticmethod
    def _link_payload(link: VendorSupplyChainLink) -> dict[str, Any]:
        return {
            "id": str(link.id),
            "parent_vendor_id": str(link.parent_vendor_id),
            "sub_vendor_id": str(link.sub_vendor_id),
            "relationship_type": link.relationship_type,
            "description": link.description,
            "is_active": link.is_active,
        }

    @staticmethod
    def _alert_payload(alert: VendorSupplyChainAlert) -> dict[str, Any]:
        return {
            "id": str(alert.id),
            "parent_vendor_id": str(alert.parent_vendor_id),
            "triggering_vendor_id": str(alert.triggering_vendor_id),
            "signal_type": alert.signal_type,
            "severity": alert.severity,
            "status": alert.status,
            "explanation": alert.explanation,
            "source_entity_type": alert.source_entity_type,
            "source_entity_id": str(alert.source_entity_id) if alert.source_entity_id else None,
            "detected_at": alert.detected_at.isoformat() if alert.detected_at else None,
        }

    @staticmethod
    def _cycle_finding(cycle: list[uuid.UUID], vendors_by_id: dict[uuid.UUID, Vendor]) -> dict[str, Any]:
        names = [vendors_by_id[vendor_id].name for vendor_id in cycle if vendor_id in vendors_by_id]
        return {
            "type": "cycle_detected",
            "severity": "high",
            "vendor_ids": [str(vendor_id) for vendor_id in cycle],
            "vendor_names": names,
            "message": "Supply-chain graph contains a circular vendor dependency; validate ownership and dependency data.",
        }
