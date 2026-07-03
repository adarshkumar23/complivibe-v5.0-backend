import uuid

from app.models.permission import Permission
from tests.helpers.auth_org import bootstrap_org_user

TEMPLATES_BASE = "/api/v1/compliance/questionnaire-templates"
RESPONSES_BASE = "/api/v1/compliance/questionnaire-responses"
RULES_BASE = "/api/v1/compliance/questionnaire-scoring-rules"
VENDORS_BASE = "/api/v1/compliance/vendors"


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str = "Questionnaire Vendor") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _list_templates(client, headers: dict[str, str]) -> list[dict]:
    response = client.get(TEMPLATES_BASE, headers=headers)
    assert response.status_code == 200
    return response.json()


def _template_by_type(client, headers: dict[str, str], template_type: str) -> dict:
    rows = _list_templates(client, headers)
    matches = [row for row in rows if row["template_type"] == template_type]
    assert matches, f"template not found: {template_type}"
    return matches[0]


def _template_detail(client, headers: dict[str, str], template_id: str) -> dict:
    response = client.get(f"{TEMPLATES_BASE}/{template_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def _create_response(client, headers: dict[str, str], *, vendor_id: str, template_id: str, title: str) -> dict:
    response = client.post(
        RESPONSES_BASE,
        headers=headers,
        json={"vendor_id": vendor_id, "template_id": template_id, "title": title},
    )
    assert response.status_code == 201
    return response.json()


def _get_response(client, headers: dict[str, str], response_id: str) -> dict:
    response = client.get(f"{RESPONSES_BASE}/{response_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def _submit_answer(client, headers: dict[str, str], response_id: str, question_id: str, answer_value: str, answer_text: str | None = None) -> dict:
    response = client.post(
        f"{RESPONSES_BASE}/{response_id}/answers",
        headers=headers,
        json={"question_id": question_id, "answer_value": answer_value, "answer_text": answer_text},
    )
    assert response.status_code == 200
    return response.json()


def _transition(client, headers: dict[str, str], response_id: str, new_status: str) -> dict:
    response = client.post(
        f"{RESPONSES_BASE}/{response_id}/transition",
        headers=headers,
        json={"new_status": new_status},
    )
    assert response.status_code == 200
    return response.json()


def _complete_after_answers(client, headers: dict[str, str], response_id: str) -> None:
    _transition(client, headers, response_id, "submitted")
    _transition(client, headers, response_id, "under_review")
    _transition(client, headers, response_id, "completed")


def _question_id_by_category(template_detail: dict, category_tag: str) -> str:
    for row in template_detail["questions"]:
        if row["category_tag"] == category_tag:
            return row["id"]
    raise AssertionError(f"missing question category: {category_tag}")


def test_a51_permissions_seeded_for_vendor_questionnaires(client, db_session):
    _ = bootstrap_org_user(client, email_prefix="a51-perms")
    keys = {p.key for p in db_session.query(Permission).all()}
    assert "vendor:read" in keys
    assert "vendor:write" in keys


def test_a51_list_system_templates_visible_for_any_org(client):
    org_a = bootstrap_org_user(client, email_prefix="a51-list-a")
    org_b = bootstrap_org_user(client, email_prefix="a51-list-b")

    rows_a = _list_templates(client, org_a["org_headers"])
    rows_b = _list_templates(client, org_b["org_headers"])

    types_a = {row["template_type"] for row in rows_a}
    types_b = {row["template_type"] for row in rows_b}
    assert "sig_lite" in types_a and "caiq" in types_a
    assert "sig_lite" in types_b and "caiq" in types_b


def test_a51_custom_template_org_scope_and_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="a51-custom-a")
    org_b = bootstrap_org_user(client, email_prefix="a51-custom-b")

    created = client.post(
        TEMPLATES_BASE,
        headers=org_a["org_headers"],
        json={"name": "Org A Template", "version": "1.0", "description": "A only"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["template_type"] == "custom"
    assert body["organization_id"] == org_a["organization_id"]

    list_a = _list_templates(client, org_a["org_headers"])
    list_b = _list_templates(client, org_b["org_headers"])
    ids_a = {row["id"] for row in list_a}
    ids_b = {row["id"] for row in list_b}
    assert body["id"] in ids_a
    assert body["id"] not in ids_b


def test_a51_clone_system_template_and_guard_cross_org_clone(client):
    org_a = bootstrap_org_user(client, email_prefix="a51-clone-a")
    org_b = bootstrap_org_user(client, email_prefix="a51-clone-b")

    sig = _template_by_type(client, org_a["org_headers"], "sig_lite")
    src_detail = _template_detail(client, org_a["org_headers"], sig["id"])

    cloned = client.post(
        f"{TEMPLATES_BASE}/{sig['id']}/clone",
        headers=org_a["org_headers"],
        json={"new_name": "SIG Lite Clone A"},
    )
    assert cloned.status_code == 201
    clone_body = cloned.json()
    assert clone_body["template_type"] == "custom"
    assert clone_body["organization_id"] == org_a["organization_id"]

    clone_detail = _template_detail(client, org_a["org_headers"], clone_body["id"])
    assert len(clone_detail["sections"]) == len(src_detail["sections"])
    assert len(clone_detail["questions"]) == len(src_detail["questions"])

    org_a_custom = client.post(
        TEMPLATES_BASE,
        headers=org_a["org_headers"],
        json={"name": "Org A Private", "version": "1.0"},
    ).json()

    forbidden_clone = client.post(
        f"{TEMPLATES_BASE}/{org_a_custom['id']}/clone",
        headers=org_b["org_headers"],
        json={"new_name": "Cross Org Clone"},
    )
    assert forbidden_clone.status_code in {403, 404}


def test_a51_add_section_constraints_and_create_response_prepopulates_answers(client):
    org = bootstrap_org_user(client, email_prefix="a51-section")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")

    denied = client.post(
        f"{TEMPLATES_BASE}/{sig['id']}/sections",
        headers=org["org_headers"],
        json={"title": "Should Fail", "order_index": 99},
    )
    assert denied.status_code == 422

    custom = client.post(
        TEMPLATES_BASE,
        headers=org["org_headers"],
        json={"name": "Mutable Template", "version": "1.0"},
    ).json()
    added = client.post(
        f"{TEMPLATES_BASE}/{custom['id']}/sections",
        headers=org["org_headers"],
        json={"title": "Custom Section", "description": "ok", "order_index": 0},
    )
    assert added.status_code == 201

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Prepopulate Vendor")
    response = _create_response(
        client,
        org["org_headers"],
        vendor_id=vendor["id"],
        template_id=sig["id"],
        title="SIG Lite 2026",
    )
    detail = _get_response(client, org["org_headers"], response["id"])
    assert len(detail["answers"]) == 20
    assert all(item["is_answered"] is False for item in detail["answers"])


def test_a51_org_isolation_cannot_read_other_org_template(client):
    org_a = bootstrap_org_user(client, email_prefix="a51-iso-a")
    org_b = bootstrap_org_user(client, email_prefix="a51-iso-b")

    created = client.post(
        TEMPLATES_BASE,
        headers=org_a["org_headers"],
        json={"name": "Org A Hidden", "version": "1.0"},
    ).json()

    cross = client.get(f"{TEMPLATES_BASE}/{created['id']}", headers=org_b["org_headers"])
    assert cross.status_code == 404


def test_a52_submit_no_and_yes_mfa_scoring_and_score_refresh(client):
    org = bootstrap_org_user(client, email_prefix="a52-mfa")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")
    detail = _template_detail(client, org["org_headers"], sig["id"])
    mfa_question_id = _question_id_by_category(detail, "access_control_mfa")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="MFA Vendor")
    response = _create_response(client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="MFA Score")

    no_answer = _submit_answer(client, org["org_headers"], response["id"], mfa_question_id, "No")
    assert no_answer["score_contribution"] == 20

    response_after_no = _get_response(client, org["org_headers"], response["id"])
    assert response_after_no["calculated_risk_score"] == 20
    assert response_after_no["score_computed_at"] is not None

    yes_answer = _submit_answer(client, org["org_headers"], response["id"], mfa_question_id, "Yes")
    assert yes_answer["score_contribution"] == -5

    response_after_yes = _get_response(client, org["org_headers"], response["id"])
    assert response_after_yes["calculated_risk_score"] == 0
    assert response_after_yes["score_computed_at"] is not None


def test_a52_scoring_uses_answer_text_only_field_not_just_answer_value(client):
    """Regression: submitting only the documented answer_text field (no answer_value)
    must still score correctly, not silently compute 0. answer_value is a legacy/
    alternate field; answer_text is what the schema documents as the primary answer."""
    org = bootstrap_org_user(client, email_prefix="a52-text-only")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")
    detail = _template_detail(client, org["org_headers"], sig["id"])
    mfa_question_id = _question_id_by_category(detail, "access_control_mfa")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Text-Only Vendor")
    response = _create_response(
        client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="Text-Only Score"
    )

    answer_resp = client.post(
        f"{RESPONSES_BASE}/{response['id']}/answers",
        headers=org["org_headers"],
        json={"question_id": mfa_question_id, "answer_text": "No"},
    )
    assert answer_resp.status_code == 200, answer_resp.text
    body = answer_resp.json()
    assert body["answer_value"] is None
    assert body["answer_text"] == "No"
    assert body["score_contribution"] == 20, "score must reflect answer_text-only submission, not be 0"

    scored = _get_response(client, org["org_headers"], response["id"])
    assert scored["calculated_risk_score"] == 20


def test_a52_bulk_submit_clamp_zero_and_unanswered_in_breakdown(client):
    org = bootstrap_org_user(client, email_prefix="a52-bulk")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")
    sig_detail = _template_detail(client, org["org_headers"], sig["id"])

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Bulk Vendor")
    response = _create_response(client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="Bulk Score")

    only_one = _submit_answer(
        client,
        org["org_headers"],
        response["id"],
        _question_id_by_category(sig_detail, "penetration_testing"),
        "No",
    )
    assert only_one["score_contribution"] == 20

    breakdown = client.get(f"{RESPONSES_BASE}/{response['id']}/score", headers=org["org_headers"])
    assert breakdown.status_code == 200
    score_body = breakdown.json()
    assert score_body["total_score"] == 20
    assert len(score_body["unanswered"]) == 19

    all_yes = [
        {"question_id": question["id"], "answer_value": "Yes", "answer_text": "affirmative"}
        for question in sig_detail["questions"]
    ]
    bulk = client.post(
        f"{RESPONSES_BASE}/{response['id']}/answers/bulk",
        headers=org["org_headers"],
        json={"answers": all_yes},
    )
    assert bulk.status_code == 200
    assert bulk.json()["updated"] == 20
    assert bulk.json()["score"] == 0

    final = _get_response(client, org["org_headers"], response["id"])
    assert final["calculated_risk_score"] == 0


def test_a52_clamp_hundred_and_org_specific_rule_precedence(client):
    org = bootstrap_org_user(client, email_prefix="a52-precedence")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")
    sig_detail = _template_detail(client, org["org_headers"], sig["id"])
    mfa_question_id = _question_id_by_category(sig_detail, "access_control_mfa")

    create_rule = client.post(
        RULES_BASE,
        headers=org["org_headers"],
        json={
            "template_id": sig["id"],
            "question_id": mfa_question_id,
            "rule_name": "Org override MFA",
            "condition_operator": "eq",
            "condition_value": "No",
            "score_delta": 120,
            "rationale": "test override",
        },
    )
    assert create_rule.status_code == 201

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Precedence Vendor")
    response = _create_response(client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="Override Score")

    answer = _submit_answer(client, org["org_headers"], response["id"], mfa_question_id, "No")
    assert answer["score_contribution"] == 120

    detail = _get_response(client, org["org_headers"], response["id"])
    assert detail["calculated_risk_score"] == 100


def test_a52_vendor_risk_aggregation_and_unanswered_no_contribution(client):
    org = bootstrap_org_user(client, email_prefix="a52-aggregate")
    sig = _template_by_type(client, org["org_headers"], "sig_lite")
    sig_detail = _template_detail(client, org["org_headers"], sig["id"])
    mfa_question_id = _question_id_by_category(sig_detail, "access_control_mfa")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Aggregate Vendor")

    first = _create_response(client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="R1")
    _submit_answer(client, org["org_headers"], first["id"], mfa_question_id, "No")
    _complete_after_answers(client, org["org_headers"], first["id"])

    second = _create_response(client, org["org_headers"], vendor_id=vendor["id"], template_id=sig["id"], title="R2")
    # keep unanswered first to verify no contribution
    empty_detail = _get_response(client, org["org_headers"], second["id"])
    assert empty_detail["calculated_risk_score"] is None

    _submit_answer(client, org["org_headers"], second["id"], mfa_question_id, "Yes")
    _complete_after_answers(client, org["org_headers"], second["id"])

    risk = client.get(f"{RESPONSES_BASE}/vendor/{vendor['id']}/risk", headers=org["org_headers"])
    assert risk.status_code == 200
    payload = risk.json()
    assert payload["response_count"] == 2
    assert payload["latest_score"] in {0, 20}
    assert payload["highest_risk_score"] == 20
    assert payload["average_score"] == 10
    assert payload["latest_response_id"] in {first["id"], second["id"]}

    breakdown = client.get(f"{RESPONSES_BASE}/{second['id']}/score", headers=org["org_headers"])
    assert breakdown.status_code == 200
    body = breakdown.json()
    assert body["total_score"] == 0
    assert len(body["unanswered"]) == 19
