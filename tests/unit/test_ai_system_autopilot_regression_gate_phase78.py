from pathlib import Path
import re

from tests.helpers.auth_org import bootstrap_org_user


def _phase7_router_paths_in_order() -> list[str]:
    source = Path("app/api/v1/ai_governance.py").read_text(encoding="utf-8")
    start = source.index('@router.get("/contracts/phase7"')
    end = source.index("def _policy_read(")
    segment = source[start:end]
    seg_lines = segment.splitlines()
    paths: list[str] = []
    i = 0
    while i < len(seg_lines):
        line = seg_lines[i]
        if "@router." not in line:
            i += 1
            continue
        blob = line
        j = i + 1
        while j < len(seg_lines) and ")" not in blob and (j - i) < 12:
            blob += "\n" + seg_lines[j]
            j += 1
        match = re.search(r'"([^"]+)"', blob)
        if match:
            paths.append(match.group(1))
        i = j
    return paths


def _assert_order(paths: list[str], first: str, second: str) -> None:
    assert first in paths
    assert second in paths
    assert paths.index(first) < paths.index(second)


def test_phase78_route_inventory_and_static_before_dynamic_ordering():
    paths = _phase7_router_paths_in_order()

    # Phase 7 route inventory coverage
    assert "/contracts/phase7" in paths
    assert "/autopilot/policies" in paths
    assert "/autopilot/evaluate-candidate-action" in paths
    assert "/autopilot/capabilities" in paths
    assert "/autopilot/execution-intents" in paths
    assert "/autopilot/execution-approvals" in paths
    assert "/autopilot/approval-policies" in paths
    assert "/autopilot/execution-approvals/{approval_id}/votes" in paths
    assert "/autopilot/runner-simulations" in paths
    assert "/autopilot/runner-admissions" in paths
    assert "/autopilot/runner-sessions" in paths
    assert "/autopilot/runner-handshakes" in paths

    # conflict-prone static-before-dynamic checks
    _assert_order(paths, "/autopilot/policies/resolved", "/autopilot/policies/{policy_id}")
    _assert_order(paths, "/autopilot/approval-policies/resolved", "/autopilot/approval-policies/{policy_id}")
    _assert_order(paths, "/autopilot/approval-policies/summary", "/autopilot/approval-policies/{policy_id}")
    _assert_order(paths, "/autopilot/runner-simulations/summary", "/autopilot/runner-simulations/{simulation_id}")
    _assert_order(paths, "/autopilot/runner-admissions/summary", "/autopilot/runner-admissions/{admission_id}")
    _assert_order(paths, "/autopilot/runner-sessions/summary", "/autopilot/runner-sessions/{session_id}")
    _assert_order(paths, "/autopilot/runner-sessions/expire-stale", "/autopilot/runner-sessions/{session_id}")
    _assert_order(paths, "/autopilot/runner-handshakes/summary", "/autopilot/runner-handshakes/{handshake_id}")
    _assert_order(paths, "/autopilot/execution-intents/summary", "/autopilot/execution-intents/{intent_id}")
    _assert_order(paths, "/autopilot/execution-approvals/summary", "/autopilot/execution-approvals/{approval_id}")


def test_phase78_phase7_contract_completeness_and_boundary_wording(client):
    org = bootstrap_org_user(client, email_prefix="p78-contract")
    resp = client.get("/api/v1/ai-governance/contracts/phase7", headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()

    expected_groups = {
        "governance_autopilot_policies",
        "governance_autopilot_policy_evaluations",
        "governance_autopilot_capabilities",
        "governance_autopilot_execution_intents",
        "governance_autopilot_execution_approvals",
        "governance_autopilot_approval_policies",
        "governance_autopilot_approval_votes",
        "governance_autopilot_approval_quorum",
        "governance_autopilot_runner_interface",
        "governance_autopilot_runner_simulations",
        "governance_autopilot_runner_admissions",
        "governance_autopilot_runner_sessions",
        "governance_autopilot_runner_handshakes",
    }
    groups = body["groups"]
    keys = {group["group_key"] for group in groups}
    assert expected_groups.issubset(keys)

    for group in groups:
        assert group["critical_endpoints"]
        assert group["endpoints"]
        assert group["response_contract_fields"]
        assert group["protected_fields"]
        assert group["read_write_semantics"]
        assert group["caveats"]
        assert isinstance(group["non_execution_guarantee"], str) and group["non_execution_guarantee"]
        assert (
            isinstance(group["no_legal_regulatory_determination"], str)
            and group["no_legal_regulatory_determination"]
        )

    assert "does not execute automation" in body["caveat"].lower()
    assert "does not make legal or regulatory determinations" in body["caveat"].lower()
