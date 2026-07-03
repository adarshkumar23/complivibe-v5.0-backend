import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.technical_control_agent import TechnicalControlAgent
from app.models.technical_control_result import TechnicalControlResult
from app.models.technical_control_rule import TechnicalControlRule
from app.schemas.technical_control import (
    TechnicalControlAgentCreate,
    TechnicalControlResultFilters,
    TechnicalControlResultIngestRequest,
    TechnicalControlRuleCreate,
    TechnicalControlRuleUpdate,
)
from app.services.audit_service import AuditService
from app.services.control_service import ControlService


class TechnicalControlEvaluator:
    def evaluate(self, rule: TechnicalControlRule, actual_value: str | None) -> tuple[bool, str | None]:
        operator = rule.evaluation_operator
        expected = (rule.expected_config_value or "").strip()

        if operator == "exists":
            passed = actual_value is not None
            return (passed, None if passed else "key not found in agent payload")

        if operator == "not_exists":
            passed = actual_value is None
            return (passed, None if passed else "key exists in agent payload")

        if actual_value is None:
            return False, "key not found in agent payload"

        actual = actual_value.strip()
        expected_l = expected.lower()
        actual_l = actual.lower()

        if operator == "equals":
            passed = actual_l == expected_l
            return (passed, None if passed else f"expected '{expected}' but got '{actual}'")

        if operator == "not_equals":
            passed = actual_l != expected_l
            return (passed, None if passed else f"expected value different than '{expected}'")

        if operator == "contains":
            passed = expected_l in actual_l
            return (passed, None if passed else f"expected '{expected}' to be contained in '{actual}'")

        if operator == "not_contains":
            passed = expected_l not in actual_l
            return (passed, None if passed else f"expected '{expected}' to not be contained in '{actual}'")

        if operator in {"gte", "lte"}:
            try:
                actual_num = float(actual)
                expected_num = float(expected)
            except ValueError:
                return False, "could not parse value as number"

            if operator == "gte":
                passed = actual_num >= expected_num
                return (passed, None if passed else f"expected >= {expected_num} but got {actual_num}")
            passed = actual_num <= expected_num
            return (passed, None if passed else f"expected <= {expected_num} but got {actual_num}")

        if operator == "is_true":
            passed = actual_l in {"true", "1", "yes", "enabled"}
            return (passed, None if passed else f"expected truthy value but got '{actual}'")

        if operator == "is_false":
            passed = actual_l in {"false", "0", "no", "disabled"}
            return (passed, None if passed else f"expected falsy value but got '{actual}'")

        return False, f"unsupported operator: {operator}"


class TechnicalControlAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def register_agent(
        self,
        org_id: uuid.UUID,
        payload: TechnicalControlAgentCreate,
        created_by: uuid.UUID,
    ) -> tuple[TechnicalControlAgent, str]:
        duplicate = self.db.execute(
            select(TechnicalControlAgent.id).where(
                TechnicalControlAgent.organization_id == org_id,
                TechnicalControlAgent.name == payload.name,
                TechnicalControlAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent name already exists")

        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        agent = TechnicalControlAgent(
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
            action="technical_control.agent_registered",
            entity_type="technical_control_agent",
            entity_id=agent.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": agent.name, "is_active": agent.is_active},
            metadata_json={"source": "api"},
        )
        return agent, token

    def list_agents(self, org_id: uuid.UUID) -> list[TechnicalControlAgent]:
        return self.db.execute(
            select(TechnicalControlAgent)
            .where(
                TechnicalControlAgent.organization_id == org_id,
                TechnicalControlAgent.deleted_at.is_(None),
                TechnicalControlAgent.is_active.is_(True),
            )
            .order_by(TechnicalControlAgent.created_at.desc())
        ).scalars().all()

    def get_agent(self, org_id: uuid.UUID, agent_id: uuid.UUID) -> TechnicalControlAgent:
        row = self.db.execute(
            select(TechnicalControlAgent).where(
                TechnicalControlAgent.organization_id == org_id,
                TechnicalControlAgent.id == agent_id,
                TechnicalControlAgent.deleted_at.is_(None),
                TechnicalControlAgent.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technical control agent not found")
        return row

    def deregister_agent(self, org_id: uuid.UUID, agent_id: uuid.UUID, actor_id: uuid.UUID) -> TechnicalControlAgent:
        row = self.get_agent(org_id, agent_id)
        row.is_active = False
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="technical_control.agent_deregistered",
            entity_type="technical_control_agent",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"is_active": True},
            after_json={"is_active": False},
            metadata_json={"source": "api"},
        )
        return row


class TechnicalControlRuleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_control_in_org(self, org_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.id == control_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def get_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID) -> TechnicalControlRule:
        row = self.db.execute(
            select(TechnicalControlRule).where(
                TechnicalControlRule.organization_id == org_id,
                TechnicalControlRule.id == rule_id,
                TechnicalControlRule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technical control rule not found")
        return row

    def create_rule(self, org_id: uuid.UUID, payload: TechnicalControlRuleCreate, created_by: uuid.UUID) -> TechnicalControlRule:
        self._require_control_in_org(org_id, payload.control_id)

        row = TechnicalControlRule(
            organization_id=org_id,
            control_id=payload.control_id,
            name=payload.name,
            description=payload.description,
            target_resource_type=payload.target_resource_type,
            expected_config_key=payload.expected_config_key,
            expected_config_value=payload.expected_config_value,
            evaluation_operator=payload.evaluation_operator,
            severity=payload.severity,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="technical_control.rule_created",
            entity_type="technical_control_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "control_id": str(row.control_id),
                "name": row.name,
                "target_resource_type": row.target_resource_type,
                "evaluation_operator": row.evaluation_operator,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_rules(
        self,
        org_id: uuid.UUID,
        *,
        control_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        resource_type: str | None = None,
    ) -> list[TechnicalControlRule]:
        stmt = select(TechnicalControlRule).where(
            TechnicalControlRule.organization_id == org_id,
            TechnicalControlRule.deleted_at.is_(None),
        )
        if control_id is not None:
            stmt = stmt.where(TechnicalControlRule.control_id == control_id)
        if is_active is not None:
            stmt = stmt.where(TechnicalControlRule.is_active.is_(is_active))
        if resource_type is not None:
            stmt = stmt.where(TechnicalControlRule.target_resource_type == resource_type)
        return self.db.execute(stmt.order_by(TechnicalControlRule.created_at.desc())).scalars().all()

    def update_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID, payload: TechnicalControlRuleUpdate, actor_id: uuid.UUID) -> TechnicalControlRule:
        row = self.get_rule(org_id, rule_id)
        updates = payload.model_dump(exclude_unset=True)

        if "control_id" in updates:
            self._require_control_in_org(org_id, updates["control_id"])

        before = {
            "name": row.name,
            "description": row.description,
            "target_resource_type": row.target_resource_type,
            "expected_config_key": row.expected_config_key,
            "expected_config_value": row.expected_config_value,
            "evaluation_operator": row.evaluation_operator,
            "severity": row.severity,
            "is_active": row.is_active,
        }

        for field, value in updates.items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="technical_control.rule_updated",
            entity_type="technical_control_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "name": row.name,
                "description": row.description,
                "target_resource_type": row.target_resource_type,
                "expected_config_key": row.expected_config_key,
                "expected_config_value": row.expected_config_value,
                "evaluation_operator": row.evaluation_operator,
                "severity": row.severity,
                "is_active": row.is_active,
            },
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_rule(self, org_id: uuid.UUID, rule_id: uuid.UUID, actor_id: uuid.UUID) -> TechnicalControlRule:
        row = self.get_rule(org_id, rule_id)
        row.is_active = False
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="technical_control.rule_deactivated",
            entity_type="technical_control_rule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"is_active": True, "deleted_at": None},
            after_json={"is_active": False, "deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def get_rule_results(self, org_id: uuid.UUID, rule_id: uuid.UUID, limit: int = 50) -> list[TechnicalControlResult]:
        self.get_rule(org_id, rule_id)
        return self.db.execute(
            select(TechnicalControlResult)
            .where(
                TechnicalControlResult.organization_id == org_id,
                TechnicalControlResult.rule_id == rule_id,
            )
            .order_by(TechnicalControlResult.created_at.desc())
            .limit(max(1, min(limit, 500)))
        ).scalars().all()

    def _pass_rate(self, org_id: uuid.UUID, rule_id: uuid.UUID, since: datetime) -> float | None:
        total = int(
            self.db.execute(
                select(func.count(TechnicalControlResult.id)).where(
                    TechnicalControlResult.organization_id == org_id,
                    TechnicalControlResult.rule_id == rule_id,
                    TechnicalControlResult.created_at >= since,
                )
            ).scalar_one()
        )
        if total == 0:
            return None
        passed = int(
            self.db.execute(
                select(func.count(TechnicalControlResult.id)).where(
                    TechnicalControlResult.organization_id == org_id,
                    TechnicalControlResult.rule_id == rule_id,
                    TechnicalControlResult.created_at >= since,
                    TechnicalControlResult.passed.is_(True),
                )
            ).scalar_one()
        )
        return round((passed / total) * 100.0, 2)

    def get_rule_summary(self, org_id: uuid.UUID, rule_id: uuid.UUID) -> dict:
        rule = self.get_rule(org_id, rule_id)
        results = self.get_rule_results(org_id, rule_id, limit=5000)
        latest = results[0] if results else None

        last_failed_at = next((row.created_at for row in results if not row.passed), None)
        last_passed_at = next((row.created_at for row in results if row.passed), None)

        now = self.utcnow()
        return {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "last_result": "never_run" if latest is None else ("passed" if latest.passed else "failed"),
            "pass_rate_7d": self._pass_rate(org_id, rule_id, now - timedelta(days=7)),
            "pass_rate_30d": self._pass_rate(org_id, rule_id, now - timedelta(days=30)),
            "total_checks": len(results),
            "last_checked_at": latest.created_at if latest else None,
            "last_failed_at": last_failed_at,
            "last_passed_at": last_passed_at,
            "severity": rule.severity,
        }


class TechnicalControlResultService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evaluator = TechnicalControlEvaluator()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _get_rule(self, rule_id: uuid.UUID) -> TechnicalControlRule | None:
        return self.db.execute(select(TechnicalControlRule).where(TechnicalControlRule.id == rule_id)).scalar_one_or_none()

    def _require_result_in_org(self, org_id: uuid.UUID, result_id: uuid.UUID) -> TechnicalControlResult:
        row = self.db.execute(
            select(TechnicalControlResult).where(
                TechnicalControlResult.organization_id == org_id,
                TechnicalControlResult.id == result_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technical control result not found")
        return row

    def _get_or_create_control_test_definition(self, rule: TechnicalControlRule, evaluated_at: datetime) -> ControlTestDefinition:
        existing = self.db.execute(
            select(ControlTestDefinition)
            .where(
                ControlTestDefinition.organization_id == rule.organization_id,
                ControlTestDefinition.control_id == rule.control_id,
                ControlTestDefinition.status != "archived",
            )
            .order_by(ControlTestDefinition.created_at.asc())
        ).scalars().first()
        if existing is not None:
            existing.last_run_at = evaluated_at
            self.db.flush()
            return existing

        created = ControlTestDefinition(
            organization_id=rule.organization_id,
            control_id=rule.control_id,
            name=f"Automated technical checks: {rule.name}"[:255],
            description="Auto-generated definition for technical control ingestion failures",
            test_type="internal_metadata_check",
            check_key="control_status_implemented",
            status="active",
            cadence="none",
            next_due_at=None,
            last_run_at=evaluated_at,
            owner_user_id=None,
            created_by_user_id=rule.created_by,
            metadata_json={"source": "technical_control_ingest", "rule_id": str(rule.id)},
        )
        self.db.add(created)
        self.db.flush()
        return created

    def ingest_result(
        self,
        agent: TechnicalControlAgent,
        rule_id: uuid.UUID,
        payload: TechnicalControlResultIngestRequest,
    ) -> TechnicalControlResult:
        rule = self._get_rule(rule_id)
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technical control rule not found")
        if rule.organization_id != agent.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rule does not belong to agent organization")
        if rule.deleted_at is not None or not rule.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Technical control rule is inactive")

        evaluated_at = self.utcnow()
        passed, failure_reason = self.evaluator.evaluate(rule, payload.actual_config_value)

        control_test_run_id: uuid.UUID | None = None
        if not passed:
            definition = self._get_or_create_control_test_definition(rule, evaluated_at)
            run = ControlTestRun(
                organization_id=agent.organization_id,
                control_test_definition_id=definition.id,
                control_id=rule.control_id,
                result="failed",
                result_reason=f"Automated technical check failed: {failure_reason}",
                check_key=definition.check_key,
                executed_by_user_id=None,
                execution_source="automation",
                evidence_item_id=None,
                metadata_json={
                    "source": "technical_control_ingest",
                    "rule_id": str(rule.id),
                    "agent_id": str(agent.id),
                    "resource_identifier": payload.resource_identifier,
                },
                created_at=evaluated_at,
            )
            self.db.add(run)
            self.db.flush()
            control_test_run_id = run.id

        result = TechnicalControlResult(
            organization_id=agent.organization_id,
            rule_id=rule.id,
            agent_id=agent.id,
            resource_identifier=payload.resource_identifier,
            actual_config_key=payload.actual_config_key,
            actual_config_value=payload.actual_config_value,
            raw_payload=payload.raw_payload or {},
            passed=passed,
            failure_reason=failure_reason,
            control_test_run_id=control_test_run_id,
            evaluated_at=evaluated_at,
        )
        self.db.add(result)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="technical_control.result_ingested",
            entity_type="technical_control_result",
            entity_id=result.id,
            organization_id=agent.organization_id,
            actor_user_id=None,
            after_json={
                "rule_id": str(rule.id),
                "agent_id": str(agent.id),
                "passed": result.passed,
            },
            metadata_json={"source": "agent_ingest"},
        )

        if not passed:
            AuditService(self.db).write_audit_log(
                action="technical_control.result_failed",
                entity_type="technical_control_result",
                entity_id=result.id,
                organization_id=agent.organization_id,
                actor_user_id=None,
                after_json={
                    "rule_id": str(rule.id),
                    "agent_id": str(agent.id),
                    "failure_reason": failure_reason,
                },
                metadata_json={"source": "agent_ingest"},
            )

        self._update_control_status_from_result(rule.control_id, agent.organization_id, passed)

        return result

    def _update_control_status_from_result(
        self,
        control_id: uuid.UUID,
        org_id: uuid.UUID,
        passed: bool,
    ) -> None:
        control = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if control is None:
            return

        if control.status in {"archived", "not_applicable"}:
            return

        new_status = "implemented" if passed else "failed"
        if control.status == new_status:
            return

        previous_status = control.status
        ControlService.set_status(
            self.db,
            organization_id=org_id,
            control_id=control.id,
            new_status=new_status,
            triggered_by="technical_control_ingest",
        )
        AuditService(self.db).write_audit_log(
            action="control.updated",
            entity_type="control",
            entity_id=control.id,
            organization_id=org_id,
            actor_user_id=None,
            before_json={"status": previous_status},
            after_json={"status": new_status},
            metadata_json={"source": "technical_control_ingest", "passed": passed},
        )

    def list_results(self, org_id: uuid.UUID, filters: TechnicalControlResultFilters) -> list[tuple[TechnicalControlResult, TechnicalControlRule]]:
        stmt = (
            select(TechnicalControlResult, TechnicalControlRule)
            .join(TechnicalControlRule, TechnicalControlRule.id == TechnicalControlResult.rule_id)
            .where(TechnicalControlResult.organization_id == org_id)
        )

        if filters.rule_id is not None:
            stmt = stmt.where(TechnicalControlResult.rule_id == filters.rule_id)
        if filters.agent_id is not None:
            stmt = stmt.where(TechnicalControlResult.agent_id == filters.agent_id)
        if filters.passed is not None:
            stmt = stmt.where(TechnicalControlResult.passed.is_(filters.passed))
        if filters.from_date is not None:
            start_dt = datetime.combine(filters.from_date, time.min, tzinfo=UTC)
            stmt = stmt.where(TechnicalControlResult.created_at >= start_dt)
        if filters.control_id is not None:
            stmt = stmt.where(TechnicalControlRule.control_id == filters.control_id)

        return self.db.execute(stmt.order_by(TechnicalControlResult.created_at.desc())).all()

    def get_result(self, org_id: uuid.UUID, result_id: uuid.UUID) -> tuple[TechnicalControlResult, TechnicalControlRule]:
        row = self.db.execute(
            select(TechnicalControlResult, TechnicalControlRule)
            .join(TechnicalControlRule, TechnicalControlRule.id == TechnicalControlResult.rule_id)
            .where(
                TechnicalControlResult.organization_id == org_id,
                TechnicalControlResult.id == result_id,
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technical control result not found")
        return row

    @staticmethod
    def _severity_rank(value: str) -> int:
        return {"critical": 3, "warning": 2, "info": 1}.get(value, 0)

    def get_summary(self, org_id: uuid.UUID, control_id: uuid.UUID | None = None) -> dict:
        rule_stmt = select(TechnicalControlRule).where(
            TechnicalControlRule.organization_id == org_id,
            TechnicalControlRule.deleted_at.is_(None),
        )
        if control_id is not None:
            rule_stmt = rule_stmt.where(TechnicalControlRule.control_id == control_id)

        rules = self.db.execute(rule_stmt.order_by(TechnicalControlRule.created_at.desc())).scalars().all()
        rule_ids = [row.id for row in rules]

        total_rules = len(rules)
        active_rules = sum(1 for row in rules if row.is_active)

        if not rule_ids:
            return {
                "total_rules": 0,
                "active_rules": 0,
                "checks_last_7d": 0,
                "pass_rate_7d": None,
                "failing_rules": [],
            }

        now = self.utcnow()
        since_7d = now - timedelta(days=7)

        checks_last_7d = int(
            self.db.execute(
                select(func.count(TechnicalControlResult.id)).where(
                    TechnicalControlResult.organization_id == org_id,
                    TechnicalControlResult.rule_id.in_(rule_ids),
                    TechnicalControlResult.created_at >= since_7d,
                )
            ).scalar_one()
        )

        pass_rate_7d: float | None = None
        if checks_last_7d > 0:
            passed_7d = int(
                self.db.execute(
                    select(func.count(TechnicalControlResult.id)).where(
                        TechnicalControlResult.organization_id == org_id,
                        TechnicalControlResult.rule_id.in_(rule_ids),
                        TechnicalControlResult.created_at >= since_7d,
                        TechnicalControlResult.passed.is_(True),
                    )
                ).scalar_one()
            )
            pass_rate_7d = round((passed_7d / checks_last_7d) * 100.0, 2)

        failing_rules: list[dict] = []
        rule_service = TechnicalControlRuleService(self.db)
        for rule in rules:
            summary = rule_service.get_rule_summary(org_id, rule.id)
            if summary["last_result"] == "failed":
                failing_rules.append(summary)

        failing_rules.sort(
            key=lambda row: (self._severity_rank(row["severity"]), row["last_checked_at"] or datetime.min.replace(tzinfo=UTC)),
            reverse=True,
        )

        cleaned = []
        for row in failing_rules:
            row_copy = dict(row)
            row_copy.pop("severity", None)
            cleaned.append(row_copy)

        return {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "checks_last_7d": checks_last_7d,
            "pass_rate_7d": pass_rate_7d,
            "failing_rules": cleaned,
        }


def get_agent_from_token(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> TechnicalControlAgent:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    agent = db.execute(
        select(TechnicalControlAgent).where(
            and_(
                TechnicalControlAgent.token_hash == token_hash,
                TechnicalControlAgent.is_active.is_(True),
                TechnicalControlAgent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    agent.last_seen_at = datetime.now(UTC)
    db.commit()
    db.refresh(agent)
    return agent
