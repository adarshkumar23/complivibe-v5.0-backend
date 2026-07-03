SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "low",
}


class TrivyParser:
    def parse(self, payload: dict) -> list[dict]:
        findings: list[dict] = []
        artifact = payload.get("ArtifactName", "unknown")

        for result in payload.get("Results", []):
            target = result.get("Target", artifact)
            for vuln in result.get("Vulnerabilities", []):
                findings.append(
                    {
                        "cve_id": vuln.get("VulnerabilityID", "UNKNOWN"),
                        "package": vuln.get("PkgName", ""),
                        "installed_version": vuln.get("InstalledVersion", ""),
                        "fixed_version": vuln.get("FixedVersion"),
                        "severity": SEVERITY_MAP.get(vuln.get("Severity", "UNKNOWN"), "low"),
                        "title": vuln.get("Title", ""),
                        "description": vuln.get("Description", ""),
                        "target": target,
                        "artifact": artifact,
                        "class": result.get("Class", ""),
                        "references": vuln.get("References", [])[:3],
                    }
                )

        return findings
