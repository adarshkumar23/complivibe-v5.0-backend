from __future__ import annotations

import socket
from datetime import UTC, datetime

from app.satellites.tprm_intelligence.config import get_tprm_intelligence_settings
from app.satellites.tprm_intelligence.http_client import SatelliteHTTPClient
from app.satellites.tprm_intelligence.vendor_security_rating import normalize_domain


class ThreatIntelligenceService:
    WEIGHTS = {"alienvault_otx": 0.45, "abuseipdb": 0.30, "gdelt_threat_media": 0.25}

    def __init__(self, http_client: SatelliteHTTPClient | None = None) -> None:
        self.http = http_client or SatelliteHTTPClient()
        self.settings = get_tprm_intelligence_settings()

    def compute(self, domain: str) -> dict:
        normalized = normalize_domain(domain)
        signals = {
            "alienvault_otx": self._alienvault_otx(normalized),
            "abuseipdb": self._abuseipdb(normalized),
            "gdelt_threat_media": self._gdelt(normalized),
        }
        indicators = self._collect_indicators(signals)
        return {
            "domain": normalized,
            "signals_used": signals,
            "threat_score": self._weighted_score(signals),
            "indicators_found": indicators,
            "computed_at": datetime.now(UTC).isoformat(),
        }

    def _alienvault_otx(self, domain: str) -> dict:
        if not self.settings.ALIENVAULT_OTX_API_KEY:
            return {"status": "skipped", "source": "alienvault_otx", "score": None, "message": "OTX signal skipped: no API key configured"}
        try:
            payload = self.http.get_json(
                f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/general",
                headers={"X-OTX-API-KEY": self.settings.ALIENVAULT_OTX_API_KEY},
            )
            pulse_info = payload.get("pulse_info") or {}
            pulses = pulse_info.get("pulses") or []
            pulse_count = int(pulse_info.get("count") or len(pulses) or 0)
            return {
                "status": "available",
                "source": "alienvault_otx",
                "score": min(100, pulse_count * 10),
                "pulse_count": pulse_count,
                "pulses": [p.get("name") for p in pulses[:5] if isinstance(p, dict)],
            }
        except Exception as exc:
            return {"status": "error", "source": "alienvault_otx", "score": None, "message": str(exc)}

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
            return {"status": "available", "source": "abuseipdb", "score": confidence, "ip_address": ip, "abuse_confidence_score": confidence}
        except Exception as exc:
            return {"status": "error", "source": "abuseipdb", "score": None, "message": str(exc)}

    def _gdelt(self, domain: str) -> dict:
        query = f'"{domain}" (malware OR ransomware OR phishing OR botnet OR exploit OR compromise OR threat)'
        try:
            payload = self.http.get_json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": query, "mode": "ArtList", "format": "json", "maxrecords": 10, "sort": "hybridrel"},
            )
            articles = payload.get("articles") or []
            count = len(articles) if isinstance(articles, list) else 0
            return {
                "status": "available",
                "source": "gdelt",
                "score": min(100, count * 10),
                "article_count": count,
                "articles": [
                    {"title": item.get("title"), "url": item.get("url"), "domain": item.get("domain")}
                    for item in articles[:5]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            return {"status": "error", "source": "gdelt", "score": None, "message": str(exc)}

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

    def _collect_indicators(self, signals: dict[str, dict]) -> dict:
        indicators: dict[str, object] = {}
        otx = signals.get("alienvault_otx") or {}
        if otx.get("status") == "available":
            indicators["otx_pulses"] = otx.get("pulses", [])
        abuse = signals.get("abuseipdb") or {}
        if abuse.get("status") == "available":
            indicators["abuseipdb"] = {"ip_address": abuse.get("ip_address"), "abuse_confidence_score": abuse.get("abuse_confidence_score")}
        gdelt = signals.get("gdelt_threat_media") or {}
        if gdelt.get("status") == "available":
            indicators["threat_media"] = gdelt.get("articles", [])
        return indicators
