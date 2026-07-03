from __future__ import annotations

import xml.etree.ElementTree as ET

XCCDF_RESULT_MAP = {
    "pass": "pass",
    "fail": "fail",
    "error": "warning",
    "unknown": "warning",
    "notchecked": "skipped",
    "notapplicable": "skipped",
    "notselected": "skipped",
    "informational": "skipped",
    "fixed": "pass",
}

XCCDF_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "unknown": "low",
    "info": "low",
}

XCCDF_NAMESPACES = {
    "xccdf": "http://checklists.nist.gov/xccdf/1.2",
    "xccdf11": "http://checklists.nist.gov/xccdf/1.1",
}


class OpenSCAPParser:
    def parse(self, xml_content: str) -> list[dict]:
        findings: list[dict] = []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid XCCDF XML: {exc}") from exc

        rule_results: list[ET.Element] = []
        for ns_key in ("xccdf", "xccdf11"):
            ns = {ns_key: XCCDF_NAMESPACES[ns_key]}
            rows = root.findall(f".//{ns_key}:rule-result", ns)
            if rows:
                rule_results = rows
                break

        if not rule_results:
            rule_results = root.findall(".//rule-result")

        for rr in rule_results:
            rule_id = rr.get("idref") or rr.get("id") or "unknown"
            severity_raw = (rr.get("severity") or "unknown").lower()
            severity = XCCDF_SEVERITY_MAP.get(severity_raw, "low")
            time_val = rr.get("time")

            result_elem = rr.find("{http://checklists.nist.gov/xccdf/1.2}result")
            if result_elem is None:
                result_elem = rr.find("{http://checklists.nist.gov/xccdf/1.1}result")
            if result_elem is None:
                result_elem = rr.find("result")
            result_text = result_elem.text.strip() if result_elem is not None and result_elem.text else "unknown"
            result = XCCDF_RESULT_MAP.get(result_text.lower(), "warning")

            cce_id = None
            ident_nodes = (
                rr.findall("{http://checklists.nist.gov/xccdf/1.2}ident")
                or rr.findall("{http://checklists.nist.gov/xccdf/1.1}ident")
                or rr.findall("ident")
            )
            for ident in ident_nodes:
                text = (ident.text or "").strip()
                if "CCE" in text:
                    cce_id = text
                    break

            findings.append(
                {
                    "rule_id": rule_id,
                    "result": result,
                    "severity": severity,
                    "cce_id": cce_id,
                    "time": time_val,
                }
            )

        return findings

    def map_rule_to_control_family(self, rule_id: str, db_mappings: list) -> tuple[str, str]:
        for mapping in db_mappings:
            if rule_id.startswith(mapping.rule_prefix):
                return mapping.control_family, mapping.control_type
        return "CM", "configuration_management"
