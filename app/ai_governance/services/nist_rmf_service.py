import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_rmf_function_response import AIRMFFunctionResponse
from app.models.ai_system import AISystem
from app.models.nist_ai_rmf_implementation import NISTAIRMFImplementation
from app.services.audit_service import AuditService
from app.services.seed_service import NIST_AI_RMF_SUBCATEGORIES, SeedService

ALLOWED_RESPONSE_STATUS = {"not_addressed", "partial", "implemented"}
FUNCTIONS = ("govern", "map", "measure", "manage")


class NISTRMFService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _required_subcategories(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for function_name, rows in NIST_AI_RMF_SUBCATEGORIES.items():
            function_slug = function_name.lower()
            for reference_code, _ in rows:
                pairs.append((function_slug, reference_code))
        return pairs

    def _status_for_function(self, rows: list[AIRMFFunctionResponse]) -> str:
        if not rows or all(row.response_status == "not_addressed" for row in rows):
            return "not_started"
        if all(row.response_status == "implemented" for row in rows):
            return "implemented"
        return "in_progress"

    def _recompute_function_statuses(self, implementation: NISTAIRMFImplementation) -> None:
        rows = self.db.execute(
            select(AIRMFFunctionResponse).where(
                AIRMFFunctionResponse.organization_id == implementation.organization_id,
                AIRMFFunctionResponse.implementation_id == implementation.id,
            )
        ).scalars().all()

        grouped: dict[str, list[AIRMFFunctionResponse]] = defaultdict(list)
        for row in rows:
            grouped[row.function].append(row)

        implementation.govern_status = self._status_for_function(grouped.get("govern", []))
        implementation.map_status = self._status_for_function(grouped.get("map", []))
        implementation.measure_status = self._status_for_function(grouped.get("measure", []))
        implementation.manage_status = self._status_for_function(grouped.get("manage", []))
        implementation.last_updated_at = self.utcnow()
        self.db.flush()

    def _ensure_response_rows(self, implementation: NISTAIRMFImplementation) -> list[AIRMFFunctionResponse]:
        existing = {
            row.subcategory_ref: row
            for row in self.db.execute(
                select(AIRMFFunctionResponse).where(
                    AIRMFFunctionResponse.organization_id == implementation.organization_id,
                    AIRMFFunctionResponse.implementation_id == implementation.id,
                )
            ).scalars().all()
        }

        now = self.utcnow()
        for function_name, subcategory_ref in self._required_subcategories():
            if subcategory_ref in existing:
                continue
            row = AIRMFFunctionResponse(
                organization_id=implementation.organization_id,
                implementation_id=implementation.id,
                function=function_name,
                subcategory_ref=subcategory_ref,
                response_status="not_addressed",
                notes=None,
                evidence_id=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
            existing[subcategory_ref] = row

        return sorted(existing.values(), key=lambda row: (row.function, row.subcategory_ref))

    def get_or_create_implementation(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> NISTAIRMFImplementation:
        self._require_system(org_id, system_id)
        SeedService.ensure_starter_obligations(self.db)

        implementation = self.db.execute(
            select(NISTAIRMFImplementation).where(
                NISTAIRMFImplementation.organization_id == org_id,
                NISTAIRMFImplementation.ai_system_id == system_id,
            )
        ).scalar_one_or_none()

        created_now = False
        if implementation is None:
            now = self.utcnow()
            implementation = NISTAIRMFImplementation(
                organization_id=org_id,
                ai_system_id=system_id,
                govern_status="not_started",
                map_status="not_started",
                measure_status="not_started",
                manage_status="not_started",
                last_updated_at=now,
                created_by=created_by,
                created_at=now,
            )
            self.db.add(implementation)
            self.db.flush()
            created_now = True

        self._ensure_response_rows(implementation)
        self._recompute_function_statuses(implementation)

        if created_now:
            AIGovernanceEventService.log(
                self.db,
                org_id,
                "nist_rmf.implementation_created",
                actor_id=created_by,
                actor_type="user",
                ai_system_id=system_id,
                event_data={"implementation_id": str(implementation.id)},
            )
            AuditService(self.db).write_audit_log(
                action="nist_rmf.implementation_created",
                entity_type="nist_ai_rmf_implementation",
                entity_id=implementation.id,
                organization_id=org_id,
                actor_user_id=created_by,
                after_json={
                    "ai_system_id": str(system_id),
                    "govern_status": implementation.govern_status,
                    "map_status": implementation.map_status,
                    "measure_status": implementation.measure_status,
                    "manage_status": implementation.manage_status,
                },
                metadata_json={"source": "api"},
            )

        return implementation

    def get_implementation(self, org_id: uuid.UUID, system_id: uuid.UUID) -> NISTAIRMFImplementation:
        implementation = self.db.execute(
            select(NISTAIRMFImplementation).where(
                NISTAIRMFImplementation.organization_id == org_id,
                NISTAIRMFImplementation.ai_system_id == system_id,
            )
        ).scalar_one_or_none()
        if implementation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NIST AI RMF implementation not found")
        self._ensure_response_rows(implementation)
        self._recompute_function_statuses(implementation)
        return implementation

    def list_responses(self, org_id: uuid.UUID, implementation_id: uuid.UUID) -> list[AIRMFFunctionResponse]:
        return self.db.execute(
            select(AIRMFFunctionResponse)
            .where(
                AIRMFFunctionResponse.organization_id == org_id,
                AIRMFFunctionResponse.implementation_id == implementation_id,
            )
            .order_by(AIRMFFunctionResponse.function.asc(), AIRMFFunctionResponse.subcategory_ref.asc())
        ).scalars().all()

    def update_subcategory(
        self,
        org_id: uuid.UUID,
        implementation_id: uuid.UUID,
        subcategory_ref: str,
        response_status: str,
        notes: str | None,
        evidence_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> AIRMFFunctionResponse:
        if response_status not in ALLOWED_RESPONSE_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid response status")

        implementation = self.db.execute(
            select(NISTAIRMFImplementation).where(
                NISTAIRMFImplementation.id == implementation_id,
                NISTAIRMFImplementation.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if implementation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NIST AI RMF implementation not found")

        self._ensure_response_rows(implementation)
        row = self.db.execute(
            select(AIRMFFunctionResponse).where(
                AIRMFFunctionResponse.organization_id == org_id,
                AIRMFFunctionResponse.implementation_id == implementation_id,
                AIRMFFunctionResponse.subcategory_ref == subcategory_ref,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NIST AI RMF subcategory not found")

        row.response_status = response_status
        row.notes = notes
        row.evidence_id = evidence_id
        row.updated_at = self.utcnow()
        self.db.flush()

        self._recompute_function_statuses(implementation)

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "nist_rmf.subcategory_updated",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=implementation.ai_system_id,
            event_data={
                "implementation_id": str(implementation.id),
                "subcategory_ref": row.subcategory_ref,
                "function": row.function,
                "response_status": row.response_status,
            },
        )
        AuditService(self.db).write_audit_log(
            action="nist_rmf.subcategory_updated",
            entity_type="ai_rmf_function_response",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "implementation_id": str(implementation.id),
                "subcategory_ref": row.subcategory_ref,
                "response_status": row.response_status,
                "function": row.function,
            },
            metadata_json={"source": "api"},
        )
        return row

    def _function_maturity(self, rows: list[AIRMFFunctionResponse], function_name: str) -> dict[str, int | float]:
        function_rows = [row for row in rows if row.function == function_name]
        total = len(function_rows)
        implemented = len([row for row in function_rows if row.response_status == "implemented"])
        pct = round((implemented / total) * 100, 2) if total else 0.0
        return {"total": total, "implemented": implemented, "pct": pct}

    def get_maturity(self, org_id: uuid.UUID, system_id: uuid.UUID) -> dict:
        implementation = self.get_implementation(org_id, system_id)
        rows = self.list_responses(org_id, implementation.id)

        payload = {function_name: self._function_maturity(rows, function_name) for function_name in FUNCTIONS}
        total = sum(int(payload[name]["total"]) for name in FUNCTIONS)
        implemented = sum(int(payload[name]["implemented"]) for name in FUNCTIONS)
        payload["overall_maturity_pct"] = round((implemented / total) * 100, 2) if total else 0.0
        payload["implementation_id"] = str(implementation.id)
        return payload

    def get_org_summary(self, org_id: uuid.UUID) -> dict:
        implementations = self.db.execute(
            select(NISTAIRMFImplementation).where(NISTAIRMFImplementation.organization_id == org_id)
        ).scalars().all()
        if not implementations:
            return {
                "govern": {"total": 0, "implemented": 0, "pct": 0.0},
                "map": {"total": 0, "implemented": 0, "pct": 0.0},
                "measure": {"total": 0, "implemented": 0, "pct": 0.0},
                "manage": {"total": 0, "implemented": 0, "pct": 0.0},
                "overall_maturity_pct": 0.0,
                "systems_count": 0,
            }

        implementation_ids = [row.id for row in implementations]
        rows = self.db.execute(
            select(AIRMFFunctionResponse).where(
                AIRMFFunctionResponse.organization_id == org_id,
                AIRMFFunctionResponse.implementation_id.in_(implementation_ids),
            )
        ).scalars().all()

        payload = {function_name: self._function_maturity(rows, function_name) for function_name in FUNCTIONS}
        total = sum(int(payload[name]["total"]) for name in FUNCTIONS)
        implemented = sum(int(payload[name]["implemented"]) for name in FUNCTIONS)
        payload["overall_maturity_pct"] = round((implemented / total) * 100, 2) if total else 0.0
        payload["systems_count"] = len(implementations)
        return payload
