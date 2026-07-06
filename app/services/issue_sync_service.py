from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import requests
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.models.external_sync_connection import ExternalSyncConnection
from app.models.external_sync_event import ExternalSyncEvent
from app.models.external_sync_link import ExternalSyncLink
from app.models.issue import Issue
from app.models.issue_sync_comment import IssueSyncComment
from app.schemas.issue_sync import IssueSyncConnectionCreate, IssueSyncConnectionUpdate, IssueSyncLinkCreate, IssueSyncOutboundRequest
from app.services.audit_service import AuditService

# External API reference points (verified July 2026):
# - Jira Cloud webhooks + REST v3 issues/comments/transitions:
#   https://developer.atlassian.com/cloud/jira/platform/webhooks/
#   https://developer.atlassian.com/cloud/jira/platform/rest/v3/
# - Linear webhooks + GraphQL API:
#   https://linear.app/developers/webhooks
#   https://linear.app/developers/graphql


class IssueSyncService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_connection(self, org_id: uuid.UUID, connection_id: uuid.UUID) -> ExternalSyncConnection:
        row = self.db.execute(
            select(ExternalSyncConnection).where(
                ExternalSyncConnection.organization_id == org_id,
                ExternalSyncConnection.id == connection_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue sync connection not found")
        return row

    def _require_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
        return IssueService(self.db).get_issue(org_id, issue_id)

    def _log_event(
        self,
        *,
        org_id: uuid.UUID,
        connection: ExternalSyncConnection,
        direction: str,
        event_type: str,
        status_value: str,
        payload_json: dict[str, Any],
        error_message: str | None = None,
        external_event_id: str | None = None,
    ) -> ExternalSyncEvent:
        row = ExternalSyncEvent(
            organization_id=org_id,
            connection_id=connection.id,
            provider=connection.provider,
            direction=direction,
            entity_type="issue",
            event_type=event_type,
            external_event_id=external_event_id,
            status=status_value,
            payload_json=payload_json,
            error_message=error_message,
            processed_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _direction_allows(direction_mode: str, wanted: str) -> bool:
        if direction_mode == "two_way":
            return True
        if direction_mode == "inbound_only":
            return wanted == "inbound"
        if direction_mode == "outbound_only":
            return wanted == "outbound"
        return False

    def create_connection(self, org_id: uuid.UUID, payload: IssueSyncConnectionCreate, actor_user_id: uuid.UUID) -> ExternalSyncConnection:
        row = ExternalSyncConnection(
            organization_id=org_id,
            name=payload.name,
            provider=payload.provider,
            entity_type=payload.entity_type,
            direction_mode=payload.direction_mode,
            is_active=payload.is_active,
            project_ref=payload.project_ref,
            api_base_url=payload.api_base_url,
            credentials_json=dict(payload.credentials_json or {}),
            webhook_secret=payload.webhook_secret,
            field_mapping_json=dict(payload.field_mapping_json or {}),
            created_by=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.write_audit_log(
            action="issue_sync.connection_created",
            entity_type="external_sync_connection",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "provider": row.provider,
                "direction_mode": row.direction_mode,
                "entity_type": row.entity_type,
                "is_active": row.is_active,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_connections(self, org_id: uuid.UUID) -> list[ExternalSyncConnection]:
        return self.db.execute(
            select(ExternalSyncConnection)
            .where(ExternalSyncConnection.organization_id == org_id)
            .order_by(ExternalSyncConnection.created_at.desc())
        ).scalars().all()

    def update_connection(
        self,
        org_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: IssueSyncConnectionUpdate,
        actor_user_id: uuid.UUID,
    ) -> ExternalSyncConnection:
        row = self._require_connection(org_id, connection_id)
        before = {
            "name": row.name,
            "direction_mode": row.direction_mode,
            "is_active": row.is_active,
            "project_ref": row.project_ref,
            "api_base_url": row.api_base_url,
            "webhook_secret": row.webhook_secret,
        }
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            if key in {"credentials_json", "field_mapping_json"} and value is not None:
                setattr(row, key, dict(value))
            else:
                setattr(row, key, value)
        self.db.flush()
        self.audit.write_audit_log(
            action="issue_sync.connection_updated",
            entity_type="external_sync_connection",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "name": row.name,
                "direction_mode": row.direction_mode,
                "is_active": row.is_active,
                "project_ref": row.project_ref,
                "api_base_url": row.api_base_url,
                "webhook_secret": row.webhook_secret,
            },
            metadata_json={"source": "api"},
        )
        return row

    def upsert_link(
        self,
        org_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: IssueSyncLinkCreate,
        actor_user_id: uuid.UUID | None,
    ) -> ExternalSyncLink:
        connection = self._require_connection(org_id, connection_id)
        self._require_issue(org_id, payload.internal_entity_id)
        row = self.db.execute(
            select(ExternalSyncLink).where(
                ExternalSyncLink.organization_id == org_id,
                ExternalSyncLink.connection_id == connection.id,
                ExternalSyncLink.entity_type == "issue",
                ExternalSyncLink.internal_entity_id == payload.internal_entity_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = ExternalSyncLink(
                organization_id=org_id,
                connection_id=connection.id,
                entity_type="issue",
                internal_entity_id=payload.internal_entity_id,
                external_entity_id=payload.external_entity_id,
                external_key=payload.external_key,
                last_synced_at=None,
                last_status=None,
            )
            self.db.add(row)
            self.db.flush()
            self.audit.write_audit_log(
                action="issue_sync.link_created",
                entity_type="external_sync_link",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={
                    "connection_id": str(connection.id),
                    "internal_entity_id": str(row.internal_entity_id),
                    "external_entity_id": row.external_entity_id,
                },
                metadata_json={"source": "api"},
            )
            return row

        before = {"external_entity_id": row.external_entity_id, "external_key": row.external_key}
        row.external_entity_id = payload.external_entity_id
        row.external_key = payload.external_key
        self.db.flush()
        self.audit.write_audit_log(
            action="issue_sync.link_updated",
            entity_type="external_sync_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"external_entity_id": row.external_entity_id, "external_key": row.external_key},
            metadata_json={"source": "api"},
        )
        return row

    def _get_link_by_external(
        self, org_id: uuid.UUID, connection_id: uuid.UUID, external_entity_id: str | None, external_key: str | None
    ) -> ExternalSyncLink | None:
        if external_entity_id:
            row = self.db.execute(
                select(ExternalSyncLink).where(
                    ExternalSyncLink.organization_id == org_id,
                    ExternalSyncLink.connection_id == connection_id,
                    ExternalSyncLink.external_entity_id == external_entity_id,
                )
            ).scalar_one_or_none()
            if row is not None:
                return row
        if external_key:
            return self.db.execute(
                select(ExternalSyncLink).where(
                    ExternalSyncLink.organization_id == org_id,
                    ExternalSyncLink.connection_id == connection_id,
                    ExternalSyncLink.external_key == external_key,
                )
            ).scalar_one_or_none()
        return None

    def _jira_request(self, connection: ExternalSyncConnection, *, method: str, path: str, json_body: dict | None = None) -> dict:
        base_url = (connection.api_base_url or "").rstrip("/")
        if not base_url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="jira api_base_url is required")
        creds = dict(connection.credentials_json or {})
        email = creds.get("email")
        api_token = creds.get("api_token")
        if not email or not api_token:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="jira email and api_token are required")
        response = requests.request(
            method=method,
            url=f"{base_url}{path}",
            json=json_body,
            auth=(email, api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=25,
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"jira api error {response.status_code}: {response.text[:300]}",
            )
        if not response.text:
            return {}
        return response.json()

    def _linear_request(self, connection: ExternalSyncConnection, *, query: str, variables: dict[str, Any]) -> dict:
        base_url = (connection.api_base_url or "https://api.linear.app").rstrip("/")
        creds = dict(connection.credentials_json or {})
        api_key = creds.get("api_key")
        if not api_key:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="linear api_key is required")
        response = requests.post(
            f"{base_url}/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=25,
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"linear api error {response.status_code}: {response.text[:300]}",
            )
        payload = response.json()
        if payload.get("errors"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"linear api error: {payload['errors'][0]}")
        return payload.get("data", {})

    def _send_outbound_jira(
        self,
        *,
        connection: ExternalSyncConnection,
        link: ExternalSyncLink,
        issue: Issue,
        include_status: bool,
        include_comment: bool,
        comment_body: str | None,
    ) -> dict:
        mapping = dict(connection.field_mapping_json or {})
        status_map = dict(mapping.get("internal_to_jira_status", {}) or {})
        external_status = status_map.get(issue.status, issue.status)
        if include_status:
            transitions = self._jira_request(
                connection, method="GET", path=f"/rest/api/3/issue/{link.external_entity_id}/transitions"
            ).get("transitions", [])
            target = None
            for item in transitions:
                to_name = str(((item or {}).get("to") or {}).get("name") or "")
                if to_name.lower() == str(external_status).lower():
                    target = item
                    break
            if target is not None:
                self._jira_request(
                    connection,
                    method="POST",
                    path=f"/rest/api/3/issue/{link.external_entity_id}/transitions",
                    json_body={"transition": {"id": target["id"]}},
                )
        if include_comment and comment_body:
            self._jira_request(
                connection,
                method="POST",
                path=f"/rest/api/3/issue/{link.external_entity_id}/comment",
                json_body={
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_body}]}],
                    }
                },
            )
        return {"provider": "jira", "external_status": external_status}

    def _send_outbound_linear(
        self,
        *,
        connection: ExternalSyncConnection,
        link: ExternalSyncLink,
        issue: Issue,
        include_status: bool,
        include_comment: bool,
        comment_body: str | None,
    ) -> dict:
        mapping = dict(connection.field_mapping_json or {})
        state_map = dict(mapping.get("internal_to_linear_state_id", {}) or {})
        state_id = state_map.get(issue.status)
        if include_status and state_id:
            self._linear_request(
                connection,
                query="mutation($id:String!,$stateId:String!){ issueUpdate(id:$id,input:{stateId:$stateId}){ success } }",
                variables={"id": link.external_entity_id, "stateId": state_id},
            )
        if include_comment and comment_body:
            self._linear_request(
                connection,
                query="mutation($issueId:String!,$body:String!){ commentCreate(input:{issueId:$issueId, body:$body}){ success } }",
                variables={"issueId": link.external_entity_id, "body": comment_body},
            )
        return {"provider": "linear", "state_id": state_id}

    def run_outbound_sync(
        self,
        *,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: IssueSyncOutboundRequest,
    ) -> ExternalSyncEvent:
        connection = self._require_connection(org_id, connection_id)
        if not connection.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Issue sync connection is inactive")
        if not self._direction_allows(connection.direction_mode, "outbound"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connection does not allow outbound sync")
        issue = self._require_issue(org_id, payload.issue_id)
        link = self.db.execute(
            select(ExternalSyncLink).where(
                ExternalSyncLink.organization_id == org_id,
                ExternalSyncLink.connection_id == connection.id,
                ExternalSyncLink.internal_entity_id == issue.id,
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No sync link found for issue")
        comment_body = (payload.comment_body or "").strip() or None
        if payload.include_comment and not comment_body:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="comment_body is required when include_comment is true")
        try:
            if connection.provider == "jira":
                details = self._send_outbound_jira(
                    connection=connection,
                    link=link,
                    issue=issue,
                    include_status=payload.include_status,
                    include_comment=payload.include_comment,
                    comment_body=comment_body,
                )
            else:
                details = self._send_outbound_linear(
                    connection=connection,
                    link=link,
                    issue=issue,
                    include_status=payload.include_status,
                    include_comment=payload.include_comment,
                    comment_body=comment_body,
                )
            if payload.include_comment and comment_body:
                row = IssueSyncComment(
                    organization_id=org_id,
                    issue_id=issue.id,
                    provider="internal",
                    direction="outbound",
                    external_comment_id=None,
                    body=comment_body,
                    author_ref=str(actor_user_id),
                    created_by_user_id=actor_user_id,
                )
                self.db.add(row)
            link.last_synced_at = self.utcnow()
            link.last_status = issue.status
            event = self._log_event(
                org_id=org_id,
                connection=connection,
                direction="outbound",
                event_type="issue.outbound_sync",
                status_value="processed",
                payload_json={"issue_id": str(issue.id), "details": details},
            )
            self.audit.write_audit_log(
                action="issue_sync.outbound_synced",
                entity_type="external_sync_event",
                entity_id=event.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={"provider": connection.provider, "issue_id": str(issue.id), "status": issue.status},
                metadata_json={"source": "api"},
            )
            return event
        except HTTPException as exc:
            event = self._log_event(
                org_id=org_id,
                connection=connection,
                direction="outbound",
                event_type="issue.outbound_sync",
                status_value="failed",
                payload_json={"issue_id": str(issue.id)},
                error_message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            )
            self.audit.write_audit_log(
                action="issue_sync.outbound_failed",
                entity_type="external_sync_event",
                entity_id=event.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={"provider": connection.provider, "issue_id": str(issue.id)},
                metadata_json={"source": "api"},
            )
            raise

    def _map_external_status(self, connection: ExternalSyncConnection, *, provider_status: str) -> str | None:
        mapping = dict(connection.field_mapping_json or {})
        key = "jira_status_to_internal" if connection.provider == "jira" else "linear_status_to_internal"
        status_map = dict(mapping.get(key, {}) or {})
        if provider_status in status_map:
            return status_map[provider_status]
        lowered = provider_status.lower()
        for k, v in status_map.items():
            if str(k).lower() == lowered:
                return v
        return None

    def _apply_inbound_issue_status(self, org_id: uuid.UUID, issue: Issue, status_value: str, actor_user_id: uuid.UUID | None) -> bool:
        mapped = status_value.strip().lower()
        if not mapped or mapped == issue.status:
            return False
        actor = actor_user_id or issue.owner_id
        IssueService(self.db).transition_issue(
            org_id,
            issue.id,
            mapped,
            actor,
            notes=f"inbound sync status update from external provider ({status_value})",
        )
        return True

    def _create_inbound_comment(
        self,
        *,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        provider: str,
        external_comment_id: str | None,
        body: str,
        author_ref: str | None,
    ) -> None:
        if not body.strip():
            return
        row = IssueSyncComment(
            organization_id=org_id,
            issue_id=issue_id,
            provider=provider,
            direction="inbound",
            external_comment_id=external_comment_id,
            body=body[:5000],
            author_ref=author_ref,
            created_by_user_id=None,
        )
        self.db.add(row)

    def _process_inbound_common(
        self,
        *,
        org_id: uuid.UUID,
        connection: ExternalSyncConnection,
        external_entity_id: str | None,
        external_key: str | None,
        external_status: str | None,
        comment_body: str | None,
        external_comment_id: str | None,
        author_ref: str | None,
        payload_json: dict[str, Any],
        external_event_id: str | None,
    ) -> ExternalSyncEvent:
        link = self._get_link_by_external(org_id, connection.id, external_entity_id, external_key)
        if link is None:
            event = self._log_event(
                org_id=org_id,
                connection=connection,
                direction="inbound",
                event_type="issue.webhook",
                status_value="ignored",
                payload_json=payload_json,
                error_message="No sync link for external issue",
                external_event_id=external_event_id,
            )
            return event
        issue = self._require_issue(org_id, link.internal_entity_id)
        changed = False
        mapped_status = self._map_external_status(connection, provider_status=external_status or "") if external_status else None
        if mapped_status:
            changed = self._apply_inbound_issue_status(org_id, issue, mapped_status, actor_user_id=connection.created_by) or changed
            link.last_status = mapped_status
        if comment_body and comment_body.strip():
            self._create_inbound_comment(
                org_id=org_id,
                issue_id=issue.id,
                provider=connection.provider,
                external_comment_id=external_comment_id,
                body=comment_body,
                author_ref=author_ref,
            )
            changed = True
        link.last_synced_at = self.utcnow()
        event = self._log_event(
            org_id=org_id,
            connection=connection,
            direction="inbound",
            event_type="issue.webhook",
            status_value="processed",
            payload_json=payload_json,
            external_event_id=external_event_id,
        )
        self.audit.write_audit_log(
            action="issue_sync.inbound_processed",
            entity_type="external_sync_event",
            entity_id=event.id,
            organization_id=org_id,
            actor_user_id=connection.created_by,
            after_json={"provider": connection.provider, "changed": changed, "issue_id": str(issue.id)},
            metadata_json={"source": "webhook"},
        )
        return event

    def ingest_jira_webhook(self, *, org_id: uuid.UUID, connection_id: uuid.UUID, payload: dict[str, Any]) -> ExternalSyncEvent:
        connection = self._require_connection(org_id, connection_id)
        if connection.provider != "jira":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connection provider is not jira")
        if not self._direction_allows(connection.direction_mode, "inbound"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connection does not allow inbound sync")

        issue_obj = dict(payload.get("issue") or {})
        fields = dict(issue_obj.get("fields") or {})
        status_obj = dict(fields.get("status") or {})
        comment_obj = dict(payload.get("comment") or {})
        comment_body = comment_obj.get("body")
        if isinstance(comment_body, dict):
            comment_body = str(comment_body)
        event_id = payload.get("timestamp")
        return self._process_inbound_common(
            org_id=org_id,
            connection=connection,
            external_entity_id=str(issue_obj.get("id")) if issue_obj.get("id") else None,
            external_key=issue_obj.get("key"),
            external_status=status_obj.get("name"),
            comment_body=str(comment_body) if comment_body else None,
            external_comment_id=str(comment_obj.get("id")) if comment_obj.get("id") else None,
            author_ref=str(((comment_obj.get("author") or {}).get("accountId") or "")) or None,
            payload_json=payload,
            external_event_id=str(event_id) if event_id is not None else None,
        )

    def ingest_linear_webhook(self, *, org_id: uuid.UUID, connection_id: uuid.UUID, payload: dict[str, Any]) -> ExternalSyncEvent:
        connection = self._require_connection(org_id, connection_id)
        if connection.provider != "linear":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connection provider is not linear")
        if not self._direction_allows(connection.direction_mode, "inbound"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Connection does not allow inbound sync")

        data = dict(payload.get("data") or {})
        issue_data = dict(data.get("issue") or {}) if isinstance(data.get("issue"), dict) else {}
        state_data = dict(data.get("state") or {}) if isinstance(data.get("state"), dict) else {}
        comment_data = dict(data.get("comment") or {}) if isinstance(data.get("comment"), dict) else {}

        external_issue_id = str(data.get("id") or issue_data.get("id") or "") or None
        external_key = str(data.get("identifier") or issue_data.get("identifier") or "") or None
        external_status = str(state_data.get("name") or data.get("stateName") or "") or None
        comment_body = str(data.get("body") or comment_data.get("body") or "") or None
        external_comment_id = str(data.get("commentId") or comment_data.get("id") or "") or None
        author_ref = str(((data.get("user") or {}).get("id") or "")) or None if isinstance(data.get("user"), dict) else None
        event_id = str(payload.get("id") or payload.get("eventId") or "") or None
        return self._process_inbound_common(
            org_id=org_id,
            connection=connection,
            external_entity_id=external_issue_id,
            external_key=external_key,
            external_status=external_status,
            comment_body=comment_body,
            external_comment_id=external_comment_id,
            author_ref=author_ref,
            payload_json=payload,
            external_event_id=event_id,
        )

    def list_events(self, org_id: uuid.UUID, connection_id: uuid.UUID, limit: int) -> list[ExternalSyncEvent]:
        self._require_connection(org_id, connection_id)
        return self.db.execute(
            select(ExternalSyncEvent)
            .where(
                ExternalSyncEvent.organization_id == org_id,
                ExternalSyncEvent.connection_id == connection_id,
            )
            .order_by(ExternalSyncEvent.processed_at.desc())
            .limit(limit)
        ).scalars().all()

    def list_issue_comments(self, org_id: uuid.UUID, issue_id: uuid.UUID, limit: int) -> list[IssueSyncComment]:
        self._require_issue(org_id, issue_id)
        return self.db.execute(
            select(IssueSyncComment)
            .where(
                IssueSyncComment.organization_id == org_id,
                IssueSyncComment.issue_id == issue_id,
            )
            .order_by(IssueSyncComment.created_at.desc())
            .limit(limit)
        ).scalars().all()
