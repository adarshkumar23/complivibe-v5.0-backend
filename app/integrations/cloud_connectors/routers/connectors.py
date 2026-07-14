import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.finding_mapping_service import FindingControlMappingService
from app.integrations.cloud_connectors.schemas import (
    ConnectorCreate,
    ConnectorCreateResponse,
    ConnectorHealthRead,
    ConnectorRead,
    ConnectorSecretRotateResponse,
    ConnectorSetupRead,
    ConnectorUpdate,
    DismissSuggestionRequest,
    FindingSuggestionRead,
    MappingRuleCreate,
    MappingRuleRead,
    MappingRuleUpdate,
)
from app.integrations.cloud_connectors.setup_instructions import build_setup_payload
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/cloud-connectors", tags=["cloud-evidence-connectors"])


@router.post("", response_model=ConnectorCreateResponse, status_code=status.HTTP_201_CREATED)
def create_connector(
    payload: ConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorCreateResponse:
    row, plaintext_secret = CloudConnectorService(db).create_connector(
        organization.id,
        payload.connector_type,
        payload.display_name,
        payload.provider_config_json,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ConnectorCreateResponse(connector=ConnectorRead.model_validate(row), signing_secret=plaintext_secret)


@router.get("", response_model=list[ConnectorRead])
def list_connectors(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> list[ConnectorRead]:
    rows = CloudConnectorService(db).list_connectors(organization.id)
    return [ConnectorRead.model_validate(row) for row in rows]


@router.post("/mapping-rules", response_model=MappingRuleRead, status_code=status.HTTP_201_CREATED)
def create_mapping_rule(
    payload: MappingRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> MappingRuleRead:
    rule = FindingControlMappingService(db).create_mapping_rule(
        organization.id,
        payload.finding_category,
        payload.target_control_id,
        payload.target_control_common_tag,
        payload.confidence,
        current_user.id,
    )
    db.commit()
    db.refresh(rule)
    return MappingRuleRead.model_validate(rule)


@router.get("/mapping-rules", response_model=list[MappingRuleRead])
def list_mapping_rules(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> list[MappingRuleRead]:
    rows = FindingControlMappingService(db).list_mapping_rules(organization.id)
    return [MappingRuleRead.model_validate(row) for row in rows]


@router.get("/mapping-rules/{rule_id}", response_model=MappingRuleRead)
def get_mapping_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> MappingRuleRead:
    rule = FindingControlMappingService(db).get_mapping_rule(organization.id, rule_id)
    return MappingRuleRead.model_validate(rule)


@router.patch("/mapping-rules/{rule_id}", response_model=MappingRuleRead)
def update_mapping_rule(
    rule_id: uuid.UUID,
    payload: MappingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> MappingRuleRead:
    rule = FindingControlMappingService(db).update_mapping_rule(
        organization.id,
        rule_id,
        payload.target_control_id,
        payload.target_control_common_tag,
        payload.confidence,
        payload.is_active,
        current_user.id,
    )
    db.commit()
    db.refresh(rule)
    return MappingRuleRead.model_validate(rule)


@router.delete("/mapping-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> None:
    FindingControlMappingService(db).delete_mapping_rule(organization.id, rule_id, current_user.id)
    db.commit()


@router.get("/{connector_id}", response_model=ConnectorRead)
def get_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorRead:
    row = CloudConnectorService(db).get_connector(organization.id, connector_id)
    return ConnectorRead.model_validate(row)


@router.patch("/{connector_id}", response_model=ConnectorRead)
def update_connector(
    connector_id: uuid.UUID,
    payload: ConnectorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorRead:
    row = CloudConnectorService(db).update_connector(
        organization.id, connector_id, payload.model_dump(exclude_unset=True), current_user.id
    )
    db.commit()
    db.refresh(row)
    return ConnectorRead.model_validate(row)


@router.get("/{connector_id}/health", response_model=ConnectorHealthRead)
def get_connector_health(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorHealthRead:
    return ConnectorHealthRead(**CloudConnectorService(db).health(organization.id, connector_id))


@router.get("/{connector_id}/setup", response_model=ConnectorSetupRead)
def get_connector_setup(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorSetupRead:
    service = CloudConnectorService(db)
    connector = service.get_connector(organization.id, connector_id)
    # Signing secret is only ever revealed in the create response; setup always redacts it.
    payload = build_setup_payload(connector.connector_type, connector.webhook_token, signing_secret=None)
    return ConnectorSetupRead(**payload)


@router.post("/{connector_id}/activate", response_model=ConnectorRead)
def activate_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorRead:
    row = CloudConnectorService(db).activate_connector(organization.id, connector_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConnectorRead.model_validate(row)


@router.post("/{connector_id}/rotate-secret", response_model=ConnectorSecretRotateResponse)
def rotate_connector_secret(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorSecretRotateResponse:
    row, new_secret = CloudConnectorService(db).rotate_secret(organization.id, connector_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConnectorSecretRotateResponse(connector=ConnectorRead.model_validate(row), signing_secret=new_secret)


@router.post("/{connector_id}/disable", response_model=ConnectorRead)
def disable_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorRead:
    row = CloudConnectorService(db).disable_connector(organization.id, connector_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConnectorRead.model_validate(row)


@router.post("/suggestions/{suggestion_id}/apply", response_model=FindingSuggestionRead)
def apply_finding_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> FindingSuggestionRead:
    row = FindingControlMappingService(db).apply_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    db.refresh(row)
    return FindingSuggestionRead.model_validate(row)


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=FindingSuggestionRead)
def dismiss_finding_suggestion(
    suggestion_id: uuid.UUID,
    payload: DismissSuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> FindingSuggestionRead:
    row = FindingControlMappingService(db).dismiss_suggestion(organization.id, suggestion_id, payload.reason, current_user.id)
    db.commit()
    db.refresh(row)
    return FindingSuggestionRead.model_validate(row)
