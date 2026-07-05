from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.sod_conflict import SodConflictFinding, SodConflictRule
from app.services.audit_service import AuditService

OPEN_FINDING_STATUSES = {"open", "acknowledged"}
VALID_RULE_STATUSES = {"active", "inactive"}
VALID_FINDING_STATUSES = {"open", "acknowledged", "waived"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}


class SodConflictService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _normalize_permission_code(self, code: str) -> str:
        normalized = code.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Permission codes cannot be blank")
        return normalized

    def _canonical_pair(self, permission_a: str, permission_b: str) -> tuple[str, str]:
        a = self._normalize_permission_code(permission_a)
        b = self._normalize_permission_code(permission_b)
        if a == b:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="SoD conflict rule permissions must be different",
            )
        return tuple(sorted((a, b)))

    def _validate_severity(self, severity: str) -> str:
        normalized = severity.strip().lower()
        if normalized not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid severity: {severity}",
            )
        return normalized

    def _validate_rule_status(self, rule_status: str) -> str:
        normalized = rule_status.strip().lower()
        if normalized not in VALID_RULE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid rule status: {rule_status}",
            )
        return normalized

    def _validate_permissions_exist(self, permission_a: str, permission_b: str) -> None:
        keys = set(
            self.db.execute(select(Permission.key).where(Permission.key.in_([permission_a, permission_b]))).scalars().all()
        )
        missing = sorted({permission_a, permission_b} - keys)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown permission code(s): {', '.join(missing)}",
            )

    def _require_rule(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> SodConflictRule:
        rule = self.db.execute(
            select(SodConflictRule).where(
                SodConflictRule.id == rule_id,
                SodConflictRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SoD conflict rule not found")
        return rule

    def _require_finding(self, organization_id: uuid.UUID, finding_id: uuid.UUID) -> SodConflictFinding:
        finding = self.db.execute(
            select(SodConflictFinding).where(
                SodConflictFinding.id == finding_id,
                SodConflictFinding.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if finding is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SoD conflict finding not found")
        return finding

    def _active_duplicate_rule_exists(
        self,
        organization_id: uuid.UUID,
        permission_a: str,
        permission_b: str,
        *,
        exclude_rule_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(func.count(SodConflictRule.id)).where(
            SodConflictRule.organization_id == organization_id,
            SodConflictRule.active.is_(True),
            SodConflictRule.status == "active",
            or_(
                and_(SodConflictRule.permission_a == permission_a, SodConflictRule.permission_b == permission_b),
                and_(SodConflictRule.permission_a == permission_b, SodConflictRule.permission_b == permission_a),
            ),
        )
        if exclude_rule_id is not None:
            stmt = stmt.where(SodConflictRule.id != exclude_rule_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def _unresolved_finding_exists(self, organization_id: uuid.UUID, user_id: uuid.UUID, rule_id: uuid.UUID) -> bool:
        stmt = select(func.count(SodConflictFinding.id)).where(
            SodConflictFinding.organization_id == organization_id,
            SodConflictFinding.user_id == user_id,
            SodConflictFinding.rule_id == rule_id,
            SodConflictFinding.status.in_(OPEN_FINDING_STATUSES),
        )
        return int(self.db.execute(stmt).scalar_one()) > 0

    def create_rule(
        self,
        organization_id: uuid.UUID,
        *,
        permission_a: str,
        permission_b: str,
        severity: str = "medium",
        description: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> SodConflictRule:
        permission_a, permission_b = self._canonical_pair(permission_a, permission_b)
        self._validate_permissions_exist(permission_a, permission_b)
        severity = self._validate_severity(severity)
        if self._active_duplicate_rule_exists(organization_id, permission_a, permission_b):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active SoD conflict rule already exists")

        rule = SodConflictRule(
            organization_id=organization_id,
            permission_a=permission_a,
            permission_b=permission_b,
            severity=severity,
            active=True,
            status="active",
            description=description,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.db.add(rule)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sod_conflict_rule.created",
            entity_type="sod_conflict_rule",
            entity_id=rule.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json=self._rule_snapshot(rule),
            metadata_json={"source": "api"},
        )
        return rule

    def list_rules(self, organization_id: uuid.UUID, *, include_inactive: bool = False) -> list[SodConflictRule]:
        stmt = select(SodConflictRule).where(SodConflictRule.organization_id == organization_id)
        if not include_inactive:
            stmt = stmt.where(SodConflictRule.active.is_(True), SodConflictRule.status == "active")
        stmt = stmt.order_by(SodConflictRule.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_rule(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> SodConflictRule:
        return self._require_rule(organization_id, rule_id)

    def update_rule(
        self,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        *,
        permission_a: str | None = None,
        permission_b: str | None = None,
        severity: str | None = None,
        active: bool | None = None,
        rule_status: str | None = None,
        description: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> SodConflictRule:
        rule = self._require_rule(organization_id, rule_id)
        before = self._rule_snapshot(rule)

        next_permission_a = permission_a if permission_a is not None else rule.permission_a
        next_permission_b = permission_b if permission_b is not None else rule.permission_b
        next_permission_a, next_permission_b = self._canonical_pair(next_permission_a, next_permission_b)
        if permission_a is not None or permission_b is not None:
            self._validate_permissions_exist(next_permission_a, next_permission_b)
            if self._active_duplicate_rule_exists(
                organization_id,
                next_permission_a,
                next_permission_b,
                exclude_rule_id=rule.id,
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active SoD conflict rule already exists")
            rule.permission_a = next_permission_a
            rule.permission_b = next_permission_b

        if severity is not None:
            rule.severity = self._validate_severity(severity)
        if description is not None:
            rule.description = description
        if active is not None:
            rule.active = active
            rule.status = "active" if active else "inactive"
        if rule_status is not None:
            rule.status = self._validate_rule_status(rule_status)
            rule.active = rule.status == "active"
        rule.updated_by = actor_user_id

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sod_conflict_rule.updated",
            entity_type="sod_conflict_rule",
            entity_id=rule.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._rule_snapshot(rule),
            metadata_json={"source": "api"},
        )
        return rule

    def deactivate_rule(
        self,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> SodConflictRule:
        rule = self._require_rule(organization_id, rule_id)
        before = self._rule_snapshot(rule)
        rule.active = False
        rule.status = "inactive"
        rule.updated_by = actor_user_id
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sod_conflict_rule.deactivated",
            entity_type="sod_conflict_rule",
            entity_id=rule.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._rule_snapshot(rule),
            metadata_json={"source": "api"},
        )
        return rule

    def get_user_permission_codes(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> set[str]:
        stmt = (
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Membership, Membership.role_id == RolePermission.role_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        )
        return set(self.db.execute(stmt).scalars().all())

    def detect_for_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
        source: str = "service",
    ) -> tuple[list[SodConflictFinding], set[str]]:
        permission_codes = self.get_user_permission_codes(organization_id, user_id)
        if not permission_codes:
            return [], permission_codes

        rules = self.list_rules(organization_id, include_inactive=False)
        created: list[SodConflictFinding] = []
        for rule in rules:
            if rule.permission_a not in permission_codes or rule.permission_b not in permission_codes:
                continue
            if self._unresolved_finding_exists(organization_id, user_id, rule.id):
                continue
            finding = SodConflictFinding(
                organization_id=organization_id,
                user_id=user_id,
                rule_id=rule.id,
                status="open",
            )
            self.db.add(finding)
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="sod_conflict_finding.created",
                entity_type="sod_conflict_finding",
                entity_id=finding.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json=self._finding_snapshot(finding),
                metadata_json={
                    "source": source,
                    "rule_id": str(rule.id),
                    "permission_a": rule.permission_a,
                    "permission_b": rule.permission_b,
                    "severity": rule.severity,
                },
            )
            created.append(finding)
        return created, permission_codes

    def detect_for_membership(
        self,
        organization_id: uuid.UUID,
        membership_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
        source: str = "membership_role_change",
    ) -> tuple[list[SodConflictFinding], set[str]]:
        membership = self.db.execute(
            select(Membership).where(
                Membership.id == membership_id,
                Membership.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
        return self.detect_for_user(
            organization_id,
            membership.user_id,
            actor_user_id=actor_user_id,
            source=source,
        )

    def scan_organization(
        self,
        organization_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
        source: str = "organization_scan",
    ) -> list[SodConflictFinding]:
        memberships = self.db.execute(
            select(Membership).where(Membership.organization_id == organization_id, Membership.status == "active")
        ).scalars().all()
        created: list[SodConflictFinding] = []
        for membership in memberships:
            findings, _ = self.detect_for_user(
                organization_id,
                membership.user_id,
                actor_user_id=actor_user_id,
                source=source,
            )
            created.extend(findings)
        return created

    def list_findings(
        self,
        organization_id: uuid.UUID,
        *,
        finding_status: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[SodConflictFinding]:
        stmt = select(SodConflictFinding).where(SodConflictFinding.organization_id == organization_id)
        if finding_status is not None:
            normalized = finding_status.strip().lower()
            if normalized not in VALID_FINDING_STATUSES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid finding status")
            stmt = stmt.where(SodConflictFinding.status == normalized)
        if user_id is not None:
            stmt = stmt.where(SodConflictFinding.user_id == user_id)
        stmt = stmt.order_by(SodConflictFinding.detected_at.desc(), SodConflictFinding.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_finding_rule(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> SodConflictRule | None:
        return self.db.execute(
            select(SodConflictRule).where(SodConflictRule.id == rule_id, SodConflictRule.organization_id == organization_id)
        ).scalar_one_or_none()

    def acknowledge_finding(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        note: str | None = None,
    ) -> SodConflictFinding:
        finding = self._require_finding(organization_id, finding_id)
        if finding.status == "waived":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Waived findings cannot be acknowledged")
        before = self._finding_snapshot(finding)
        finding.status = "acknowledged"
        finding.acknowledged_at = datetime.now(timezone.utc)
        finding.acknowledged_by = actor_user_id
        if note is not None:
            finding.note = note
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sod_conflict_finding.acknowledged",
            entity_type="sod_conflict_finding",
            entity_id=finding.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._finding_snapshot(finding),
            metadata_json={"source": "api"},
        )
        return finding

    def waive_finding(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        note: str | None = None,
    ) -> SodConflictFinding:
        finding = self._require_finding(organization_id, finding_id)
        if finding.status == "waived":
            return finding
        before = self._finding_snapshot(finding)
        finding.status = "waived"
        finding.waived_at = datetime.now(timezone.utc)
        finding.waived_by = actor_user_id
        if note is not None:
            finding.note = note
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sod_conflict_finding.waived",
            entity_type="sod_conflict_finding",
            entity_id=finding.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._finding_snapshot(finding),
            metadata_json={"source": "api"},
        )
        return finding

    def _rule_snapshot(self, rule: SodConflictRule) -> dict[str, object]:
        return {
            "id": str(rule.id),
            "organization_id": str(rule.organization_id),
            "permission_a": rule.permission_a,
            "permission_b": rule.permission_b,
            "severity": rule.severity,
            "active": rule.active,
            "status": rule.status,
            "description": rule.description,
        }

    def _finding_snapshot(self, finding: SodConflictFinding) -> dict[str, object]:
        return {
            "id": str(finding.id),
            "organization_id": str(finding.organization_id),
            "user_id": str(finding.user_id),
            "rule_id": str(finding.rule_id),
            "status": finding.status,
            "detected_at": finding.detected_at.isoformat() if finding.detected_at else None,
            "acknowledged_at": finding.acknowledged_at.isoformat() if finding.acknowledged_at else None,
            "acknowledged_by": str(finding.acknowledged_by) if finding.acknowledged_by else None,
            "waived_at": finding.waived_at.isoformat() if finding.waived_at else None,
            "waived_by": str(finding.waived_by) if finding.waived_by else None,
            "note": finding.note,
        }
