import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_control_link import CompliancePolicyControlLink
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.vendor import Vendor
from app.models.vendor_control_link import VendorControlLink
from app.models.vendor_risk_score import VendorRiskScore


class RiskGraphService:
    NODE_TYPES = ["control", "vendor", "obligation", "evidence", "policy"]

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    @classmethod
    def _normalize_dt(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def derive_node_health(cls, node_type: str, record: dict[str, Any]) -> str:
        now = cls.utcnow()
        horizon = now + timedelta(days=30)
        today = cls.utcdate()
        due_horizon = today + timedelta(days=30)

        if node_type == "control":
            status_value = (record.get("status") or "").lower()
            has_approved_evidence = bool(record.get("has_approved_evidence", False))
            has_expiring_evidence = bool(record.get("has_expiring_evidence", False))

            if status_value in {"inactive", "failed"}:
                return "critical"
            if status_value == "draft":
                return "unknown"
            if status_value == "active" and has_approved_evidence and not has_expiring_evidence:
                return "healthy"
            if status_value == "active" and (not has_approved_evidence or has_expiring_evidence):
                return "degraded"
            return "unknown"

        if node_type == "vendor":
            tier = (record.get("risk_tier") or "").lower()
            status_value = (record.get("status") or "").lower()

            if tier == "critical" or status_value == "inactive":
                return "critical"
            if tier == "high" or status_value == "under_review":
                return "degraded"
            if tier in {"low", "medium"} and status_value == "active":
                return "healthy"
            if tier == "not_assessed":
                return "unknown"
            return "unknown"

        if node_type == "obligation":
            status_value = (record.get("status") or "").lower()
            if status_value in {"non_compliant", "overdue"}:
                return "critical"
            if status_value == "partial":
                return "degraded"
            if status_value in {"met", "compliant"}:
                return "healthy"
            if not status_value or status_value == "pending":
                return "unknown"
            return "unknown"

        if node_type == "evidence":
            status_value = (record.get("status") or "").lower()
            expiry = cls._normalize_dt(record.get("expiry_date"))

            if status_value in {"rejected", "expired"}:
                return "critical"
            if isinstance(expiry, datetime) and expiry < now:
                return "critical"
            if status_value == "approved":
                if expiry is None or expiry > horizon:
                    return "healthy"
                if now <= expiry <= horizon:
                    return "degraded"
            if status_value in {"pending", "submitted"}:
                return "unknown"
            return "unknown"

        if node_type == "policy":
            status_value = (record.get("status") or "").lower()
            review_due = record.get("review_due_date")

            if status_value in {"deprecated", "archived"}:
                return "critical"
            if isinstance(review_due, date) and review_due < today:
                return "critical"
            if status_value == "approved":
                if review_due is None or review_due > due_horizon:
                    return "healthy"
                if today <= review_due <= due_horizon:
                    return "degraded"
            if status_value in {"draft", "under_review"}:
                return "unknown"
            return "unknown"

        return "unknown"

    @classmethod
    def build(cls, *, risk_id: uuid.UUID, org_id: uuid.UUID, depth: int, db: Session) -> dict[str, Any]:
        effective_depth = 2 if depth > 2 else 1 if depth < 1 else depth

        risk = db.execute(
            select(Risk).where(
                Risk.id == risk_id,
                Risk.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if risk is None:
            return {}

        risk_payload = {
            "id": risk.id,
            "name": risk.title,
            "status": risk.status,
            "score": risk.inherent_score,
            "category": risk.category,
        }

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_ids: set[uuid.UUID] = set()
        edge_keys: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

        def add_node(*, node_id: uuid.UUID, node_type: str, label: str, status: str, health: str, metadata: dict[str, Any]) -> None:
            if node_id in node_ids:
                return
            node_ids.add(node_id)
            nodes.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "label": label,
                    "status": status,
                    "health": health,
                    "metadata": metadata,
                }
            )

        def add_edge(*, source_id: uuid.UUID, target_id: uuid.UUID, relationship: str) -> None:
            key = (source_id, target_id, relationship)
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship": relationship,
                }
            )

        control_links = db.execute(
            select(RiskControlLink).where(
                RiskControlLink.organization_id == org_id,
                RiskControlLink.risk_id == risk.id,
                RiskControlLink.status == "active",
            )
        ).scalars().all()
        control_ids = [row.control_id for row in control_links]

        controls = []
        if control_ids:
            controls = db.execute(
                select(Control).where(
                    Control.organization_id == org_id,
                    Control.id.in_(control_ids),
                )
            ).scalars().all()

        evidence_stats: dict[uuid.UUID, dict[str, Any]] = {}
        last_tested_map: dict[uuid.UUID, datetime | None] = {}

        if control_ids:
            evidence_rows = db.execute(
                select(
                    EvidenceControlLink.control_id,
                    EvidenceItem.id,
                    EvidenceItem.status,
                    EvidenceItem.valid_until,
                )
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.control_id.in_(control_ids),
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == org_id,
                )
            ).all()
            now = cls.utcnow()
            horizon = now + timedelta(days=30)

            for control_id, evidence_id, evidence_status, valid_until in evidence_rows:
                stat = evidence_stats.setdefault(
                    control_id,
                    {
                        "evidence_count": 0,
                        "has_approved_evidence": False,
                        "has_expiring_evidence": False,
                        "evidence_ids": set(),
                    },
                )
                if evidence_id not in stat["evidence_ids"]:
                    stat["evidence_count"] += 1
                    stat["evidence_ids"].add(evidence_id)
                if evidence_status == "approved":
                    stat["has_approved_evidence"] = True
                    normalized_valid_until = cls._normalize_dt(valid_until)
                    if isinstance(normalized_valid_until, datetime) and now <= normalized_valid_until <= horizon:
                        stat["has_expiring_evidence"] = True

            test_rows = db.execute(
                select(ControlTestRun.control_id, func.max(ControlTestRun.created_at))
                .where(
                    ControlTestRun.organization_id == org_id,
                    ControlTestRun.control_id.in_(control_ids),
                )
                .group_by(ControlTestRun.control_id)
            ).all()
            last_tested_map = {control_id: tested_at for control_id, tested_at in test_rows}

        control_map = {row.id: row for row in controls}
        for control_id in control_ids:
            control = control_map.get(control_id)
            if control is None:
                continue
            stat = evidence_stats.get(control_id, {})
            record = {
                "status": control.status,
                "has_approved_evidence": bool(stat.get("has_approved_evidence", False)),
                "has_expiring_evidence": bool(stat.get("has_expiring_evidence", False)),
            }
            health = cls.derive_node_health("control", record)
            add_node(
                node_id=control.id,
                node_type="control",
                label=control.title,
                status=control.status,
                health=health,
                metadata={
                    "control_type": control.control_type,
                    "owner_user_id": control.owner_user_id,
                    "evidence_count": int(stat.get("evidence_count", 0)),
                    "last_tested_at": last_tested_map.get(control.id),
                },
            )
            add_edge(source_id=risk.id, target_id=control.id, relationship="mitigated_by")

        # Depth-1 vendors via shared controls
        vendor_rows = []
        if control_ids:
            vendor_rows = db.execute(
                select(Vendor)
                .join(VendorControlLink, VendorControlLink.vendor_id == Vendor.id)
                .where(
                    Vendor.organization_id == org_id,
                    VendorControlLink.organization_id == org_id,
                    VendorControlLink.control_id.in_(control_ids),
                    VendorControlLink.status == "active",
                )
            ).scalars().all()

        vendor_score_map: dict[uuid.UUID, str] = {}
        vendor_ids = [vendor.id for vendor in vendor_rows]
        if vendor_ids:
            latest_scores = db.execute(
                select(VendorRiskScore)
                .where(
                    VendorRiskScore.organization_id == org_id,
                    VendorRiskScore.vendor_id.in_(vendor_ids),
                )
                .order_by(VendorRiskScore.vendor_id, VendorRiskScore.created_at.desc(), VendorRiskScore.id.desc())
            ).scalars().all()
            for score_row in latest_scores:
                if score_row.vendor_id not in vendor_score_map:
                    vendor_score_map[score_row.vendor_id] = score_row.risk_level

        for vendor in vendor_rows:
            health = cls.derive_node_health(
                "vendor",
                {
                    "risk_tier": vendor.risk_tier,
                    "status": vendor.status,
                },
            )
            add_node(
                node_id=vendor.id,
                node_type="vendor",
                label=vendor.name,
                status=vendor.status,
                health=health,
                metadata={
                    "vendor_type": vendor.vendor_type,
                    "risk_tier": vendor.risk_tier,
                    "risk_level": vendor_score_map.get(vendor.id),
                    "last_assessment_at": None,
                },
            )
            add_edge(source_id=risk.id, target_id=vendor.id, relationship="affects")
            if vendor.id in vendor_score_map:
                add_edge(source_id=risk.id, target_id=vendor.id, relationship="vendor_risk_factor")

        # Depth-1 obligations via control mappings
        obligation_rows = []
        if control_ids:
            obligation_rows = db.execute(
                select(Obligation)
                .join(ControlObligationMapping, ControlObligationMapping.obligation_id == Obligation.id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.control_id.in_(control_ids),
                    ControlObligationMapping.status == "active",
                )
            ).scalars().all()

        for obligation in obligation_rows:
            health = cls.derive_node_health("obligation", {"status": obligation.status})
            add_node(
                node_id=obligation.id,
                node_type="obligation",
                label=obligation.title,
                status=obligation.status,
                health=health,
                metadata={
                    "framework_id": obligation.framework_id,
                    "section_ref": obligation.reference_code,
                    "status": obligation.status,
                },
            )
            add_edge(source_id=risk.id, target_id=obligation.id, relationship="governed_by")

        # Depth-1 evidence via control links
        evidence_rows = []
        if control_ids:
            evidence_rows = db.execute(
                select(EvidenceItem, EvidenceControlLink.control_id)
                .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
                .where(
                    EvidenceItem.organization_id == org_id,
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.control_id.in_(control_ids),
                    EvidenceControlLink.link_status == "active",
                )
            ).all()

        seen_evidence: set[uuid.UUID] = set()
        for evidence, linked_control_id in evidence_rows:
            if evidence.id in seen_evidence:
                continue
            seen_evidence.add(evidence.id)
            health = cls.derive_node_health(
                "evidence",
                {
                    "status": evidence.status,
                    "expiry_date": evidence.valid_until,
                },
            )
            add_node(
                node_id=evidence.id,
                node_type="evidence",
                label=evidence.title,
                status=evidence.status,
                health=health,
                metadata={
                    "evidence_type": evidence.evidence_type,
                    "submitted_by": evidence.uploaded_by_user_id,
                    "expiry_date": evidence.valid_until,
                    "linked_control_id": linked_control_id,
                },
            )
            add_edge(source_id=risk.id, target_id=evidence.id, relationship="evidenced_by")

        # Direct risk-evidence links
        direct_risk_evidence_rows = db.execute(
            select(EvidenceItem)
            .join(RiskEvidenceLink, RiskEvidenceLink.evidence_item_id == EvidenceItem.id)
            .where(
                RiskEvidenceLink.organization_id == org_id,
                RiskEvidenceLink.risk_id == risk.id,
                RiskEvidenceLink.status == "active",
                EvidenceItem.organization_id == org_id,
            )
        ).scalars().all()
        for evidence in direct_risk_evidence_rows:
            health = cls.derive_node_health(
                "evidence",
                {
                    "status": evidence.status,
                    "expiry_date": evidence.valid_until,
                },
            )
            add_node(
                node_id=evidence.id,
                node_type="evidence",
                label=evidence.title,
                status=evidence.status,
                health=health,
                metadata={
                    "evidence_type": evidence.evidence_type,
                    "submitted_by": evidence.uploaded_by_user_id,
                    "expiry_date": evidence.valid_until,
                    "linked_control_id": None,
                },
            )
            add_edge(source_id=risk.id, target_id=evidence.id, relationship="has_evidence")

        # Depth-1 policies via policy-control links
        policy_rows = []
        if control_ids:
            policy_rows = db.execute(
                select(CompliancePolicy)
                .join(CompliancePolicyControlLink, CompliancePolicyControlLink.policy_id == CompliancePolicy.id)
                .where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicyControlLink.organization_id == org_id,
                    CompliancePolicyControlLink.control_id.in_(control_ids),
                    CompliancePolicyControlLink.status == "active",
                    CompliancePolicy.archived_at.is_(None),
                )
            ).scalars().all()

        for policy in policy_rows:
            health = cls.derive_node_health(
                "policy",
                {
                    "status": policy.status,
                    "review_due_date": policy.review_due_date,
                },
            )
            add_node(
                node_id=policy.id,
                node_type="policy",
                label=policy.title,
                status=policy.status,
                health=health,
                metadata={
                    "policy_type": policy.policy_type,
                    "owner_user_id": policy.owner_user_id,
                    "effective_date": policy.effective_date,
                    "review_due_date": policy.review_due_date,
                },
            )
            add_edge(source_id=risk.id, target_id=policy.id, relationship="policy_linked")

        if effective_depth == 2 and control_ids:
            for control_id in control_ids:
                control = control_map.get(control_id)
                if control is None:
                    continue

                # Vendors from this control
                control_vendors = db.execute(
                    select(Vendor)
                    .join(VendorControlLink, VendorControlLink.vendor_id == Vendor.id)
                    .where(
                        Vendor.organization_id == org_id,
                        VendorControlLink.organization_id == org_id,
                        VendorControlLink.control_id == control_id,
                        VendorControlLink.status == "active",
                    )
                ).scalars().all()
                for vendor in control_vendors:
                    health = cls.derive_node_health(
                        "vendor",
                        {
                            "risk_tier": vendor.risk_tier,
                            "status": vendor.status,
                        },
                    )
                    add_node(
                        node_id=vendor.id,
                        node_type="vendor",
                        label=vendor.name,
                        status=vendor.status,
                        health=health,
                        metadata={
                            "vendor_type": vendor.vendor_type,
                            "risk_tier": vendor.risk_tier,
                            "last_assessment_at": None,
                        },
                    )
                    add_edge(source_id=control.id, target_id=vendor.id, relationship="affects")

                # Evidence from this control
                control_evidence_rows = db.execute(
                    select(EvidenceItem)
                    .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
                    .where(
                        EvidenceItem.organization_id == org_id,
                        EvidenceControlLink.organization_id == org_id,
                        EvidenceControlLink.control_id == control_id,
                        EvidenceControlLink.link_status == "active",
                    )
                ).scalars().all()
                for evidence in control_evidence_rows:
                    health = cls.derive_node_health(
                        "evidence",
                        {
                            "status": evidence.status,
                            "expiry_date": evidence.valid_until,
                        },
                    )
                    add_node(
                        node_id=evidence.id,
                        node_type="evidence",
                        label=evidence.title,
                        status=evidence.status,
                        health=health,
                        metadata={
                            "evidence_type": evidence.evidence_type,
                            "submitted_by": evidence.uploaded_by_user_id,
                            "expiry_date": evidence.valid_until,
                            "linked_control_id": control.id,
                        },
                    )
                    add_edge(source_id=control.id, target_id=evidence.id, relationship="evidenced_by")

                # Policies from this control
                control_policies = db.execute(
                    select(CompliancePolicy)
                    .join(CompliancePolicyControlLink, CompliancePolicyControlLink.policy_id == CompliancePolicy.id)
                    .where(
                        CompliancePolicy.organization_id == org_id,
                        CompliancePolicyControlLink.organization_id == org_id,
                        CompliancePolicyControlLink.control_id == control_id,
                        CompliancePolicyControlLink.status == "active",
                        CompliancePolicy.archived_at.is_(None),
                    )
                ).scalars().all()
                for policy in control_policies:
                    health = cls.derive_node_health(
                        "policy",
                        {
                            "status": policy.status,
                            "review_due_date": policy.review_due_date,
                        },
                    )
                    add_node(
                        node_id=policy.id,
                        node_type="policy",
                        label=policy.title,
                        status=policy.status,
                        health=health,
                        metadata={
                            "policy_type": policy.policy_type,
                            "owner_user_id": policy.owner_user_id,
                            "effective_date": policy.effective_date,
                            "review_due_date": policy.review_due_date,
                        },
                    )
                    add_edge(source_id=control.id, target_id=policy.id, relationship="policy_linked")

        by_type = {key: 0 for key in cls.NODE_TYPES}
        by_health = {"healthy": 0, "degraded": 0, "critical": 0, "unknown": 0}
        for node in nodes:
            by_type[node["node_type"]] = by_type.get(node["node_type"], 0) + 1
            by_health[node["health"]] = by_health.get(node["health"], 0) + 1

        return {
            "risk": risk_payload,
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "total_nodes": len(nodes),
                "by_type": by_type,
                "by_health": by_health,
                "depth_reached": effective_depth,
            },
        }
