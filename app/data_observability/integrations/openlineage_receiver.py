import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_lineage_edge import DataLineageEdge
from app.models.data_lineage_node import DataLineageNode


class OpenLineageReceiver:
    """
    Receives OpenLineage events pushed by data stack tools.
    """

    @staticmethod
    def _parse_event_time(raw_event_time: str | None) -> datetime | None:
        if not raw_event_time:
            return None
        try:
            return datetime.fromisoformat(raw_event_time.replace("Z", "+00:00"))
        except Exception:
            return None

    def _get_or_create_node(
        self,
        org_id: uuid.UUID,
        dataset: dict,
        node_type: str,
        system_name: str,
        db: Session,
    ) -> DataLineageNode:
        name = str(dataset.get("name") or "unknown")
        existing = db.execute(
            select(DataLineageNode).where(
                DataLineageNode.organization_id == org_id,
                DataLineageNode.name == name,
                DataLineageNode.system_name == system_name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = datetime.now(UTC)
        node = DataLineageNode(
            organization_id=org_id,
            node_type=node_type,
            data_asset_id=None,
            name=name,
            description=None,
            system_name=system_name,
            created_at=now,
            updated_at=now,
        )
        db.add(node)
        db.flush()
        return node

    def _upsert_edge(
        self,
        *,
        org_id: uuid.UUID,
        upstream_id: uuid.UUID,
        downstream_id: uuid.UUID,
        source_method: str,
        pipeline_name: str | None,
        pipeline_run_id: str | None,
        job_name: str | None,
        event_time: datetime | None,
        metadata: dict,
        db: Session,
    ) -> tuple[DataLineageEdge, bool]:
        pipeline_filter = (
            DataLineageEdge.pipeline_name.is_(None)
            if pipeline_name is None
            else DataLineageEdge.pipeline_name == pipeline_name
        )
        existing = db.execute(
            select(DataLineageEdge).where(
                DataLineageEdge.organization_id == org_id,
                DataLineageEdge.upstream_node_id == upstream_id,
                DataLineageEdge.downstream_node_id == downstream_id,
                pipeline_filter,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.pipeline_run_id = pipeline_run_id
            existing.job_name = job_name
            existing.event_time = event_time
            existing.metadata_json = metadata or {}
            db.flush()
            return existing, False

        edge = DataLineageEdge(
            organization_id=org_id,
            upstream_node_id=upstream_id,
            downstream_node_id=downstream_id,
            transformation_description=None,
            source_method=source_method,
            pipeline_name=pipeline_name,
            pipeline_run_id=pipeline_run_id,
            job_name=job_name,
            event_time=event_time,
            metadata_json=metadata or {},
            created_at=datetime.now(UTC),
        )
        db.add(edge)
        db.flush()
        return edge, True

    def process_event(self, event: dict, org_id: uuid.UUID, db: Session) -> dict:
        job_name = str(event.get("job", {}).get("name") or "unknown")
        run_id = str(event.get("run", {}).get("runId") or "")
        inputs = event.get("inputs") or []
        outputs = event.get("outputs") or []
        event_time = self._parse_event_time(event.get("eventTime"))

        created_count = 0
        for inp in inputs:
            for out in outputs:
                upstream = self._get_or_create_node(org_id, inp, "external_source", job_name, db)
                downstream = self._get_or_create_node(org_id, out, "external_destination", job_name, db)
                _, is_created = self._upsert_edge(
                    org_id=org_id,
                    upstream_id=upstream.id,
                    downstream_id=downstream.id,
                    source_method="openlineage_event",
                    pipeline_name=job_name,
                    pipeline_run_id=run_id,
                    job_name=job_name,
                    event_time=event_time,
                    metadata=event,
                    db=db,
                )
                created_count += int(is_created)

        return {
            "edges_created": created_count,
            "job_name": job_name,
        }
