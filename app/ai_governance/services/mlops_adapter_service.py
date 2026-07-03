from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, func, literal, select
from sqlalchemy.orm import Session

from app.compliance.services.risk_scoring_service import RiskScoringService
from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.mlflow_connection import MLflowConnection
from app.models.mlflow_drift_event import MLflowDriftEvent
from app.models.mlflow_model_registration import MLflowModelRegistration
from app.models.risk import Risk
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService


class MLopsAdapterService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def mask_token(token: str) -> str:
        return f"{token[:8]}..." if token else ""

    @staticmethod
    def generate_ingest_token() -> str:
        return secrets.token_urlsafe(48)

    def require_connection(self, org_id: uuid.UUID, connection_id: uuid.UUID) -> MLflowConnection:
        row = self.db.execute(
            select(MLflowConnection).where(
                MLflowConnection.id == connection_id,
                MLflowConnection.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MLflow connection not found")
        return row

    def require_registration(self, org_id: uuid.UUID, registration_id: uuid.UUID) -> MLflowModelRegistration:
        row = self.db.execute(
            select(MLflowModelRegistration).where(
                MLflowModelRegistration.id == registration_id,
                MLflowModelRegistration.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model registration not found")
        return row

    def require_drift(self, org_id: uuid.UUID, drift_id: uuid.UUID) -> MLflowDriftEvent:
        row = self.db.execute(
            select(MLflowDriftEvent).where(
                MLflowDriftEvent.id == drift_id,
                MLflowDriftEvent.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drift event not found")
        return row

    def get_connection_by_token(self, ingest_token: str) -> MLflowConnection:
        row = self.db.execute(
            select(MLflowConnection).where(MLflowConnection.ingest_token == ingest_token)
        ).scalar_one_or_none()
        if row is None or not row.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive ingest token")
        return row

    def create_connection(
        self,
        *,
        org_id: uuid.UUID,
        connection_name: str,
        tracking_server_url: str | None,
        created_by: uuid.UUID,
    ) -> tuple[MLflowConnection, str]:
        existing = self.db.execute(
            select(MLflowConnection).where(MLflowConnection.organization_id == org_id)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MLflow connection already exists for org")

        now = self.utcnow()
        token = self.generate_ingest_token()
        row = MLflowConnection(
            organization_id=org_id,
            connection_name=connection_name,
            ingest_token=token,
            tracking_server_url=tracking_server_url,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.connection_created",
            entity_type="mlflow_connection",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=row.id,
            metadata_json={
                "connection_name": connection_name,
                "token_masked": self.mask_token(token),
            },
        )
        return row, token

    def rotate_connection_token(self, *, org_id: uuid.UUID, rotated_by: uuid.UUID) -> tuple[MLflowConnection, str]:
        row = self.db.execute(
            select(MLflowConnection).where(
                MLflowConnection.organization_id == org_id,
                MLflowConnection.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MLflow connection not found")

        token = self.generate_ingest_token()
        row.ingest_token = token
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.connection_token_rotated",
            entity_type="mlflow_connection",
            organization_id=org_id,
            actor_user_id=rotated_by,
            entity_id=row.id,
            metadata_json={"token_masked": self.mask_token(token)},
        )
        return row, token

    def deactivate_connection(self, *, org_id: uuid.UUID, user_id: uuid.UUID) -> MLflowConnection:
        row = self.db.execute(
            select(MLflowConnection).where(
                MLflowConnection.organization_id == org_id,
                MLflowConnection.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MLflow connection not found")

        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.connection_deactivated",
            entity_type="mlflow_connection",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=row.id,
        )
        return row

    def get_connection(self, org_id: uuid.UUID) -> MLflowConnection | None:
        return self.db.execute(
            select(MLflowConnection).where(MLflowConnection.organization_id == org_id)
        ).scalar_one_or_none()

    def _auto_link_ai_system(self, org_id: uuid.UUID, model_name: str) -> tuple[uuid.UUID | None, bool]:
        name = model_name.strip().lower()
        systems = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalars().all()

        matches = [
            s for s in systems
            if s.model_name and (name in s.model_name.lower() or s.model_name.lower() in name)
        ]
        if len(matches) == 1:
            return matches[0].id, True
        return None, False

    def _has_completed_assessment(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> bool:
        found = self.db.execute(
            select(AISystemRiskAssessment.id).where(
                AISystemRiskAssessment.organization_id == org_id,
                AISystemRiskAssessment.ai_system_id == ai_system_id,
                AISystemRiskAssessment.status == "completed",
                AISystemRiskAssessment.archived_at.is_(None),
            )
        ).first()
        return found is not None

    def _create_auto_risk(
        self,
        *,
        org_id: uuid.UUID,
        title: str,
        description: str,
        actor_user_id: uuid.UUID | None,
        trigger: str,
        metadata_json: dict | None = None,
    ) -> Risk:
        # Auto-created by the adapter with system actor context (created_by_user_id nullable in Risk model).
        # Uses existing risk scoring logic to avoid parallel bespoke risk behavior.
        merged_metadata = dict(metadata_json or {})
        merged_metadata.setdefault("auto_created_by", "complivibe_mlops_adapter")
        merged_metadata.setdefault("trigger", trigger)
        risk = Risk(
            organization_id=org_id,
            title=title,
            description=description,
            category="ai_governance",
            status="identified",
            likelihood=4,
            impact=4,
            treatment_strategy="mitigate",
            created_by_user_id=actor_user_id,
            metadata_json=merged_metadata,
        )
        settings = RiskScoringService.get_or_create_org_settings(org_id, self.db)
        risk.inherent_score = RiskScoringService.compute_score(risk, settings)
        risk.severity = RiskService.score_to_severity(risk.inherent_score)

        self.db.add(risk)
        self.db.flush()
        RiskService(self.db).check_appetite_breach(organization_id=org_id, risk=risk, actor_user_id=actor_user_id)
        return risk

    @staticmethod
    def _ensure_registered_at(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def ingest_model_event(
        self,
        *,
        connection_id: uuid.UUID,
        org_id: uuid.UUID,
        event_type: str,
        model_name: str,
        model_version: str,
        ai_system_id: uuid.UUID | None = None,
        stage: str,
        run_id: str | None = None,
        metrics_json: dict | None = None,
        tags_json: dict | None = None,
        registered_at: datetime | None = None,
    ) -> MLflowModelRegistration:
        if ai_system_id is not None:
            auto_linked = False
        else:
            ai_system_id, auto_linked = self._auto_link_ai_system(org_id, model_name)
        row = MLflowModelRegistration(
            organization_id=org_id,
            mlflow_connection_id=connection_id,
            ai_system_id=ai_system_id,
            model_name=model_name,
            model_version=model_version,
            stage=stage,
            run_id=run_id,
            metrics_json=metrics_json,
            tags_json=tags_json,
            event_type=event_type,
            registered_at=self._ensure_registered_at(registered_at),
            compliance_status="pending_review",
            auto_linked=auto_linked,
            created_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.model_event_ingested",
            entity_type="mlflow_model_registration",
            organization_id=org_id,
            entity_id=row.id,
            metadata_json={
                "event_type": event_type,
                "model_name": model_name,
                "model_version": model_version,
                "auto_linked": auto_linked,
            },
        )

        if event_type == "model.deployed" and ai_system_id and not self._has_completed_assessment(org_id, ai_system_id):
            risk = self._create_auto_risk(
                org_id=org_id,
                title=f"AI Model deployed without compliance review: {model_name} v{model_version}",
                description=(
                    "Model deployment event was ingested from MLOps before a completed AI risk assessment was found."
                ),
                actor_user_id=None,
                trigger="model_deployed_without_review",
                metadata_json={
                    "model_name": model_name,
                    "model_version": model_version,
                    "event_type": event_type,
                },
            )
            row.auto_risk_created = True
            row.linked_risk_id = risk.id
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="mlops.auto_risk_created",
                entity_type="risk",
                organization_id=org_id,
                entity_id=risk.id,
                metadata_json={"model_registration_id": str(row.id)},
            )

        return row

    @staticmethod
    def _compute_severity(
        *,
        drift_metric: str,
        drift_value: Decimal,
        drift_threshold: Decimal | None,
    ) -> str:
        metric = drift_metric.strip().lower()

        if drift_threshold is not None and drift_threshold > 0:
            over = (drift_value - drift_threshold) / drift_threshold
            if over < Decimal("0.20"):
                return "low"
            if over < Decimal("0.50"):
                return "medium"
            if over <= Decimal("1.00"):
                return "high"
            return "critical"

        if metric == "psi":
            if drift_value > Decimal("0.2"):
                return "high"
            if drift_value > Decimal("0.1"):
                return "medium"
            return "low"

        if metric in {"accuracy_drop", "accuracy"}:
            if drift_value > Decimal("0.20"):
                return "critical"
            if drift_value > Decimal("0.10"):
                return "high"
            if drift_value > Decimal("0.05"):
                return "medium"
            return "low"

        if metric == "kl_divergence":
            if drift_value > Decimal("0.5"):
                return "high"
            if drift_value > Decimal("0.1"):
                return "medium"
            return "low"

        if drift_value > Decimal("0.5"):
            return "high"
        if drift_value > Decimal("0.1"):
            return "medium"
        return "low"

    def ingest_drift_event(
        self,
        *,
        connection_id: uuid.UUID,
        org_id: uuid.UUID,
        model_name: str,
        model_version: str | None,
        ai_system_id: uuid.UUID | None = None,
        drift_metric: str,
        drift_value: Decimal,
        drift_threshold: Decimal | None,
        drift_context_json: dict | None,
        detected_at: datetime | None,
    ) -> MLflowDriftEvent:
        if ai_system_id is None:
            ai_system_id, _ = self._auto_link_ai_system(org_id, model_name)

        reg_stmt = select(MLflowModelRegistration).where(
            MLflowModelRegistration.organization_id == org_id,
            MLflowModelRegistration.model_name == model_name,
        )
        if model_version:
            reg_stmt = reg_stmt.where(MLflowModelRegistration.model_version == model_version)
        reg_stmt = reg_stmt.order_by(MLflowModelRegistration.registered_at.desc())
        linked_registration = self.db.execute(reg_stmt).scalars().first()

        severity = self._compute_severity(
            drift_metric=drift_metric,
            drift_value=drift_value,
            drift_threshold=drift_threshold,
        )

        row = MLflowDriftEvent(
            organization_id=org_id,
            mlflow_connection_id=connection_id,
            ai_system_id=ai_system_id,
            mlflow_model_registration_id=linked_registration.id if linked_registration else None,
            model_name=model_name,
            model_version=model_version,
            drift_metric=drift_metric,
            drift_value=drift_value,
            drift_threshold=drift_threshold,
            severity=severity,
            drift_context_json=drift_context_json,
            auto_risk_created=False,
            linked_risk_id=None,
            detected_at=self._ensure_registered_at(detected_at),
            created_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.drift_event_ingested",
            entity_type="mlflow_drift_event",
            organization_id=org_id,
            entity_id=row.id,
            metadata_json={
                "model_name": model_name,
                "model_version": model_version,
                "drift_metric": drift_metric,
                "severity": severity,
            },
        )

        if severity in {"high", "critical"} and ai_system_id:
            risk = self._create_auto_risk(
                org_id=org_id,
                title=f"Model Drift Detected: {model_name} - {drift_metric} = {drift_value}",
                description=(
                    "High-severity model drift detected from MLOps ingest stream. Immediate review is recommended."
                ),
                actor_user_id=None,
                trigger="drift_threshold_exceeded",
                metadata_json={
                    "model_name": model_name,
                    "model_version": model_version,
                    "drift_metric": drift_metric,
                    "drift_value": str(drift_value),
                },
            )
            row.auto_risk_created = True
            row.linked_risk_id = risk.id
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="mlops.auto_risk_created",
                entity_type="risk",
                organization_id=org_id,
                entity_id=risk.id,
                metadata_json={"drift_event_id": str(row.id)},
            )

        return row

    def link_model_to_ai_system(
        self,
        *,
        org_id: uuid.UUID,
        registration_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        linked_by: uuid.UUID,
    ) -> MLflowModelRegistration:
        reg = self.require_registration(org_id, registration_id)
        system = self.db.execute(
            select(AISystem).where(
                AISystem.id == ai_system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if system is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")

        reg.ai_system_id = ai_system_id
        reg.auto_linked = False
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.model_manually_linked",
            entity_type="mlflow_model_registration",
            organization_id=org_id,
            actor_user_id=linked_by,
            entity_id=reg.id,
            metadata_json={"ai_system_id": str(ai_system_id)},
        )
        return reg

    def update_compliance_status(
        self,
        *,
        org_id: uuid.UUID,
        registration_id: uuid.UUID,
        new_status: str,
        updated_by: uuid.UUID,
    ) -> MLflowModelRegistration:
        reg = self.require_registration(org_id, registration_id)
        reg.compliance_status = new_status
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="mlops.compliance_status_updated",
            entity_type="mlflow_model_registration",
            organization_id=org_id,
            actor_user_id=updated_by,
            entity_id=reg.id,
            metadata_json={"compliance_status": new_status},
        )
        return reg

    def list_model_registrations(
        self,
        *,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID | None,
        compliance_status: str | None,
        model_name: str | None,
        stage: str | None,
        offset: int,
        limit: int,
    ) -> list[MLflowModelRegistration]:
        stmt = select(MLflowModelRegistration).where(MLflowModelRegistration.organization_id == org_id)
        if ai_system_id is not None:
            stmt = stmt.where(MLflowModelRegistration.ai_system_id == ai_system_id)
        if compliance_status:
            stmt = stmt.where(MLflowModelRegistration.compliance_status == compliance_status)
        if model_name:
            stmt = stmt.where(MLflowModelRegistration.model_name.ilike(f"%{model_name.strip()}%"))
        if stage:
            stmt = stmt.where(MLflowModelRegistration.stage == stage)
        stmt = stmt.order_by(MLflowModelRegistration.registered_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def list_drift_events(
        self,
        *,
        org_id: uuid.UUID,
        severity: str | None,
        model_name: str | None,
        ai_system_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> list[MLflowDriftEvent]:
        stmt = select(MLflowDriftEvent).where(MLflowDriftEvent.organization_id == org_id)
        if severity:
            stmt = stmt.where(MLflowDriftEvent.severity == severity)
        if model_name:
            stmt = stmt.where(MLflowDriftEvent.model_name.ilike(f"%{model_name.strip()}%"))
        if ai_system_id is not None:
            stmt = stmt.where(MLflowDriftEvent.ai_system_id == ai_system_id)

        sev_order = case(
            (MLflowDriftEvent.severity == "critical", 0),
            (MLflowDriftEvent.severity == "high", 1),
            (MLflowDriftEvent.severity == "medium", 2),
            else_=3,
        )
        stmt = stmt.order_by(sev_order.asc(), MLflowDriftEvent.detected_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def get_mlops_coverage(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> dict:
        system = self.db.execute(
            select(AISystem).where(
                AISystem.id == ai_system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if system is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")

        active_conn = self.db.execute(
            select(MLflowConnection).where(
                MLflowConnection.organization_id == org_id,
                MLflowConnection.is_active.is_(True),
            )
        ).scalars().first()

        latest_reg = self.db.execute(
            select(MLflowModelRegistration)
            .where(
                MLflowModelRegistration.organization_id == org_id,
                MLflowModelRegistration.ai_system_id == ai_system_id,
            )
            .order_by(MLflowModelRegistration.registered_at.desc())
        ).scalars().first()

        latest_deploy = self.db.execute(
            select(MLflowModelRegistration)
            .where(
                MLflowModelRegistration.organization_id == org_id,
                MLflowModelRegistration.ai_system_id == ai_system_id,
                MLflowModelRegistration.event_type == "model.deployed",
            )
            .order_by(MLflowModelRegistration.registered_at.desc())
        ).scalars().first()

        now = self.utcnow()
        days_since_last = None
        if latest_deploy is not None:
            deployed_at = latest_deploy.registered_at
            if deployed_at.tzinfo is None:
                deployed_at = deployed_at.replace(tzinfo=UTC)
            days_since_last = max(0, (now - deployed_at).days)

        active_drift_events = self.db.execute(
            select(MLflowDriftEvent).where(
                MLflowDriftEvent.organization_id == org_id,
                MLflowDriftEvent.ai_system_id == ai_system_id,
                MLflowDriftEvent.severity.in_(["high", "critical"]),
                MLflowDriftEvent.detected_at >= (now - timedelta(days=30)),
            )
        ).scalars().all()
        active_drift_alerts = len(active_drift_events)

        has_risk_assessment = self._has_completed_assessment(org_id, ai_system_id)

        pending = self.db.execute(
            select(func.count(MLflowModelRegistration.id)).where(
                MLflowModelRegistration.organization_id == org_id,
                MLflowModelRegistration.ai_system_id == ai_system_id,
                MLflowModelRegistration.compliance_status == "pending_review",
            )
        ).scalar_one()
        pending_review = int(pending) > 0

        has_critical_drift = any(item.severity == "critical" for item in active_drift_events)
        deployed_without_assessment = latest_deploy is not None and not has_risk_assessment

        if has_critical_drift or deployed_without_assessment:
            health = "at_risk"
        elif has_risk_assessment and active_drift_alerts == 0 and not pending_review:
            health = "good"
        else:
            health = "needs_attention"

        is_mlflow_connected = active_conn is not None and latest_reg is not None

        return {
            "ai_system_id": str(ai_system_id),
            "is_mlflow_connected": is_mlflow_connected,
            "latest_model_version": latest_reg.model_version if latest_reg else None,
            "latest_deployment_at": latest_deploy.registered_at.isoformat() if latest_deploy else None,
            "days_since_last_deployment": days_since_last,
            "active_drift_alerts": active_drift_alerts,
            "has_risk_assessment": has_risk_assessment,
            "pending_compliance_review": pending_review,
            "overall_governance_health": health,
        }
