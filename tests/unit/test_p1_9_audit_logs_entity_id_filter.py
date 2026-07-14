"""P1.9 regression: GET /audit-logs must honor an entity_id filter. Previously
the endpoint declared no query params, so ?entity_id=X was silently ignored
(FastAPI drops undeclared params) and every caller got the full org-wide log
stream regardless of the filter.
"""
from __future__ import annotations

import uuid

from app.services.audit_service import AuditService
from tests.helpers.auth_org import bootstrap_org_user


def test_audit_logs_entity_id_filter_is_applied(client, db_session):
    org = bootstrap_org_user(client, email_prefix="audit-filter")
    org_id = uuid.UUID(org["organization_id"])
    e1, e2 = uuid.uuid4(), uuid.uuid4()

    svc = AuditService(db_session)
    svc.write_audit_log(action="thing.created", entity_type="thing", organization_id=org_id, entity_id=e1)
    svc.write_audit_log(action="thing.created", entity_type="thing", organization_id=org_id, entity_id=e2)
    db_session.commit()

    resp = client.get(f"/api/v1/audit-logs?entity_id={e1}", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    returned_entity_ids = {row.get("entity_id") for row in resp.json()}
    assert str(e1) in returned_entity_ids
    assert str(e2) not in returned_entity_ids, "entity_id filter must exclude other entities' logs"
    assert returned_entity_ids <= {str(e1)}, f"filter leaked other entity_ids: {returned_entity_ids}"
