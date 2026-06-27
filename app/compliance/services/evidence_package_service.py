import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.audit_engagement import AuditEngagement
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.evidence_package import EvidencePackage
from app.models.evidence_package_item import EvidencePackageItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.user import User
from app.schemas.evidence_package import EvidencePackageAddItem, EvidencePackageCreate
from app.services.audit_service import AuditService


class EvidencePackageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engagement_service = AuditEngagementService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_package(self, org_id: uuid.UUID, package_id: uuid.UUID) -> EvidencePackage:
        row = self.db.execute(
            select(EvidencePackage).where(
                EvidencePackage.organization_id == org_id,
                EvidencePackage.id == package_id,
                EvidencePackage.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence package not found")
        return row

    def _require_item(self, org_id: uuid.UUID, package_id: uuid.UUID, item_id: uuid.UUID) -> EvidencePackageItem:
        row = self.db.execute(
            select(EvidencePackageItem).where(
                EvidencePackageItem.organization_id == org_id,
                EvidencePackageItem.package_id == package_id,
                EvidencePackageItem.id == item_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence package item not found")
        return row

    def _require_control(self, org_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.id == control_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="control_id must belong to same organization")
        return row

    def _require_evidence(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        row = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.id == evidence_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="evidence_id must belong to same organization")
        return row

    def _framework_names(self, framework_ids: list[uuid.UUID]) -> list[str]:
        if not framework_ids:
            return []
        rows = self.db.execute(select(Framework).where(Framework.id.in_(framework_ids))).scalars().all()
        return [row.name for row in rows]

    def _build_cover_sheet_data(
        self,
        *,
        org: Organization,
        engagement: AuditEngagement,
        scope_framework_ids: list[uuid.UUID],
        preparer: User,
    ) -> dict:
        return {
            "organization_name": org.name,
            "audit_type": engagement.audit_type,
            "audit_title": engagement.title,
            "date_range": {
                "from": engagement.start_date.isoformat(),
                "to": engagement.end_date.isoformat(),
            },
            "framework_scope": self._framework_names(scope_framework_ids),
            "preparer_name": preparer.full_name or preparer.email,
            "preparer_id": str(preparer.id),
            "prepared_at": self.utcnow().isoformat(),
        }

    def _append_custody_event(self, package: EvidencePackage, event_type: str, actor: User, note: str | None = None) -> None:
        events = list(package.chain_of_custody or [])
        events.append(
            {
                "event": event_type,
                "actor_id": str(actor.id),
                "actor_email": actor.email,
                "timestamp": self.utcnow().isoformat(),
                "note": note,
            }
        )
        package.chain_of_custody = events

    @staticmethod
    def _require_status(package: EvidencePackage, expected: str, detail: str) -> None:
        if package.status != expected:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    def create_package(
        self,
        org_id: uuid.UUID,
        engagement_id: uuid.UUID,
        data: EvidencePackageCreate,
        user: User,
    ) -> EvidencePackage:
        engagement = self.engagement_service.require_engagement(org_id, engagement_id)
        org = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        scope_framework_ids = data.scope_framework_ids or [uuid.UUID(item) for item in (engagement.scope_framework_ids or [])]
        row = EvidencePackage(
            organization_id=org_id,
            audit_engagement_id=engagement_id,
            title=data.title,
            scope_framework_ids=[str(item) for item in scope_framework_ids],
            cover_sheet_data=self._build_cover_sheet_data(
                org=org,
                engagement=engagement,
                scope_framework_ids=scope_framework_ids,
                preparer=user,
            ),
            chain_of_custody=[],
            status="draft",
            item_count=0,
        )
        self._append_custody_event(row, "assembled", user, note="initial_package_created")

        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.created",
            entity_type="evidence_package",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={
                "audit_engagement_id": str(row.audit_engagement_id),
                "status": row.status,
                "item_count": row.item_count,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_package(self, org_id: uuid.UUID, package_id: uuid.UUID) -> EvidencePackage:
        return self.require_package(org_id, package_id)

    def list_packages(
        self,
        org_id: uuid.UUID,
        *,
        engagement_id: uuid.UUID | None = None,
        status_value: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EvidencePackage]:
        stmt = select(EvidencePackage).where(
            EvidencePackage.organization_id == org_id,
            EvidencePackage.deleted_at.is_(None),
        )
        if engagement_id is not None:
            stmt = stmt.where(EvidencePackage.audit_engagement_id == engagement_id)
        if status_value is not None:
            stmt = stmt.where(EvidencePackage.status == status_value)

        rows = self.db.execute(stmt.order_by(EvidencePackage.created_at.desc())).scalars().all()
        return rows[skip : skip + limit]

    def _validate_control_in_scope(self, package: EvidencePackage, control: Control) -> None:
        if not package.scope_framework_ids:
            return
        if control.obligation_id is None:
            return

        obligation = self.db.execute(select(Obligation).where(Obligation.id == control.obligation_id)).scalar_one_or_none()
        if obligation is None:
            return

        if str(obligation.framework_id) not in package.scope_framework_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="control framework is out of package scope")

    def add_item(
        self,
        org_id: uuid.UUID,
        package_id: uuid.UUID,
        data: EvidencePackageAddItem,
        user: User,
    ) -> EvidencePackageItem:
        package = self.require_package(org_id, package_id)
        self._require_status(package, "draft", "Cannot add items unless package is in draft status")

        control = self._require_control(org_id, data.control_id)
        evidence = self._require_evidence(org_id, data.evidence_id)
        self._validate_control_in_scope(package, control)

        next_order = int(
            self.db.execute(
                select(func.coalesce(func.max(EvidencePackageItem.display_order), 0)).where(
                    EvidencePackageItem.package_id == package.id,
                )
            ).scalar_one()
            or 0
        ) + 1

        row = EvidencePackageItem(
            package_id=package.id,
            organization_id=org_id,
            control_id=control.id,
            evidence_id=evidence.id,
            framework_requirement_ref=data.framework_requirement_ref,
            display_order=next_order,
            added_by=user.id,
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duplicate evidence_id for package") from exc

        package.item_count = int(package.item_count or 0) + 1
        self._append_custody_event(package, "item_added", user, note=evidence.title)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.item_added",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={
                "item_id": str(row.id),
                "evidence_id": str(row.evidence_id),
                "item_count": package.item_count,
            },
            metadata_json={"source": "api"},
        )
        return row

    def remove_item(self, org_id: uuid.UUID, package_id: uuid.UUID, item_id: uuid.UUID, user: User) -> None:
        package = self.require_package(org_id, package_id)
        self._require_status(package, "draft", "Cannot remove items unless package is in draft status")
        item = self._require_item(org_id, package_id, item_id)

        self.db.delete(item)
        package.item_count = max(0, int(package.item_count or 0) - 1)
        self._append_custody_event(package, "item_removed", user)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.item_removed",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={"item_id": str(item_id), "item_count": package.item_count},
            metadata_json={"source": "api"},
        )

    def get_manifest(self, org_id: uuid.UUID, package_id: uuid.UUID) -> dict:
        package = self.require_package(org_id, package_id)

        item_rows = self.db.execute(
            select(EvidencePackageItem, Control, EvidenceItem)
            .join(Control, Control.id == EvidencePackageItem.control_id)
            .join(EvidenceItem, EvidenceItem.id == EvidencePackageItem.evidence_id)
            .where(
                EvidencePackageItem.package_id == package.id,
                EvidencePackageItem.organization_id == org_id,
            )
            .order_by(EvidencePackageItem.display_order.asc())
        ).all()

        grouped: dict[str, list[dict]] = {}
        ungrouped: list[dict] = []
        for item, control, evidence in item_rows:
            payload = {
                "item_id": item.id,
                "control_id": control.id,
                "control_name": control.title,
                "evidence_id": evidence.id,
                "evidence_title": evidence.title,
                "display_order": item.display_order,
            }
            if item.framework_requirement_ref:
                grouped.setdefault(item.framework_requirement_ref, []).append(payload)
            else:
                ungrouped.append(payload)

        for key in grouped:
            grouped[key] = sorted(grouped[key], key=lambda row: row["display_order"])
        ungrouped = sorted(ungrouped, key=lambda row: row["display_order"])

        return {
            "package": {
                "id": package.id,
                "title": package.title,
                "status": package.status,
                "item_count": package.item_count,
                "assembled_at": package.assembled_at,
                "cover_sheet_data": package.cover_sheet_data,
            },
            "items_by_framework_ref": grouped,
            "items_ungrouped": ungrouped,
            "chain_of_custody": list(package.chain_of_custody or []),
        }

    def assemble_package(self, org_id: uuid.UUID, package_id: uuid.UUID, user: User) -> EvidencePackage:
        package = self.require_package(org_id, package_id)
        self._require_status(package, "draft", "Only draft packages can be assembled")
        if int(package.item_count or 0) == 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot assemble empty package")

        engagement = self.engagement_service.require_engagement(org_id, package.audit_engagement_id)
        org = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        scope_ids = [uuid.UUID(item) for item in (package.scope_framework_ids or [])]
        package.cover_sheet_data = self._build_cover_sheet_data(
            org=org,
            engagement=engagement,
            scope_framework_ids=scope_ids,
            preparer=user,
        )
        package.status = "assembled"
        package.assembled_at = self.utcnow()
        package.assembled_by = user.id
        self._append_custody_event(package, "assembled", user, note=str(package.item_count))
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.assembled",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={
                "status": package.status,
                "assembled_at": package.assembled_at.isoformat() if package.assembled_at else None,
                "item_count": package.item_count,
            },
            metadata_json={"source": "api"},
        )
        return package

    def mark_exported(self, org_id: uuid.UUID, package_id: uuid.UUID, user: User) -> EvidencePackage:
        package = self.require_package(org_id, package_id)
        self._require_status(package, "assembled", "Only assembled packages can be exported")

        package.status = "exported"
        package.exported_at = self.utcnow()
        self._append_custody_event(package, "exported", user)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.exported",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={
                "status": package.status,
                "exported_at": package.exported_at.isoformat() if package.exported_at else None,
            },
            metadata_json={"source": "api"},
        )
        return package

    def archive_package(self, org_id: uuid.UUID, package_id: uuid.UUID, user: User) -> EvidencePackage:
        package = self.require_package(org_id, package_id)
        self._require_status(package, "exported", "Only exported packages can be archived")

        package.status = "archived"
        self._append_custody_event(package, "archived", user)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.archived",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={"status": package.status},
            metadata_json={"source": "api"},
        )
        return package

    def soft_delete_package(self, org_id: uuid.UUID, package_id: uuid.UUID, user: User) -> EvidencePackage:
        package = self.require_package(org_id, package_id)
        if package.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only draft packages can be deleted")

        package.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="evidence_package.deleted",
            entity_type="evidence_package",
            entity_id=package.id,
            organization_id=org_id,
            actor_user_id=user.id,
            after_json={"status": package.status, "deleted_at": package.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return package
