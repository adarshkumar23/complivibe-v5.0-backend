from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.search import SearchHit, SearchResponse
from app.services.search_indexing_service import (
    TRACKED_ENTITY_TYPES,
    SearchIndexingService,
    SearchUnavailableError,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=256, description="Free-text search query (fuzzy matched)"),
    entity_types: list[str] | None = Query(
        default=None,
        description="Restrict search to a subset of: " + ", ".join(sorted(TRACKED_ENTITY_TYPES)),
    ),
    limit: int = Query(default=20, ge=1, le=100),
    db=Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("search:read")),
) -> SearchResponse:
    if entity_types:
        invalid = [t for t in entity_types if t not in TRACKED_ENTITY_TYPES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported entity_types: {invalid}. Supported: {sorted(TRACKED_ENTITY_TYPES)}",
            )

    try:
        result = SearchIndexingService(db).search(
            query=q,
            organization_id=organization.id,
            entity_types=entity_types,
            limit=limit,
        )
    except SearchUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service is temporarily unavailable. Please try again shortly.",
        ) from exc

    return SearchResponse(
        query=result["query"],
        took_ms=result["took_ms"],
        hits=[SearchHit(**hit) for hit in result["hits"]],
    )
