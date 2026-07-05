import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/training-datasets"


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


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Fraud Agent") -> dict:
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


def _create_dataset(client, headers: dict[str, str], *, ai_system_id: str, **overrides) -> dict:
    payload = {
        "name": "Dataset A",
        "source": "internal-corpus",
        "license_type": "unclear",
        "consent_basis": None,
        "linked_ai_system_id": ai_system_id,
        "record_count": 100,
        "notes": "notes",
    }
    payload.update(overrides)
    response = client.post(BASE, headers=headers, json=payload)
    return response


def test_t4_13_dataset_crud_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t413-crud")
    headers = org["org_headers"]

    ai_system = _create_ai_system(client, headers, name="Crud Agent")

    create_resp = _create_dataset(
        client,
        headers,
        ai_system_id=ai_system["id"],
        name="Training Set 1",
        license_type="commercial_license",
        consent_basis="contractual",
        record_count=5000,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Training Set 1"
    assert created["license_type"] == "commercial_license"
    assert created["consent_basis"] == "contractual"
    assert created["linked_ai_system_id"] == ai_system["id"]
    assert created["deleted_at"] is None

    list_resp = client.get(BASE, headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == created["id"] for item in list_resp.json())

    get_resp = client.get(f"{BASE}/{created['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]

    update_resp = client.patch(
        f"{BASE}/{created['id']}",
        headers=headers,
        json={"name": "Training Set 1 Updated", "record_count": 6000},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Training Set 1 Updated"
    assert updated["record_count"] == 6000

    delete_resp = client.delete(f"{BASE}/{created['id']}", headers=headers)
    assert delete_resp.status_code == 204

    get_after_delete = client.get(f"{BASE}/{created['id']}", headers=headers)
    assert get_after_delete.status_code == 404

    list_after_delete = client.get(BASE, headers=headers)
    assert list_after_delete.status_code == 200
    assert all(item["id"] != created["id"] for item in list_after_delete.json())


def test_t4_13_rights_gaps_classification(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t413-gaps")
    headers = org["org_headers"]

    no_dataset_system = _create_ai_system(client, headers, name="No Dataset System")
    unclear_system = _create_ai_system(client, headers, name="Unclear Rights System")
    documented_system = _create_ai_system(client, headers, name="Documented System")

    unclear_resp = _create_dataset(
        client,
        headers,
        ai_system_id=unclear_system["id"],
        name="Unclear Dataset",
        license_type="unclear",
        consent_basis=None,
    )
    assert unclear_resp.status_code == 201, unclear_resp.text

    documented_resp = _create_dataset(
        client,
        headers,
        ai_system_id=documented_system["id"],
        name="Documented Dataset",
        license_type="commercial_license",
        consent_basis="contractual",
    )
    assert documented_resp.status_code == 201, documented_resp.text

    gaps_resp = client.get(f"{BASE}/rights-gaps", headers=headers)
    assert gaps_resp.status_code == 200, gaps_resp.text
    body = gaps_resp.json()

    no_dataset_ids = {item["id"] for item in body["no_dataset_linked"]}
    unclear_ids = {item["id"] for item in body["unclear_rights"]}

    assert no_dataset_system["id"] in no_dataset_ids
    assert unclear_system["id"] in unclear_ids

    # documented system must not appear in either gap list
    assert documented_system["id"] not in no_dataset_ids
    assert documented_system["id"] not in unclear_ids

    # sanity check names came through correctly
    no_dataset_names = {item["name"] for item in body["no_dataset_linked"]}
    unclear_names = {item["name"] for item in body["unclear_rights"]}
    assert "No Dataset System" in no_dataset_names
    assert "Unclear Rights System" in unclear_names

    assert body["total_ai_systems"] >= 3
    assert body["documented_count"] >= 1
    assert body["unclear_rights_count"] >= 1
    assert body["no_dataset_linked_count"] >= 1


def test_t4_13_link_to_missing_or_cross_org_ai_system_returns_404_no_orphan(client, db_session):
    from sqlalchemy import select

    from app.models.training_dataset import TrainingDataset

    org1 = bootstrap_org_user(client, email_prefix="t413-crossorg-a")
    org2 = bootstrap_org_user(client, email_prefix="t413-crossorg-b")

    org2_system = _create_ai_system(client, org2["org_headers"], name="Org2 System")

    cross_org_resp = _create_dataset(
        client,
        org1["org_headers"],
        ai_system_id=org2_system["id"],
        name="Cross Org Dataset",
    )
    assert cross_org_resp.status_code == 404
    assert "not found" in cross_org_resp.json()["detail"].lower()

    nonexistent_resp = _create_dataset(
        client,
        org1["org_headers"],
        ai_system_id=str(uuid.uuid4()),
        name="Nonexistent Link Dataset",
    )
    assert nonexistent_resp.status_code == 404
    assert "not found" in nonexistent_resp.json()["detail"].lower()

    orphans = db_session.execute(
        select(TrainingDataset).where(TrainingDataset.name.in_(["Cross Org Dataset", "Nonexistent Link Dataset"]))
    ).scalars().all()
    assert orphans == []


def test_t4_13_invalid_enum_values_return_422_with_allowed_values(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t413-enum")
    headers = org["org_headers"]

    ai_system = _create_ai_system(client, headers, name="Enum Agent")

    bad_license = _create_dataset(
        client,
        headers,
        ai_system_id=ai_system["id"],
        name="Bad License Dataset",
        license_type="not_a_real_license",
    )
    assert bad_license.status_code == 422
    body = bad_license.json()
    detail_str = str(body["detail"])
    assert "license_type" in detail_str
    for value in ["public_domain", "creative_commons", "commercial_license", "proprietary_internal", "unclear", "none"]:
        assert value in detail_str

    bad_consent = _create_dataset(
        client,
        headers,
        ai_system_id=ai_system["id"],
        name="Bad Consent Dataset",
        consent_basis="not_a_real_basis",
    )
    assert bad_consent.status_code == 422
    body2 = bad_consent.json()
    detail_str2 = str(body2["detail"])
    assert "consent_basis" in detail_str2
    for value in ["explicit_consent", "legitimate_interest", "contractual", "statutory", "not_applicable", "unclear"]:
        assert value in detail_str2


def test_t4_13_audit_log_rows_for_create_update_delete(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t413-audit")
    headers = org["org_headers"]

    ai_system = _create_ai_system(client, headers, name="Audit Agent")

    create_resp = _create_dataset(
        client,
        headers,
        ai_system_id=ai_system["id"],
        name="Audit Dataset",
        license_type="proprietary_internal",
        consent_basis="statutory",
    )
    assert create_resp.status_code == 201
    dataset_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"{BASE}/{dataset_id}",
        headers=headers,
        json={"notes": "updated notes"},
    )
    assert update_resp.status_code == 200

    delete_resp = client.delete(f"{BASE}/{dataset_id}", headers=headers)
    assert delete_resp.status_code == 204

    logs = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.entity_type == "training_dataset",
            AuditLog.entity_id == uuid.UUID(dataset_id),
        )
        .all()
    )
    actions = {log.action for log in logs}
    assert "training_dataset.created" in actions
    assert "training_dataset.updated" in actions
    assert "training_dataset.deleted" in actions


def test_t4_13_user_without_permission_gets_403(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t413-perm")
    owner_headers = org["org_headers"]

    # sanity: owner has access
    owner_gaps = client.get(f"{BASE}/rights-gaps", headers=owner_headers)
    assert owner_gaps.status_code == 200

    auditor_email = "t413-auditor@example.com"
    _create_active_user_with_role(db_session, org["organization_id"], auditor_email, role_name="auditor")
    auditor_token = login_user(client, auditor_email)
    auditor_headers = org_headers(auditor_token, org["organization_id"])

    auditor_gaps = client.get(f"{BASE}/rights-gaps", headers=auditor_headers)
    assert auditor_gaps.status_code == 403
