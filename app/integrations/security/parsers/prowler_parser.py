PROWLER_CONTROL_MAPPING = {
    "iam_root_credentials_not_used": "privileged_access_control",
    "iam_root_mfa_enabled": "mfa_control",
    "iam_user_mfa_enabled_console": "mfa_control",
    "iam_password_policy_minimum_length": "password_policy",
    "s3_bucket_default_encryption": "encryption_at_rest",
    "s3_bucket_public_access_block": "public_access_control",
    "cloudtrail_enabled_all_regions": "audit_logging",
    "cloudtrail_log_file_validation_enabled": "audit_log_integrity",
    "vpc_flow_logs_enabled": "network_monitoring",
    "ec2_securitygroup_not_launch_wizard": "network_security",
    "rds_instance_storage_encrypted": "encryption_at_rest",
    "ebs_volume_encryption_enabled": "encryption_at_rest",
    "kms_cmk_rotation_enabled": "key_management",
    "guardduty_is_enabled": "threat_detection",
    "config_recorder_all_regions_enabled": "configuration_management",
}

PROWLER_FRAMEWORK_MAPPING = {
    "CIS": "CIS Controls",
    "PCI": "PCI DSS",
    "NIST": "NIST SP 800-53",
    "HIPAA": "HIPAA",
    "GDPR": "GDPR",
    "SOC2": "SOC 2",
    "ISO27001": "ISO 27001",
}


class ProwlerParser:
    def parse(self, payload: list | dict) -> list[dict]:
        if isinstance(payload, dict):
            findings_raw = payload.get("findings", payload.get("Results", []))
        elif isinstance(payload, list):
            findings_raw = payload
        else:
            return []

        findings: list[dict] = []
        for item in findings_raw:
            raw_sev = str(item.get("Severity", item.get("severity", "medium"))).lower()
            severity = raw_sev if raw_sev in ("critical", "high", "medium", "low") else "medium"

            status = str(item.get("Status", item.get("status", "FAIL"))).upper()
            result = "pass" if status == "PASS" else "fail"

            check_id = item.get("CheckID") or item.get("check_id") or item.get("checkID", "unknown")

            compliance_raw = item.get("Compliance") or item.get("compliance", {})
            framework_refs: list[dict] = []
            for framework_key, refs in (compliance_raw.items() if isinstance(compliance_raw, dict) else []):
                framework_name = None
                for key, value in PROWLER_FRAMEWORK_MAPPING.items():
                    if framework_key.upper().startswith(key):
                        framework_name = value
                        break
                if framework_name:
                    framework_refs.append(
                        {
                            "framework": framework_name,
                            "refs": refs if isinstance(refs, list) else [str(refs)],
                        }
                    )

            findings.append(
                {
                    "check_id": check_id,
                    "check_title": item.get("CheckTitle") or item.get("check_title", check_id),
                    "result": result,
                    "severity": severity,
                    "region": item.get("Region", ""),
                    "resource_id": item.get("ResourceId", ""),
                    "description": item.get("Description", ""),
                    "remediation": str(item.get("Remediation", ""))[:500],
                    "control_type": PROWLER_CONTROL_MAPPING.get(check_id, "security_control"),
                    "framework_refs": framework_refs,
                }
            )

        return findings
