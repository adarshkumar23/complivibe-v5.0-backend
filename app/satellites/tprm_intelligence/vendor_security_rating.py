from __future__ import annotations

import re
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.satellites.tprm_intelligence.config import get_tprm_intelligence_settings
from app.satellites.tprm_intelligence.http_client import SatelliteHTTPClient


GRADE_SCORES = {"A+": 100, "A": 95, "B": 85, "C": 70, "D": 55, "E": 35, "F": 15}


def normalize_domain(value: str) -> str:
    raw = (value or "").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = parsed.hostname or raw
    host = host.lower().strip("./")
    if not host or not re.match(r"^[a-z0-9.-]+$", host):
        raise ValueError("Vendor website/domain is required for external intelligence checks")
    return host


class VendorSecurityRatingService:
    """Aggregates free/open vendor security signals inside the satellite boundary."""

    # Composite formula: each available signal contributes its configured weight.
    # When a signal is skipped/unavailable, its weight is redistributed proportionally
    # by dividing the weighted sum by the sum of weights actually used.
    WEIGHTS = {
        "mozilla_observatory": 0.45,
        "gdelt_adverse_media": 0.25,
        "abuseipdb": 0.20,
        "hibp": 0.10,
    }

    def __init__(self, http_client: SatelliteHTTPClient | None = None) -> None:
        self.http = http_client or SatelliteHTTPClient()
        self.settings = get_tprm_intelligence_settings()

    def compute(self, domain: str) -> dict:
        normalized = normalize_domain(domain)
        signals = {
            "mozilla_observatory": self._mozilla_observatory(normalized),
            "gdelt_adverse_media": self._gdelt_adverse_media(normalized),
            "abuseipdb": self._abuseipdb(normalized),
            "hibp": self._hibp(normalized),
        }
        score = self._weighted_score(signals)
        return {
            "domain": normalized,
            "signals_used": signals,
            "composite_score": score,
            "computed_at": datetime.now(UTC).isoformat(),
        }

    def _mozilla_observatory(self, domain: str) -> dict:
        try:
            # The old Mozilla Observatory v1 endpoint was shut down; MDN's v2
            # scanner is the current no-key API for the same header grade.
            payload = self.http.post_json("https://observatory-api.mdn.mozilla.net/api/v2/scan", params={"host": domain})
            grade = str(payload.get("grade") or payload.get("scan", {}).get("grade") or "").upper()
            score = None
            if isinstance(payload.get("score"), (int, float)):
                score = max(0, min(100, int(payload["score"])))
            if score is None:
                score = GRADE_SCORES.get(grade)
            return {
                "status": "available" if score is not None else "unavailable",
                "source": "mozilla_observatory",
                "grade": grade or None,
                "score": score,
                "raw_summary": {key: payload.get(key) for key in ("grade", "score", "state", "tests_failed", "tests_passed") if key in payload},
            }
        except Exception as exc:
            return {"status": "error", "source": "mozilla_observatory", "score": None, "message": str(exc)}

    def _gdelt_adverse_media(self, domain: str) -> dict:
        query = f'"{domain}" (breach OR ransomware OR malware OR fraud OR lawsuit OR sanction OR vulnerability)'
        try:
            payload = self.http.get_json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": query, "mode": "ArtList", "format": "json", "maxrecords": 10, "sort": "hybridrel"},
            )
            articles = payload.get("articles") or []
            count = len(articles) if isinstance(articles, list) else 0
            # Fewer adverse articles is better: 0 => 100, 10+ => 0.
            score = max(0, 100 - min(count, 10) * 10)
            return {
                "status": "available",
                "source": "gdelt",
                "score": score,
                "article_count": count,
                "articles": [
                    {"title": item.get("title"), "url": item.get("url"), "domain": item.get("domain")}
                    for item in articles[:5]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            return {"status": "error", "source": "gdelt", "score": None, "message": str(exc)}

    def _abuseipdb(self, domain: str) -> dict:
        if not self.settings.ABUSEIPDB_API_KEY:
            return {"status": "skipped", "source": "abuseipdb", "score": None, "message": "AbuseIPDB signal skipped: API key not configured"}
        try:
            ip = socket.gethostbyname(domain)
            payload = self.http.get_json(
                "https://api.abuseipdb.com/api/v2/check",
                params={"ipAddress": ip, "maxAgeInDays": 90},
                headers={"Key": self.settings.ABUSEIPDB_API_KEY, "Accept": "application/json"},
            )
            data = payload.get("data") or {}
            confidence = int(data.get("abuseConfidenceScore") or 0)
            return {
                "status": "available",
                "source": "abuseipdb",
                "ip_address": ip,
                "score": max(0, 100 - confidence),
                "abuse_confidence_score": confidence,
            }
        except Exception as exc:
            return {"status": "error", "source": "abuseipdb", "score": None, "message": str(exc)}

    def _hibp(self, domain: str) -> dict:
        if not self.settings.HIBP_API_KEY:
            return {"status": "skipped", "source": "hibp", "score": None, "message": "HIBP signal skipped: no API key configured"}
        try:
            payload = self.http.get_json(
                f"https://haveibeenpwned.com/api/v3/breacheddomain/{domain}",
                headers={"hibp-api-key": self.settings.HIBP_API_KEY, "user-agent": "CompliVibe-TPRM-Intelligence"},
            )
            breaches = payload if isinstance(payload, list) else payload.get("items", [])
            count = len(breaches) if isinstance(breaches, list) else 0
            return {"status": "available", "source": "hibp", "score": max(0, 100 - min(count, 20) * 5), "breach_count": count}
        except Exception as exc:
            return {"status": "error", "source": "hibp", "score": None, "message": str(exc)}

    def _weighted_score(self, signals: dict[str, dict]) -> float:
        weighted_sum = 0.0
        weight_used = 0.0
        for name, signal in signals.items():
            score = signal.get("score")
            if signal.get("status") == "available" and isinstance(score, (int, float)):
                weight = self.WEIGHTS[name]
                weighted_sum += float(score) * weight
                weight_used += weight
        if weight_used == 0:
            return 0.0
        return round(weighted_sum / weight_used, 2)
