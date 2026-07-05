import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.role import Role
from app.models.synthetic_dataset import SyntheticDataset
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user

BASE = "/api/v1/synthetic-datasets"

GOVERNANCE_GAP_REASON = (
    "Dataset is marked 'validated' but uses privacy_technique='none' -- claiming "
    "privacy-validated status without applying a privacy-preserving technique is a "
    "logical contradiction and should be reviewed by governance."
)


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _create_ai_system(client, headers: dict[str, str], *, name: str = "AI System for T4-14") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={
            "name": name,
            "system_type": "agent",
            "lifecycle_status": "proposed",
            "tags_json": ["core"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_training_dataset(client, headers: dict[str, str], *, linked_ai_system_id: str, name: str = "Training Dataset T4-14") -> dict:
    response = client.post(
        "/api/v1/training-datasets",
        headers=headers,
        json={
            "name": name,
            "license_type": "unclear",
            "linked_ai_system_id": linked_ai_system_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_synthetic_dataset(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "name": "Synthetic Dataset T4-14",
        "generation_method": "gan",
    }
    payload.update(overrides)
    response = client.post(BASE, headers=headers, json=payload)
    return response


def test_happy_path_crud_and_validate_with_privacy_technique(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t414-happy")
    headers = org["org_headers"]

    created = _create_synthetic_dataset(
        client,
        headers,
        name="DP Synthetic Dataset",
        generation_method="differential_privacy_gan",
        privacy_technique="differential_privacy",
    )
    assert created.status_code == 201
    body = created.json()
    dataset_id = body["id"]
    assert body["privacy_technique"] == "differential_privacy"
    assert body["validation_status"] == "unvalidated"
    assert body["governance_gap_flag"] is False
    assert body["governance_gap_reason"] is None

    # list
    listed = client.get(BASE, headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == dataset_id for item in listed.json())

    # get
    fetched = client.get(f"{BASE}/{dataset_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == dataset_id

    # update
    updated = client.patch(
        f"{BASE}/{dataset_id}",
        headers=headers,
        json={"validation_notes": "looks good so far"},
    )
    assert updated.status_code == 200
    assert updated.json()["validation_notes"] == "looks good so far"

    # validate -> validated, with differential_privacy -> no contradiction
    validated = client.post(
        f"{BASE}/{dataset_id}/validate",
        headers=headers,
        json={"validation_status": "validated", "validation_notes": "reviewed by DPO"},
    )
    assert validated.status_code == 200
    vbody = validated.json()
    assert vbody["validation_status"] == "validated"
    assert vbody["governance_gap_flag"] is False
    assert vbody["governance_gap_reason"] is None

    # soft delete
    deleted = client.delete(f"{BASE}/{dataset_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    # no longer visible in list/get
    listed_after = client.get(BASE, headers=headers)
    assert listed_after.status_code == 200
    assert all(item["id"] != dataset_id for item in listed_after.json())

    get_after = client.get(f"{BASE}/{dataset_id}", headers=headers)
    assert get_after.status_code == 404

    row = db_session.query(SyntheticDataset).filter_by(id=uuid.UUID(dataset_id)).one()
    assert row.deleted_at is not None


def test_governance_gap_flagged_on_validate_and_clears_on_privacy_technique_update(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t414-gap")
    headers = org["org_headers"]

    created = _create_synthetic_dataset(
        client,
        headers,
        name="No-Privacy Synthetic Dataset",
        generation_method="basic_sampling",
        privacy_technique="none",
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    assert created.json()["governance_gap_flag"] is False  # unvalidated, no contradiction yet

    # validate -> validated while privacy_technique='none' should SUCCEED but flag a gap
    validated = client.post(
        f"{BASE}/{dataset_id}/validate",
        headers=headers,
        json={"validation_status": "validated"},
    )
    assert validated.status_code == 200
    vbody = validated.json()
    assert vbody["validation_status"] == "validated"
    assert vbody["governance_gap_flag"] is True
    assert vbody["governance_gap_reason"] == GOVERNANCE_GAP_REASON

    # appears in governance-gaps listing
    gaps = client.get(f"{BASE}/governance-gaps", headers=headers)
    assert gaps.status_code == 200
    gap_ids = [item["id"] for item in gaps.json()]
    assert dataset_id in gap_ids
    flagged_item = next(item for item in gaps.json() if item["id"] == dataset_id)
    assert flagged_item["governance_gap_reason"] == GOVERNANCE_GAP_REASON

    # also filterable via list endpoint with governance_gap_flag=true
    filtered = client.get(BASE, headers=headers, params={"governance_gap_flag": True})
    assert filtered.status_code == 200
    assert any(item["id"] == dataset_id for item in filtered.json())

    # now patch privacy_technique to k_anonymity -> gap should clear
    patched = client.patch(
        f"{BASE}/{dataset_id}",
        headers=headers,
        json={"privacy_technique": "k_anonymity"},
    )
    assert patched.status_code == 200
    pbody = patched.json()
    assert pbody["privacy_technique"] == "k_anonymity"
    assert pbody["governance_gap_flag"] is False
    assert pbody["governance_gap_reason"] is None

    # re-fetch to confirm persisted
    refetched = client.get(f"{BASE}/{dataset_id}", headers=headers)
    assert refetched.status_code == 200
    assert refetched.json()["governance_gap_flag"] is False

    gaps_after = client.get(f"{BASE}/governance-gaps", headers=headers)
    assert gaps_after.status_code == 200
    assert all(item["id"] != dataset_id for item in gaps_after.json())


def test_invalid_enum_values_return_422_with_allowed_values(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t414-enum")
    headers = org["org_headers"]

    bad_create = _create_synthetic_dataset(
        client,
        headers,
        privacy_technique="anonymization_magic",
    )
    assert bad_create.status_code == 422
    detail_text = str(bad_create.json())
    for value in ("differential_privacy", "k_anonymity", "none"):
        assert value in detail_text

    bad_create_status = _create_synthetic_dataset(
        client,
        headers,
        validation_status="approved_forever",
    )
    assert bad_create_status.status_code == 422
    detail_text_2 = str(bad_create_status.json())
    for value in ("unvalidated", "validated", "failed_validation"):
        assert value in detail_text_2

    # need a real dataset to hit /validate
    created = _create_synthetic_dataset(client, headers)
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    bad_validate = client.post(
        f"{BASE}/{dataset_id}/validate",
        headers=headers,
        json={"validation_status": "super_validated"},
    )
    assert bad_validate.status_code == 422
    validate_detail_text = str(bad_validate.json())
    for value in ("unvalidated", "validated", "failed_validation"):
        assert value in validate_detail_text


def test_source_dataset_id_nonexistent_or_cross_org_returns_404_and_no_orphan(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="t414-src-a")
    org2 = bootstrap_org_user(client, email_prefix="t414-src-b")

    # nonexistent training dataset
    missing_id = str(uuid.uuid4())
    resp_missing = _create_synthetic_dataset(
        client,
        org1["org_headers"],
        source_dataset_id=missing_id,
    )
    assert resp_missing.status_code == 404
    assert "not found" in resp_missing.json()["detail"].lower()

    # confirm no orphaned synthetic_datasets row was created
    orphans = db_session.query(SyntheticDataset).filter_by(
        organization_id=uuid.UUID(org1["organization_id"])
    ).all()
    assert orphans == []

    # cross-org training dataset: create in org2, reference from org1
    ai_system_org2 = _create_ai_system(client, org2["org_headers"], name="org2 ai system")
    training_dataset_org2 = _create_training_dataset(
        client, org2["org_headers"], linked_ai_system_id=ai_system_org2["id"]
    )

    resp_cross_org = _create_synthetic_dataset(
        client,
        org1["org_headers"],
        source_dataset_id=training_dataset_org2["id"],
    )
    assert resp_cross_org.status_code == 404
    assert "not found" in resp_cross_org.json()["detail"].lower()

    orphans_after = db_session.query(SyntheticDataset).filter_by(
        organization_id=uuid.UUID(org1["organization_id"])
    ).all()
    assert orphans_after == []

    # sanity: a valid same-org source_dataset_id works fine
    ai_system_org1 = _create_ai_system(client, org1["org_headers"], name="org1 ai system")
    training_dataset_org1 = _create_training_dataset(
        client, org1["org_headers"], linked_ai_system_id=ai_system_org1["id"]
    )
    ok = _create_synthetic_dataset(
        client,
        org1["org_headers"],
        source_dataset_id=training_dataset_org1["id"],
    )
    assert ok.status_code == 201
    assert ok.json()["source_dataset_id"] == training_dataset_org1["id"]


def test_audit_log_rows_written_for_create_and_contradiction_validate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t414-audit")
    headers = org["org_headers"]

    created = _create_synthetic_dataset(
        client,
        headers,
        name="Audit Synthetic Dataset",
        generation_method="basic_sampling",
        privacy_technique="none",
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    create_log = (
        db_session.query(AuditLog)
        .filter_by(
            organization_id=uuid.UUID(org["organization_id"]),
            entity_type="synthetic_dataset",
            entity_id=uuid.UUID(dataset_id),
            action="synthetic_dataset.created",
        )
        .one()
    )
    assert create_log.after_json["name"] == "Audit Synthetic Dataset"

    validated = client.post(
        f"{BASE}/{dataset_id}/validate",
        headers=headers,
        json={"validation_status": "validated"},
    )
    assert validated.status_code == 200
    assert validated.json()["governance_gap_flag"] is True

    validate_log = (
        db_session.query(AuditLog)
        .filter_by(
            organization_id=uuid.UUID(org["organization_id"]),
            entity_type="synthetic_dataset",
            entity_id=uuid.UUID(dataset_id),
            action="synthetic_dataset.validated",
        )
        .one()
    )
    assert validate_log.metadata_json.get("governance_gap") is True
    assert validate_log.metadata_json.get("reason") == GOVERNANCE_GAP_REASON
    assert validate_log.after_json["governance_gap_flag"] is True
    assert validate_log.after_json["validation_status"] == "validated"


def test_user_without_permission_gets_403(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t414-perm")
    headers = org["org_headers"]

    auditor_email = "t414-auditor@example.com"
    _create_active_user_with_role(db_session, org["organization_id"], auditor_email, role_name="auditor")
    auditor_token = login_user(client, auditor_email)
    auditor_headers = {
        "Authorization": f"Bearer {auditor_token}",
        "X-Organization-ID": org["organization_id"],
    }

    # owner creates a dataset first, so there's something to try to access
    created = _create_synthetic_dataset(client, headers)
    assert created.status_code == 201
    dataset_id = created.json()["id"]

    forbidden_create = _create_synthetic_dataset(client, auditor_headers)
    assert forbidden_create.status_code == 403

    forbidden_list = client.get(BASE, headers=auditor_headers)
    assert forbidden_list.status_code == 403

    forbidden_get = client.get(f"{BASE}/{dataset_id}", headers=auditor_headers)
    assert forbidden_get.status_code == 403

    forbidden_validate = client.post(
        f"{BASE}/{dataset_id}/validate",
        headers=auditor_headers,
        json={"validation_status": "validated"},
    )
    assert forbidden_validate.status_code == 403

    forbidden_gaps = client.get(f"{BASE}/governance-gaps", headers=auditor_headers)
    assert forbidden_gaps.status_code == 403
