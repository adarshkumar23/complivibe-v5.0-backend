"""P1.11 regression: the app must bootstrap the Meilisearch indexes at startup.

ensure_indexes_ready() -- the only code that creates the indexes and sets
organization_id as a filterable attribute -- was never called anywhere, so a
live write landed in an auto-created index without the filter config and every
org-scoped search then failed (degraded/empty). The FastAPI lifespan startup
must invoke it. (ensure_indexes_ready is itself gated by APP_ENV/MEILISEARCH so
it is a no-op in the test env; here we assert only that startup calls it.)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_mod


def test_startup_invokes_search_index_bootstrap(monkeypatch):
    calls: list[bool] = []

    def _spy(db):
        calls.append(True)

    # raising=False so the test also runs against code where the wiring is absent
    # (in which case the spy is simply never called -> assertion fails = repro).
    monkeypatch.setattr(main_mod, "ensure_indexes_ready", _spy, raising=False)

    app = main_mod.create_application()
    with TestClient(app):  # entering the context manager runs the lifespan startup
        pass

    assert calls, "app startup must call ensure_indexes_ready to bootstrap search indexes"
