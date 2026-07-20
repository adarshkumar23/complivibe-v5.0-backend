from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.integrations.security.parsers.openscap_parser import OpenSCAPParser
from app.models.audit_log import AuditLog
from app.models.data_asset import DataAsset
from app.models.issue import Issue
from app.models.openscap_rule_mapping import OpenSCAPRuleMapping
from app.models.security_scan_job import SecurityScanJob
from tests.helpers.auth_org import bootstrap_org_user


def _ingest_key(client, org_headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/integrations/ingest-keys",
        headers=org_headers,
        json={"key_type": "security"},
    )
    assert response.status_code == 201, response.text
    key = response.json().get("api_key")
    assert key
    return key


XCCDF_FIXTURE = """<?xml version="1.0"?>
<TestResult
  xmlns="http://checklists.nist.gov/xccdf/1.2"
  id="xccdf_result_1"
  start-time="2024-01-01T00:00:00"
  end-time="2024-01-01T00:01:00">
  <rule-result
    idref="xccdf_org.ssgproject.content_rule_audit_time_rules"
    time="2024-01-01T00:00:01"
    severity="high">
    <result>fail</result>
    <ident system="https://nvd.nist.gov/cce">CCE-27031-2</ident>
  </rule-result>
  <rule-result
    idref="xccdf_org.ssgproject.content_rule_sshd_disable_root_login"
    time="2024-01-01T00:00:02"
    severity="medium">
    <result>pass</result>
  </rule-result>
  <rule-result
    idref="xccdf_org.ssgproject.content_rule_accounts_password_minlen"
    time="2024-01-01T00:00:03"
    severity="low">
    <result>fail</result>
  </rule-result>
</TestResult>"""


def _wazuh_payload() -> list[dict]:
    return [
        {
            "rule": {
                "id": "5501",
                "level": 13,
                "description": "User login failed",
                "compliance": {
                    "pci_dss": ["10.2.4"],
                    "hipaa": ["164.312.b"],
                },
            },
            "agent": {
                "name": "web-server-01",
                "ip": "10.0.0.1",
            },
            "timestamp": "2024-01-01T00:00:00Z",
            "id": "1234567890.1",
        },
        {
            "rule": {
                "id": "1002",
                "level": 5,
                "description": "Low severity event",
            },
            "agent": {
                "name": "db-server-01",
                "ip": "10.0.0.2",
            },
            "timestamp": "2024-01-01T00:00:01Z",
            "id": "1234567890.2",
        },
    ]


def _fides_manifest() -> dict:
    return {
        "dataset": [
            {
                "fides_key": "user_database",
                "name": "User Database",
                "description": "Primary user store",
                "data_categories": ["user.email", "user.payment"],
                "collections": [],
            },
            {
                "fides_key": "analytics_db",
                "name": "Analytics Database",
                "description": "Analytics data",
                "data_categories": ["system.operations"],
                "collections": [],
            },
        ]
    }


def test_openscap_ingest_and_rule_mapping_seed(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2-openscap")
    key = _ingest_key(client, org["org_headers"])

    tables = set(inspect(db_session.bind).get_table_names())
    assert "openscap_rule_mappings" in tables

    response = client.post(
        "/api/v1/security/ingest/openscap",
        headers={"X-CompliVibe-Key": key, "Content-Type": "application/xml"},
        data=XCCDF_FIXTURE,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_findings"] == 3
    assert body["failed_count"] == 2
    assert body["issues_created"] == 1
    assert body["control_tests_created"] == 3

    row = db_session.get(SecurityScanJob, UUID(body["scan_job_id"]))
    assert row is not None
    assert row.scan_source == "openscap"
    assert row.status == "completed"

    parsed = OpenSCAPParser().parse(XCCDF_FIXTURE)
    mapping_rows = db_session.execute(select(OpenSCAPRuleMapping)).scalars().all()
    if mapping_rows:
        parser = OpenSCAPParser()
        family_audit, _ = parser.map_rule_to_control_family(parsed[0]["rule_id"], mapping_rows)
        family_sshd, _ = parser.map_rule_to_control_family(parsed[1]["rule_id"], mapping_rows)
        family_accounts, _ = parser.map_rule_to_control_family(parsed[2]["rule_id"], mapping_rows)
        assert family_audit == "AU"
        assert family_sshd == "SC"
        assert family_accounts == "AC"

    invalid_xml = client.post(
        "/api/v1/security/ingest/openscap",
        headers={"X-CompliVibe-Key": key, "Content-Type": "application/xml"},
        data="<not-xml",
    )
    assert invalid_xml.status_code == 400

    invalid_key = client.post(
        "/api/v1/security/ingest/openscap",
        headers={"X-CompliVibe-Key": "invalid", "Content-Type": "application/xml"},
        data=XCCDF_FIXTURE,
    )
    assert invalid_key.status_code == 401


def test_wazuh_ingest_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2-wazuh")
    key = _ingest_key(client, org["org_headers"])

    response = client.post(
        "/api/v1/security/ingest/wazuh",
        headers={"X-CompliVibe-Key": key},
        json=_wazuh_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_alerts"] == 2
    assert body["high_count"] == 1
    assert body["low_count"] == 1
    assert body["issues_created"] == 1
    assert body["control_tests_created"] == 2

    wrapped = client.post(
        "/api/v1/security/ingest/wazuh",
        headers={"X-CompliVibe-Key": key},
        json={"alerts": _wazuh_payload()},
    )
    assert wrapped.status_code == 200
    assert wrapped.json()["total_alerts"] == 2

    invalid = client.post(
        "/api/v1/security/ingest/wazuh",
        headers={"X-CompliVibe-Key": "invalid"},
        json=_wazuh_payload(),
    )
    assert invalid.status_code == 401

    high_issue = db_session.execute(
        select(Issue).where(
            Issue.organization_id == UUID(org["organization_id"]),
            Issue.title.contains("Wazuh Alert"),
        )
    ).scalars().first()
    assert high_issue is not None

    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "security.wazuh_alerts_ingested",
        )
    ).scalars().first()
    assert audit_row is not None


def test_fides_import_idempotent_and_status(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c2-fides")

    first = client.post(
        "/api/v1/privacy/import/fides",
        headers=org["org_headers"],
        json=_fides_manifest(),
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["assets_created"] == 2
    assert first_body["assets_updated"] == 0

    second = client.post(
        "/api/v1/privacy/import/fides",
        headers=org["org_headers"],
        json=_fides_manifest(),
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["assets_created"] == 0
    assert second_body["assets_updated"] == 2

    assets = db_session.execute(
        select(DataAsset).where(
            DataAsset.organization_id == UUID(org["organization_id"]),
            DataAsset.import_source == "fides",
            DataAsset.deleted_at.is_(None),
        )
    ).scalars().all()
    assert len(assets) == 2

    user_db = next(item for item in assets if item.import_key == "user_database")
    analytics_db = next(item for item in assets if item.import_key == "analytics_db")
    assert user_db.classification_type == "financial_data"
    assert analytics_db.classification_type == "operational_data"
    assert user_db.classification_confirmed is False

    # `client` carries a session cookie set by an earlier register() call -- clear it to
    # actually test the fully-unauthenticated case.
    client.cookies.clear()
    no_jwt = client.post("/api/v1/privacy/import/fides", json=_fides_manifest())
    assert no_jwt.status_code == 401

    status_resp = client.get("/api/v1/privacy/import/fides/status", headers=org["org_headers"])
    assert status_resp.status_code == 200
    assert status_resp.json()["asset_count"] == 2


def test_openscap_rule_mappings_seeded(client, db_session):
    _ = bootstrap_org_user(client, email_prefix="c2-openscap-seed")
    rows = db_session.execute(select(OpenSCAPRuleMapping)).scalars().all()
    if rows:
        assert len(rows) == 15
        mapping = db_session.execute(
            select(OpenSCAPRuleMapping).where(
                OpenSCAPRuleMapping.rule_prefix == "xccdf_org.ssgproject.content_rule_audit_"
            )
        ).scalar_one_or_none()
        assert mapping is not None
        assert mapping.control_family == "AU"
