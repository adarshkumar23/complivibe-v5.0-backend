from __future__ import annotations


class BuiltInPolicyEngine:
    """Pure Python guardrail evaluator with no external calls."""

    def evaluate(self, guardrail, action_context: dict) -> dict:
        if guardrail.guardrail_type == "financial_limit":
            max_usd = guardrail.constraint_value.get("max_usd", float("inf"))
            amount = action_context.get("estimated_value", 0)
            if amount > max_usd:
                return {
                    "decision": "block",
                    "violations": [
                        f"Transaction ${amount} exceeds limit of ${max_usd}",
                    ],
                }

        elif guardrail.guardrail_type == "geographic_scope":
            allowed = guardrail.constraint_value.get("allowed_regions", [])
            jurisdiction = action_context.get("jurisdiction")
            if allowed and jurisdiction not in allowed:
                return {
                    "decision": "block",
                    "violations": [
                        f"Jurisdiction '{jurisdiction}' not in permitted regions: {allowed}",
                    ],
                }

        elif guardrail.guardrail_type == "user_scope":
            allowed_roles = guardrail.constraint_value.get("allowed_user_roles", [])
            user_role = action_context.get("user_role")
            if allowed_roles and user_role not in allowed_roles:
                return {
                    "decision": "block",
                    "violations": [
                        f"User role '{user_role}' not permitted",
                    ],
                }

        elif guardrail.guardrail_type == "action_scope":
            prohibited = guardrail.constraint_value.get("prohibited_actions", [])
            action = action_context.get("action_type", "")
            if action in prohibited:
                return {
                    "decision": "block",
                    "violations": [
                        f"Action '{action}' is prohibited",
                    ],
                }

        elif guardrail.guardrail_type == "approval_required":
            approved = action_context.get("pre_approved", False)
            if not approved:
                return {
                    "decision": "block",
                    "violations": [
                        "This action requires explicit pre-approval",
                    ],
                }

        # data_scope: default permit in this phase.
        return {"decision": "permit", "violations": []}


def get_policy_engine() -> BuiltInPolicyEngine:
    return BuiltInPolicyEngine()
