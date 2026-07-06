from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
from app.models.import_parity_tracking import ImportParityTracking
from app.services.audit_service import AuditService

MODULES: tuple[str, ...] = ("control", "evidence", "policy", "business_unit")
SOURCES: tuple[str, ...] = ("vanta", "drata", "sprinto", "scrut", "generic")
TERMINAL_IMPORT_STATES: tuple[str, ...] = ("preview_ready", "completed", "failed")


class ImportParityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def _parity_pct(verified_count: int, expected_count: int) -> float:
        if expected_count <= 0:
            return 100.0
        ratio = min(verified_count / expected_count, 1.0)
        return round(ratio * 100.0, 2)

    def _latest_expected_counts(self, organization_id: uuid.UUID) -> dict[str, dict[str, int]]:
        by_tool: dict[str, dict[str, int]] = {tool: {module: 0 for module in MODULES} for tool in SOURCES}
        latest_jobs_by_tool: dict[str, ImportJob] = {}
        rows = self.db.execute(
            select(ImportJob)
            .where(
                ImportJob.organization_id == organization_id,
                ImportJob.status.in_(TERMINAL_IMPORT_STATES),
                ImportJob.source_tool.in_(SOURCES),
            )
            .order_by(ImportJob.updated_at.desc(), ImportJob.created_at.desc())
        ).scalars()

        for row in rows:
            if row.source_tool not in latest_jobs_by_tool:
                latest_jobs_by_tool[row.source_tool] = row
            if len(latest_jobs_by_tool) == len(SOURCES):
                break

        for tool, job in latest_jobs_by_tool.items():
            result_json = job.result_json or {}
            parsed_rows = result_json.get("parsed_rows") if isinstance(result_json, dict) else None
            if not isinstance(parsed_rows, list):
                continue
            for parsed in parsed_rows:
                if not isinstance(parsed, dict):
                    continue
                entity_type = str(parsed.get("entity_type") or "").strip().lower()
                if entity_type in MODULES:
                    by_tool[tool][entity_type] += 1
        return by_tool

    def _observed_tools(self, organization_id: uuid.UUID) -> set[str]:
        tools: set[str] = set()
        statements = [
            select(Control.source_import_tool).where(
                Control.organization_id == organization_id,
                Control.source_import_tool.is_not(None),
                Control.status != "archived",
            ),
            select(EvidenceItem.source_import_tool).where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.source_import_tool.is_not(None),
                EvidenceItem.status != "archived",
            ),
            select(CompliancePolicy.source_import_tool).where(
                CompliancePolicy.organization_id == organization_id,
                CompliancePolicy.source_import_tool.is_not(None),
                CompliancePolicy.archived_at.is_(None),
            ),
            select(BusinessUnit.source_import_tool).where(
                BusinessUnit.organization_id == organization_id,
                BusinessUnit.source_import_tool.is_not(None),
                BusinessUnit.deleted_at.is_(None),
            ),
        ]
        for stmt in statements:
            for row in self.db.execute(stmt).scalars():
                if row and row in SOURCES:
                    tools.add(str(row))
        return tools

    def _counts_for(self, organization_id: uuid.UUID, tool_source: str, entity_type: str) -> tuple[int, int]:
        if entity_type == "control":
            imported_count = int(
                self.db.execute(
                    select(func.count(Control.id)).where(
                        Control.organization_id == organization_id,
                        Control.source_import_tool == tool_source,
                        Control.status != "archived",
                    )
                ).scalar_one()
            )
            verified_count = int(
                self.db.execute(
                    select(func.count(func.distinct(Control.id)))
                    .join(EvidenceControlLink, EvidenceControlLink.control_id == Control.id)
                    .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                    .where(
                        Control.organization_id == organization_id,
                        Control.source_import_tool == tool_source,
                        Control.status != "archived",
                        EvidenceControlLink.organization_id == organization_id,
                        EvidenceControlLink.link_status == "active",
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.status != "archived",
                        EvidenceItem.review_status == "verified",
                    )
                ).scalar_one()
            )
            return imported_count, verified_count

        if entity_type == "evidence":
            imported_count = int(
                self.db.execute(
                    select(func.count(EvidenceItem.id)).where(
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.source_import_tool == tool_source,
                        EvidenceItem.status != "archived",
                    )
                ).scalar_one()
            )
            verified_count = int(
                self.db.execute(
                    select(func.count(EvidenceItem.id)).where(
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.source_import_tool == tool_source,
                        EvidenceItem.status != "archived",
                        EvidenceItem.review_status == "verified",
                    )
                ).scalar_one()
            )
            return imported_count, verified_count

        if entity_type == "policy":
            imported_count = int(
                self.db.execute(
                    select(func.count(CompliancePolicy.id)).where(
                        CompliancePolicy.organization_id == organization_id,
                        CompliancePolicy.source_import_tool == tool_source,
                        CompliancePolicy.archived_at.is_(None),
                    )
                ).scalar_one()
            )
            verified_count = int(
                self.db.execute(
                    select(func.count(CompliancePolicy.id)).where(
                        CompliancePolicy.organization_id == organization_id,
                        CompliancePolicy.source_import_tool == tool_source,
                        CompliancePolicy.archived_at.is_(None),
                        CompliancePolicy.status == "approved",
                    )
                ).scalar_one()
            )
            return imported_count, verified_count

        imported_count = int(
            self.db.execute(
                select(func.count(BusinessUnit.id)).where(
                    BusinessUnit.organization_id == organization_id,
                    BusinessUnit.source_import_tool == tool_source,
                    BusinessUnit.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        verified_count = int(
            self.db.execute(
                select(func.count(BusinessUnit.id)).where(
                    BusinessUnit.organization_id == organization_id,
                    BusinessUnit.source_import_tool == tool_source,
                    BusinessUnit.deleted_at.is_(None),
                    BusinessUnit.is_active.is_(True),
                )
            ).scalar_one()
        )
        return imported_count, verified_count

    def _upsert_tracking(
        self,
        *,
        organization_id: uuid.UUID,
        tool_source: str,
        entity_type: str,
        imported_count: int,
        verified_count: int,
        parity_pct: float,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        existing = self.db.execute(
            select(ImportParityTracking).where(
                ImportParityTracking.organization_id == organization_id,
                ImportParityTracking.tool_source == tool_source,
                ImportParityTracking.entity_type == entity_type,
            )
        ).scalar_one_or_none()
        parity_decimal = Decimal(str(parity_pct))

        if existing is None:
            row = ImportParityTracking(
                organization_id=organization_id,
                tool_source=tool_source,
                entity_type=entity_type,
                imported_count=imported_count,
                verified_count=verified_count,
                parity_pct=parity_decimal,
            )
            self.db.add(row)
            self.db.flush()
            self.audit.write_audit_log(
                action="import.parity_tracking.created",
                entity_type="import_parity_tracking",
                entity_id=row.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                before_json={},
                after_json={
                    "tool_source": tool_source,
                    "entity_type": entity_type,
                    "imported_count": imported_count,
                    "verified_count": verified_count,
                    "parity_pct": float(parity_decimal),
                },
                metadata_json={"module": "import_parity_dashboard"},
            )
            return

        before = {
            "imported_count": existing.imported_count,
            "verified_count": existing.verified_count,
            "parity_pct": float(existing.parity_pct),
        }
        after = {
            "imported_count": imported_count,
            "verified_count": verified_count,
            "parity_pct": float(parity_decimal),
        }
        if before == after:
            return
        existing.imported_count = imported_count
        existing.verified_count = verified_count
        existing.parity_pct = parity_decimal
        self.db.flush()
        self.audit.write_audit_log(
            action="import.parity_tracking.updated",
            entity_type="import_parity_tracking",
            entity_id=existing.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
            metadata_json={
                "tool_source": tool_source,
                "entity_type": entity_type,
                "module": "import_parity_dashboard",
            },
        )

    def dashboard(self, organization_id: uuid.UUID, threshold_pct: float = 95.0, actor_user_id: uuid.UUID | None = None) -> dict:
        if threshold_pct < 0 or threshold_pct > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="threshold_pct must be between 0 and 100")

        expected_counts = self._latest_expected_counts(organization_id)
        tools = set(expected_counts.keys()) | self._observed_tools(organization_id)
        tools = {tool for tool in tools if tool in SOURCES}
        metrics_by_source: dict[str, dict[str, dict[str, int | float]]] = defaultdict(dict)

        for tool in sorted(tools):
            for entity_type in MODULES:
                expected_count = int(expected_counts.get(tool, {}).get(entity_type, 0))
                imported_count, verified_count = self._counts_for(organization_id, tool, entity_type)
                parity_pct = self._parity_pct(verified_count=verified_count, expected_count=expected_count)
                metrics_by_source[tool][entity_type] = {
                    "expected_count": expected_count,
                    "imported_count": imported_count,
                    "verified_count": verified_count,
                    "parity_pct": parity_pct,
                }
                self._upsert_tracking(
                    organization_id=organization_id,
                    tool_source=tool,
                    entity_type=entity_type,
                    imported_count=imported_count,
                    verified_count=verified_count,
                    parity_pct=parity_pct,
                    actor_user_id=actor_user_id,
                )

        module_rollups: dict[str, dict[str, int | float]] = {
            entity_type: {"expected_count": 0, "imported_count": 0, "verified_count": 0}
            for entity_type in MODULES
        }
        by_source: list[dict] = []
        for tool in sorted(metrics_by_source.keys()):
            tool_expected = 0
            tool_imported = 0
            tool_verified = 0
            modules: list[dict] = []
            for entity_type in MODULES:
                row = metrics_by_source[tool][entity_type]
                expected_count = int(row["expected_count"])
                imported_count = int(row["imported_count"])
                verified_count = int(row["verified_count"])
                parity_pct = float(row["parity_pct"])
                modules.append(
                    {
                        "entity_type": entity_type,
                        "expected_count": expected_count,
                        "imported_count": imported_count,
                        "verified_count": verified_count,
                        "parity_pct": parity_pct,
                    }
                )
                tool_expected += expected_count
                tool_imported += imported_count
                tool_verified += verified_count
                module_rollups[entity_type]["expected_count"] = int(module_rollups[entity_type]["expected_count"]) + expected_count
                module_rollups[entity_type]["imported_count"] = int(module_rollups[entity_type]["imported_count"]) + imported_count
                module_rollups[entity_type]["verified_count"] = int(module_rollups[entity_type]["verified_count"]) + verified_count

            by_source.append(
                {
                    "tool_source": tool,
                    "modules": modules,
                    "expected_count": tool_expected,
                    "imported_count": tool_imported,
                    "verified_count": tool_verified,
                    "parity_pct": self._parity_pct(verified_count=tool_verified, expected_count=tool_expected),
                }
            )

        modules = []
        overall_expected = 0
        overall_imported = 0
        overall_verified = 0
        for entity_type in MODULES:
            expected_count = int(module_rollups[entity_type]["expected_count"])
            imported_count = int(module_rollups[entity_type]["imported_count"])
            verified_count = int(module_rollups[entity_type]["verified_count"])
            modules.append(
                {
                    "entity_type": entity_type,
                    "expected_count": expected_count,
                    "imported_count": imported_count,
                    "verified_count": verified_count,
                    "parity_pct": self._parity_pct(verified_count=verified_count, expected_count=expected_count),
                }
            )
            overall_expected += expected_count
            overall_imported += imported_count
            overall_verified += verified_count

        overall_parity = self._parity_pct(verified_count=overall_verified, expected_count=overall_expected)
        return {
            "threshold_pct": round(threshold_pct, 2),
            "ready_to_switch": overall_parity >= threshold_pct,
            "overall": {
                "entity_type": "overall",
                "expected_count": overall_expected,
                "imported_count": overall_imported,
                "verified_count": overall_verified,
                "parity_pct": overall_parity,
            },
            "modules": modules,
            "by_source": by_source,
        }
