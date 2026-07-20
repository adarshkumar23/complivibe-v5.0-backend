from __future__ import annotations

import ipaddress
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.org_ip_allowlist import OrgIPAllowlist
from app.services.audit_service import AuditService

# Cloudflare's published edge IP ranges (https://www.cloudflare.com/ips/). Used to
# confirm the immediate upstream really is Cloudflare before believing its
# CF-Connecting-IP header, for the orange-cloud (proxy-to-public-origin) topology.
_CLOUDFLARE_CIDRS: tuple[str, ...] = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)


def _is_valid_ip(value: str | None) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_trusted_cf_upstream(client_host: str | None) -> bool:
    """Is the immediate socket peer a legitimate Cloudflare upstream?

    Two supported topologies (both verified against a live cloudflared tunnel):
      * cloudflared tunnel: cloudflared (and the Next.js proxy) connect to this
        origin from loopback, so the peer is 127.0.0.1 / ::1.
      * orange-cloud proxy to a public origin: the peer is a Cloudflare edge IP.
    A direct public attacker forging CF-Connecting-IP would present neither, so we
    refuse to trust the header for them.
    """
    if not client_host:
        return False
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    for cidr in _CLOUDFLARE_CIDRS:
        if addr in ipaddress.ip_network(cidr):
            return True
    return False


class IPAllowlistService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def extract_request_ip(
        *,
        x_forwarded_for: str | None,
        client_host: str | None,
        cf_connecting_ip: str | None = None,
    ) -> str | None:
        """Resolve the real client IP from a request's forwarded headers.

        Priority (both forwarded sources are opt-in and default OFF):
          1. CF-Connecting-IP when BEHIND_CLOUDFLARE_TUNNEL and the upstream hop is
             a trusted Cloudflare/tunnel peer. The edge sets this to the real client
             and rejects client-supplied values, so it is unspoofable through CF.
          2. X-Forwarded-For read from the RIGHT, skipping TRUSTED_PROXY_COUNT
             trusted-proxy hops -- i.e. parts[-TRUSTED_PROXY_COUNT]. Client-prepended
             values sit to the left of the entries our own proxies appended and are
             never read.
          3. The raw socket peer (client.host).

        With the safe defaults (TRUSTED_PROXY_COUNT=0, BEHIND_CLOUDFLARE_TUNNEL off)
        only (3) applies: no forwarded header is ever trusted.
        """
        settings = get_settings()

        if settings.BEHIND_CLOUDFLARE_TUNNEL and cf_connecting_ip:
            candidate = cf_connecting_ip.strip()
            if _is_valid_ip(candidate) and _is_trusted_cf_upstream(client_host):
                return candidate

        if settings.TRUSTED_PROXY_COUNT > 0 and x_forwarded_for:
            parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
            if len(parts) >= settings.TRUSTED_PROXY_COUNT:
                candidate = parts[-settings.TRUSTED_PROXY_COUNT]
                if _is_valid_ip(candidate):
                    return candidate

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
