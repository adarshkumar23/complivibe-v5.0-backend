from app.auth.routers.scim import router as scim_router
from app.auth.routers.sso import router as sso_router

__all__ = ["sso_router", "scim_router"]
