import json
import uuid

from app.models.audit_log import AuditLog
from app.models.framework_content_import import FrameworkContentImport
from app.models.obligation import Obligation
from app.services.framework_content_pack_service import FrameworkContentPackService


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _framework_id_by_code(client, token: str, code: str) -> str:
    response = client.get("/api/v1/frameworks", headers=_headers(token))
    assert response.status_code == 200
    for item in response.json():
        if item["code"] == code:
            return item["id"]
    raise AssertionError(f"Framework {code} not found")


def test_list_local_packs_and_caveat_and_global_coverage_summary(client):
    owner = _register(client, "p37-owner1@example.com", "Pass1234!@", "P37 Org1")
    org_id = _org_id(client, owner)

    packs = client.get("/api/v1/framework-content/packs", headers=_headers(owner, org_id))
    assert packs.status_code == 200
    pack_items = packs.json()
    assert len(pack_items) >= 8
    keys = {item["pack_key"] for item in pack_items}
    assert "eu_ai_act_starter" in keys
    assert all("structured starter representation" in item["caveat"].lower() for item in pack_items)

    summary = client.get("/api/v1/framework-content/coverage-summary", headers=_headers(owner, org_id))
    assert summary.status_code == 200
    rows = summary.json()
    assert len(rows) >= 8
    assert all(row["coverage_level"] != "full_verified" for row in rows)


def test_validate_pack_success_and_invalid_schema_failure(client, monkeypatch, tmp_path):
    owner = _register(client, "p37-owner2@example.com", "Pass1234!@", "P37 Org2")
    org_id = _org_id(client, owner)

    valid = client.post("/api/v1/framework-content/packs/eu_ai_act_starter/validate", headers=_headers(owner, org_id))
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    invalid_dir = tmp_path / "frameworks"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "broken_pack.json").write_text(json.dumps({"pack_key": "broken_pack"}))
    monkeypatch.setattr(FrameworkContentPackService, "PACK_ROOT", invalid_dir)

    invalid = client.post("/api/v1/framework-content/packs/broken_pack/validate", headers=_headers(owner, org_id))
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert invalid.json()["validation_errors"]


def test_pack_apply_dry_run_and_live_apply_idempotent(client, db_session):
    owner = _register(client, "p37-owner3@example.com", "Pass1234!@", "P37 Org3")
    org_id = _org_id(client, owner)

    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    before_imports = db_session.query(FrameworkContentImport).count()

    dry_run = client.post(
        "/api/v1/framework-content/packs/eu_ai_act_starter/apply",
        headers=_headers(owner, org_id),
        json={"dry_run": True, "force_update": False},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["valid"] is True
    assert dry_run.json()["persisted"] is False
    assert db_session.query(FrameworkContentImport).count() == before_imports

    live_1 = client.post(
        "/api/v1/framework-content/packs/eu_ai_act_starter/apply",
        headers=_headers(owner, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert live_1.status_code == 200
    assert live_1.json()["valid"] is True
    assert live_1.json()["persisted"] is True

    live_2 = client.post(
        "/api/v1/framework-content/packs/eu_ai_act_starter/apply",
        headers=_headers(owner, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert live_2.status_code == 200
    assert live_2.json()["valid"] is True

    obligations = (
        db_session.query(Obligation)
        .filter(Obligation.framework_id == uuid.UUID(framework_id), Obligation.reference_code == "EUAI-OBL-1")
        .all()
    )
    assert len(obligations) == 1


def test_pack_with_full_verified_is_rejected(client, monkeypatch, tmp_path):
    owner = _register(client, "p37-owner4@example.com", "Pass1234!@", "P37 Org4")
    org_id = _org_id(client, owner)

    pack_dir = tmp_path / "frameworks"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "bad_full_verified.json").write_text(
        json.dumps(
            {
                "pack_key": "bad_full_verified",
                "framework_code": "EU_AI_ACT",
                "framework_name": "EU AI Act",
                "version_label": "2024",
                "coverage_level": "full_verified",
                "review_status": "unreviewed",
                "caveat": "This framework content pack is a structured starter representation and does not constitute legal advice or complete regulatory coverage.",
                "sections": [],
                "obligations": [],
                "content_versions": [],
                "applicability_questions": [],
                "evidence_requirements": [],
                "control_suggestions": [],
            }
        )
    )
    monkeypatch.setattr(FrameworkContentPackService, "PACK_ROOT", pack_dir)

    response = client.post("/api/v1/framework-content/packs/bad_full_verified/validate", headers=_headers(owner, org_id))
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert any("full_verified" in msg for msg in response.json()["validation_errors"])


def test_framework_coverage_report_persist_list_and_gaps(client):
    owner = _register(client, "p37-owner5@example.com", "Pass1234!@", "P37 Org5")
    org_id = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "GDPR")

    client.post(
        "/api/v1/framework-content/packs/gdpr_starter/apply",
        headers=_headers(owner, org_id),
        json={"dry_run": False, "force_update": False},
    )

    report = client.post(
        f"/api/v1/frameworks/{framework_id}/coverage-report",
        headers=_headers(owner, org_id),
        json={"persist": True},
    )
    assert report.status_code == 200
    report_body = report.json()
    assert report_body["id"] is not None
    assert report_body["total_obligations"] >= 1

    listed = client.get(f"/api/v1/frameworks/{framework_id}/coverage-reports", headers=_headers(owner, org_id))
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    gaps = client.get(f"/api/v1/frameworks/{framework_id}/coverage-gaps", headers=_headers(owner, org_id))
    assert gaps.status_code == 200
    gap_body = gaps.json()
    assert "obligations_missing_content" in gap_body
    assert "sections_without_obligations" in gap_body
    assert "caveat" in gap_body


def test_framework_content_pack_phase37_audit_log_written(client, db_session):
    owner = _register(client, "p37-owner6@example.com", "Pass1234!@", "P37 Org6")
    org_id = _org_id(client, owner)

    applied = client.post(
        "/api/v1/framework-content/packs/nist_ai_rmf_starter/apply",
        headers=_headers(owner, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert applied.status_code == 200

    logs = db_session.query(AuditLog).filter(AuditLog.action == "framework_content_pack.applied").all()
    assert len(logs) >= 1


def test_seed_pack_consistency_check_reports_zero_drift_for_current_packs(client):
    owner = _register(client, "p37-owner7@example.com", "Pass1234!@", "P37 Org7")
    org_id = _org_id(client, owner)

    result = client.get("/api/v1/framework-content/consistency-check", headers=_headers(owner, org_id))
    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is True
    assert body["drift_count"] == 0
    assert body["drift_rows"] == []


def test_seed_pack_consistency_check_catches_reintroduced_gdpr_drift(client, monkeypatch, tmp_path):
    owner = _register(client, "p37-owner8@example.com", "Pass1234!@", "P37 Org8")
    org_id = _org_id(client, owner)

    pack_dir = tmp_path / "frameworks"
    pack_dir.mkdir(parents=True, exist_ok=True)
    source_path = FrameworkContentPackService.PACK_ROOT / "gdpr_starter.json"
    payload = json.loads(source_path.read_text())
    for item in payload["obligations"]:
        if item.get("reference_code") == "GDPR-OBL-02":
            item["description"] = "DRIFTED DESCRIPTION"
            break
    (pack_dir / "gdpr_starter.json").write_text(json.dumps(payload))
    monkeypatch.setattr(FrameworkContentPackService, "PACK_ROOT", pack_dir)

    consistency = client.get("/api/v1/framework-content/consistency-check?pack_key=gdpr_starter", headers=_headers(owner, org_id))
    assert consistency.status_code == 200
    body = consistency.json()
    assert body["ok"] is False
    assert body["drift_count"] >= 1
    assert any(row["reference_code"] == "GDPR-OBL-02" for row in body["drift_rows"])

    validate = client.post("/api/v1/framework-content/packs/gdpr_starter/validate", headers=_headers(owner, org_id))
    assert validate.status_code == 200
    assert validate.json()["valid"] is False
    assert any("seed/pack drift" in msg for msg in validate.json()["validation_errors"])


def _minimal_pack(*, framework_code: str, control_title: str, control_description: str, control_domain: str) -> dict:
    return {
        "pack_key": f"{framework_code.lower()}_synthetic",
        "framework_code": framework_code,
        "framework_name": framework_code,
        "version_label": "2024",
        "coverage_level": "starter",
        "review_status": "unreviewed",
        "caveat": (
            "This framework content pack is a structured starter representation and does not "
            "constitute legal advice or complete regulatory coverage."
        ),
        "sections": [],
        "obligations": [],
        "content_versions": [],
        "applicability_questions": [],
        "evidence_requirements": [],
        "control_suggestions": [
            {
                "reference_code": f"{framework_code}-OBL-1",
                "control_title": control_title,
                "control_description": control_description,
                "control_domain": control_domain,
                "priority": "high",
                "status": "active",
            }
        ],
    }


def test_consistency_check_flags_cross_framework_control_description_conflict(client, monkeypatch, tmp_path):
    owner = _register(client, "p37-owner-crossfw@example.com", "Pass1234!@", "P37 CrossFW Org")
    org_id = _org_id(client, owner)

    pack_dir = tmp_path / "frameworks"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "framework_a.json").write_text(
        json.dumps(
            _minimal_pack(
                framework_code="FW_A",
                control_title="Multi-factor authentication",
                control_description="Require MFA for all administrative access.",
                control_domain="access_control",
            )
        )
    )
    (pack_dir / "framework_b.json").write_text(
        json.dumps(
            _minimal_pack(
                framework_code="FW_B",
                control_title="Multi-factor authentication",
                control_description="Require MFA for all customer-facing logins.",
                control_domain="identity",
            )
        )
    )
    monkeypatch.setattr(FrameworkContentPackService, "PACK_ROOT", pack_dir)

    result = client.get("/api/v1/framework-content/consistency-check", headers=_headers(owner, org_id))
    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is False
    inconsistencies = body["cross_framework_control_inconsistencies"]
    assert len(inconsistencies) == 1
    entry = inconsistencies[0]
    assert entry["control_title"] == "Multi-factor authentication"
    assert set(entry["frameworks"]) == {"FW_A", "FW_B"}
    assert len(entry["conflicting_descriptions"]) == 2


def test_consistency_check_does_not_flag_same_framework_or_identical_controls(client, monkeypatch, tmp_path):
    owner = _register(client, "p37-owner-crossfw-clean@example.com", "Pass1234!@", "P37 CrossFW Clean Org")
    org_id = _org_id(client, owner)

    pack_dir = tmp_path / "frameworks"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "framework_c.json").write_text(
        json.dumps(
            _minimal_pack(
                framework_code="FW_C",
                control_title="Encryption at rest",
                control_description="Encrypt all data at rest using AES-256.",
                control_domain="cryptography",
            )
        )
    )
    (pack_dir / "framework_d.json").write_text(
        json.dumps(
            _minimal_pack(
                framework_code="FW_D",
                control_title="Encryption at rest",
                control_description="Encrypt all data at rest using AES-256.",
                control_domain="cryptography",
            )
        )
    )
    monkeypatch.setattr(FrameworkContentPackService, "PACK_ROOT", pack_dir)

    result = client.get("/api/v1/framework-content/consistency-check", headers=_headers(owner, org_id))
    assert result.status_code == 200
    body = result.json()
    assert body["cross_framework_control_inconsistencies"] == []
    assert body["ok"] is True
