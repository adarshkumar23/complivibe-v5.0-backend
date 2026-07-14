"""P1.7 regression: the direct control<->obligation read endpoints must reflect
BOTH mapping mechanisms (ControlObligationMapping via POST /controls/{id}/
obligations, and CommonControlMapping via POST /compliance/common-controls/
mappings). The aggregate/coverage view already unions both; the direct reads
previously consulted only ControlObligationMapping, so a common-control mapping
was invisible at GET /obligations/{id}/controls and GET /controls/{id}.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user


def _control(client, h, title):
    r = client.post("/api/v1/controls", headers=h, json={"title": title, "control_type": "policy", "criticality": "medium"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _framework_obligation(db_session):
    fw = Framework(code=f"P17-{uuid.uuid4().hex[:6]}", name="P17 FW", description="d", category="Security",
                   jurisdiction="US", authority="Auth", version="1.0", status="active", coverage_level="starter",
                   source_url=None, effective_date=date.today())
    db_session.add(fw); db_session.flush()
    ob = Obligation(framework_id=fw.id, framework_section_id=None, reference_code="CC6.1", title="ob",
                    description="o", plain_language_summary="s", obligation_type="control", jurisdiction="US",
                    source_url=None, version="1.0", status="active", effective_date=date.today(), parent_obligation_id=None)
    db_session.add(ob); db_session.flush(); db_session.commit()
    return fw, ob


def test_direct_reads_union_both_mapping_mechanisms(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p17")
    h = org["org_headers"]
    control_std = _control(client, h, "Std-mapped control")
    control_cc = _control(client, h, "Common-control-mapped control")

    fw, ob = _framework_obligation(db_session)
    db_session.add(OrganizationFramework(organization_id=uuid.UUID(org["organization_id"]), framework_id=fw.id,
                                         status="active", activated_by_user_id=uuid.UUID(org["user_id"]),
                                         activated_at=datetime.now(UTC), notes="t"))
    db_session.commit()

    # Mechanism 1: standard control->obligation mapping.
    m1 = client.post(f"/api/v1/controls/{control_std}/obligations", headers=h,
                     json={"obligation_id": str(ob.id), "mapping_type": "satisfies", "confidence": "manual_confirmed", "rationale": "r"})
    assert m1.status_code in (200, 201), m1.text

    # Mechanism 2: common-control mapping (same obligation, different control).
    m2 = client.post("/api/v1/compliance/common-controls/mappings", headers=h,
                     json={"control_id": control_cc, "framework_id": str(fw.id), "obligation_id": str(ob.id),
                           "section_reference": "CC6.1", "mapping_rationale": "covers", "mapping_strength": "full"})
    assert m2.status_code == 201, m2.text

    # Direct read A: obligation -> controls must include BOTH controls.
    controls_for_ob = client.get(f"/api/v1/obligations/{ob.id}/controls", headers=h)
    assert controls_for_ob.status_code == 200, controls_for_ob.text
    returned = {c["id"] for c in controls_for_ob.json()}
    assert control_std in returned, "standard mapping missing from obligation->controls"
    assert control_cc in returned, "common-control mapping missing from obligation->controls (P1.7)"

    # Direct read B: the common-control-mapped control's detail must show the obligation.
    detail = client.get(f"/api/v1/controls/{control_cc}", headers=h)
    assert detail.status_code == 200, detail.text
    mapped_ob_ids = {m["obligation_id"] for m in detail.json().get("mapped_obligations", [])}
    assert str(ob.id) in mapped_ob_ids, "common-control mapping missing from control detail (P1.7)"
