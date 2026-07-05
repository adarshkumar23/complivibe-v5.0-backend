"""Meilisearch-backed cross-entity search indexing.

This module reacts to audit log writes for a small allowlist of entity types
(risks, controls, vendors, issues, compliance policies, obligations) and keeps
a Meilisearch index in sync with the source-of-truth Postgres/SQLite rows.

Design notes:
  * Meilisearch is an external, best-effort search cache -- never a system of
    record. Every public method here swallows and logs connectivity/API
    errors from indexing operations so that an unavailable or misbehaving
    search server can never break the underlying business write (creating a
    risk, archiving a vendor, etc.). The one exception is `search()`, which is
    called directly from a read-only search endpoint and raises
    `SearchUnavailableError` on failure so the API layer can return a clear,
    specific 503 instead of a generic error.
  * No schema migration is used to track indexing state. On every audit event
    for a tracked entity type we simply re-derive the current document from
    the live DB row (or remove it from the index if the row is gone / soft
    deleted / archived). This keeps the feature schema-free per the platform
    ground rules for this project.
  * Multi-tenancy: every tracked entity except `obligation` is organization
    owned, and `organization_id` is configured as a filterable attribute on
    each of those indexes. All search queries scoped to an organization pass
    an explicit `organization_id = '<uuid>'` filter -- this is the mechanism
    that prevents cross-org data leakage in results. `obligation` rows are
    global regulatory content (no organization_id column on the model) and
    are intentionally excluded from per-org filtering; see `search()`.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.issue import Issue
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.vendor import Vendor

logger = logging.getLogger(__name__)

try:
    import meilisearch
    from meilisearch.errors import MeilisearchError
except ImportError:  # pragma: no cover - meilisearch is a hard dependency once installed
    meilisearch = None  # type: ignore[assignment]

    class MeilisearchError(Exception):  # type: ignore[no-redef]
        pass


class SearchUnavailableError(Exception):
    """Raised by `search()` when the search backend cannot service a query.

    Deliberately does not mention the third-party product by name in its
    message -- callers (API layer) should surface a generic
    "search service unavailable" message to end users.
    """


@dataclass(frozen=True)
class EntityIndexSpec:
    index_name: str
    model: type
    searchable_attributes: tuple[str, ...]
    filterable_attributes: tuple[str, ...]
    # Whether this entity type is scoped to a single organization. Obligation
    # content is global regulatory text and is not organization owned.
    org_scoped: bool = True


# Allowlist of audit-logged entity types this service reacts to, and how to
# build/index a document for each. Any entity_type NOT in this dict is
# ignored entirely by the dispatch hook (no Meilisearch cost is paid for the
# dozens of other audit-logged entity types in the platform).
ENTITY_INDEX_SPECS: dict[str, EntityIndexSpec] = {
    "risk": EntityIndexSpec(
        index_name="risks",
        model=Risk,
        searchable_attributes=("title", "description", "category", "severity", "status"),
        filterable_attributes=("organization_id", "status", "severity", "category", "treatment_strategy"),
    ),
    "control": EntityIndexSpec(
        index_name="controls",
        model=Control,
        searchable_attributes=("title", "description", "control_code", "control_type"),
        filterable_attributes=("organization_id", "status", "criticality", "control_type"),
    ),
    "vendor": EntityIndexSpec(
        index_name="vendors",
        model=Vendor,
        searchable_attributes=("name", "description", "vendor_type", "primary_contact_name"),
        filterable_attributes=("organization_id", "status", "risk_tier", "vendor_type"),
    ),
    "issue": EntityIndexSpec(
        index_name="issues",
        model=Issue,
        searchable_attributes=("title", "description", "issue_type", "severity"),
        filterable_attributes=("organization_id", "status", "severity", "issue_type"),
    ),
    "compliance_policy": EntityIndexSpec(
        index_name="policies",
        model=CompliancePolicy,
        searchable_attributes=("title", "description", "policy_type", "notes"),
        filterable_attributes=("organization_id", "status", "policy_type"),
    ),
    "obligation": EntityIndexSpec(
        index_name="obligations",
        model=Obligation,
        searchable_attributes=("title", "description", "plain_language_summary", "reference_code", "jurisdiction"),
        filterable_attributes=("status", "jurisdiction", "framework_id"),
        org_scoped=False,
    ),
}

TRACKED_ENTITY_TYPES = frozenset(ENTITY_INDEX_SPECS.keys())

# Actions on these entity types that always mean "remove from index" even if
# the row itself has not been hard-deleted (the platform never hard-deletes,
# so this covers explicit `.deleted` / soft-delete markers).
_DELETE_ACTION_SUFFIXES = (".deleted",)


def _client() -> "meilisearch.Client":
    settings = get_settings()
    return meilisearch.Client(
        settings.MEILISEARCH_URL,
        settings.MEILISEARCH_API_KEY,
        timeout=settings.MEILISEARCH_TIMEOUT_SECONDS,
    )


def _indexing_enabled() -> bool:
    settings = get_settings()
    # Mirrors the RATE_LIMIT_ENABLED / APP_ENV=="test" convention used
    # elsewhere in this codebase: never touch a real network dependency
    # during the automated test suite.
    return settings.MEILISEARCH_ENABLED and settings.APP_ENV != "test"


class SearchIndexingService:
    """Reacts to audit-logged writes on the six tracked entity types."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def ensure_indexes(self) -> None:
        """Idempotently create/configure all tracked Meilisearch indexes.

        Safe to call repeatedly (e.g. on app startup, and lazily before the
        first search) -- Meilisearch's create_index is a no-op if the index
        already exists, and update_*_attributes calls are idempotent.
        """
        client = _client()
        for spec in ENTITY_INDEX_SPECS.values():
            try:
                client.create_index(spec.index_name, {"primaryKey": "id"})
            except MeilisearchError as exc:
                # "index_already_exists" is expected on repeat calls.
                if "already exists" not in str(exc).lower():
                    raise
            index = client.index(spec.index_name)
            index.update_searchable_attributes(list(spec.searchable_attributes))
            index.update_filterable_attributes(list(spec.filterable_attributes))

    # ------------------------------------------------------------------
    # Audit-log-driven dispatch (the reactive hook)
    # ------------------------------------------------------------------

    def handle_audit_event(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
        action: str | None = None,
    ) -> None:
        """Best-effort reindex of a single row after an audit log write.

        Never raises -- any failure (Meilisearch down, network error, bad
        row state) is logged and swallowed so the caller's business
        transaction is unaffected.
        """
        if entity_type not in TRACKED_ENTITY_TYPES or entity_id is None:
            return
        if not _indexing_enabled():
            return

        spec = ENTITY_INDEX_SPECS[entity_type]
        try:
            if action and action.endswith(_DELETE_ACTION_SUFFIXES):
                self._remove_document(spec, entity_id)
                return

            row = self.db.get(spec.model, entity_id)
            if row is None or self._is_excluded(entity_type, row):
                self._remove_document(spec, entity_id)
                return

            document = self._build_document(entity_type, row)
            self._upsert_document(spec, document)
        except Exception:  # noqa: BLE001 - deliberately broad; indexing must never break the caller
            logger.warning(
                "search indexing failed for entity_type=%s entity_id=%s action=%s",
                entity_type,
                entity_id,
                action,
                exc_info=True,
            )

    def _upsert_document(self, spec: EntityIndexSpec, document: dict[str, Any]) -> None:
        client = _client()
        client.index(spec.index_name).add_documents([document])

    def _remove_document(self, spec: EntityIndexSpec, entity_id: uuid.UUID) -> None:
        client = _client()
        client.index(spec.index_name).delete_document(str(entity_id))

    # ------------------------------------------------------------------
    # Document shaping / soft-delete exclusion rules
    # ------------------------------------------------------------------

    @staticmethod
    def _is_excluded(entity_type: str, row: Any) -> bool:
        """Whether a row should be excluded from (removed from) the index.

        The platform never hard-deletes rows, but several of these models
        have a soft "retired" state that should not surface in search:
          * risk / control: status == "archived"
          * vendor / compliance_policy: status == "archived" or archived_at set
          * issue: deleted_at is set (the model's actual soft-delete marker)
          * obligation: status != "active"
        """
        if entity_type in ("risk", "control"):
            return row.status == "archived"
        if entity_type in ("vendor", "compliance_policy"):
            return row.status == "archived" or getattr(row, "archived_at", None) is not None
        if entity_type == "issue":
            return getattr(row, "deleted_at", None) is not None
        if entity_type == "obligation":
            return row.status != "active"
        return False

    @staticmethod
    def _build_document(entity_type: str, row: Any) -> dict[str, Any]:
        base = {"id": str(row.id)}
        if entity_type == "risk":
            base.update(
                organization_id=str(row.organization_id),
                title=row.title,
                description=row.description,
                category=row.category,
                severity=row.severity,
                status=row.status,
                treatment_strategy=row.treatment_strategy,
                owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
                business_unit_id=str(row.business_unit_id) if row.business_unit_id else None,
            )
        elif entity_type == "control":
            base.update(
                organization_id=str(row.organization_id),
                title=row.title,
                description=row.description,
                control_code=row.control_code,
                control_type=row.control_type,
                status=row.status,
                criticality=row.criticality,
                owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
            )
        elif entity_type == "vendor":
            base.update(
                organization_id=str(row.organization_id),
                name=row.name,
                description=row.description,
                vendor_type=row.vendor_type,
                risk_tier=row.risk_tier,
                status=row.status,
                primary_contact_name=row.primary_contact_name,
                website=row.website,
            )
        elif entity_type == "issue":
            base.update(
                organization_id=str(row.organization_id),
                title=row.title,
                description=row.description,
                issue_type=row.issue_type,
                severity=row.severity,
                status=row.status,
                source_type=row.source_type,
            )
        elif entity_type == "compliance_policy":
            base.update(
                organization_id=str(row.organization_id),
                title=row.title,
                description=row.description,
                policy_type=row.policy_type,
                status=row.status,
                notes=row.notes,
                version=row.version,
            )
        elif entity_type == "obligation":
            base.update(
                reference_code=row.reference_code,
                title=row.title,
                description=row.description,
                plain_language_summary=row.plain_language_summary,
                jurisdiction=row.jurisdiction,
                status=row.status,
                framework_id=str(row.framework_id),
            )
        return base

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        query: str,
        organization_id: uuid.UUID,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Run a fuzzy, org-scoped search across the tracked indexes.

        Raises `SearchUnavailableError` (never a raw Meilisearch exception)
        if the backend cannot be reached -- callers should map this to a
        503 with a generic message.
        """
        types = [t for t in (entity_types or list(TRACKED_ENTITY_TYPES)) if t in TRACKED_ENTITY_TYPES]
        if not types:
            return {"query": query, "hits": [], "took_ms": 0}

        started = time.monotonic()
        try:
            client = _client()
            hits: list[dict[str, Any]] = []
            for entity_type in types:
                spec = ENTITY_INDEX_SPECS[entity_type]
                opt_params: dict[str, Any] = {"limit": limit, "showRankingScore": True}
                if spec.org_scoped:
                    opt_params["filter"] = f"organization_id = '{organization_id}'"
                result = client.index(spec.index_name).search(query, opt_params)
                for hit in result.get("hits", []):
                    hits.append({"entity_type": entity_type, **hit})
            took_ms = int((time.monotonic() - started) * 1000)
            hits.sort(key=lambda h: h.get("_rankingScore", 0), reverse=True)
            return {"query": query, "hits": hits[:limit], "took_ms": took_ms}
        except MeilisearchError as exc:
            logger.warning("search backend error for query=%r: %s", query, exc)
            raise SearchUnavailableError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - connection errors, DNS failures, etc.
            logger.warning("search backend unreachable for query=%r: %s", query, exc)
            raise SearchUnavailableError(str(exc)) from exc


@lru_cache(maxsize=1)
def _ensure_indexes_once_marker() -> bool:
    # Simple process-local guard so we don't re-issue the settings calls on
    # every single audit event; ensure_indexes() itself is idempotent so this
    # is purely a minor optimization, not a correctness requirement.
    return True


def ensure_indexes_ready(db: Session) -> None:
    """Best-effort, non-raising wrapper to bootstrap indexes (e.g. at startup)."""
    if not _indexing_enabled():
        return
    try:
        _ensure_indexes_once_marker()
        SearchIndexingService(db).ensure_indexes()
    except Exception:  # noqa: BLE001
        logger.warning("failed to ensure search indexes are configured", exc_info=True)
