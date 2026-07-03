from tests.helpers.auth_org import bootstrap_org_user

ISSUES_BASE = "/api/v1/compliance/issues"


def _create_issue(client, headers, owner_id):
    resp = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": "FixC Issue",
            "description": "d",
            "issue_type": "custom",
            "severity": "medium",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_verify_resolution_note_persists_on_non_terminal_transitions(client):
    org = bootstrap_org_user(client, email_prefix="fixC-issue")
    issue = _create_issue(client, org["org_headers"], org["user_id"])
    issue_id = issue["id"]

    # BEFORE: no resolution_note yet
    before = client.get(f"{ISSUES_BASE}/{issue_id}", headers=org["org_headers"])
    print("BEFORE open->investigating:", before.json().get("resolution_note"))
    assert before.json().get("resolution_note") is None

    # Transition 1: open -> investigating, WITH a resolution_note supplied
    t1 = client.post(
        f"{ISSUES_BASE}/{issue_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "investigating", "resolution_note": "Root cause under investigation - note A"},
    )
    assert t1.status_code == 200, t1.text
    after_t1 = client.get(f"{ISSUES_BASE}/{issue_id}", headers=org["org_headers"])
    print("AFTER open->investigating:", after_t1.json().get("resolution_note"))
    assert after_t1.json()["resolution_note"] == "Root cause under investigation - note A", (
        "BUG: resolution_note silently dropped on open->investigating transition"
    )

    # Transition 2: investigating -> mitigating, WITH a different resolution_note
    t2 = client.post(
        f"{ISSUES_BASE}/{issue_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "mitigating", "resolution_note": "Mitigation plan applied - note B"},
    )
    assert t2.status_code == 200, t2.text
    after_t2 = client.get(f"{ISSUES_BASE}/{issue_id}", headers=org["org_headers"])
    print("AFTER investigating->mitigating:", after_t2.json().get("resolution_note"))
    assert after_t2.json()["resolution_note"] == "Mitigation plan applied - note B", (
        "BUG: resolution_note silently dropped on investigating->mitigating transition"
    )
