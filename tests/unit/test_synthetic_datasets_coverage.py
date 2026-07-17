"""Additional coverage for the synthetic-dataset governance endpoints
(/synthetic-datasets). Complements test_synthetic_data_governance_t4_14.py
(which covers CRUD happy path, the none+validated governance gap, weak/strong
k_anonymity, the high-risk strict threshold, enum 422s, source-dataset 404,
param consistency, and an auditor 403 sweep).

NEW here (not covered there): org-scoping of the list/get surface, 404 on
MUTATIONS (patch/validate/delete) of a non-existent id, the standard weak
DIFFERENTIAL-PRIVACY (epsilon) governance-gap path, and a distinct readonly
403 (a different unprivileged role than the auditor case already exercised).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/synthetic-datasets"


def _create(client, headers, **overrides) -> dict:
    payload = {"name": "SD", "generation_method": "gan"}
    payload.update(overrides)
    r = client.post(BASE, headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# -- org scoping ----------------------------------------------------------------


def test_synthetic_datasets_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sd-cov-a")
    org_b = bootstrap_org_user(client, email_prefix="sd-cov-b")
    ds_a = _create(client, org_a["org_headers"], name="Org A Dataset")

    listed_b = client.get(BASE, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(item["id"] != ds_a["id"] for item in listed_b.json())

    # cross-org fetch is scoped-out (404), not a 403
    fetched = client.get(f"{BASE}/{ds_a['id']}", headers=org_b["org_headers"])
    assert fetched.status_code == 404, fetched.text


# -- 404 on mutations of a non-existent dataset ---------------------------------


def test_mutations_on_missing_dataset_return_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sd-cov-404")
    headers = org["org_headers"]
    missing = str(uuid.uuid4())

    assert client.patch(f"{BASE}/{missing}", headers=headers, json={"name": "New"}).status_code == 404
    assert (
        client.post(
            f"{BASE}/{missing}/validate", headers=headers, json={"validation_status": "validated"}
        ).status_code
        == 404
    )
    assert client.delete(f"{BASE}/{missing}", headers=headers).status_code == 404


# -- standard weak differential-privacy (epsilon) governance gap ----------------


def test_weak_epsilon_flags_gap_and_strong_epsilon_clears(client, db_session):
    """A validated differential-privacy dataset with epsilon above the standard
    ceiling (10) is a governance gap; lowering epsilon under the ceiling clears
    it. (The existing suite covers weak k_anonymity and strict-tier epsilon, but
    not the standard weak-epsilon path.)"""
    org = bootstrap_org_user(client, email_prefix="sd-cov-eps")
    headers = org["org_headers"]

    created = _create(
        client,
        headers,
        name="High-epsilon DP dataset",
        generation_method="dp_gan",
        privacy_technique="differential_privacy",
        privacy_parameter=25,  # eps=25 > standard ceiling of 10
    )
    validated = client.post(
        f"{BASE}/{created['id']}/validate", headers=headers, json={"validation_status": "validated"}
    )
    assert validated.status_code == 200
    vbody = validated.json()
    assert vbody["governance_gap_flag"] is True
    assert "epsilon=25" in vbody["governance_gap_reason"]
    assert "maximum threshold of 10" in vbody["governance_gap_reason"]

    # tighten epsilon under the ceiling -> gap clears
    tightened = client.patch(f"{BASE}/{created['id']}", headers=headers, json={"privacy_parameter": 0.5})
    assert tightened.status_code == 200
    assert tightened.json()["governance_gap_flag"] is False
    assert tightened.json()["governance_gap_reason"] is None


# -- permission enforcement (distinct role) -------------------------------------


def test_readonly_role_forbidden_from_synthetic_datasets(client, db_session):
    # readonly lacks synthetic_data:manage (which gates every endpoint, read
    # included) -> 403 on both a read and a write surface.
    org = bootstrap_org_user(client, email_prefix="sd-cov-perm")
    readonly = add_org_member(db_session, client, org["organization_id"], "sd-ro@example.com", role_name="readonly")

    assert client.get(BASE, headers=readonly).status_code == 403
    assert client.post(BASE, headers=readonly, json={"name": "X", "generation_method": "gan"}).status_code == 403
