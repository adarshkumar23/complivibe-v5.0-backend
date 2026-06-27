import base64
import hashlib
import json
import secrets
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data_observability.integrations.openlineage_receiver import OpenLineageReceiver
from app.data_observability.integrations.openmetadata_client import OpenMetadataClient
from app.models.data_asset import DataAsset
from app.models.data_lineage_edge import DataLineageEdge
from app.models.data_lineage_node import DataLineageNode
from app.models.openmetadata_integration import OpenMetadataIntegration
from app.services.audit_service import AuditService

ALLOWED_NODE_TYPES = {
    "data_asset",
    "transform",
    "external_source",
    "external_destination",
    "api_endpoint",
    "pipeline_step",
}
ALLOWED_SOURCE_METHODS = {"manual", "openlineage_event", "openmetadata_sync"}


class LineageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_api_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _fernet() -> Fernet:
        settings = get_settings()
        key_value = getattr(settings, "OPENMETADATA_CONFIG_ENCRYPTION_KEY", None) or settings.SECRET_KEY
        digest = hashlib.sha256(key_value.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @classmethod
    def encrypt_config(cls, config: dict) -> str:
        payload = json.dumps(config, sort_keys=True)
        return cls._fernet().encrypt(payload.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt_config(cls, config_json: str) -> dict:
        raw = cls._fernet().decrypt(config_json.encode("utf-8")).decode("utf-8")
        return json.loads(raw)

    def _require_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> DataAsset:
        row = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.id == asset_id,
                DataAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
        return row

    def _require_node(self, org_id: uuid.UUID, node_id: uuid.UUID) -> DataLineageNode:
        row = self.db.execute(
            select(DataLineageNode).where(
                DataLineageNode.organization_id == org_id,
                DataLineageNode.id == node_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineage node not found")
        return row

    def _require_openmetadata_integration(self, org_id: uuid.UUID) -> OpenMetadataIntegration:
        row = self.db.execute(
            select(OpenMetadataIntegration).where(OpenMetadataIntegration.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenMetadata integration not found")
        return row

    def create_node(self, org_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> DataLineageNode:
        payload = data.model_dump()
        if payload["node_type"] not in ALLOWED_NODE_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid node_type")
        if payload.get("data_asset_id") is not None:
            self._require_asset(org_id, payload["data_asset_id"])

        existing = self.db.execute(
            select(DataLineageNode).where(
                DataLineageNode.organization_id == org_id,
                DataLineageNode.name == payload["name"],
                DataLineageNode.system_name == payload.get("system_name"),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = self.utcnow()
        row = DataLineageNode(
            organization_id=org_id,
            node_type=payload["node_type"],
            data_asset_id=payload.get("data_asset_id"),
            name=payload["name"],
            description=payload.get("description"),
            system_name=payload.get("system_name"),
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="lineage.node_created",
            entity_type="data_lineage_node",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"node_type": row.node_type, "name": row.name, "system_name": row.system_name},
            metadata_json={"source": "api"},
        )
        return row

    def get_node(self, org_id: uuid.UUID, node_id: uuid.UUID) -> DataLineageNode:
        return self._require_node(org_id, node_id)

    def list_nodes(self, org_id: uuid.UUID, node_type: str | None = None, data_asset_id: uuid.UUID | None = None) -> list[DataLineageNode]:
        stmt = select(DataLineageNode).where(DataLineageNode.organization_id == org_id)
        if node_type is not None:
            if node_type not in ALLOWED_NODE_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid node_type filter")
            stmt = stmt.where(DataLineageNode.node_type == node_type)
        if data_asset_id is not None:
            stmt = stmt.where(DataLineageNode.data_asset_id == data_asset_id)
        return self.db.execute(stmt.order_by(DataLineageNode.created_at.desc())).scalars().all()

    def link_asset_to_node(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, node_id: uuid.UUID, actor_user_id: uuid.UUID) -> DataLineageNode:
        self._require_asset(org_id, data_asset_id)
        row = self._require_node(org_id, node_id)
        row.data_asset_id = data_asset_id
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="lineage.node_updated",
            entity_type="data_lineage_node",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"data_asset_id": str(data_asset_id)},
            metadata_json={"source": "api", "operation": "link_asset_to_node"},
        )
        return row

    def _find_existing_edge(
        self,
        org_id: uuid.UUID,
        upstream_node_id: uuid.UUID,
        downstream_node_id: uuid.UUID,
        pipeline_name: str | None,
    ) -> DataLineageEdge | None:
        pipeline_filter = DataLineageEdge.pipeline_name.is_(None) if pipeline_name is None else DataLineageEdge.pipeline_name == pipeline_name
        return self.db.execute(
            select(DataLineageEdge).where(
                DataLineageEdge.organization_id == org_id,
                DataLineageEdge.upstream_node_id == upstream_node_id,
                DataLineageEdge.downstream_node_id == downstream_node_id,
                pipeline_filter,
            )
        ).scalar_one_or_none()

    def create_edge(
        self,
        org_id: uuid.UUID,
        upstream_node_id: uuid.UUID,
        downstream_node_id: uuid.UUID,
        data,
        source_method: str = "manual",
        actor_user_id: uuid.UUID | None = None,
    ) -> DataLineageEdge:
        if source_method not in ALLOWED_SOURCE_METHODS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid source_method")
        self._require_node(org_id, upstream_node_id)
        self._require_node(org_id, downstream_node_id)

        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        existing = self._find_existing_edge(org_id, upstream_node_id, downstream_node_id, payload.get("pipeline_name"))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lineage edge already exists")

        row = DataLineageEdge(
            organization_id=org_id,
            upstream_node_id=upstream_node_id,
            downstream_node_id=downstream_node_id,
            transformation_description=payload.get("transformation_description"),
            source_method=source_method,
            pipeline_name=payload.get("pipeline_name"),
            pipeline_run_id=payload.get("pipeline_run_id"),
            job_name=payload.get("job_name"),
            event_time=payload.get("event_time"),
            metadata_json=payload.get("metadata") or {},
            created_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        if actor_user_id is not None:
            AuditService(self.db).write_audit_log(
                action="lineage.edge_created",
                entity_type="data_lineage_edge",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={"upstream_node_id": str(upstream_node_id), "downstream_node_id": str(downstream_node_id), "source_method": source_method},
                metadata_json={"source": "api"},
            )
        return row

    def get_edges(self, org_id: uuid.UUID, node_id: uuid.UUID, direction: str = "downstream") -> list[DataLineageEdge]:
        if direction not in {"downstream", "upstream", "both"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid direction")
        self._require_node(org_id, node_id)

        stmt = select(DataLineageEdge).where(DataLineageEdge.organization_id == org_id)
        if direction == "downstream":
            stmt = stmt.where(DataLineageEdge.upstream_node_id == node_id)
        elif direction == "upstream":
            stmt = stmt.where(DataLineageEdge.downstream_node_id == node_id)
        else:
            stmt = stmt.where(
                or_(
                    DataLineageEdge.upstream_node_id == node_id,
                    DataLineageEdge.downstream_node_id == node_id,
                )
            )
        return self.db.execute(stmt.order_by(DataLineageEdge.created_at.desc())).scalars().all()

    def get_lineage_graph(self, org_id: uuid.UUID, data_asset_id: uuid.UUID, depth: int = 3) -> dict:
        depth = max(1, min(int(depth), 5))
        self._require_asset(org_id, data_asset_id)
        start_nodes = self.db.execute(
            select(DataLineageNode).where(
                DataLineageNode.organization_id == org_id,
                DataLineageNode.data_asset_id == data_asset_id,
            )
        ).scalars().all()
        if not start_nodes:
            return {"asset_id": str(data_asset_id), "nodes": [], "edges": []}

        visited_nodes: dict[uuid.UUID, DataLineageNode] = {node.id: node for node in start_nodes}
        visited_edge_ids: set[uuid.UUID] = set()
        collected_edges: list[DataLineageEdge] = []

        queue: deque[tuple[uuid.UUID, int]] = deque((node.id, 0) for node in start_nodes)
        while queue:
            current_node_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            edges = self.db.execute(
                select(DataLineageEdge).where(
                    DataLineageEdge.organization_id == org_id,
                    or_(
                        DataLineageEdge.upstream_node_id == current_node_id,
                        DataLineageEdge.downstream_node_id == current_node_id,
                    ),
                )
            ).scalars().all()
            for edge in edges:
                if edge.id not in visited_edge_ids:
                    visited_edge_ids.add(edge.id)
                    collected_edges.append(edge)

                neighbor_ids = [edge.upstream_node_id, edge.downstream_node_id]
                for neighbor_id in neighbor_ids:
                    if neighbor_id not in visited_nodes:
                        node = self._require_node(org_id, neighbor_id)
                        visited_nodes[neighbor_id] = node
                    queue.append((neighbor_id, current_depth + 1))

        return {
            "asset_id": str(data_asset_id),
            "nodes": [
                {"id": node.id, "name": node.name, "node_type": node.node_type}
                for node in visited_nodes.values()
            ],
            "edges": [
                {
                    "upstream_id": edge.upstream_node_id,
                    "downstream_id": edge.downstream_node_id,
                    "source_method": edge.source_method,
                }
                for edge in collected_edges
            ],
        }

    def process_openlineage_event(self, org_id: uuid.UUID, event: dict, actor_user_id: uuid.UUID | None = None) -> dict:
        result = OpenLineageReceiver().process_event(event=event, org_id=org_id, db=self.db)
        AuditService(self.db).write_audit_log(
            action="lineage.openlineage_event_received",
            entity_type="data_lineage_edge",
            entity_id=None,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"edges_created": result.get("edges_created", 0), "job_name": result.get("job_name")},
            metadata_json={"source": "inbound_event"},
        )
        return result

    def configure_openmetadata(
        self,
        org_id: uuid.UUID,
        base_url: str,
        jwt_token: str,
        created_by: uuid.UUID,
        org_api_key: str | None = None,
    ) -> tuple[OpenMetadataIntegration, str | None]:
        ingest_key = org_api_key or secrets.token_urlsafe(24)
        config_payload = {
            "jwt_token": jwt_token,
            "org_api_key_hash": self.hash_api_key(ingest_key),
        }

        row = self.db.execute(
            select(OpenMetadataIntegration).where(OpenMetadataIntegration.organization_id == org_id)
        ).scalar_one_or_none()
        now = self.utcnow()
        if row is None:
            row = OpenMetadataIntegration(
                organization_id=org_id,
                base_url=base_url,
                config_json=self.encrypt_config(config_payload),
                last_synced_at=None,
                sync_status=None,
                last_sync_error=None,
                is_active=True,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.base_url = base_url
            row.config_json = self.encrypt_config(config_payload)
            row.is_active = True
            row.updated_at = now
        self.db.flush()
        return row, ingest_key

    def get_openmetadata_status(self, org_id: uuid.UUID) -> OpenMetadataIntegration | None:
        return self.db.execute(
            select(OpenMetadataIntegration).where(OpenMetadataIntegration.organization_id == org_id)
        ).scalar_one_or_none()

    def list_active_openmetadata_integrations(self) -> list[OpenMetadataIntegration]:
        return self.db.execute(
            select(OpenMetadataIntegration).where(OpenMetadataIntegration.is_active.is_(True))
        ).scalars().all()

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        if not raw_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        key_hash = self.hash_api_key(raw_key)

        integrations = self.list_active_openmetadata_integrations()
        for integration in integrations:
            try:
                config = self.decrypt_config(integration.config_json)
            except Exception:
                continue
            if config.get("org_api_key_hash") == key_hash:
                return integration.organization_id
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    def _get_or_create_node_by_name(self, org_id: uuid.UUID, name: str, node_type: str, system_name: str | None = None) -> tuple[DataLineageNode, bool]:
        row = self.db.execute(
            select(DataLineageNode).where(
                DataLineageNode.organization_id == org_id,
                DataLineageNode.name == name,
                DataLineageNode.system_name == system_name,
            )
        ).scalar_one_or_none()
        if row is not None:
            return row, False

        now = self.utcnow()
        row = DataLineageNode(
            organization_id=org_id,
            node_type=node_type,
            data_asset_id=None,
            name=name,
            description=None,
            system_name=system_name,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return row, True

    def _upsert_edge(
        self,
        org_id: uuid.UUID,
        upstream_node_id: uuid.UUID,
        downstream_node_id: uuid.UUID,
        source_method: str,
        pipeline_name: str | None,
        pipeline_run_id: str | None,
        job_name: str | None,
        event_time: datetime | None,
        metadata: dict,
    ) -> tuple[DataLineageEdge, bool]:
        existing = self._find_existing_edge(org_id, upstream_node_id, downstream_node_id, pipeline_name)
        if existing is not None:
            existing.pipeline_run_id = pipeline_run_id
            existing.job_name = job_name
            existing.event_time = event_time
            existing.metadata_json = metadata or {}
            self.db.flush()
            return existing, False

        row = DataLineageEdge(
            organization_id=org_id,
            upstream_node_id=upstream_node_id,
            downstream_node_id=downstream_node_id,
            transformation_description=None,
            source_method=source_method,
            pipeline_name=pipeline_name,
            pipeline_run_id=pipeline_run_id,
            job_name=job_name,
            event_time=event_time,
            metadata_json=metadata or {},
            created_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        return row, True

    def sync_openmetadata(self, org_id: uuid.UUID, triggered_by: uuid.UUID) -> dict:
        integration = self.get_openmetadata_status(org_id)
        if integration is None or not integration.is_active:
            return {"skipped": True, "tables_seen": 0, "nodes_created": 0, "edges_created": 0}

        integration.sync_status = "in_progress"
        integration.updated_at = self.utcnow()
        self.db.flush()

        try:
            config = self.decrypt_config(integration.config_json)
            client = OpenMetadataClient(base_url=integration.base_url, jwt_token=str(config["jwt_token"]))

            tables = client.list_tables(limit=100, offset=0)
            nodes_created = 0
            edges_created = 0

            for table in tables:
                table_name = str(table.get("fullyQualifiedName") or table.get("name") or table.get("id") or "unknown")
                table_node, created = self._get_or_create_node_by_name(org_id, table_name, "data_asset", "OpenMetadata")
                if created:
                    nodes_created += 1

                entity_id = str(table.get("id") or "")
                if not entity_id:
                    continue
                lineage_data = client.get_lineage(entity_id)
                mapped_edges = client.map_lineage_to_edges(lineage_data=lineage_data, org_id=org_id)
                for edge in mapped_edges:
                    upstream_node, upstream_created = self._get_or_create_node_by_name(
                        org_id,
                        edge["upstream_name"],
                        "external_source",
                        "OpenMetadata",
                    )
                    downstream_node, downstream_created = self._get_or_create_node_by_name(
                        org_id,
                        edge["downstream_name"],
                        "external_destination",
                        "OpenMetadata",
                    )
                    nodes_created += int(upstream_created) + int(downstream_created)
                    _, is_created = self._upsert_edge(
                        org_id=org_id,
                        upstream_node_id=upstream_node.id,
                        downstream_node_id=downstream_node.id,
                        source_method="openmetadata_sync",
                        pipeline_name="openmetadata",
                        pipeline_run_id=None,
                        job_name=None,
                        event_time=self.utcnow(),
                        metadata={"table": table_name},
                    )
                    edges_created += int(is_created)

            integration.last_synced_at = self.utcnow()
            integration.sync_status = "success"
            integration.last_sync_error = None
            integration.updated_at = self.utcnow()
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="lineage.openmetadata_synced",
                entity_type="openmetadata_integration",
                entity_id=integration.id,
                organization_id=org_id,
                actor_user_id=triggered_by,
                after_json={"tables_seen": len(tables), "nodes_created": nodes_created, "edges_created": edges_created},
                metadata_json={"source": "scheduler_or_api"},
            )
            return {
                "skipped": False,
                "tables_seen": len(tables),
                "nodes_created": nodes_created,
                "edges_created": edges_created,
            }
        except Exception as exc:
            integration.sync_status = "failed"
            integration.last_sync_error = str(exc)[:1000]
            integration.updated_at = self.utcnow()
            self.db.flush()
            raise


def run_daily_openmetadata_sync_sweep(db: Session) -> dict:
    service = LineageService(db)
    integrations = service.list_active_openmetadata_integrations()
    processed = 0
    failed = 0
    for integration in integrations:
        try:
            service.sync_openmetadata(org_id=integration.organization_id, triggered_by=integration.created_by)
            processed += 1
        except Exception:
            failed += 1

    return {
        "integrations_processed": len(integrations),
        "synced": processed,
        "failed": failed,
        "records_processed": len(integrations),
    }
