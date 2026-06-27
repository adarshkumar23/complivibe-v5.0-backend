import uuid

import httpx


class OpenMetadataClient:
    """
    Optional read-only OpenMetadata catalog client.
    """

    def __init__(self, base_url: str, jwt_token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

    def list_tables(self, limit: int = 100, offset: int = 0) -> list[dict]:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/tables",
                headers=self.headers,
                params={"limit": limit, "offset": offset},
                timeout=10.0,
            )
            response.raise_for_status()
            return list(response.json().get("data", []))
        except Exception as exc:
            raise RuntimeError(f"OpenMetadata connection failed: {str(exc)}") from exc

    def get_lineage(self, entity_id: str) -> dict:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/lineage/table/{entity_id}",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            return dict(response.json())
        except Exception as exc:
            raise RuntimeError(f"OpenMetadata lineage fetch failed: {str(exc)}") from exc

    def map_lineage_to_edges(self, lineage_data: dict, org_id: uuid.UUID) -> list[dict]:
        _ = org_id
        edges = []
        links = lineage_data.get("downstreamEdges") or []
        for link in links:
            from_id = link.get("fromEntity", {}).get("id")
            to_id = link.get("toEntity", {}).get("id")
            if from_id and to_id:
                edges.append(
                    {
                        "upstream_name": str(from_id),
                        "downstream_name": str(to_id),
                        "source_method": "openmetadata_sync",
                    }
                )
        return edges
