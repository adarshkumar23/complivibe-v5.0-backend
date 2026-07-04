from __future__ import annotations

from typing import Any

import httpx

from app.satellites.tprm_intelligence.config import get_tprm_intelligence_settings


class SatelliteHTTPClient:
    """The only place this satellite performs third-party HTTP calls."""

    def __init__(self) -> None:
        self.settings = get_tprm_intelligence_settings()

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=self.settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            return {"items": payload}
        return payload

    def post_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=self.settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.post(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            return {"items": payload}
        return payload
