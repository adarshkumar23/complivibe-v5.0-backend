from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.compliance.services.board_scorecard_builder import BoardScorecardBuilder
from app.compliance.services.entity_risk_score_service import EntityRiskScoreService
from app.models.board_scorecard_snapshot import BoardScorecardSnapshot
from app.models.business_unit import BusinessUnit
from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_report import ComplianceReport
from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.entity_risk_score import EntityRiskScore
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.risk import Risk
from app.models.risk_indicator import RiskIndicator
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.services.audit_service import AuditService
from app.services.compliance_dashboard_service import ComplianceDashboardService
from app.services.compliance_deadline_service import ComplianceDeadlineService
from app.services.report_service import REPORT_CAVEAT, ReportService


class BoardScorecardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _require_bu(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> BusinessUnit | None:
        if business_unit_id is None:
            return None
        bu = self.db.execute(
            select(BusinessUnit).where(
                BusinessUnit.id == business_unit_id,
                BusinessUnit.organization_id == org_id,
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if bu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")
        return bu

    def _risk_filters(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None):
        filters = [Risk.organization_id == org_id]
        if business_unit_id is not None:
            filters.append(Risk.business_unit_id == business_unit_id)
        return filters

    def _control_filters(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None):
        filters = [Control.organization_id == org_id]
        if business_unit_id is not None:
            filters.append(Control.business_unit_id == business_unit_id)
        return filters

    def _policy_filters(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None):
        filters = [CompliancePolicy.organization_id == org_id]
        if business_unit_id is not None:
            filters.append(CompliancePolicy.business_unit_id == business_unit_id)
        return filters

    def _vendor_filters(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None):
        filters = [Vendor.organization_id == org_id]
        if business_unit_id is not None:
            filters.append(Vendor.business_unit_id == business_unit_id)
        return filters

    def _build_posture_summary(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        dashboard = ComplianceDashboardService(self.db)
        org_posture = dashboard.posture_summary(org_id)
        if business_unit_id is None:
            return org_posture

        risk_filters = self._risk_filters(org_id, business_unit_id)
        control_filters = self._control_filters(org_id, business_unit_id)
        policy_filters = self._policy_filters(org_id, business_unit_id)
        vendor_filters = self._vendor_filters(org_id, business_unit_id)

        risk_rows = self.db.execute(
            select(Risk.severity, func.count(Risk.id)).where(and_(*risk_filters)).group_by(Risk.severity)
        ).all()
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for sev, count in risk_rows:
            if sev in by_severity:
                by_severity[str(sev)] = int(count)

        total_risks = int(self.db.execute(select(func.count(Risk.id)).where(and_(*risk_filters))).scalar_one())

        total_controls = int(self.db.execute(select(func.count(Control.id)).where(and_(*control_filters))).scalar_one())
        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    and_(*control_filters),
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        bu_control_ids = self.db.execute(select(Control.id).where(and_(*control_filters))).scalars().all()
        with_evidence = 0
        if bu_control_ids:
            with_evidence = int(
                self.db.execute(
                    select(func.count(func.distinct(EvidenceControlLink.control_id)))
                    .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                    .where(
                        EvidenceControlLink.organization_id == org_id,
                        EvidenceControlLink.link_status == "active",
                        EvidenceControlLink.control_id.in_(bu_control_ids),
                        EvidenceItem.organization_id == org_id,
                        EvidenceItem.status != "archived",
                        EvidenceItem.review_status == "verified",
                    )
                ).scalar_one()
            )

        total_policies = int(
            self.db.execute(select(func.count(CompliancePolicy.id)).where(and_(*policy_filters))).scalar_one()
        )
        today = datetime.now(UTC).date()
        expired_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    and_(*policy_filters),
                    CompliancePolicy.status != "archived",
                    CompliancePolicy.review_due_date.is_not(None),
                    CompliancePolicy.review_due_date < today,
                )
            ).scalar_one()
        )
        policy_status_rows = self.db.execute(
            select(CompliancePolicy.status, func.count(CompliancePolicy.id))
            .where(and_(*policy_filters))
            .group_by(CompliancePolicy.status)
        ).all()
        by_policy_status = {str(k): int(v) for k, v in policy_status_rows}

        total_vendors = int(self.db.execute(select(func.count(Vendor.id)).where(and_(*vendor_filters))).scalar_one())
        vendor_tier_rows = self.db.execute(
            select(Vendor.risk_tier, func.count(Vendor.id)).where(and_(*vendor_filters)).group_by(Vendor.risk_tier)
        ).all()
        vendor_by_tier = {str(k): int(v) for k, v in vendor_tier_rows}

        pending_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id))
                .join(Vendor, Vendor.id == VendorAssessment.vendor_id)
                .where(
                    Vendor.organization_id == org_id,
                    Vendor.business_unit_id == business_unit_id,
                    VendorAssessment.organization_id == org_id,
                    VendorAssessment.status.in_(["draft", "in_progress", "under_review"]),
                )
            ).scalar_one()
        )

        scoped = dict(org_posture)
        scoped["scope"] = {
            "type": "business_unit",
            "business_unit_id": str(business_unit_id),
            "note": "Framework/deadline level metrics remain organization-wide where BU partitioning is not native.",
        }
        scoped["risks"] = {
            "total": total_risks,
            "by_severity": by_severity,
            "open_treatments": org_posture.get("risks", {}).get("open_treatments", 0),
        }
        scoped["controls"] = {
            "total": total_controls,
            "active": active_controls,
            "with_evidence": with_evidence,
            "without_evidence": max(0, active_controls - with_evidence),
        }
        scoped["policies"] = {
            "total": total_policies,
            "approved": int(by_policy_status.get("approved", 0)),
            "under_review": int(by_policy_status.get("under_review", 0)),
            "expired": expired_policies,
        }
        scoped["vendors"] = {
            "total": total_vendors,
            "by_risk_tier": vendor_by_tier,
            "pending_assessments": pending_assessments,
        }
        return scoped

    def _framework_readiness(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        rows = ComplianceDashboardService(self.db).framework_readiness(org_id)
        payload: dict = {"rows": rows}
        if business_unit_id is not None:
            payload["note"] = "Framework readiness is organization-wide and shown as-is for BU scorecards."
        return payload

    def _top_risks(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        latest_scores: list[EntityRiskScore] = []
        for entity_type in EntityRiskScoreService.ENTITY_TYPES:
            latest_scores.extend(EntityRiskScoreService.get_all_latest(entity_type, org_id, self.db))

        if business_unit_id is not None:
            latest_scores = [
                row
                for row in latest_scores
                if row.entity_type == "business_unit" and row.entity_id == business_unit_id
            ]

        latest_scores.sort(key=lambda r: (float(r.composite_score), r.computed_at), reverse=True)
        top = latest_scores[:5]
        if top:
            return {
                "source": "entity_risk_scores",
                "items": [
                    {
                        "score_id": str(row.id),
                        "entity_type": row.entity_type,
                        "entity_id": str(row.entity_id),
                        "entity_label": row.entity_label,
                        "composite_score": float(row.composite_score),
                        "score_band": row.score_band,
                        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
                    }
                    for row in top
                ],
            }

        risk_filters = self._risk_filters(org_id, business_unit_id)
        risk_rows = self.db.execute(
            select(Risk)
            .where(and_(*risk_filters))
            .order_by(
                Risk.inherent_score.desc(),
                case(
                    (Risk.severity == "critical", 4),
                    (Risk.severity == "high", 3),
                    (Risk.severity == "medium", 2),
                    else_=1,
                ).desc(),
                Risk.created_at.desc(),
            )
            .limit(5)
        ).scalars().all()

        return {
            "source": "risk_inherent_score_fallback",
            "items": [
                {
                    "risk_id": str(row.id),
                    "title": row.title,
                    "severity": row.severity,
                    "inherent_score": int(row.inherent_score),
                }
                for row in risk_rows
            ],
        }

    def _risk_appetite_breaches(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        rows = self.db.execute(
            select(ControlMonitoringAlert)
            .where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
            .order_by(ControlMonitoringAlert.created_at.desc())
        ).scalars().all()

        if business_unit_id is None:
            filtered = rows
        else:
            filtered = []
            bu_text = str(business_unit_id)
            for row in rows:
                ctx = row.alert_context_json if isinstance(row.alert_context_json, dict) else {}
                if str(ctx.get("scope_id") or "") == bu_text:
                    filtered.append(row)
                    continue
                raw_risk_id = ctx.get("risk_id")
                if not isinstance(raw_risk_id, str):
                    continue
                try:
                    risk_id = uuid.UUID(raw_risk_id)
                except ValueError:
                    continue
                risk = self.db.get(Risk, risk_id)
                if risk and risk.organization_id == org_id and risk.business_unit_id == business_unit_id:
                    filtered.append(row)

        return {
            "open_breach_count": len(filtered),
            "sample_alerts": [
                {
                    "alert_id": str(row.id),
                    "title": row.title,
                    "severity": row.severity,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in filtered[:5]
            ],
        }

    def _control_effectiveness_summary(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        if business_unit_id is None:
            payload = ComplianceDashboardService(self.db).control_health(org_id)
            total = sum(int(v) for v in payload.get("total_controls_by_status", {}).values())
            without_evidence = int(payload.get("controls_with_no_evidence", 0))
            pct = round((max(0.0, 1.0 - (without_evidence / max(total, 1))) * 100.0), 2)
            payload["effectiveness_pct"] = pct
            return payload

        control_filters = self._control_filters(org_id, business_unit_id)
        total_controls = int(self.db.execute(select(func.count(Control.id)).where(and_(*control_filters))).scalar_one())
        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(and_(*control_filters), Control.status != "archived")
            ).scalar_one()
        )
        with_verified_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .join(Control, Control.id == EvidenceControlLink.control_id)
                .where(
                    Control.organization_id == org_id,
                    Control.business_unit_id == business_unit_id,
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.review_status == "verified",
                    EvidenceItem.status != "archived",
                )
            ).scalar_one()
        )
        open_alerts = int(
            self.db.execute(
                select(func.count(func.distinct(ControlMonitoringAlert.control_id)))
                .join(Control, Control.id == ControlMonitoringAlert.control_id)
                .where(
                    Control.organization_id == org_id,
                    Control.business_unit_id == business_unit_id,
                    ControlMonitoringAlert.organization_id == org_id,
                    ControlMonitoringAlert.status == "open",
                    ControlMonitoringAlert.control_id.is_not(None),
                )
            ).scalar_one()
        )
        effectiveness_pct = round((with_verified_evidence / max(active_controls, 1)) * 100.0, 2)
        return {
            "total_controls": total_controls,
            "active_controls": active_controls,
            "controls_with_verified_evidence": with_verified_evidence,
            "controls_with_no_evidence": max(0, active_controls - with_verified_evidence),
            "controls_with_open_monitoring_alerts": open_alerts,
            "effectiveness_pct": effectiveness_pct,
        }

    def _deadline_summary(self, org_id: uuid.UUID) -> dict:
        return ComplianceDeadlineService(self.db).summary(org_id)

    def _kri_summary(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(RiskIndicator.status, func.count(RiskIndicator.id))
            .where(
                RiskIndicator.organization_id == org_id,
                RiskIndicator.is_active.is_(True),
                RiskIndicator.archived_at.is_(None),
            )
            .group_by(RiskIndicator.status)
        ).all()
        by_status = {str(k): int(v) for k, v in rows}
        total = sum(by_status.values())
        return {
            "total_active_indicators": total,
            "by_status": by_status,
        }

    @staticmethod
    def _compute_overall_score(*, framework_readiness: dict, control_effectiveness: dict) -> dict:
        # Weighted score: average of org-level framework coverage and control effectiveness.
        # This is transparent and deterministic for board quick-reference use.
        rows = framework_readiness.get("rows", []) if isinstance(framework_readiness, dict) else []
        has_framework_data = bool(rows)
        if rows:
            fw_avg = sum(float(item.get("control_coverage_pct", 0.0)) for item in rows) / len(rows)
        else:
            fw_avg = 0.0

        if "total_controls_by_status" in control_effectiveness:
            total_controls = sum(int(v) for v in control_effectiveness["total_controls_by_status"].values())
        else:
            total_controls = int(control_effectiveness.get("total_controls", 0))
        has_control_data = total_controls > 0
        control_pct = float(control_effectiveness.get("effectiveness_pct", 0.0))

        score = round((fw_avg + control_pct) / 2.0, 2)
        data_sufficient = has_framework_data or has_control_data
        basis = (
            "Average of organization-wide framework control-coverage percentage and control "
            "effectiveness percentage (share of active controls with verified evidence)."
        )
        if not data_sufficient:
            basis += " No active frameworks or controls exist yet, so this score does not yet reflect a real assessment."

        return {"score": score, "basis": basis, "data_sufficient": data_sufficient}

    def _previous_snapshot(
        self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None
    ) -> BoardScorecardSnapshot | None:
        stmt = select(BoardScorecardSnapshot).where(BoardScorecardSnapshot.organization_id == org_id)
        if business_unit_id is None:
            stmt = stmt.where(BoardScorecardSnapshot.business_unit_id.is_(None))
        else:
            stmt = stmt.where(BoardScorecardSnapshot.business_unit_id == business_unit_id)
        return self.db.execute(
            stmt.order_by(BoardScorecardSnapshot.created_at.desc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _score_change_summary(
        *,
        previous: BoardScorecardSnapshot | None,
        overall_score: float,
        framework_readiness: dict,
        controls: dict,
        posture: dict,
    ) -> dict:
        """Explains *why* the score moved since the previous snapshot for this scope, using
        only data already computed for this snapshot and stored on the previous one -- this
        never invents data, it only narrates numbers that are already present.
        """
        if previous is None:
            return {
                "previous_score": None,
                "delta": None,
                "narrative": "This is the first board scorecard snapshot on record for this scope; "
                "no prior snapshot exists for comparison.",
            }

        prev_data = previous.snapshot_data if isinstance(previous.snapshot_data, dict) else {}
        previous_score = float(previous.overall_compliance_score)
        delta = round(overall_score - previous_score, 2)

        drivers: list[str] = []

        prev_controls = prev_data.get("control_effectiveness") or {}
        prev_effectiveness = float(prev_controls.get("effectiveness_pct", 0.0))
        cur_effectiveness = float(controls.get("effectiveness_pct", 0.0))
        effectiveness_delta = round(cur_effectiveness - prev_effectiveness, 2)
        if abs(effectiveness_delta) >= 0.5:
            direction = "improved" if effectiveness_delta > 0 else "dropped"
            drivers.append(f"control effectiveness {direction} {abs(effectiveness_delta)}pts")

        prev_fw = prev_data.get("framework_readiness") or {}
        prev_fw_rows = prev_fw.get("rows", []) if isinstance(prev_fw, dict) else []
        prev_fw_avg = (
            sum(float(item.get("control_coverage_pct", 0.0)) for item in prev_fw_rows) / len(prev_fw_rows)
            if prev_fw_rows
            else 0.0
        )
        cur_fw_rows = framework_readiness.get("rows", []) if isinstance(framework_readiness, dict) else []
        cur_fw_avg = (
            sum(float(item.get("control_coverage_pct", 0.0)) for item in cur_fw_rows) / len(cur_fw_rows)
            if cur_fw_rows
            else 0.0
        )
        coverage_delta = round(cur_fw_avg - prev_fw_avg, 2)
        if abs(coverage_delta) >= 0.5:
            direction = "improved" if coverage_delta > 0 else "dropped"
            drivers.append(f"framework coverage {direction} {abs(coverage_delta)}pts")

        prev_posture = prev_data.get("posture_summary") or {}
        prev_risk_severity = (prev_posture.get("risks") or {}).get("by_severity", {})
        prev_critical_high = int(prev_risk_severity.get("critical", 0)) + int(prev_risk_severity.get("high", 0))
        cur_risk_severity = (posture.get("risks") or {}).get("by_severity", {})
        cur_critical_high = int(cur_risk_severity.get("critical", 0)) + int(cur_risk_severity.get("high", 0))
        risk_delta = cur_critical_high - prev_critical_high
        if risk_delta != 0:
            direction = "more" if risk_delta > 0 else "fewer"
            drivers.append(f"{abs(risk_delta)} {direction} open critical/high risks")

        previous_at = previous.created_at.isoformat() if previous.created_at else "an earlier snapshot"
        if delta == 0 and not drivers:
            narrative = f"Score is unchanged at {overall_score} since the previous snapshot on {previous_at}."
        else:
            direction = "improved" if delta >= 0 else "dropped"
            if drivers:
                narrative = (
                    f"Score {direction} {abs(delta)}pts since {previous_at} "
                    f"({previous_score} -> {overall_score}), driven by: " + "; ".join(drivers) + "."
                )
            else:
                narrative = (
                    f"Score {direction} {abs(delta)}pts since {previous_at} "
                    f"({previous_score} -> {overall_score}); no single tracked driver crossed the reporting threshold."
                )

        return {
            "previous_score": previous_score,
            "previous_snapshot_id": str(previous.id),
            "previous_calculated_at": previous_at,
            "delta": delta,
            "narrative": narrative,
        }

    def generate_snapshot(
        self,
        org_id: uuid.UUID,
        generated_by: uuid.UUID,
        business_unit_id: uuid.UUID | None = None,
        snapshot_label: str | None = None,
    ) -> BoardScorecardSnapshot:
        bu = self._require_bu(org_id, business_unit_id)

        previous_snapshot = self._previous_snapshot(org_id, business_unit_id)

        posture = self._build_posture_summary(org_id, business_unit_id)
        framework = self._framework_readiness(org_id, business_unit_id)
        top_risks = self._top_risks(org_id, business_unit_id)
        appetite = self._risk_appetite_breaches(org_id, business_unit_id)
        controls = self._control_effectiveness_summary(org_id, business_unit_id)
        deadlines = self._deadline_summary(org_id)
        kri = self._kri_summary(org_id)

        score_result = self._compute_overall_score(
            framework_readiness=framework,
            control_effectiveness=controls,
        )
        overall_score = score_result["score"]
        score_change = self._score_change_summary(
            previous=previous_snapshot,
            overall_score=overall_score,
            framework_readiness=framework,
            controls=controls,
            posture=posture,
        )

        snapshot_data = {
            "scope": {
                "organization_id": str(org_id),
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
                "business_unit_name": bu.name if bu else None,
            },
            "posture_summary": posture,
            "framework_readiness": framework,
            "top_risks": top_risks,
            "risk_appetite_breaches": appetite,
            "control_effectiveness": controls,
            "deadlines": deadlines,
            "kri_summary": kri,
            "overall_compliance_score": overall_score,
            "overall_compliance_score_basis": score_result["basis"],
            "overall_compliance_score_data_sufficient": score_result["data_sufficient"],
            "score_change": score_change,
            "generated_at": self._now().isoformat(),
        }

        row = BoardScorecardSnapshot(
            organization_id=org_id,
            business_unit_id=business_unit_id,
            generated_by=generated_by,
            snapshot_label=snapshot_label,
            overall_compliance_score=Decimal(str(overall_score)),
            snapshot_data=snapshot_data,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="board_scorecard.generated",
            entity_type="board_scorecard_snapshot",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=generated_by,
            metadata_json={
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
                "snapshot_label": snapshot_label,
                "overall_compliance_score": overall_score,
                "overall_compliance_score_data_sufficient": score_result["data_sufficient"],
                "score_change_delta": score_change["delta"],
            },
        )
        return row

    def list_snapshots(
        self,
        org_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        business_unit_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[BoardScorecardSnapshot], int]:
        stmt = select(BoardScorecardSnapshot).where(BoardScorecardSnapshot.organization_id == org_id)

        if business_unit_id is not None:
            stmt = stmt.where(BoardScorecardSnapshot.business_unit_id == business_unit_id)
        if date_from is not None:
            start_dt = datetime.combine(date_from, time.min, tzinfo=UTC)
            stmt = stmt.where(BoardScorecardSnapshot.created_at >= start_dt)
        if date_to is not None:
            end_dt = datetime.combine(date_to, time.max, tzinfo=UTC)
            stmt = stmt.where(BoardScorecardSnapshot.created_at <= end_dt)

        total = int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

        rows = self.db.execute(
            stmt.order_by(BoardScorecardSnapshot.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return rows, total

    def get_snapshot(self, org_id: uuid.UUID, snapshot_id: uuid.UUID) -> BoardScorecardSnapshot:
        row = self.db.execute(
            select(BoardScorecardSnapshot).where(
                BoardScorecardSnapshot.id == snapshot_id,
                BoardScorecardSnapshot.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board scorecard snapshot not found")
        return row

    # Existing report-generation flow kept for compatibility with prior report endpoints.
    def generate_board_scorecard(self, org_id: uuid.UUID, created_by: uuid.UUID) -> ComplianceReport:
        payload = BoardScorecardBuilder().build(org_id, self.db)
        report_service = ReportService(self.db)

        sections = [
            report_service._section(
                key="board_scorecard",
                title="Board Scorecard",
                body=payload["narrative"],
                data=payload,
                provenance={
                    "source_models": [
                        "score_snapshots",
                        "risks",
                        "issues",
                        "compliance_certifications",
                        "compliance_deadlines",
                        "organization_obligation_states",
                    ]
                },
                sort_order=1,
            ),
            report_service._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": report_service.now().isoformat(),
            "generated_by_user_id": str(created_by),
            "organization_id": str(org_id),
            "report_type": "board_scorecard",
        }

        report, _ = report_service.persist_report(
            organization_id=org_id,
            report_type="board_scorecard",
            title="Board Scorecard",
            description="Single-page executive compliance health report for board presentation.",
            framework_id=None,
            period_start=None,
            period_end=None,
            generated_by_user_id=created_by,
            sections=sections,
            inputs_summary=payload,
            provenance=provenance,
        )
        return report
