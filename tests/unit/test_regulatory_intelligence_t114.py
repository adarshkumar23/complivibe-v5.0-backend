from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.framework import Framework
from app.models.organization_framework import OrganizationFramework
from app.models.regulatory_change_alert import RegulatoryChangeAlert
from app.services.regulatory_intelligence_service import RegulatoryIntelligenceService
from tests.helpers.auth_org import bootstrap_org_user


def _framework(db_session, code: str) -> Framework:
    row = db_session.execute(select(Framework).where(Framework.code == code)).scalar_one_or_none()
    if row is not None:
        return row
    row = Framework(
        code=code,
        name=code,
        description=None,
        category="compliance",
        jurisdiction="global",
        authority="Test",
        version="test",
        status="active",
        coverage_level="metadata_only",
        source_url=None,
        effective_date=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _activate(db_session, org_id: str, framework: Framework) -> None:
    existing = db_session.execute(
        select(OrganizationFramework).where(
            OrganizationFramework.organization_id == UUID(org_id),
            OrganizationFramework.framework_id == framework.id,
        )
    ).scalar_one_or_none()
    if existing is None:
        db_session.add(
            OrganizationFramework(
                organization_id=UUID(org_id),
                framework_id=framework.id,
                status="active",
                activated_at=datetime.now(UTC),
            )
        )
    else:
        existing.status = "active"


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeHttpClient:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def get(self, url: str, headers=None):
        if url not in self.mapping:
            raise RuntimeError(f"unexpected URL {url}")
        return _FakeResponse(self.mapping[url])


def test_t1_14_poll_creates_alerts_only_for_active_framework_orgs(client, db_session):
    org_nist = bootstrap_org_user(client, email_prefix="reg-nist")
    org_soc2 = bootstrap_org_user(client, email_prefix="reg-soc2")
    _activate(db_session, org_nist["organization_id"], _framework(db_session, "NIST_CSF"))
    _activate(db_session, org_soc2["organization_id"], _framework(db_session, "SOC2"))
    db_session.commit()

    nist_payload = """{
      "entries": [{
        "id": "https://csrc.nist.gov/pubs/test/csf",
        "title": "NIST Cybersecurity Framework draft update",
        "summary": "This draft updates CSF 2.0 implementation guidance.",
        "updated": "2026-07-05T00:00:00Z"
      }]
    }"""
    service = RegulatoryIntelligenceService(
        db_session,
        http_client=_FakeHttpClient({"https://csrc.nist.gov/CSRC/media/feeds/pubs/drafts-open-for-comment.json": nist_payload}),
    )

    result = service.poll_public_feeds()
    db_session.commit()

    assert result["created"] == 1
    nist_alerts = db_session.execute(
        select(RegulatoryChangeAlert).where(RegulatoryChangeAlert.organization_id == UUID(org_nist["organization_id"]))
    ).scalars().all()
    soc2_alerts = db_session.execute(
        select(RegulatoryChangeAlert).where(RegulatoryChangeAlert.organization_id == UUID(org_soc2["organization_id"]))
    ).scalars().all()
    assert len(nist_alerts) == 1
    assert nist_alerts[0].framework_code == "NIST_CSF"
    assert soc2_alerts == []

    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "regulatory_alert.created")).scalar_one_or_none()
    assert audit is not None
    assert audit.organization_id == UUID(org_nist["organization_id"])


def test_t1_14_source_error_is_recorded_without_marking_no_changes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="reg-dpdp")
    _activate(db_session, org["organization_id"], _framework(db_session, "INDIA_DPDP"))
    db_session.commit()

    result = RegulatoryIntelligenceService(db_session, http_client=_FakeHttpClient({})).poll_public_feeds()
    db_session.commit()

    assert result["created"] == 0
    assert result["source_errors"]
    error_row = db_session.execute(
        select(RegulatoryChangeAlert).where(
            RegulatoryChangeAlert.organization_id.is_(None),
            RegulatoryChangeAlert.source_key == "meity_dpdp",
            RegulatoryChangeAlert.status == "source_error",
        )
    ).scalar_one_or_none()
    assert error_row is not None
    assert "no official public rss" in error_row.error_message.lower()


def test_t1_14_regulatory_alert_list_and_acknowledge(client, db_session):
    org = bootstrap_org_user(client, email_prefix="reg-api")
    alert = RegulatoryChangeAlert(
        organization_id=UUID(org["organization_id"]),
        source_key="nist_csrc_drafts",
        source_name="NIST CSRC draft publications JSON",
        source_url="https://csrc.nist.gov/CSRC/media/feeds/pubs/drafts-open-for-comment.json",
        source_item_id="item-1",
        framework_code="NIST_CSF",
        title="NIST Cybersecurity Framework draft update",
        summary="CSF update",
        item_url="https://csrc.nist.gov/pubs/test/csf",
        published_at=datetime.now(UTC),
        status="new",
        severity="medium",
        match_reason="Matched active framework NIST_CSF",
        raw_item_json={"id": "item-1"},
    )
    db_session.add(alert)
    db_session.commit()

    listed = client.get("/api/v1/regulatory-alerts", headers=org["org_headers"])
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == str(alert.id)

    ack = client.post(f"/api/v1/regulatory-alerts/{alert.id}/acknowledge", headers=org["org_headers"])
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "regulatory_alert.acknowledged")).scalar_one_or_none()
    assert audit is not None
    assert audit.organization_id == UUID(org["organization_id"])
