from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User
from app.core.config import get_settings
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService

SOURCE_TOOLS = {"vanta", "drata", "sprinto", "scrut", "generic"}
CONFLICT_STRATEGIES = {"skip", "update"}
ENTITY_TYPES = {"control", "evidence", "policy", "business_unit"}


def run_import_job_validation(job_id: str) -> None:
    from app.db.session import get_session_maker

    db = get_session_maker()()
    try:
        service = ImportJobService(db)
        service.refresh_preview(uuid.UUID(job_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            job = db.execute(select(ImportJob).where(ImportJob.id == uuid.UUID(job_id))).scalar_one_or_none()
            if job is not None:
                job.status = "failed"
                job.error_summary = f"Background import preview generation failed: {type(exc).__name__}"
                job.updated_at = datetime.now(UTC)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


class ImportJobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def require_org(self, organization_id: uuid.UUID) -> Organization:
        row = self.db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        return row

    def require_job(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
        row = self.db.execute(
            select(ImportJob).where(
                ImportJob.id == job_id,
                ImportJob.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
        return row

    def create_job(
        self,
        *,
        organization_id: uuid.UUID,
        source_tool: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None,
        dry_run: bool,
        conflict_strategy: str,
        created_by: uuid.UUID | None,
    ) -> ImportJob:
        self.require_org(organization_id)
        if source_tool not in SOURCE_TOOLS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported import source")
        if conflict_strategy not in CONFLICT_STRATEGIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid conflict strategy")

        row = ImportJob(
            organization_id=organization_id,
            source_tool=source_tool,
            status="queued",
            progress_current=0,
            progress_total=0,
            dry_run=dry_run,
            conflict_strategy=conflict_strategy,
            created_by=created_by,
            raw_payload_json=payload,
            result_json={},
            error_summary=None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def enqueue_preview_job(self, app: Any, job_id: uuid.UUID) -> None:
        if get_settings().APP_ENV == "test":
            self.refresh_preview(job_id)
            return
        scheduler = getattr(app.state, "pbc_scheduler", None)
        if scheduler is not None:
            try:
                from apscheduler.triggers.date import DateTrigger

                scheduler.add_job(
                    run_import_job_validation,
                    trigger=DateTrigger(run_date=self._utcnow()),
                    args=[str(job_id)],
                    id=f"import-preview-{job_id}",
                    replace_existing=True,
                    coalesce=True,
                )
                return
            except Exception:
                pass
        self.refresh_preview(job_id)

    def refresh_preview(self, job_id: uuid.UUID) -> dict[str, Any]:
        job = self.db.execute(select(ImportJob).where(ImportJob.id == job_id)).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")

        job.status = "processing"
        parsed, row_errors = self._parse_records(job.source_tool, job.raw_payload_json)
        preview = self._build_preview(job.organization_id, parsed, row_errors, job.conflict_strategy)
        job.progress_total = len(parsed)
        job.progress_current = len(parsed)
        job.result_json = preview
        job.status = "preview_ready" if not row_errors else "failed"
        job.error_summary = self._error_summary(row_errors)
        job.updated_at = self._utcnow()
        self.db.flush()
        return preview

    def preview(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
        job = self.require_job(organization_id, job_id)
        preview = self.refresh_preview(job.id)
        return {
            "job_id": job.id,
            "status": job.status,
            "parsed_rows": len(preview["parsed_rows"]),
            "row_errors": preview["row_errors"],
            "would_create": preview["would_create"],
            "would_update": preview["would_update"],
            "would_skip": preview["would_skip"],
        }

    def commit(self, organization_id: uuid.UUID, job_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> dict[str, Any]:
        job = self.require_job(organization_id, job_id)
        parsed, row_errors = self._parse_records(job.source_tool, job.raw_payload_json)
        preview = self._build_preview(job.organization_id, parsed, row_errors, job.conflict_strategy)

        created = defaultdict(int)
        updated = defaultdict(int)
        skipped = defaultdict(int)
        audit = AuditService(self.db)

        for row in parsed:
            entity = row["entity_type"]
            action = preview["row_actions"].get(str(row["row_number"]), "skip")
            if action == "skip":
                skipped[entity] += 1
                continue
            if entity == "business_unit":
                entity_row, action_taken = self._upsert_business_unit(job, row, actor_user_id)
            elif entity == "control":
                entity_row, action_taken = self._upsert_control(job, row, actor_user_id)
            elif entity == "policy":
                entity_row, action_taken = self._upsert_policy(job, row, actor_user_id)
            elif entity == "evidence":
                entity_row, action_taken = self._upsert_evidence(job, row, actor_user_id)
            else:
                skipped[entity] += 1
                continue

            if action_taken == "created":
                created[entity] += 1
            elif action_taken == "updated":
                updated[entity] += 1
            else:
                skipped[entity] += 1
                continue

            audit.write_audit_log(
                action=f"import.{entity}.{action_taken}",
                entity_type=entity,
                entity_id=entity_row.id,
                organization_id=job.organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "title": getattr(entity_row, "title", getattr(entity_row, "name", None)),
                    "source_import_tool": getattr(entity_row, "source_import_tool", None),
                },
                metadata_json={
                    "source_tool": job.source_tool,
                    "import_job_id": str(job.id),
                    "row_number": row["row_number"],
                },
            )

        job.status = "completed" if not row_errors else "failed"
        job.progress_total = len(parsed)
        job.progress_current = len(parsed)
        job.error_summary = self._error_summary(row_errors)
        job.result_json = {
            "parsed_rows": parsed,
            "row_errors": row_errors,
            "created": dict(created),
            "updated": dict(updated),
            "skipped": dict(skipped),
        }
        job.updated_at = self._utcnow()
        self.db.flush()
        return {
            "job_id": job.id,
            "status": job.status,
            "created": dict(created),
            "updated": dict(updated),
            "skipped": dict(skipped),
            "row_errors": row_errors,
        }

    def _build_preview(
        self,
        organization_id: uuid.UUID,
        parsed_rows: list[dict[str, Any]],
        row_errors: list[dict[str, Any]],
        conflict_strategy: str,
    ) -> dict[str, Any]:
        would_create = defaultdict(int)
        would_update = defaultdict(int)
        would_skip = defaultdict(int)
        row_actions: dict[str, str] = {}

        for row in parsed_rows:
            entity = row["entity_type"]
            existing = self._find_existing(organization_id, row)
            if existing is None:
                would_create[entity] += 1
                row_actions[str(row["row_number"])] = "create"
            elif conflict_strategy == "update":
                would_update[entity] += 1
                row_actions[str(row["row_number"])] = "update"
            else:
                would_skip[entity] += 1
                row_actions[str(row["row_number"])] = "skip"

        return {
            "parsed_rows": parsed_rows,
            "row_errors": row_errors,
            "would_create": dict(would_create),
            "would_update": dict(would_update),
            "would_skip": dict(would_skip),
            "row_actions": row_actions,
        }

    def _parse_records(
        self,
        source_tool: str,
        raw_payload: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parsed_rows: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        if raw_payload is None:
            return parsed_rows, [{"row": 0, "error": "Missing payload"}]

        if isinstance(raw_payload, list):
            for idx, raw in enumerate(raw_payload, start=1):
                self._normalize_row(raw, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors

        if not isinstance(raw_payload, dict):
            return parsed_rows, [{"row": 0, "error": "Payload must be object or list"}]

        if "csv_content" in raw_payload and raw_payload.get("csv_content"):
            return self._parse_csv_rows(str(raw_payload["csv_content"]))

        if "records" in raw_payload and isinstance(raw_payload["records"], list):
            for idx, raw in enumerate(raw_payload["records"], start=1):
                self._normalize_row(raw, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors

        if source_tool == "vanta":
            row = 1
            for record in raw_payload.get("monitors", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Vanta monitors row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "control", **record}, row, parsed_rows, row_errors)
                row += 1
            for record in raw_payload.get("integrations", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Vanta integrations row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "evidence", **record}, row, parsed_rows, row_errors)
                row += 1
            for record in raw_payload.get("policies", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Vanta policies row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "policy", **record}, row, parsed_rows, row_errors)
                row += 1
            return parsed_rows, row_errors

        if source_tool == "drata":
            row = 1
            for record in raw_payload.get("controls", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Drata controls row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "control", **record}, row, parsed_rows, row_errors)
                row += 1
            for record in raw_payload.get("evidence", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Drata evidence row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "evidence", **record}, row, parsed_rows, row_errors)
                row += 1
            for record in raw_payload.get("policies", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": "Drata policies row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "policy", **record}, row, parsed_rows, row_errors)
                row += 1
            return parsed_rows, row_errors

        if source_tool in {"sprinto", "scrut"}:
            row = 1
            for record in raw_payload.get("entities", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": f"{source_tool} entities row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "business_unit", **record}, row, parsed_rows, row_errors)
                row += 1
            for record in raw_payload.get("controls", []):
                if not isinstance(record, dict):
                    row_errors.append({"row": row, "error": f"{source_tool} controls row must be an object"})
                    row += 1
                    continue
                self._normalize_row({"entity_type": "control", **record}, row, parsed_rows, row_errors)
                row += 1
            return parsed_rows, row_errors

        return parsed_rows, [{"row": 0, "error": "No parsable records found"}]

    def _parse_csv_rows(self, csv_content: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parsed_rows: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            if not reader.fieldnames:
                return parsed_rows, [{"row": 0, "error": "CSV is missing header row"}]
            for idx, raw in enumerate(reader, start=2):
                self._normalize_row(raw, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors
        except csv.Error as exc:
            return parsed_rows, [{"row": 0, "error": f"CSV parse failure: {exc}"}]

    def _normalize_row(
        self,
        raw: dict[str, Any] | Any,
        row_number: int,
        parsed_rows: list[dict[str, Any]],
        row_errors: list[dict[str, Any]],
    ) -> None:
        if not isinstance(raw, dict):
            row_errors.append({"row": row_number, "error": "Row must be an object"})
            return
        entity_type = str(raw.get("entity_type", "")).strip().lower()
        if entity_type not in ENTITY_TYPES:
            row_errors.append({"row": row_number, "error": "entity_type must be one of control/evidence/policy/business_unit"})
            return

        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not title:
            row_errors.append({"row": row_number, "error": "Missing title/name"})
            return

        parsed_rows.append(
            {
                "row_number": row_number,
                "entity_type": entity_type,
                "title": title,
                "description": str(raw.get("description") or "").strip() or None,
                "code": str(raw.get("code") or "").strip() or None,
                "policy_type": str(raw.get("policy_type") or "imported").strip(),
                "evidence_type": str(raw.get("evidence_type") or "other").strip(),
                "collected_at": raw.get("collected_at"),
            }
        )

    def _find_existing(self, organization_id: uuid.UUID, row: dict[str, Any]) -> Any | None:
        entity = row["entity_type"]
        if entity == "business_unit":
            code = row["code"] or row["title"].lower().replace(" ", "_")
            return self.db.execute(
                select(BusinessUnit).where(
                    BusinessUnit.organization_id == organization_id,
                    BusinessUnit.code == code,
                    BusinessUnit.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
        if entity == "control":
            stmt = select(Control).where(Control.organization_id == organization_id)
            if row["code"]:
                stmt = stmt.where(Control.control_code == row["code"])
            else:
                stmt = stmt.where(Control.title == row["title"])
            return self.db.execute(stmt).scalar_one_or_none()
        if entity == "policy":
            return self.db.execute(
                select(CompliancePolicy).where(
                    CompliancePolicy.organization_id == organization_id,
                    CompliancePolicy.title == row["title"],
                    CompliancePolicy.policy_type == row["policy_type"],
                    CompliancePolicy.archived_at.is_(None),
                )
            ).scalar_one_or_none()
        if entity == "evidence":
            return self.db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.title == row["title"],
                    EvidenceItem.evidence_type == row["evidence_type"],
                    EvidenceItem.status != "archived",
                )
            ).scalar_one_or_none()
        return None

    def _upsert_business_unit(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[BusinessUnit | None, str]:
        existing = self._find_existing(job.organization_id, row)
        code = row["code"] or row["title"].lower().replace(" ", "_")
        if existing is None:
            item = BusinessUnit(
                organization_id=job.organization_id,
                name=row["title"],
                code=code,
                description=row["description"],
                is_active=True,
                created_by=actor_user_id,
                source_import_tool=job.source_tool,
            )
            self.db.add(item)
            self.db.flush()
            return item, "created"
        if job.conflict_strategy != "update":
            return existing, "skipped"
        existing.name = row["title"]
        existing.description = row["description"]
        existing.source_import_tool = job.source_tool
        self.db.flush()
        return existing, "updated"

    def _upsert_control(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[Control | None, str]:
        existing = self._find_existing(job.organization_id, row)
        if existing is None:
            item = Control(
                organization_id=job.organization_id,
                control_code=row["code"],
                title=row["title"],
                description=row["description"],
                source="imported",
                status="not_started",
                control_type="process",
                criticality="medium",
                source_import_tool=job.source_tool,
                created_by_user_id=actor_user_id,
            )
            self.db.add(item)
            self.db.flush()
            return item, "created"
        if job.conflict_strategy != "update":
            return existing, "skipped"
        existing.title = row["title"]
        existing.description = row["description"]
        existing.source_import_tool = job.source_tool
        self.db.flush()
        return existing, "updated"

    def _upsert_policy(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[CompliancePolicy | None, str]:
        existing = self._find_existing(job.organization_id, row)
        if existing is None:
            if actor_user_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Missing actor for policy import")
            item = CompliancePolicy(
                organization_id=job.organization_id,
                title=row["title"],
                description=row["description"],
                policy_type=row["policy_type"],
                status="draft",
                owner_user_id=actor_user_id,
                source_import_tool=job.source_tool,
            )
            self.db.add(item)
            self.db.flush()
            return item, "created"
        if job.conflict_strategy != "update":
            return existing, "skipped"
        existing.description = row["description"]
        existing.source_import_tool = job.source_tool
        self.db.flush()
        return existing, "updated"

    def _upsert_evidence(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[EvidenceItem | None, str]:
        existing = self._find_existing(job.organization_id, row)
        collected_at = self._parse_optional_datetime(row.get("collected_at"))
        if existing is None:
            item = EvidenceService(self.db).create_imported_evidence(
                organization_id=job.organization_id,
                title=row["title"],
                description=row["description"],
                evidence_type=row["evidence_type"],
                source_import_tool=job.source_tool,
                collected_at=collected_at,
                actor_user_id=actor_user_id,
            )
            return item, "created"
        if job.conflict_strategy != "update":
            return existing, "skipped"
        existing.description = row["description"]
        existing.collected_at = collected_at
        existing.source_import_tool = job.source_tool
        existing.source = "imported"
        self.db.flush()
        return existing, "updated"

    def _parse_optional_datetime(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        try:
            normalized = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None

    def _error_summary(self, row_errors: list[dict[str, Any]]) -> str | None:
        if not row_errors:
            return None
        return "; ".join([f"row {row['row']}: {row['error']}" for row in row_errors[:10]])
