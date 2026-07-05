from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.vendor_supply_chain import VendorSupplyChainGraphRead, VendorSupplyChainLinkCreate, VendorSupplyChainLinkRead
from app.services.audit_service import AuditService
from app.services.vendor_supply_chain_service import VendorSupplyChainService

router = APIRouter(prefix="/vendors", tags=["vendor-supply-chain"])


def _link_response(row) -> dict:
    return {
        "id": row.id,
        "parent_vendor_id": row.parent_vendor_id,
        "sub_vendor_id": row.sub_vendor_id,
        "relationship_type": row.relationship_type,
        "description": row.description,
        "is_active": row.is_active,
    }


@router.post("/{vendor_id}/supply-chain-links", response_model=VendorSupplyChainLinkRead, status_code=status.HTTP_201_CREATED)
def create_vendor_supply_chain_link(
    vendor_id: uuid.UUID,
    payload: VendorSupplyChainLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_supply_chain:manage")),
) -> dict:
    service = VendorSupplyChainService(db)
    row = service.create_link(
        organization_id=organization.id,
        parent_vendor_id=vendor_id,
        sub_vendor_id=payload.sub_vendor_id,
        relationship_type=payload.relationship_type,
        description=payload.description,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="vendor_supply_chain.link_created",
        entity_type="vendor_supply_chain_link",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "parent_vendor_id": str(row.parent_vendor_id),
            "sub_vendor_id": str(row.sub_vendor_id),
            "relationship_type": row.relationship_type,
        },
        metadata_json={"source": "phase2_tprm_intelligence"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _link_response(row)


@router.delete("/supply-chain-links/{link_id}", response_model=VendorSupplyChainLinkRead)
def deactivate_vendor_supply_chain_link(
    link_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_supply_chain:manage")),
) -> dict:
    row = VendorSupplyChainService(db).deactivate_link(organization_id=organization.id, link_id=link_id, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="vendor_supply_chain.link_deactivated",
        entity_type="vendor_supply_chain_link",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"is_active": True},
        after_json={"is_active": False, "deactivated_at": row.deactivated_at.isoformat() if row.deactivated_at else None},
        metadata_json={"source": "phase2_tprm_intelligence"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _link_response(row)


@router.get("/{vendor_id}/supply-chain-graph", response_model=VendorSupplyChainGraphRead)
def get_vendor_supply_chain_graph(
    vendor_id: uuid.UUID,
    depth: int = 3,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_supply_chain:read")),
) -> dict:
    return VendorSupplyChainService(db).build_graph(organization_id=organization.id, root_vendor_id=vendor_id, depth=depth)
