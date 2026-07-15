from __future__ import annotations

"""Fast, PG-free regression guard that the entity-graph endpoint is registered in
the real application and gated by authentication.

The full traversal behaviour (recursive CTE + CYCLE, org scoping, permission code)
is covered against real Postgres in
tests/integration/test_entity_graph_traversal.py. This just pins the wiring so a
future refactor can't silently drop the route or its auth gate.
"""


def test_traverse_endpoint_registered_and_requires_auth(client):
    # Unauthenticated -> 401 (route exists and is gated); a bogus sibling path -> 404.
    resp = client.get(
        "/api/v1/graph/traverse",
        params={"entity_type": "vendor", "entity_id": "11111111-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 401

    missing = client.get("/api/v1/graph/does-not-exist")
    assert missing.status_code == 404
