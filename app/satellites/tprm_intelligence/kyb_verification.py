from __future__ import annotations

from datetime import UTC, datetime

from app.satellites.tprm_intelligence.config import get_tprm_intelligence_settings
from app.satellites.tprm_intelligence.http_client import SatelliteHTTPClient


class KYBVerificationService:
    """Aggregates free/open KYB signals inside the TPRM intelligence satellite.

    OpenOwnership coverage is limited by the public register's source countries
    and availability, so it must be treated as a coverage-limited signal rather
    than a universal beneficial ownership registry.
    """

    def __init__(self, http_client: SatelliteHTTPClient | None = None) -> None:
        self.http = http_client or SatelliteHTTPClient()
        self.settings = get_tprm_intelligence_settings()

    def compute(self, company_name: str) -> dict:
        normalized = self._normalize_company_name(company_name)
        signals = {
            "opencorporates": self._opencorporates(normalized),
            "gleif": self._gleif(normalized),
            "icij_offshore_leaks": self._icij(normalized),
            "openownership": self._openownership(normalized),
            "gdelt_adverse_media": self._gdelt(normalized),
        }
        return {
            "company_name": normalized,
            "signals_used": signals,
            "offshore_links_found": self._offshore_links(signals),
            "ubo_data": self._ubo_data(signals),
            "adverse_media_found": bool((signals.get("gdelt_adverse_media") or {}).get("article_count", 0)),
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def _normalize_company_name(self, company_name: str) -> str:
        normalized = " ".join((company_name or "").strip().split())
        if not normalized:
            raise ValueError("Vendor company name is required for KYB checks")
        return normalized[:255]

    def _opencorporates(self, company_name: str) -> dict:
        if not self.settings.OPENCORPORATES_API_KEY:
            return {
                "status": "skipped",
                "source": "opencorporates",
                "score": None,
                "message": "OpenCorporates signal skipped: API key not configured",
            }
        try:
            payload = self.http.get_json(
                "https://api.opencorporates.com/v0.4/companies/search",
                params={"q": company_name, "api_token": self.settings.OPENCORPORATES_API_KEY},
            )
            companies = ((payload.get("results") or {}).get("companies") or []) if isinstance(payload, dict) else []
            return {
                "status": "available",
                "source": "opencorporates",
                "match_count": len(companies),
                "companies": [item.get("company", item) for item in companies[:5] if isinstance(item, dict)],
            }
        except Exception as exc:
            return {"status": "error", "source": "opencorporates", "message": str(exc)}

    def _gleif(self, company_name: str) -> dict:
        try:
            payload = self.http.get_json(
                "https://api.gleif.org/api/v1/lei-records",
                params={"filter[entity.legalName]": company_name, "page[size]": 5},
            )
            records = payload.get("data") or []
            return {
                "status": "available",
                "source": "gleif",
                "match_count": len(records) if isinstance(records, list) else 0,
                "records": [self._summarize_gleif_record(item) for item in records[:5] if isinstance(item, dict)],
            }
        except Exception as exc:
            return {"status": "error", "source": "gleif", "message": str(exc)}

    def _icij(self, company_name: str) -> dict:
        try:
            payload = self.http.get_json("https://offshoreleaks.icij.org/api/search", params={"q": company_name})
            results = payload.get("results") or payload.get("items") or payload.get("data") or []
            return {
                "status": "available",
                "source": "icij_offshore_leaks",
                "match_count": len(results) if isinstance(results, list) else 0,
                "results": results[:10] if isinstance(results, list) else [],
            }
        except Exception as exc:
            return {"status": "error", "source": "icij_offshore_leaks", "message": str(exc)}

    def _openownership(self, company_name: str) -> dict:
        try:
            payload = self.http.get_json(
                "https://register.openownership.org/api/v0/statements",
                params={"q": company_name, "limit": 10},
            )
            statements = payload.get("data") or payload.get("results") or payload.get("statements") or []
            return {
                "status": "available",
                "source": "openownership",
                "coverage_limitation": "Public register coverage is limited, notably to UK, Ukraine, Denmark, Norway, and other published BODS sources when available.",
                "statement_count": len(statements) if isinstance(statements, list) else 0,
                "statements": statements[:10] if isinstance(statements, list) else [],
            }
        except Exception as exc:
            return {
                "status": "error",
                "source": "openownership",
                "coverage_limitation": "Public register coverage is limited, notably to UK, Ukraine, Denmark, Norway, and other published BODS sources when available.",
                "message": str(exc),
            }

    def _gdelt(self, company_name: str) -> dict:
        query = f'"{company_name}" (fraud OR bribery OR corruption OR sanctions OR laundering OR lawsuit OR investigation)'
        try:
            payload = self.http.get_json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": query, "mode": "ArtList", "format": "json", "maxrecords": 10, "sort": "hybridrel"},
            )
            articles = payload.get("articles") or []
            return {
                "status": "available",
                "source": "gdelt",
                "article_count": len(articles) if isinstance(articles, list) else 0,
                "articles": [
                    {"title": item.get("title"), "url": item.get("url"), "domain": item.get("domain")}
                    for item in articles[:5]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            return {"status": "error", "source": "gdelt", "message": str(exc)}

    def _summarize_gleif_record(self, item: dict) -> dict:
        attributes = item.get("attributes") or {}
        entity = attributes.get("entity") or {}
        registration = attributes.get("registration") or {}
        legal_name = entity.get("legalName") or {}
        return {
            "lei": item.get("id"),
            "legal_name": legal_name.get("name") if isinstance(legal_name, dict) else legal_name,
            "entity_status": entity.get("status"),
            "registration_status": registration.get("status"),
            "jurisdiction": entity.get("jurisdiction"),
        }

    def _offshore_links(self, signals: dict[str, dict]) -> dict:
        icij = signals.get("icij_offshore_leaks") or {}
        return {
            "source": "icij_offshore_leaks",
            "found": icij.get("status") == "available" and int(icij.get("match_count") or 0) > 0,
            "matches": icij.get("results", []),
            "status": icij.get("status"),
        }

    def _ubo_data(self, signals: dict[str, dict]) -> dict:
        openownership = signals.get("openownership") or {}
        return {
            "source": "openownership",
            "status": openownership.get("status"),
            "coverage_limitation": openownership.get("coverage_limitation"),
            "statements": openownership.get("statements", []),
        }
