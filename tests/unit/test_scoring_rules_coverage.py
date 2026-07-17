"""Coverage for the questionnaire scoring-rules endpoint
(/compliance/questionnaire-scoring-rules). Zero prior test references.

Covers create/list/update/deactivate happy path, vendor:write permission
enforcement, and the question-not-in-template validation edge case.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

TEMPLATES = "/api/v1/compliance/questionnaire-templates"
RULES = "/api/v1/compliance/questionnaire-scoring-rules"


def _template_with_question(client, headers) -> tuple[str, str]:
    t = client.post(TEMPLATES, headers=headers, json={"name": f"SR tmpl {uuid.uuid4().hex[:8]}", "version": "1.0"})
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    s = client.post(f"{TEMPLATES}/{tid}/sections", headers=headers, json={"title": "Sec", "order_index": 0})
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    q = client.post(
        f"{TEMPLATES}/{tid}/sections/{sid}/questions",
        headers=headers,
        json={"question_text": "Do you encrypt data at rest?", "question_type": "yes_no", "category_tag": "security"},
    )
    assert q.status_code == 201, q.text
    return tid, q.json()["id"]


def _rule_body(template_id, question_id, **over):
    body = {
        "template_id": template_id,
        "question_id": question_id,
        "rule_name": "encrypt-at-rest",
        "condition_operator": "eq",
        "condition_value": "no",
        "score_delta": -10,
    }
    body.update(over)
    return body


def test_create_list_update_deactivate_scoring_rule(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sr-happy")
    h = org["org_headers"]
    tid, qid = _template_with_question(client, h)

    created = client.post(RULES, headers=h, json=_rule_body(tid, qid))
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["score_delta"] == -10 and rule["condition_operator"] == "eq" and rule["is_active"] is True
    rule_id = rule["id"]

    # list (org-scoped) contains it
    listed = client.get(RULES, headers=h)
    assert listed.status_code == 200
    assert any(r["id"] == rule_id for r in listed.json())

    # list by template contains it
    by_tmpl = client.get(f"{RULES}/template/{tid}", headers=h)
    assert by_tmpl.status_code == 200
    assert any(r["id"] == rule_id for r in by_tmpl.json())

    # update
    upd = client.patch(f"{RULES}/{rule_id}", headers=h, json={"score_delta": -25})
    assert upd.status_code == 200, upd.text
    assert upd.json()["score_delta"] == -25

    # deactivate
    deact = client.delete(f"{RULES}/{rule_id}", headers=h)
    assert deact.status_code == 200, deact.text
    assert deact.json()["is_active"] is False


def test_create_scoring_rule_requires_vendor_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sr-perm")
    tid, qid = _template_with_question(client, org["org_headers"])
    # readonly lacks vendor:write
    ro = add_org_member(db_session, client, org["organization_id"], "sr-readonly@example.com", role_name="readonly")
    r = client.post(RULES, headers=ro, json=_rule_body(tid, qid))
    assert r.status_code == 403, r.text


def test_create_scoring_rule_rejects_question_not_in_template(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sr-edge")
    h = org["org_headers"]
    tid, _qid = _template_with_question(client, h)
    # a question id that does not belong to this template -> 422
    r = client.post(RULES, headers=h, json=_rule_body(tid, str(uuid.uuid4())))
    assert r.status_code == 422, r.text


def test_scoring_rules_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sr-a")
    tid, qid = _template_with_question(client, org_a["org_headers"])
    created = client.post(RULES, headers=org_a["org_headers"], json=_rule_body(tid, qid))
    assert created.status_code == 201
    rule_id = created.json()["id"]

    org_b = bootstrap_org_user(client, email_prefix="sr-b")
    listed_b = client.get(RULES, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(r["id"] != rule_id for r in listed_b.json())
