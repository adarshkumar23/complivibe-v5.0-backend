from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.compliance.services.technical_control_service import TechnicalControlResultService
from app.services.subsystem_ingest_key_service import SubsystemIngestKeyService
from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.technical_control_agent import TechnicalControlAgent
from app.models.technical_control_rule import TechnicalControlRule
from app.models.user import User
from app.schemas.issue import IssueCreate
from app.schemas.technical_control import TechnicalControlResultIngestRequest


class SecurityIngestBaseService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return SubsystemIngestKeyService(self.db).require_org_by_key(raw_key, "security")

    @staticmethod
    def _rule_severity(value: str) -> str:
        if value == "critical":
            return "critical"
        if value == "low":
            return "info"
        return "warning"

    def _get_or_create_agent(self, org_id: uuid.UUID, source: str) -> TechnicalControlAgent:
        name = f"security_ingest_{source}"
        existing = self.db.execute(
            select(TechnicalControlAgent).where(
                TechnicalControlAgent.organization_id == org_id,
                TechnicalControlAgent.name == name,
                TechnicalControlAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        token_hash = hashlib.sha256(f"{org_id}:{source}".encode("utf-8")).hexdigest()
        agent = TechnicalControlAgent(
            organization_id=org_id,
            name=name,
            description=f"Synthetic agent for {source} ingest",
            token_hash=token_hash,
            is_active=True,
            created_by=None,
            created_at=self.utcnow(),
            deleted_at=None,
        )
        self.db.add(agent)
        self.db.flush()
        return agent

    def _get_or_create_security_control(self, org_id: uuid.UUID, source: str) -> Control:
        code = f"SEC_{source.upper()}"
        existing = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.control_code == code,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        control = Control(
            organization_id=org_id,
            obligation_id=None,
            control_code=code,
            title=f"External Security Findings ({source})",
            description=f"Imported findings from {source} integration",
            control_type="technical",
            status="in_progress",
            criticality="high",
            owner_user_id=None,
            testing_procedure="Automated ingest from external security scanner",
            implementation_notes=None,
            source="system",
            created_by_user_id=None,
            suggestion_source_id=None,
        )
        self.db.add(control)
        self.db.flush()
        return control

    def _get_or_create_rule(
        self,
        org_id: uuid.UUID,
        source: str,
        check_key: str,
        check_type: str,
        severity: str,
    ) -> TechnicalControlRule:
        rule_name = f"{source}:{check_key}"[:255]
        existing = self.db.execute(
            select(TechnicalControlRule).where(
                TechnicalControlRule.organization_id == org_id,
                TechnicalControlRule.name == rule_name,
                TechnicalControlRule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        control = self._get_or_create_security_control(org_id, source)
        rule = TechnicalControlRule(
            organization_id=org_id,
            control_id=control.id,
            name=rule_name,
            description=f"Imported {source} finding rule for {check_key}",
            target_resource_type="generic",
            expected_config_key="result",
            expected_config_value="pass",
            evaluation_operator="equals",
            severity=self._rule_severity(severity),
            is_active=True,
            created_by=None,
            deleted_at=None,
        )
        self.db.add(rule)
        self.db.flush()

        definition = self.db.execute(
            select(ControlTestDefinition).where(
                ControlTestDefinition.organization_id == org_id,
                ControlTestDefinition.control_id == control.id,
                ControlTestDefinition.check_key == "control_status_implemented",
                ControlTestDefinition.status != "archived",
            )
        ).scalars().first()
        if definition is None:
            definition = ControlTestDefinition(
                organization_id=org_id,
                control_id=control.id,
                name=f"External scanner checks ({source})",
                description=f"Auto-generated control tests for {source} findings",
                test_type="internal_metadata_check",
                check_key="control_status_implemented",
                status="active",
                cadence="none",
                next_due_at=None,
                last_run_at=None,
                owner_user_id=None,
                created_by_user_id=None,
                metadata_json={"source": source},
            )
            self.db.add(definition)
            self.db.flush()

        return rule

    def create_control_test_result(
        self,
        org_id: uuid.UUID,
        check_key: str,
        check_type: str,
        result: str,
        severity: str,
        detail: dict,
        source: str,
    ) -> None:
        agent = self._get_or_create_agent(org_id, source)
        rule = self._get_or_create_rule(org_id, source, check_key, check_type, severity)

        payload = TechnicalControlResultIngestRequest(
            rule_id=rule.id,
            resource_identifier=str(detail.get("target") or detail.get("resource_id") or detail.get("artifact") or "unknown"),
            actual_config_key="result",
            actual_config_value=result,
            raw_payload=detail,
        )
        TechnicalControlResultService(self.db).ingest_result(agent, rule.id, payload)

    def _find_issue_owner(self, org_id: uuid.UUID) -> User:
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
                # "Oldest active member" must resolve to a person. The system account
                # predates nobody, but it must never be handed ownership of an issue a
                # human is expected to work.
                User.is_system_account.is_(False),
            )
            .order_by(User.created_at.asc())
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No active member available for issue ownership")
        return row

    def create_issue(self, org_id: uuid.UUID, title: str, description: str, severity: str) -> None:
        owner = self._find_issue_owner(org_id)
        IssueService(self.db).create_issue(
            org_id=org_id,
            data=IssueCreate(
                title=title[:255],
                description=description,
                issue_type="security_incident",
                severity=severity,
                source_type="external_report",
                owner_id=owner.id,
                assigned_to=None,
            ),
            created_by=owner.id,
        )

    def resolve_framework_refs(self, framework_refs: list[dict]) -> list[dict]:
        resolved: list[dict] = []
        for item in framework_refs:
            framework_name = str(item.get("framework") or "").strip()
            refs = item.get("refs") if isinstance(item.get("refs"), list) else []
            framework = self.db.execute(select(Framework).where(Framework.name == framework_name)).scalar_one_or_none()
            obligation_ids: list[str] = []
            if framework is not None and refs:
                obligations = self.db.execute(
                    select(Obligation).where(
                        Obligation.framework_id == framework.id,
                        Obligation.reference_code.in_([str(ref) for ref in refs]),
                    )
                ).scalars().all()
                obligation_ids = [str(row.id) for row in obligations]

            resolved.append(
                {
                    "framework": framework_name,
                    "framework_id": str(framework.id) if framework is not None else None,
                    "refs": [str(ref) for ref in refs],
                    "matched_obligation_ids": obligation_ids,
                }
            )
        return resolved
