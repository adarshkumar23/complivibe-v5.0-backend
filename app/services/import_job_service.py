from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from base64 import b64decode
from binascii import Error as BinasciiError
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.core.config import get_settings
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService

SOURCE_TOOLS = {"vanta", "drata", "sprinto", "scrut", "generic"}
CONFLICT_STRATEGIES = {"skip", "update"}
ENTITY_TYPES = {"control", "evidence", "policy", "business_unit"}
_CONTROL_HINTS = {"control", "controls", "monitor", "monitors", "requirement", "requirements", "test", "tests"}
_EVIDENCE_HINTS = {"evidence", "artifact", "artifacts", "integration", "integrations", "event", "events"}
_POLICY_HINTS = {"policy", "policies", "document", "documents"}
_BUSINESS_UNIT_HINTS = {"entity", "entities", "business_unit", "business_units", "department", "departments"}

# Every CSV header alias that _map_csv_row() knows how to recognize (directly, or via
# an explicit column_map entry). Any CSV column present in the source file that isn't
# in this set -- and isn't explicitly mapped by the caller -- is silently dropped
# during import unless surfaced as a warning (see _parse_csv_rows' unmapped_columns).
_RECOGNIZED_CSV_COLUMN_ALIASES = {
    "entity_type", "module", "object_type", "section", "type",
    "title", "name", "control_name", "policy_name", "artifact_name", "entity_name",
    "description", "details", "summary", "notes",
    "code", "control_code", "reference", "id",
    "policy_type", "policy_category", "category",
    "evidence_type", "artifact_type", "kind",
    "collected_at", "captured_at", "observed_at", "updated_at",
    "original_created_at", "created_at", "uploaded_at",
    "status", "control_status",
    "owner", "owner_email", "owner_user_id",
    "criticality", "priority",
    "last_reviewed", "last_reviewed_at", "reviewed_at",
}

# Controls only accept these status/criticality values (see Control model +
# ControlUpdate schema patterns). An imported value outside this set is not
# an error -- it's treated as unrecognized and the field is left at its
# default rather than persisting an invalid value.
_CONTROL_STATUS_VALUES = {
    "not_started", "in_progress", "implemented", "needs_review", "failed", "not_applicable", "archived",
}
_CONTROL_CRITICALITY_VALUES = {"low", "medium", "high", "critical"}


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
        # Populated by _parse_csv_rows() (via _parse_records()) each time a CSV source
        # is parsed -- the set of source-file column headers that weren't recognized
        # or explicitly mapped, and were therefore not imported into any field.
        self._last_unmapped_columns: list[str] = []
        # Incremented by _upsert_evidence() each time an incoming import row matches
        # an existing evidence item whose provenance is protected (manual source or a
        # real checksum/file attached) -- the match was found but NOT overwritten.
        self._last_provenance_protected_count: int = 0

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
        if scheduler is not None and getattr(scheduler, "running", False):
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
        preview["unmapped_columns"] = list(self._last_unmapped_columns)
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
            "context_flags": preview.get("context_flags", []),
            "insights": preview.get("insights", {}),
            "unmapped_columns": preview.get("unmapped_columns", []),
        }

    def commit(self, organization_id: uuid.UUID, job_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> dict[str, Any]:
        job = self.require_job(organization_id, job_id)
        self._last_provenance_protected_count = 0
        parsed, row_errors = self._parse_records(job.source_tool, job.raw_payload_json)
        unmapped_columns = list(self._last_unmapped_columns)
        preview = self._build_preview(job.organization_id, parsed, row_errors, job.conflict_strategy)
        job.status = "processing"
        job.progress_total = len(parsed)
        job.progress_current = 0
        job.updated_at = self._utcnow()
        self.db.flush()

        created = defaultdict(int)
        updated = defaultdict(int)
        skipped = defaultdict(int)
        audit = AuditService(self.db)

        for idx, row in enumerate(parsed, start=1):
            entity = row["entity_type"]
            action = preview["row_actions"].get(str(row["row_number"]), "skip")
            if action not in {"create", "update"}:
                skipped[entity] += 1
                job.progress_current = idx
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
                job.progress_current = idx
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
            job.progress_current = idx

        job.status = "completed" if not row_errors else "failed"
        job.progress_current = len(parsed)
        job.error_summary = self._error_summary(row_errors)
        job.result_json = {
            "parsed_rows": parsed,
            "row_errors": row_errors,
            "created": dict(created),
            "updated": dict(updated),
            "skipped": dict(skipped),
            "unmapped_columns": unmapped_columns,
            "provenance_protected_count": self._last_provenance_protected_count,
        }
        job.updated_at = self._utcnow()
        self.db.flush()
        execution_insights = self._execution_insights(
            parsed_rows=parsed,
            row_errors=row_errors,
            created=dict(created),
            updated=dict(updated),
            skipped=dict(skipped),
            preview_payload=preview,
        )
        if self._last_provenance_protected_count > 0:
            execution_insights["context_flags"] = sorted(
                set(execution_insights["context_flags"]) | {"provenance_protected_skip"}
            )
        return {
            "job_id": job.id,
            "status": job.status,
            "created": dict(created),
            "updated": dict(updated),
            "skipped": dict(skipped),
            "row_errors": row_errors,
            "context_flags": execution_insights["context_flags"],
            "insights": execution_insights["insights"],
            "unmapped_columns": unmapped_columns,
            "provenance_protected_count": self._last_provenance_protected_count,
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
        seen_identity_keys: set[tuple[str, str]] = set()
        duplicate_rows: list[dict[str, Any]] = []
        timestamp_anomaly_count = 0

        for row in parsed_rows:
            entity = row["entity_type"]
            identity_key = self._row_identity_key(row)
            if identity_key in seen_identity_keys:
                would_skip[entity] += 1
                row_actions[str(row["row_number"])] = "skip_duplicate"
                duplicate_rows.append(
                    {
                        "row_number": row["row_number"],
                        "entity_type": entity,
                        "identity": identity_key[1],
                    }
                )
                continue
            seen_identity_keys.add(identity_key)

            if entity == "evidence" and self._has_evidence_timestamp_anomaly(row):
                timestamp_anomaly_count += 1

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

        context_flags: list[str] = []
        if not parsed_rows:
            context_flags.append("no_parsed_rows")
        if row_errors:
            context_flags.append("row_errors_present")
        if duplicate_rows:
            context_flags.append("duplicate_rows_skipped")
        if sum(would_update.values()) > 0:
            context_flags.append("updates_pending")
        if timestamp_anomaly_count > 0:
            context_flags.append("evidence_timestamp_anomaly_detected")

        total_rows = len(parsed_rows) + len(row_errors)
        estimated_success_rate_pct = round((len(parsed_rows) / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

        return {
            "parsed_rows": parsed_rows,
            "row_errors": row_errors,
            "would_create": dict(would_create),
            "would_update": dict(would_update),
            "would_skip": dict(would_skip),
            "row_actions": row_actions,
            "context_flags": sorted(set(context_flags)),
            "insights": {
                "duplicate_row_count": len(duplicate_rows),
                "duplicate_rows": duplicate_rows[:20],
                "timestamp_anomaly_count": timestamp_anomaly_count,
                "estimated_success_rate_pct": estimated_success_rate_pct,
            },
        }

    def _execution_insights(
        self,
        *,
        parsed_rows: list[dict[str, Any]],
        row_errors: list[dict[str, Any]],
        created: dict[str, int],
        updated: dict[str, int],
        skipped: dict[str, int],
        preview_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context_flags = list(preview_payload.get("context_flags", []))
        if sum(created.values()) == 0 and sum(updated.values()) == 0 and parsed_rows:
            context_flags.append("no_material_changes")
        if row_errors:
            context_flags.append("commit_completed_with_parse_errors")
        if sum(updated.values()) > 0:
            context_flags.append("existing_records_updated")
        if sum(skipped.values()) > 0:
            context_flags.append("rows_skipped")

        total_rows = len(parsed_rows) + len(row_errors)
        applied_rows = sum(created.values()) + sum(updated.values())
        applied_rate_pct = round((applied_rows / total_rows) * 100.0, 2) if total_rows > 0 else 0.0
        insights = {
            "applied_row_count": applied_rows,
            "skipped_row_count": sum(skipped.values()),
            "row_error_count": len(row_errors),
            "applied_rate_pct": applied_rate_pct,
            "duplicate_row_count": int((preview_payload.get("insights") or {}).get("duplicate_row_count", 0)),
        }
        return {
            "context_flags": sorted(set(context_flags)),
            "insights": insights,
        }

    def _row_identity_key(self, row: dict[str, Any]) -> tuple[str, str]:
        entity = str(row.get("entity_type") or "").strip().lower()
        if entity == "business_unit":
            identity = str(row.get("code") or row.get("title") or "").strip().lower().replace(" ", "_")
        elif entity == "control":
            identity = str(row.get("code") or row.get("title") or "").strip().lower()
        elif entity == "policy":
            identity = f"{str(row.get('title') or '').strip().lower()}::{str(row.get('policy_type') or '').strip().lower()}"
        elif entity == "evidence":
            identity = f"{str(row.get('title') or '').strip().lower()}::{str(row.get('evidence_type') or '').strip().lower()}"
        else:
            identity = str(row.get("title") or "").strip().lower()
        return entity, identity

    def _has_evidence_timestamp_anomaly(self, row: dict[str, Any]) -> bool:
        if str(row.get("entity_type") or "") != "evidence":
            return False
        collected_at = self._parse_optional_datetime(row.get("collected_at"))
        original_created_at = self._parse_optional_datetime(row.get("original_created_at"))
        if collected_at is None or original_created_at is None:
            return False
        return original_created_at > collected_at

    def _parse_records(
        self,
        source_tool: str,
        raw_payload: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parsed_rows: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        self._last_unmapped_columns = []
        if raw_payload is None:
            return parsed_rows, [{"row": 0, "error": "Missing payload"}]

        if isinstance(raw_payload, list):
            for idx, raw in enumerate(raw_payload, start=1):
                self._normalize_row(raw, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors

        if not isinstance(raw_payload, dict):
            return parsed_rows, [{"row": 0, "error": "Payload must be object or list"}]

        if "csv_content" in raw_payload and raw_payload.get("csv_content"):
            return self._parse_csv_rows(
                csv_content=str(raw_payload["csv_content"]),
                source_tool=source_tool,
                column_map=raw_payload.get("column_map"),
            )

        if source_tool == "drata":
            zip_payload = raw_payload.get("zip_base64") or raw_payload.get("zip_content_base64")
            if zip_payload:
                return self._parse_drata_zip(str(zip_payload))

        if "records" in raw_payload and isinstance(raw_payload["records"], list):
            for idx, raw in enumerate(raw_payload["records"], start=1):
                if source_tool in SOURCE_TOOLS:
                    section_name = str(raw.get("section") or raw.get("module") or "").strip()
                    self._normalize_source_row(source_tool, section_name, raw, idx, parsed_rows, row_errors)
                    continue
                self._normalize_row(raw, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors

        if source_tool == "vanta":
            row = self._collect_section_rows("vanta", "monitors", raw_payload.get("monitors"), row_errors, parsed_rows, 1)
            row = self._collect_section_rows("vanta", "integrations", raw_payload.get("integrations"), row_errors, parsed_rows, row)
            self._collect_section_rows("vanta", "policies", raw_payload.get("policies"), row_errors, parsed_rows, row)
            return parsed_rows, row_errors

        if source_tool == "drata":
            row = self._collect_section_rows("drata", "controls", raw_payload.get("controls"), row_errors, parsed_rows, 1)
            row = self._collect_section_rows("drata", "evidence", raw_payload.get("evidence"), row_errors, parsed_rows, row)
            self._collect_section_rows("drata", "policies", raw_payload.get("policies"), row_errors, parsed_rows, row)
            return parsed_rows, row_errors

        if source_tool in {"sprinto", "scrut"}:
            row = self._collect_section_rows(source_tool, "entities", raw_payload.get("entities"), row_errors, parsed_rows, 1)
            self._collect_section_rows(source_tool, "controls", raw_payload.get("controls"), row_errors, parsed_rows, row)
            return parsed_rows, row_errors

        return parsed_rows, [{"row": 0, "error": "No parsable records found"}]

    def _collect_section_rows(
        self,
        source_tool: str,
        section_name: str,
        rows: Any,
        row_errors: list[dict[str, Any]],
        parsed_rows: list[dict[str, Any]],
        start_row: int,
    ) -> int:
        row = start_row
        if rows is None:
            return row
        if not isinstance(rows, list):
            row_errors.append({"row": row, "error": f"{source_tool.capitalize()} {section_name} payload must be a list"})
            return row + 1
        for record in rows:
            if not isinstance(record, dict):
                row_errors.append({"row": row, "error": f"{source_tool.capitalize()} {section_name} row must be an object"})
                row += 1
                continue
            self._normalize_source_row(source_tool, section_name, record, row, parsed_rows, row_errors)
            row += 1
        return row

    def _parse_csv_rows(
        self,
        *,
        csv_content: str,
        source_tool: str,
        column_map: dict[str, str] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parsed_rows: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            if not reader.fieldnames:
                return parsed_rows, [{"row": 0, "error": "CSV is missing header row"}]

            recognized = set(_RECOGNIZED_CSV_COLUMN_ALIASES)
            if column_map:
                # Columns explicitly mapped by the caller (either as a key the caller
                # is targeting, or as a source header they've pointed at a known field)
                # are, by definition, not "unrecognized".
                recognized.update(str(k).strip().lower() for k in column_map.keys())
                recognized.update(str(v).strip().lower() for v in column_map.values())
            self._last_unmapped_columns = sorted(
                {
                    field.strip()
                    for field in reader.fieldnames
                    if field and field.strip().lower() not in recognized
                }
            )

            for idx, raw in enumerate(reader, start=2):
                mapped = self._map_csv_row(raw, source_tool=source_tool, column_map=column_map, row_number=idx, row_errors=row_errors)
                if mapped is None:
                    continue
                self._normalize_row(mapped, idx, parsed_rows, row_errors)
            return parsed_rows, row_errors
        except csv.Error as exc:
            return parsed_rows, [{"row": 0, "error": f"CSV parse failure: {exc}"}]

    def _parse_drata_zip(self, zip_payload_b64: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parsed_rows: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        try:
            zip_bytes = b64decode(zip_payload_b64, validate=True)
        except (BinasciiError, ValueError):
            return parsed_rows, [{"row": 0, "error": "Drata ZIP payload is not valid base64"}]

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
                row = 1
                for file_name in archive.namelist():
                    if file_name.endswith("/"):
                        continue
                    section = self._infer_section_from_filename(file_name)
                    if section is None:
                        continue
                    with archive.open(file_name, "r") as handle:
                        content = handle.read().decode("utf-8", errors="replace")
                    if file_name.lower().endswith(".json"):
                        try:
                            loaded = json.loads(content)
                        except json.JSONDecodeError as exc:
                            row_errors.append({"row": row, "error": f"{file_name}: invalid JSON ({exc.msg})"})
                            row += 1
                            continue
                        records = loaded if isinstance(loaded, list) else loaded.get("items") if isinstance(loaded, dict) else None
                        if not isinstance(records, list):
                            row_errors.append({"row": row, "error": f"{file_name}: expected JSON array or object with items[]"})
                            row += 1
                            continue
                        for entry in records:
                            if not isinstance(entry, dict):
                                row_errors.append({"row": row, "error": f"{file_name}: JSON row must be an object"})
                                row += 1
                                continue
                            self._normalize_source_row("drata", section, entry, row, parsed_rows, row_errors, file_name=file_name)
                            row += 1
                        continue

                    try:
                        reader = csv.DictReader(io.StringIO(content))
                    except csv.Error as exc:
                        row_errors.append({"row": row, "error": f"{file_name}: CSV parse failure ({exc})"})
                        row += 1
                        continue
                    if not reader.fieldnames:
                        row_errors.append({"row": row, "error": f"{file_name}: CSV header row missing"})
                        row += 1
                        continue
                    for raw in reader:
                        self._normalize_source_row("drata", section, raw, row, parsed_rows, row_errors, file_name=file_name)
                        row += 1
        except zipfile.BadZipFile:
            return parsed_rows, [{"row": 0, "error": "Drata ZIP payload is corrupted or invalid"}]
        return parsed_rows, row_errors

    def _infer_section_from_filename(self, file_name: str) -> str | None:
        lowered = file_name.lower()
        if any(token in lowered for token in ("control", "requirement")):
            return "controls"
        if any(token in lowered for token in ("evidence", "event", "artifact")):
            return "evidence"
        if any(token in lowered for token in ("policy", "policies", "document")):
            return "policies"
        if any(token in lowered for token in ("entity", "business_unit", "department")):
            return "entities"
        return None

    def _normalize_source_row(
        self,
        source_tool: str,
        section_name: str,
        raw: dict[str, Any],
        row_number: int,
        parsed_rows: list[dict[str, Any]],
        row_errors: list[dict[str, Any]],
        file_name: str | None = None,
    ) -> None:
        mapped = self._map_source_row(source_tool, section_name, raw)
        if mapped is None:
            row_errors.append(
                {
                    "row": row_number,
                    "error": (
                        f"{file_name}: could not map {source_tool} {section_name} row to supported entity"
                        if file_name
                        else f"Could not map {source_tool} {section_name} row to supported entity"
                    ),
                }
            )
            return
        self._normalize_row(mapped, row_number, parsed_rows, row_errors)

    def _map_source_row(self, source_tool: str, section_name: str, raw: dict[str, Any]) -> dict[str, Any] | None:
        section = section_name.strip().lower()
        title = self._pick(raw, "title", "name", "display_name", "control_name", "policy_name", "monitor_name", "integration_name")
        description = self._pick(raw, "description", "details", "summary", "notes")
        code = self._pick(raw, "code", "control_code", "control_id", "id", "reference")
        policy_type = self._pick(raw, "policy_type", "type", "category") or "imported"
        evidence_type = self._pick(raw, "evidence_type", "artifact_type", "kind")
        collected_at = self._pick(raw, "collected_at", "captured_at", "updated_at", "observed_at")
        original_created_at = self._pick(raw, "original_created_at", "created_at", "uploaded_at")

        if source_tool == "vanta":
            if section in {"monitors"}:
                return {
                    "entity_type": "control",
                    "title": title,
                    "description": description,
                    "code": code,
                }
            if section in {"integrations"}:
                run_status = self._pick(raw, "status", "result", "test_result")
                run_description = " ; ".join(part for part in [description, run_status] if part)
                return {
                    "entity_type": "evidence",
                    "title": title or "Imported integration test result",
                    "description": run_description or None,
                    "evidence_type": evidence_type or "technical_control_test_result",
                    "collected_at": collected_at,
                    "original_created_at": original_created_at,
                }
            if section in {"policies"}:
                return {
                    "entity_type": "policy",
                    "title": title,
                    "description": description,
                    "policy_type": policy_type,
                }
            return None

        if source_tool == "drata":
            if section in {"controls"}:
                return {
                    "entity_type": "control",
                    "title": title,
                    "description": description,
                    "code": code,
                }
            if section in {"evidence"}:
                return {
                    "entity_type": "evidence",
                    "title": title,
                    "description": description,
                    "evidence_type": evidence_type or "document",
                    "collected_at": collected_at,
                    "original_created_at": original_created_at,
                }
            if section in {"policies"}:
                return {
                    "entity_type": "policy",
                    "title": title,
                    "description": description,
                    "policy_type": policy_type,
                }
            return None

        if source_tool in {"sprinto", "scrut"}:
            if section in {"entities"}:
                return {
                    "entity_type": "business_unit",
                    "title": title,
                    "description": description,
                    "code": code,
                }
            if section in {"controls"}:
                return {
                    "entity_type": "control",
                    "title": title,
                    "description": description,
                    "code": code,
                }
            return None

        return raw

    def _map_csv_row(
        self,
        raw: dict[str, Any],
        *,
        source_tool: str,
        column_map: dict[str, str] | None,
        row_number: int,
        row_errors: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        cmap = column_map or {}
        if not isinstance(raw, dict):
            row_errors.append({"row": row_number, "error": "CSV row must be an object"})
            return None

        def from_columns(*aliases: str) -> Any:
            configured = [cmap.get(alias) for alias in aliases if cmap.get(alias)]
            candidates = [*configured, *aliases]
            for key in candidates:
                if key in raw and raw[key] not in (None, ""):
                    return raw[key]
                if key is None:
                    continue
                lowered = key.lower()
                for present, value in raw.items():
                    if str(present).strip().lower() == lowered and value not in (None, ""):
                        return value
            return None

        mapped: dict[str, Any] = {
            "entity_type": str(from_columns("entity_type", "module", "object_type", "section", "type") or "").strip().lower(),
            "title": from_columns("title", "name", "control_name", "policy_name", "artifact_name", "entity_name"),
            "description": from_columns("description", "details", "summary", "notes"),
            "code": from_columns("code", "control_code", "reference", "id"),
            "policy_type": from_columns("policy_type", "policy_category", "category") or "imported",
            "evidence_type": from_columns("evidence_type", "artifact_type", "kind") or "other",
            "collected_at": from_columns("collected_at", "captured_at", "observed_at", "updated_at"),
            "original_created_at": from_columns("original_created_at", "created_at", "uploaded_at"),
            "status": from_columns("status", "control_status"),
            "owner": from_columns("owner", "owner_email", "owner_user_id"),
            "criticality": from_columns("criticality", "priority"),
            "last_reviewed": from_columns("last_reviewed", "last_reviewed_at", "reviewed_at"),
        }

        if source_tool in {"sprinto", "scrut"}:
            hint = mapped["entity_type"]
            if hint in _BUSINESS_UNIT_HINTS:
                mapped["entity_type"] = "business_unit"
            elif hint in _CONTROL_HINTS:
                mapped["entity_type"] = "control"
            elif not hint:
                mapped["entity_type"] = "control" if mapped["code"] else "business_unit"

        if source_tool == "vanta":
            hint = mapped["entity_type"]
            if hint in _CONTROL_HINTS:
                mapped["entity_type"] = "control"
            elif hint in _EVIDENCE_HINTS:
                mapped["entity_type"] = "evidence"
                if mapped["evidence_type"] == "other":
                    mapped["evidence_type"] = "technical_control_test_result"
            elif hint in _POLICY_HINTS:
                mapped["entity_type"] = "policy"

        if source_tool == "drata":
            hint = mapped["entity_type"]
            if hint in _CONTROL_HINTS:
                mapped["entity_type"] = "control"
            elif hint in _EVIDENCE_HINTS:
                mapped["entity_type"] = "evidence"
            elif hint in _POLICY_HINTS:
                mapped["entity_type"] = "policy"

        return mapped

    @staticmethod
    def _pick(raw: dict[str, Any], *keys: str) -> Any | None:
        for key in keys:
            if key in raw and raw[key] not in (None, ""):
                return raw[key]
            lowered = key.lower()
            for present, value in raw.items():
                if str(present).strip().lower() == lowered and value not in (None, ""):
                    return value
        return None

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

        raw_status = str(raw.get("status") or "").strip().lower()
        raw_criticality = str(raw.get("criticality") or "").strip().lower()

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
                "original_created_at": raw.get("original_created_at") or raw.get("created_at"),
                "status": raw_status if raw_status in _CONTROL_STATUS_VALUES else None,
                "owner": str(raw.get("owner") or "").strip() or None,
                "criticality": raw_criticality if raw_criticality in _CONTROL_CRITICALITY_VALUES else None,
                "last_reviewed": raw.get("last_reviewed") or raw.get("last_reviewed_at"),
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

    def _resolve_owner_user_id(self, organization_id: uuid.UUID, owner: str | None) -> uuid.UUID | None:
        """Resolve an imported "owner" cell to a user id.

        Accepts either a literal user UUID or an email address, and only
        returns a user who actually has an active membership in this org --
        matching an arbitrary email from a CSV to a user in a different org
        would be a cross-tenant data leak.
        """
        if not owner:
            return None
        try:
            candidate_id = uuid.UUID(owner)
        except ValueError:
            candidate_id = None

        if candidate_id is not None:
            user = self.db.execute(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(User.id == candidate_id, Membership.organization_id == organization_id)
            ).scalar_one_or_none()
            return user.id if user is not None else None

        user = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(func.lower(User.email) == owner.strip().lower(), Membership.organization_id == organization_id)
        ).scalar_one_or_none()
        return user.id if user is not None else None

    def _upsert_control(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[Control | None, str]:
        existing = self._find_existing(job.organization_id, row)
        status_value = row.get("status") or "not_started"
        criticality_value = row.get("criticality") or "medium"
        owner_user_id = self._resolve_owner_user_id(job.organization_id, row.get("owner"))
        last_reviewed_at = self._parse_optional_datetime(row.get("last_reviewed"))

        if existing is None:
            item = Control(
                organization_id=job.organization_id,
                control_code=row["code"],
                title=row["title"],
                description=row["description"],
                source="imported",
                status=status_value,
                control_type="process",
                criticality=criticality_value,
                owner_user_id=owner_user_id,
                last_reviewed_at=last_reviewed_at,
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
        if row.get("status"):
            existing.status = status_value
        if row.get("criticality"):
            existing.criticality = criticality_value
        if owner_user_id is not None:
            existing.owner_user_id = owner_user_id
        if last_reviewed_at is not None:
            existing.last_reviewed_at = last_reviewed_at
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

    @staticmethod
    def _evidence_provenance_is_protected(existing: EvidenceItem) -> bool:
        """A manually-verified evidence item -- one entered by hand (source=="manual")
        or one with a real checksum/file already attached -- has provenance that must
        not be silently rewritten by an automated import match. Matching on
        title+evidence_type is a fuzzy heuristic; when it lands on a record like
        this, treat it as a conflict to protect rather than an automatic overwrite.
        """
        return existing.source == "manual" or bool(existing.checksum_sha256) or bool(existing.storage_key)

    def _upsert_evidence(self, job: ImportJob, row: dict[str, Any], actor_user_id: uuid.UUID | None) -> tuple[EvidenceItem | None, str]:
        existing = self._find_existing(job.organization_id, row)
        collected_at = self._parse_optional_datetime(row.get("collected_at"))
        original_created_at = self._parse_optional_datetime(row.get("original_created_at"))
        import_fallback_created_at = original_created_at or collected_at or self._utcnow()
        if existing is None:
            item = EvidenceService(self.db).create_imported_evidence(
                organization_id=job.organization_id,
                title=row["title"],
                description=row["description"],
                evidence_type=row["evidence_type"],
                source_import_tool=job.source_tool,
                collected_at=collected_at,
                original_created_at=import_fallback_created_at,
                actor_user_id=actor_user_id,
                # This bulk-import loop writes its own import.evidence.* audit row
                # per item; opt out of the service-level audit to avoid duplication.
                write_audit=False,
            )
            return item, "created"
        if job.conflict_strategy != "update":
            return existing, "skipped"
        if self._evidence_provenance_is_protected(existing):
            # Do NOT silently overwrite source/description/collected_at/
            # source_import_tool on a manually-verified or checksummed record.
            # original_created_at is the one exception: it's only ever tightened
            # to an earlier, more-accurate date below and never invented from
            # scratch on a record that already has provenance, so backfilling it
            # is genuinely supplementary rather than destructive.
            if existing.original_created_at is None and import_fallback_created_at is not None:
                existing.original_created_at = import_fallback_created_at
                self.db.flush()
            self._last_provenance_protected_count += 1
            return existing, "skipped"
        existing.description = row["description"]
        existing.collected_at = collected_at
        existing_original_created_at = existing.original_created_at
        if existing_original_created_at is not None and existing_original_created_at.tzinfo is None:
            # Some backends (notably SQLite, used in tests) don't round-trip tzinfo
            # on this column -- treat a naive value as UTC rather than letting the
            # naive/aware comparison below raise.
            existing_original_created_at = existing_original_created_at.replace(tzinfo=UTC)
        existing.original_created_at = (
            min(existing_original_created_at, import_fallback_created_at)
            if existing_original_created_at
            else import_fallback_created_at
        )
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
