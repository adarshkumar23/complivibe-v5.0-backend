from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users() -> dict:
    return {"items": [], "detail": "Not implemented yet"}
