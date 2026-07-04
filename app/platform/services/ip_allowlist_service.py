from __future__ import annotations

import ipaddress
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_ip_allowlist import OrgIPAllowlist
from app.services.audit_service import AuditService


class IPAllowlistService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def extract_request_ip(*, x_forwarded_for: str | None, client_host: str | None) -> str | None:
        if x_forwarded_for:
            first = x_forwarded_for.split(",", 1)[0].strip()
            if first:
                return first
        return client_host

    @staticmethod
    def _normalize_cidr(cidr_range: str) -> str:
        value = (cidr_range or "").strip()
        try:
            if "/" in value:
                network = ipaddress.ip_network(value, strict=False)
                return str(network)
            addr = ipaddress.ip_address(value)
            suffix = 32 if addr.version == 4 else 128
            return f"{addr}/{suffix}"
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid CIDR/IP range") from exc

    def add_ip_range(
        self,
        *,
        org_id: uuid.UUID,
        cidr_range: str,
        label: str | None,
        created_by: uuid.UUID,
        requester_ip: str | None,
    ) -> OrgIPAllowlist:
        normalized = self._normalize_cidr(cidr_range)

        # Guard against self-lockout: reject the change if the requester's own current IP
        # would fall outside the resulting active range set. The requester already passed
        # the existing allowlist check to reach this endpoint (see require_org_membership),
        # so this only fires when the *new* range itself would be the one to exclude them.
        existing_ranges = [
            row.cidr_range
            for row in self.db.execute(
                select(OrgIPAllowlist.cidr_range).where(
                    OrgIPAllowlist.organization_id == org_id,
                    OrgIPAllowlist.is_active.is_(True),
                )
            ).all()
        ]
        if not self._ip_in_any_range(requester_ip, [*existing_ranges, normalized]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This range would exclude your own current IP address "
                    f"({requester_ip or 'unknown'}), which would lock you out of the "
                    "organization. Add a range that includes your own IP first."
                ),
            )

        row = OrgIPAllowlist(
            organization_id=org_id,
            cidr_range=normalized,
            label=label,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _ip_in_any_range(request_ip: str | None, cidrs: list[str]) -> bool:
        if not request_ip:
            return False
        try:
            addr = ipaddress.ip_address(request_ip)
        except ValueError:
            return False
        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if addr in network:
                return True
        return False

    def _remaining_active_ranges(self, *, org_id: uuid.UUID, exclude_id: uuid.UUID) -> list[str]:
        return [
            r.cidr_range
            for r in self.db.execute(
                select(OrgIPAllowlist.cidr_range).where(
                    OrgIPAllowlist.organization_id == org_id,
                    OrgIPAllowlist.is_active.is_(True),
                    OrgIPAllowlist.id != exclude_id,
                )
            ).all()
        ]

    def remove_ip_range(
        self,
        *,
        org_id: uuid.UUID,
        range_id: uuid.UUID,
        requester_ip: str | None,
        removed_by: uuid.UUID,
    ) -> OrgIPAllowlist:
        row = self.db.execute(
            select(OrgIPAllowlist).where(
                OrgIPAllowlist.id == range_id,
                OrgIPAllowlist.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP allowlist range not found")

        if row.is_active:
            remaining = self._remaining_active_ranges(org_id=org_id, exclude_id=row.id)
            if not self._ip_in_any_range(requester_ip, remaining):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Deactivating this range would exclude your own current IP address "
                        f"({requester_ip or 'unknown'}), locking you out of the organization. "
                        "If you intend to disable IP allowlisting entirely, use the disable endpoint instead."
                    ),
                )
            row.is_active = False

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_allowlist.range_deactivated",
            entity_type="org_ip_allowlist",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=removed_by,
            after_json={"cidr_range": row.cidr_range, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def disable_allowlist(
        self,
        *,
        org_id: uuid.UUID,
        requester_ip: str | None,
        disabled_by: uuid.UUID,
    ) -> list[OrgIPAllowlist]:
        """Explicitly disable IP allowlisting for the organization by deactivating all active ranges."""
        rows = list(
            self.db.execute(
                select(OrgIPAllowlist).where(
                    OrgIPAllowlist.organization_id == org_id,
                    OrgIPAllowlist.is_active.is_(True),
                )
            ).scalars().all()
        )
        for row in rows:
            row.is_active = False

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_allowlist.disabled",
            entity_type="org_ip_allowlist",
            entity_id=org_id,
            organization_id=org_id,
            actor_user_id=disabled_by,
            after_json={"deactivated_range_ids": [str(row.id) for row in rows]},
            metadata_json={"requester_ip": requester_ip, "source": "api"},
        )
        return rows

    def list_ranges(self, *, org_id: uuid.UUID) -> list[OrgIPAllowlist]:
        return list(
            self.db.execute(
                select(OrgIPAllowlist)
                .where(OrgIPAllowlist.organization_id == org_id)
                .order_by(OrgIPAllowlist.created_at.desc())
            ).scalars().all()
        )

    def is_ip_allowed(self, *, org_id: uuid.UUID, request_ip: str | None) -> bool:
        rows = self.db.execute(
            select(OrgIPAllowlist.cidr_range).where(
                OrgIPAllowlist.organization_id == org_id,
                OrgIPAllowlist.is_active.is_(True),
            )
        ).scalars().all()

        if not rows:
            return True
        if not request_ip:
            return False

        try:
            addr = ipaddress.ip_address(request_ip)
        except ValueError:
            return False

        for cidr in rows:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if addr in network:
                return True
        return False
