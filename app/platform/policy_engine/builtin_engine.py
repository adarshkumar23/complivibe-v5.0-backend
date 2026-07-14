from __future__ import annotations


class BuiltInPolicyEngine:
    """Pure Python guardrail evaluator with no external calls."""

    def evaluate(self, guardrail, action_context: dict) -> dict:
        if guardrail.guardrail_type == "financial_limit":
            max_usd = guardrail.constraint_value.get("max_usd", float("inf"))
            # Fail CLOSED: a financial guardrail must never treat a missing/mis-named
            # or non-numeric amount as a $0 transaction (which would silently permit
            # any spend). An unquantifiable amount is blocked explicitly.
            if "estimated_value" not in action_context:
                return {
                    "decision": "block",
                    "violations": [
                        "financial_limit guardrail requires a numeric 'estimated_value' in the "
                        "action context; refusing to permit an unquantified transaction",
                    ],
                }
            amount = action_context["estimated_value"]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                return {
                    "decision": "block",
                    "violations": [
                        f"financial_limit guardrail received a non-numeric 'estimated_value': {amount!r}",
                    ],
                }
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

        elif guardrail.guardrail_type == "data_scope":
            allowed_categories = guardrail.constraint_value.get("allowed_data_categories", [])
            requested_categories = action_context.get("data_categories", [])
            if allowed_categories:
                disallowed = [c for c in requested_categories if c not in allowed_categories]
                if disallowed:
                    return {
                        "decision": "block",
                        "violations": [
                            f"Data categories {disallowed} are not in permitted scope: {allowed_categories}",
                        ],
                    }

        return {"decision": "permit", "violations": []}


def get_policy_engine() -> BuiltInPolicyEngine:
    return BuiltInPolicyEngine()
