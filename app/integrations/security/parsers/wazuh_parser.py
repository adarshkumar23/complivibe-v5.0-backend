from __future__ import annotations


def wazuh_level_to_severity(level: int) -> str:
    if level >= 15:
        return "critical"
    if level >= 12:
        return "high"
    if level >= 8:
        return "medium"
    return "low"


WAZUH_COMPLIANCE_MAP = {
    "pci_dss": "PCI DSS",
    "hipaa": "HIPAA",
    "gdpr_iv": "GDPR",
    "nist_800_53": "NIST SP 800-53",
    "tsc": "SOC 2",
    "cis": "CIS Controls",
    "mitre_attack": None,
}


class WazuhParser:
    def parse(self, payload: list | dict) -> list[dict]:
        if isinstance(payload, dict):
            alerts = payload.get("alerts")
            if alerts is None:
                hits = payload.get("hits", {}).get("hits", [])
                if hits and isinstance(hits, list) and isinstance(hits[0], dict) and "_source" in hits[0]:
                    alerts = [item.get("_source", {}) for item in hits]
                else:
                    alerts = [payload]
        elif isinstance(payload, list):
            alerts = payload
        else:
            return []

        findings: list[dict] = []
        for alert in alerts:
            rule = alert.get("rule", {}) if isinstance(alert, dict) else {}
            level = int(rule.get("level", 0) or 0)
            severity = wazuh_level_to_severity(level)

            framework_refs: list[dict] = []
            compliance_raw = rule.get("compliance", {})
            if isinstance(compliance_raw, dict):
                for key, refs in compliance_raw.items():
                    framework_name = WAZUH_COMPLIANCE_MAP.get(str(key))
                    if not framework_name:
                        continue
                    framework_refs.append(
                        {
                            "framework": framework_name,
                            "refs": refs if isinstance(refs, list) else [str(refs)],
                        }
                    )

            agent = alert.get("agent", {}) if isinstance(alert, dict) else {}
            findings.append(
                {
                    "rule_id": str(rule.get("id", "unknown")),
                    "rule_description": str(rule.get("description", "")),
                    "level": level,
                    "severity": severity,
                    "agent_name": str(agent.get("name", "")),
                    "agent_ip": str(agent.get("ip", "")),
                    "timestamp": str(alert.get("timestamp", "")) if isinstance(alert, dict) else "",
                    "alert_id": str(alert.get("id", "")) if isinstance(alert, dict) else "",
                    "framework_refs": framework_refs,
                    "data": alert.get("data", {}) if isinstance(alert, dict) else {},
                }
            )

        return findings
