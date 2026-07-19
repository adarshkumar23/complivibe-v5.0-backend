"""GET endpoints must not write.

Part 1 removed lazy `SeedService.ensure_* + db.commit()` from the framework and
obligation read handlers -- a read that mutated the database, with no permission
check covering the write. Five GET endpoints were left with the same defect and
are covered here:

  * GET /framework-content/packs
  * GET /framework-content/coverage-summary
  * GET /ai-governance/iso42001/conformity-tracker
  * GET /ai-governance/iso42001/summary
  * GET /ai-governance/iso42001/conformity-summary

The reference catalogue is seeded once at application startup (app/main.py
lifespan), so these handlers do not need to seed it themselves.

NOTE on the iso42001 endpoints: they also materialise per-organization
ISO42001ConformityTracker rows via `get_or_create_trackers`. That is the
endpoint's documented contract, not the seeding defect, and is deliberately left
alone -- see the module docstring in iso42001_service. These tests therefore
assert that the *global reference catalogue* is not written by a read, which is
the defect being fixed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.framework import Framework
from app.models.obligation import Obligation
from tests.helpers.auth_org import bootstrap_org_user

# Deliberately NOT using seeded_reference_data for the side-effect tests: with the
# catalogue already present, SeedService.ensure_* is a no-op and writes nothing, so
# the test would pass whether or not the defect exists. Starting from an empty
# catalogue is the only way to observe a read creating rows.

READ_ENDPOINTS = [
    "/api/v1/framework-content/packs",
    "/api/v1/framework-content/coverage-summary",
    "/api/v1/ai-governance/iso42001/conformity-tracker",
    "/api/v1/ai-governance/iso42001/summary",
    "/api/v1/ai-governance/iso42001/conformity-summary",
]


def _catalogue_counts(db) -> tuple[int, int]:
    return (
        db.execute(select(func.count()).select_from(Framework)).scalar_one(),
        db.execute(select(func.count()).select_from(Obligation)).scalar_one(),
    )


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_read_endpoint_does_not_write_reference_catalogue(client, db_session, path):
    """A GET must not create framework/obligation rows, even on an empty catalogue."""
    org = bootstrap_org_user(client, email_prefix="noside")
    before = _catalogue_counts(db_session)
    assert before == (0, 0) or before[1] == 0, (
        "this test must start from an unseeded catalogue to be meaningful; "
        f"got frameworks={before[0]} obligations={before[1]}"
    )

    response = client.get(path, headers=org["org_headers"])
    # On an unseeded catalogue a 404 is the correct answer -- the endpoint must fail
    # loudly rather than silently materialise reference data mid-read. What must not
    # happen, either way, is a write.
    assert response.status_code in (200, 404), f"{path} -> {response.status_code}: {response.text}"

    db_session.expire_all()
    after = _catalogue_counts(db_session)
    assert after == before, (
        f"{path} mutated the reference catalogue: "
        f"frameworks {before[0]}->{after[0]}, obligations {before[1]}->{after[1]}"
    )


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_read_endpoint_is_repeatable_without_growth(client, db_session, path):
    """Calling a read twice must not accumulate rows."""
    org = bootstrap_org_user(client, email_prefix="noside-rep")
    client.get(path, headers=org["org_headers"])
    db_session.expire_all()
    after_first = _catalogue_counts(db_session)

    client.get(path, headers=org["org_headers"])
    db_session.expire_all()
    after_second = _catalogue_counts(db_session)

    assert after_second == after_first


@pytest.mark.usefixtures("seeded_reference_data")
def test_reads_still_return_real_catalogue_data(client, db_session):
    """The fix must not hollow out the responses -- seeded data is still served."""
    org = bootstrap_org_user(client, email_prefix="noside-data")

    packs = client.get("/api/v1/framework-content/packs", headers=org["org_headers"])
    assert packs.status_code == 200
    assert isinstance(packs.json(), list)

    coverage = client.get(
        "/api/v1/framework-content/coverage-summary", headers=org["org_headers"]
    )
    assert coverage.status_code == 200

    tracker = client.get(
        "/api/v1/ai-governance/iso42001/conformity-tracker", headers=org["org_headers"]
    )
    assert tracker.status_code == 200
    assert len(tracker.json()) > 0, "ISO 42001 clauses come from the startup-seeded catalogue"
