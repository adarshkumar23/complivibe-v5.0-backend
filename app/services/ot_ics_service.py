import hashlib
import secrets
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.data_asset import DataAsset
from app.models.ot_ics_agent import OtIcsAgent
from app.models.ot_ics_asset import OtIcsAsset
from app.models.ot_ics_finding import OtIcsFinding
from app.models.ot_ics_segment_risk_detection import OtIcsSegmentRiskDetection
from app.schemas.ot_ics import (
    OtIcsAgentCreate,
    OtIcsAssetCreate,
    OtIcsAssetUpdate,
    OtIcsFindingIngestRequest,
    OtIcsFindingResolveRequest,
)
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService

# A finding at this severity or above is a genuine risk to the org, not just
# monitoring noise -- it must create a real risk-register entry (see
# _cascade_finding_to_risk), matching every other domain's staleness/finding logic
# in this codebase (vendor concentration risk, KYB/AML, geopolitical risk, ...).
FINDING_RISK_CASCADE_SEVERITIES = {"high", "critical"}
# Matches OtIcsFindingService.get_summary's existing "flagged_network_segments"
# threshold for concentration reporting.
SEGMENT_FLAG_THRESHOLD = 2


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OtIcsAgentService:
    """Registration/lifecycle for OT/ICS agent-push credentials (mirrors TechnicalControlAgentService)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register_agent(
        self,
        org_id: uuid.UUID,
        payload: OtIcsAgentCreate,
        created_by: uuid.UUID,
    ) -> tuple[OtIcsAgent, str]:
        duplicate = self.db.execute(
            select(OtIcsAgent.id).where(
                OtIcsAgent.organization_id == org_id,
                OtIcsAgent.name == payload.name,
                OtIcsAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent name already exists")

        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        agent = OtIcsAgent(
            organization_id=org_id,
            name=payload.name,
            description=payload.description,
            token_hash=token_hash,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(agent)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.agent_registered",
            entity_type="ot_ics_agent",
            entity_id=agent.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": agent.name, "is_active": agent.is_active},
            metadata_json={"source": "api"},
        )
        return agent, token

    def list_agents(self, org_id: uuid.UUID) -> list[OtIcsAgent]:
        return self.db.execute(
            select(OtIcsAgent)
            .where(
                OtIcsAgent.organization_id == org_id,
                OtIcsAgent.deleted_at.is_(None),
                OtIcsAgent.is_active.is_(True),
            )
            .order_by(OtIcsAgent.created_at.desc())
        ).scalars().all()

    def get_agent(self, org_id: uuid.UUID, agent_id: uuid.UUID) -> OtIcsAgent:
        row = self.db.execute(
            select(OtIcsAgent).where(
                OtIcsAgent.organization_id == org_id,
                OtIcsAgent.id == agent_id,
                OtIcsAgent.deleted_at.is_(None),
                OtIcsAgent.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OT/ICS agent not found")
        return row

    def deregister_agent(self, org_id: uuid.UUID, agent_id: uuid.UUID, actor_id: uuid.UUID) -> OtIcsAgent:
        row = self.get_agent(org_id, agent_id)
        row.is_active = False
        row.deleted_at = _utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.agent_deregistered",
            entity_type="ot_ics_agent",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"is_active": True},
            after_json={"is_active": False},
            metadata_json={"source": "api"},
        )
        return row


def get_ot_ics_agent_from_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> OtIcsAgent:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    agent = db.execute(
        select(OtIcsAgent).where(
            and_(
                OtIcsAgent.token_hash == token_hash,
                OtIcsAgent.is_active.is_(True),
                OtIcsAgent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    agent.last_seen_at = _utcnow()
    db.commit()
    db.refresh(agent)
    return agent


class OtIcsAssetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _require_linked_data_asset(self, org_id: uuid.UUID, data_asset_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(DataAsset.id).where(
                DataAsset.organization_id == org_id,
                DataAsset.id == data_asset_id,
                DataAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked data asset not found")

    def create_asset(self, org_id: uuid.UUID, payload: OtIcsAssetCreate, created_by: uuid.UUID) -> OtIcsAsset:
        if payload.linked_data_asset_id is not None:
            self._require_linked_data_asset(org_id, payload.linked_data_asset_id)

        row = OtIcsAsset(
            organization_id=org_id,
            name=payload.name,
            asset_type=payload.asset_type,
            network_segment=payload.network_segment,
            criticality=payload.criticality,
            linked_data_asset_id=payload.linked_data_asset_id,
            status=payload.status,
            description=payload.description,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.asset_created",
            entity_type="ot_ics_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "name": row.name,
                "asset_type": row.asset_type,
                "criticality": row.criticality,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> OtIcsAsset:
        row = self.db.execute(
            select(OtIcsAsset).where(
                OtIcsAsset.organization_id == org_id,
                OtIcsAsset.id == asset_id,
                OtIcsAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OT/ICS asset not found")
        return row

    def list_assets(
        self,
        org_id: uuid.UUID,
        *,
        asset_type: str | None = None,
        criticality: str | None = None,
        status_filter: str | None = None,
        network_segment: str | None = None,
    ) -> list[OtIcsAsset]:
        stmt = select(OtIcsAsset).where(
            OtIcsAsset.organization_id == org_id,
            OtIcsAsset.deleted_at.is_(None),
        )
        if asset_type is not None:
            stmt = stmt.where(OtIcsAsset.asset_type == asset_type)
        if criticality is not None:
            stmt = stmt.where(OtIcsAsset.criticality == criticality)
        if status_filter is not None:
            stmt = stmt.where(OtIcsAsset.status == status_filter)
        if network_segment is not None:
            stmt = stmt.where(OtIcsAsset.network_segment == network_segment)
        return self.db.execute(stmt.order_by(OtIcsAsset.created_at.desc())).scalars().all()

    def update_asset(
        self,
        org_id: uuid.UUID,
        asset_id: uuid.UUID,
        payload: OtIcsAssetUpdate,
        actor_id: uuid.UUID,
    ) -> OtIcsAsset:
        row = self.get_asset(org_id, asset_id)
        updates = payload.model_dump(exclude_unset=True)

        if "linked_data_asset_id" in updates and updates["linked_data_asset_id"] is not None:
            self._require_linked_data_asset(org_id, updates["linked_data_asset_id"])

        before = {
            "name": row.name,
            "asset_type": row.asset_type,
            "network_segment": row.network_segment,
            "criticality": row.criticality,
            "linked_data_asset_id": str(row.linked_data_asset_id) if row.linked_data_asset_id else None,
            "status": row.status,
            "description": row.description,
        }

        for field, value in updates.items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.asset_updated",
            entity_type="ot_ics_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "name": row.name,
                "asset_type": row.asset_type,
                "network_segment": row.network_segment,
                "criticality": row.criticality,
                "linked_data_asset_id": str(row.linked_data_asset_id) if row.linked_data_asset_id else None,
                "status": row.status,
                "description": row.description,
            },
            metadata_json={"source": "api"},
        )
        return row

    def delete_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID, actor_id: uuid.UUID) -> OtIcsAsset:
        row = self.get_asset(org_id, asset_id)
        row.deleted_at = _utcnow()
        row.status = "decommissioned"
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.asset_deleted",
            entity_type="ot_ics_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"status": "active"},
            after_json={"status": row.status, "deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row


class OtIcsFindingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _require_asset_in_org(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> OtIcsAsset:
        row = self.db.execute(
            select(OtIcsAsset).where(
                OtIcsAsset.organization_id == org_id,
                OtIcsAsset.id == asset_id,
                OtIcsAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OT/ICS asset not found for this finding")
        return row

    def _get_finding_in_org(self, org_id: uuid.UUID, finding_id: uuid.UUID) -> OtIcsFinding:
        row = self.db.execute(
            select(OtIcsFinding).where(
                OtIcsFinding.organization_id == org_id,
                OtIcsFinding.id == finding_id,
                OtIcsFinding.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OT/ICS finding not found")
        return row

    def resolve_finding(
        self,
        org_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: OtIcsFindingResolveRequest,
        actor_id: uuid.UUID,
    ) -> OtIcsFinding:
        row = self._get_finding_in_org(org_id, finding_id)
        if row.resolved_at is not None:
            # Already resolved: idempotent no-op (no duplicate audit entry), but
            # still returns the existing resolved state rather than erroring.
            return row

        row.resolved_at = _utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.finding_resolved",
            entity_type="ot_ics_finding",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"resolved_at": None},
            after_json={"resolved_at": row.resolved_at.isoformat()},
            metadata_json={"source": "api", "resolution_note": payload.resolution_note},
        )

        asset = self.db.get(OtIcsAsset, row.asset_id)
        if asset is not None and asset.network_segment:
            self._recompute_segment_risk(org_id, asset.network_segment)
        return row

    def ingest_finding(self, agent: OtIcsAgent, payload: OtIcsFindingIngestRequest) -> OtIcsFinding:
        # Critical edge case: never create an orphaned finding row. Validate the asset
        # exists in the agent's org *before* any insert.
        asset = self._require_asset_in_org(agent.organization_id, payload.asset_id)

        detected_at = payload.detected_at or _utcnow()
        row = OtIcsFinding(
            organization_id=agent.organization_id,
            asset_id=asset.id,
            agent_id=agent.id,
            finding_type=payload.finding_type,
            severity=payload.severity,
            description=payload.description,
            raw_payload=payload.raw_payload,
            detected_at=detected_at,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ot_ics.finding_ingested",
            entity_type="ot_ics_finding",
            entity_id=row.id,
            organization_id=agent.organization_id,
            actor_user_id=None,
            after_json={
                "asset_id": str(row.asset_id),
                "agent_id": str(agent.id),
                "finding_type": row.finding_type,
                "severity": row.severity,
            },
            metadata_json={"source": "agent_ingest"},
        )

        self._cascade_finding_to_risk(row, asset)
        return row

    def _cascade_finding_to_risk(self, finding: OtIcsFinding, asset: OtIcsAsset) -> None:
        """A high/critical OT/ICS finding is a genuine operational-technology risk, not
        just monitoring noise -- create a real risk-register entry for it, the same
        way every other domain's staleness/finding logic in this codebase does
        (vendor concentration risk, KYB/AML, geopolitical risk). One finding creates
        at most one Risk (tracked via ``finding.risk_id``).
        """
        if finding.severity not in FINDING_RISK_CASCADE_SEVERITIES:
            return

        description = (
            f"OT/ICS convergence monitoring detected a {finding.severity}-severity "
            f"{finding.finding_type.replace('_', ' ')} finding on asset {asset.name!r} "
            f"({asset.asset_type}, network segment {asset.network_segment or 'unspecified'})."
        )
        if finding.description:
            description += f" {finding.description}"

        risk = RiskService(self.db).create_risk_from_service(
            organization_id=finding.organization_id,
            title=f"OT/ICS finding: {finding.finding_type.replace('_', ' ')} on {asset.name}",
            description=description,
            category="operational",
            likelihood=3 if finding.severity == "high" else 4,
            impact=4 if finding.severity == "high" else 5,
            treatment_strategy="mitigate",
            risk_context_external=(
                f"Source: OT/ICS convergence-monitoring agent ingest. Finding id {finding.id}, "
                f"asset id {asset.id}, detected_at {finding.detected_at.isoformat()}."
            ),
            metadata_json={
                "source": "ot_ics",
                "finding_id": str(finding.id),
                "asset_id": str(asset.id),
                "network_segment": asset.network_segment,
                "finding_type": finding.finding_type,
                "severity": finding.severity,
            },
            created_by_user_id=None,
            audit_source="ot_ics_finding_ingest",
        )
        finding.risk_id = risk.id
        self.db.flush()

        if asset.network_segment:
            self._recompute_segment_risk(finding.organization_id, asset.network_segment)

    def _recompute_segment_risk(self, org_id: uuid.UUID, network_segment: str) -> None:
        """Recompute open high/critical finding concentration for one network segment
        and, the first time it crosses ``SEGMENT_FLAG_THRESHOLD`` (matching
        ``get_summary``'s existing "flagged_network_segments" reporting threshold),
        create a single Risk register entry for the segment as a whole -- a flagged
        multi-finding segment is a distinct, worse risk than any one finding alone.
        """
        count = self.db.execute(
            select(func.count(OtIcsFinding.id))
            .select_from(OtIcsFinding)
            .join(OtIcsAsset, OtIcsAsset.id == OtIcsFinding.asset_id)
            .where(
                OtIcsFinding.organization_id == org_id,
                OtIcsFinding.deleted_at.is_(None),
                OtIcsFinding.resolved_at.is_(None),
                OtIcsFinding.severity.in_(FINDING_RISK_CASCADE_SEVERITIES),
                OtIcsAsset.network_segment == network_segment,
            )
        ).scalar_one()

        detection = self.db.execute(
            select(OtIcsSegmentRiskDetection).where(
                OtIcsSegmentRiskDetection.organization_id == org_id,
                OtIcsSegmentRiskDetection.network_segment == network_segment,
            )
        ).scalar_one_or_none()
        if detection is None:
            detection = OtIcsSegmentRiskDetection(
                organization_id=org_id,
                network_segment=network_segment,
                threshold_count=SEGMENT_FLAG_THRESHOLD,
                computed_at=_utcnow(),
            )
            self.db.add(detection)

        detection.open_high_or_critical_count = count
        detection.computed_at = _utcnow()
        detection.status = "flagged" if count >= SEGMENT_FLAG_THRESHOLD else "below_threshold"
        self.db.flush()

        if detection.status == "flagged" and detection.risk_id is None:
            risk = RiskService(self.db).create_risk_from_service(
                organization_id=org_id,
                title=f"OT/ICS network segment risk concentration: {network_segment}",
                description=(
                    f"Network segment {network_segment!r} has {count} open high-or-critical "
                    "OT/ICS convergence-monitoring findings across its assets, exceeding the "
                    f"{SEGMENT_FLAG_THRESHOLD}-finding concentration threshold."
                ),
                category="operational",
                likelihood=4,
                impact=4,
                treatment_strategy="mitigate",
                risk_context_external="Source: OT/ICS convergence-monitoring findings/summary concentration threshold.",
                metadata_json={
                    "source": "ot_ics_segment_concentration",
                    "network_segment": network_segment,
                    "open_high_or_critical_count": count,
                },
                created_by_user_id=None,
                audit_source="ot_ics_segment_concentration",
            )
            detection.risk_id = risk.id
            self.db.flush()

    def list_findings(
        self,
        org_id: uuid.UUID,
        *,
        asset_id: uuid.UUID | None = None,
        severity: str | None = None,
        finding_type: str | None = None,
        unresolved_only: bool = False,
    ) -> list[OtIcsFinding]:
        stmt = select(OtIcsFinding).where(
            OtIcsFinding.organization_id == org_id,
            OtIcsFinding.deleted_at.is_(None),
        )
        if asset_id is not None:
            stmt = stmt.where(OtIcsFinding.asset_id == asset_id)
        if severity is not None:
            stmt = stmt.where(OtIcsFinding.severity == severity)
        if finding_type is not None:
            stmt = stmt.where(OtIcsFinding.finding_type == finding_type)
        if unresolved_only:
            stmt = stmt.where(OtIcsFinding.resolved_at.is_(None))
        return self.db.execute(stmt.order_by(OtIcsFinding.detected_at.desc())).scalars().all()

    def get_summary(self, org_id: uuid.UUID) -> dict:
        findings = self.list_findings(org_id)
        total = len(findings)
        open_findings = [row for row in findings if row.resolved_at is None]
        resolved_count = total - len(open_findings)

        counts_by_severity = Counter(row.severity for row in findings)
        counts_by_finding_type = Counter(row.finding_type for row in findings)

        asset_ids = {row.asset_id for row in open_findings}
        assets = {}
        if asset_ids:
            assets = {
                row.id: row
                for row in self.db.execute(
                    select(OtIcsAsset).where(OtIcsAsset.id.in_(asset_ids))
                ).scalars().all()
            }

        high_critical_open = [row for row in open_findings if row.severity in {"high", "critical"}]
        assets_with_open_high_or_critical = sorted({row.asset_id for row in high_critical_open}, key=str)

        segment_counts: dict[str, int] = defaultdict(int)
        for row in high_critical_open:
            asset = assets.get(row.asset_id)
            segment = asset.network_segment if asset is not None else None
            if segment:
                segment_counts[segment] += 1

        flagged_segments = [
            {"network_segment": segment, "open_high_or_critical_count": count}
            for segment, count in sorted(segment_counts.items(), key=lambda item: item[1], reverse=True)
            if count >= 2
        ]

        return {
            "total_findings": total,
            "open_findings": len(open_findings),
            "resolved_findings": resolved_count,
            "counts_by_severity": dict(counts_by_severity),
            "counts_by_finding_type": dict(counts_by_finding_type),
            "assets_with_open_high_or_critical": assets_with_open_high_or_critical,
            "flagged_network_segments": flagged_segments,
        }
