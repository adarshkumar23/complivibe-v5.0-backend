import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_item import EvidenceItem
from app.models.vendor import Vendor
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_remediation_portal_token import VendorRemediationPortalToken
from app.schemas.vendor_remediation_portal import (
    VendorRemediationPortalEvidenceSubmitRequest,
    VendorRemediationPortalTokenCreate,
)
from app.services.audit_service import AuditService


class VendorRemediationPortalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def mask_email(email: str) -> str:
        local, _, domain = email.partition("@")
        if not local:
            return f"***@{domain}" if domain else "***"
        return f"{local[0]}***@{domain}" if domain else f"{local[0]}***"

    def _require_case(self, org_id: uuid.UUID, case_id: uuid.UUID) -> VendorMitigationCase:
        row = self.db.execute(
            select(VendorMitigationCase).where(
                VendorMitigationCase.organization_id == org_id,
                VendorMitigationCase.id == case_id,
                VendorMitigationCase.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitigation case not found")
        return row

    def _require_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.organization_id == org_id,
                Vendor.id == vendor_id,
                Vendor.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def _require_token(self, org_id: uuid.UUID, token_id: uuid.UUID) -> VendorRemediationPortalToken:
        row = self.db.execute(
            select(VendorRemediationPortalToken).where(
                VendorRemediationPortalToken.organization_id == org_id,
                VendorRemediationPortalToken.id == token_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor remediation portal token not found")
        return row

    def _scoped_action_ids(self, token: VendorRemediationPortalToken) -> list[uuid.UUID] | None:
        if token.scoped_action_ids is None:
            return None
        return [uuid.UUID(item) for item in token.scoped_action_ids]

    def _validate_scoped_actions(
        self,
        org_id: uuid.UUID,
        case_id: uuid.UUID,
        scoped_action_ids: list[uuid.UUID] | None,
    ) -> None:
        if scoped_action_ids is None:
            return
        if not scoped_action_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scoped_action_ids cannot be empty")
        rows = self.db.execute(
            select(VendorMitigationAction.id).where(
                VendorMitigationAction.organization_id == org_id,
                VendorMitigationAction.case_id == case_id,
                VendorMitigationAction.id.in_(scoped_action_ids),
                VendorMitigationAction.assigned_to_vendor.is_(True),
                VendorMitigationAction.deleted_at.is_(None),
            )
        ).all()
        found = {row[0] for row in rows}
        missing = [str(item) for item in scoped_action_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown or unassigned scoped action ids: {', '.join(missing)}",
            )

    def create_token(
        self,
        org_id: uuid.UUID,
        data: VendorRemediationPortalTokenCreate,
        created_by: uuid.UUID,
    ) -> tuple[VendorRemediationPortalToken, str]:
        case = self._require_case(org_id, data.case_id)
        self._require_vendor(org_id, case.vendor_id)
        self._validate_scoped_actions(org_id, case.id, data.scoped_action_ids)

        plaintext_token = secrets.token_urlsafe(32)
        row = VendorRemediationPortalToken(
            organization_id=org_id,
            vendor_id=case.vendor_id,
            case_id=case.id,
            vendor_contact_email=str(data.vendor_contact_email),
            vendor_contact_name=data.vendor_contact_name,
            token_hash=self.hash_token(plaintext_token),
            scoped_action_ids=[str(item) for item in data.scoped_action_ids] if data.scoped_action_ids is not None else None,
            expires_at=self.utcnow() + timedelta(days=data.expires_in_days),
            first_accessed_at=None,
            last_accessed_at=None,
            access_count=0,
            status="active",
            revoked_at=None,
            revoked_by=None,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_remediation_portal.token_created",
            entity_type="vendor_remediation_portal_token",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "vendor_id": str(row.vendor_id),
                "case_id": str(row.case_id),
                "vendor_contact_email": row.vendor_contact_email,
                "expires_at": row.expires_at.isoformat(),
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row, plaintext_token

    def list_tokens(
        self,
        org_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        case_id: uuid.UUID | None = None,
    ) -> list[VendorRemediationPortalToken]:
        stmt = select(VendorRemediationPortalToken).where(VendorRemediationPortalToken.organization_id == org_id)
        if vendor_id is not None:
            stmt = stmt.where(VendorRemediationPortalToken.vendor_id == vendor_id)
        if case_id is not None:
            stmt = stmt.where(VendorRemediationPortalToken.case_id == case_id)
        return self.db.execute(stmt.order_by(VendorRemediationPortalToken.created_at.desc())).scalars().all()

    def get_token(self, org_id: uuid.UUID, token_id: uuid.UUID) -> VendorRemediationPortalToken:
        return self._require_token(org_id, token_id)

    def revoke_token(self, org_id: uuid.UUID, token_id: uuid.UUID, revoked_by: uuid.UUID) -> VendorRemediationPortalToken:
        row = self._require_token(org_id, token_id)
        before = {"status": row.status, "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None}
        row.status = "revoked"
        row.revoked_at = self.utcnow()
        row.revoked_by = revoked_by
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_remediation_portal.token_revoked",
            entity_type="vendor_remediation_portal_token",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=revoked_by,
            before_json=before,
            after_json={
                "status": row.status,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "revoked_by": str(row.revoked_by) if row.revoked_by else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def authenticate_portal_token(self, raw_token: str) -> VendorRemediationPortalToken:
        token_hash = self.hash_token(raw_token)
        row = self.db.execute(
            select(VendorRemediationPortalToken).where(VendorRemediationPortalToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

        now = self.utcnow()
        if row.status == "revoked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal token revoked")

        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            if row.status != "expired":
                before = {"status": row.status}
                row.status = "expired"
                self.db.flush()
                AuditService(self.db).write_audit_log(
                    action="vendor_remediation_portal.token_expired",
                    entity_type="vendor_remediation_portal_token",
                    entity_id=row.id,
                    organization_id=row.organization_id,
                    actor_user_id=None,
                    before_json=before,
                    after_json={"status": row.status, "expires_at": row.expires_at.isoformat()},
                    metadata_json={"source": "portal", "vendor_contact_email": row.vendor_contact_email},
                )
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Portal token expired")

        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

        row.access_count = int(row.access_count or 0) + 1
        row.last_accessed_at = now
        if row.first_accessed_at is None:
            row.first_accessed_at = now

        AuditService(self.db).write_audit_log(
            action="vendor_remediation_portal.access",
            entity_type="vendor_remediation_portal_token",
            entity_id=row.id,
            organization_id=row.organization_id,
            actor_user_id=None,
            after_json={
                "status": row.status,
                "access_count": row.access_count,
                "last_accessed_at": row.last_accessed_at.isoformat() if row.last_accessed_at else None,
            },
            metadata_json={"source": "portal", "vendor_contact_email": row.vendor_contact_email},
        )
        self.db.flush()
        return row

    def get_portal_vendor(self, token: VendorRemediationPortalToken) -> Vendor:
        return self._require_vendor(token.organization_id, token.vendor_id)

    def get_portal_case(self, token: VendorRemediationPortalToken) -> VendorMitigationCase:
        return self._require_case(token.organization_id, token.case_id)

    def get_portal_actions(self, token: VendorRemediationPortalToken) -> list[VendorMitigationAction]:
        scoped_action_ids = self._scoped_action_ids(token)
        stmt = select(VendorMitigationAction).where(
            VendorMitigationAction.organization_id == token.organization_id,
            VendorMitigationAction.case_id == token.case_id,
            VendorMitigationAction.assigned_to_vendor.is_(True),
            VendorMitigationAction.deleted_at.is_(None),
        )
        if scoped_action_ids is not None:
            stmt = stmt.where(VendorMitigationAction.id.in_(scoped_action_ids))
        return self.db.execute(stmt.order_by(VendorMitigationAction.created_at.asc())).scalars().all()

    def log_portal_view(
        self,
        token: VendorRemediationPortalToken,
        resource_type: str,
        item_ids: list[uuid.UUID],
    ) -> None:
        AuditService(self.db).write_audit_log(
            action="vendor_remediation_portal.data_viewed",
            entity_type="vendor_remediation_portal_token",
            entity_id=token.id,
            organization_id=token.organization_id,
            actor_user_id=None,
            after_json={
                "resource_type": resource_type,
                "item_count": len(item_ids),
                "item_ids": [str(item) for item in item_ids],
            },
            metadata_json={"source": "portal", "vendor_contact_email": token.vendor_contact_email},
        )
        self.db.flush()

    def submit_action_evidence(
        self,
        token: VendorRemediationPortalToken,
        action_id: uuid.UUID,
        payload: VendorRemediationPortalEvidenceSubmitRequest,
    ) -> tuple[VendorMitigationAction, EvidenceItem]:
        actions = {row.id: row for row in self.get_portal_actions(token)}
        row = actions.get(action_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation action not found")
        if row.status in {"accepted", "overdue"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Remediation action is not accepting submissions")

        before = {
            "status": row.status,
            "evidence_id": str(row.evidence_id) if row.evidence_id else None,
            "evidence_submitted_at": row.evidence_submitted_at.isoformat() if row.evidence_submitted_at else None,
        }
        now = self.utcnow()
        evidence = EvidenceItem(
            organization_id=token.organization_id,
            title=f"Vendor remediation evidence: {row.title}",
            description=payload.remediation_notes,
            evidence_type="other",
            source="external_vendor",
            status="active",
            review_status="needs_review",
            freshness_status="current",
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
            checksum_sha256=payload.checksum_sha256,
            external_reference_url=payload.external_reference_url,
            collected_at=now,
            uploaded_by_user_id=None,
            metadata_json={
                "source": "vendor_remediation_portal",
                "portal_token_id": str(token.id),
                "vendor_id": str(token.vendor_id),
                "case_id": str(token.case_id),
                "action_id": str(row.id),
                "vendor_contact_email": token.vendor_contact_email,
            },
        )
        self.db.add(evidence)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="evidence.created",
            entity_type="evidence_item",
            entity_id=evidence.id,
            organization_id=token.organization_id,
            actor_user_id=None,
            after_json={
                "title": evidence.title,
                "status": evidence.status,
                "review_status": evidence.review_status,
                "freshness_status": evidence.freshness_status,
            },
            metadata_json={
                "source": "portal",
                "portal_token_id": str(token.id),
                "vendor_contact_email": token.vendor_contact_email,
            },
        )

        row.evidence_id = evidence.id
        row.status = "evidence_submitted"
        row.evidence_submitted_at = now

        case = self._require_case(token.organization_id, token.case_id)
        case_before_status = case.status
        if case.status not in {"closed", "cancelled", "escalated"}:
            case.status = "pending_vendor_evidence"
        self.db.flush()
        if case.status != case_before_status:
            AuditService(self.db).write_audit_log(
                action="vendor_mitigation_case.transitioned",
                entity_type="vendor_mitigation_case",
                entity_id=case.id,
                organization_id=token.organization_id,
                actor_user_id=None,
                before_json={"status": case_before_status},
                after_json={"status": case.status},
                metadata_json={
                    "source": "portal",
                    "portal_token_id": str(token.id),
                    "vendor_contact_email": token.vendor_contact_email,
                },
            )

        AuditService(self.db).write_audit_log(
            action="vendor_remediation_portal.evidence_submitted",
            entity_type="vendor_mitigation_action",
            entity_id=row.id,
            organization_id=token.organization_id,
            actor_user_id=None,
            before_json=before,
            after_json={
                "status": row.status,
                "evidence_id": str(evidence.id),
                "evidence_submitted_at": row.evidence_submitted_at.isoformat() if row.evidence_submitted_at else None,
                "case_status": case.status,
            },
            metadata_json={
                "source": "portal",
                "portal_token_id": str(token.id),
                "vendor_contact_email": token.vendor_contact_email,
            },
        )
        return row, evidence
