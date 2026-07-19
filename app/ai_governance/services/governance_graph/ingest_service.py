"""'Satellites Compute, Core Decides' ingest service (patent P2).

Core independently re-validates every satellite-submitted derivation before
writing anything durable:
  1. re-validate submitted obligation/control ids against the live catalog
     (reject unknown/inactive -> 422);
  2. independently re-derive via core's own recursive CTE and COMPARE
     (validation_status = validated | flagged_mismatch);
  3. persist the traversal result always, but write obligation LINKS only when
     the submission matched core's re-derivation (mismatches are flagged, never
     silently written);
  4. audit the event.

AuditService is called through core's REAL frozen signature (this is the
rewrite of P2's 5 broken call-sites): instance form `AuditService(db).
write_audit_log(*, action, entity_type, organization_id, actor_user_id, ...)`,
not the classmethod `write_audit_log(session=, org_id=, actor_id=, event_type=,
payload=)` P2 assumed.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.constants import CORE_REFERENCE_METHODOLOGY_VERSION
from app.ai_governance.services.governance_graph.graph_query import resolve_max_traversal_depth
from app.ai_governance.services.governance_graph.metrics import MismatchMetrics
from app.ai_governance.services.governance_graph.reference_cte import derive_obligations_reference
from app.ai_governance.services.governance_graph.repository import (
    load_active_catalog,
    resolve_ai_system_node_id,
    upsert_ai_system_obligation_links,
    upsert_graph_structure,
)
from app.ai_governance.services.governance_graph.validation import compare_derivation, validate_obligation_control_ids
from app.models.governance_graph_traversal_result import GovernanceGraphTraversalResult
from app.services.audit_service import AuditService


class GovernanceGraphIngestService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process_one_derivation(self, org_id: uuid.UUID, actor_user_id: uuid.UUID | None, payload) -> dict:
        submitted = {
            "derived_obligations": list(payload.derived_obligations),
            "derived_controls": list(payload.derived_controls),
        }

        # Step 1: re-validate references against the live catalog.
        catalog = load_active_catalog(self.db, org_id)
        bad_ids = validate_obligation_control_ids(submitted, catalog)
        if bad_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "unknown_or_inactive_obligation_control_ids", "ids": bad_ids},
            )

        # Step 2: independently re-derive and compare.
        ai_system_uuid = uuid.UUID(str(payload.ai_system_id))
        node_id = resolve_ai_system_node_id(self.db, org_id, ai_system_uuid)
        if node_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "unknown_ai_system_node", "ai_system_id": str(payload.ai_system_id)},
            )
        reference = derive_obligations_reference(self.db, org_id, node_id, resolve_max_traversal_depth())
        matches = compare_derivation(submitted, reference)
        validation_status = "validated" if matches else "flagged_mismatch"
        MismatchMetrics.record(org_id, validation_status)

        # Step 3: persist the traversal result ALWAYS; write links ONLY on match.
        result = GovernanceGraphTraversalResult(
            organization_id=org_id,
            ai_system_id=ai_system_uuid,
            input_context={
                "trigger_reason": payload.trigger_reason,
                "derivation_hash": payload.derivation_hash,
            },
            derived_obligations=submitted["derived_obligations"],
            derived_controls=submitted["derived_controls"],
            graph_path=payload.graph_path,
            methodology_version=payload.methodology_version,
            trigger_reason=payload.trigger_reason,
            validation_status=validation_status,
        )
        self.db.add(result)
        self.db.flush()
        if matches:
            upsert_ai_system_obligation_links(
                self.db, org_id, ai_system_uuid, submitted["derived_obligations"], submitted["derived_controls"]
            )

        # Step 4: audit (REAL frozen signature).
        AuditService(self.db).write_audit_log(
            action="governance_graph.obligation_derivation_ingest",
            entity_type="governance_graph_traversal_result",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            entity_id=result.id,
            after_json={
                "ai_system_id": str(payload.ai_system_id),
                "methodology_version": payload.methodology_version,
                "trigger_reason": payload.trigger_reason,
                "validation_status": validation_status,
                "derivation_hash": payload.derivation_hash,
            },
            metadata_json={"source": "satellite"},
        )
        return {
            "status": "ok",
            "validation_status": validation_status,
            "traversal_result_id": str(result.id),
            "reference_derived_obligations": reference["derived_obligations"],
            "reference_derived_controls": reference["derived_controls"],
        }

    def process_graph_structure(self, org_id: uuid.UUID, actor_user_id: uuid.UUID | None, nodes, edges, structure_hash: str) -> dict:
        result = upsert_graph_structure(self.db, org_id, nodes, edges)
        AuditService(self.db).write_audit_log(
            action="governance_graph.structure_ingest",
            entity_type="governance_graph_node",
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"structure_hash": structure_hash, **result},
            metadata_json={"source": "satellite"},
        )
        return {"structure_hash": structure_hash, **result}
