DORA_SLA_HOURS: dict[str, int] = {
    "early_warning": 4,
    "intermediate_notification": 72,
    "final_report": 720,
}

NIS2_SLA_HOURS: dict[str, int] = {
    "early_warning": 24,
    "incident_notification": 72,
    "final_report": 720,
}

HIPAA_SLA_HOURS = 1440


def get_framework_sla_hours(framework: str | None) -> int | None:
    normalized = (framework or "").strip().lower()
    if normalized == "dora":
        return DORA_SLA_HOURS["early_warning"]
    if normalized == "nis2":
        return NIS2_SLA_HOURS["early_warning"]
    if normalized == "gdpr":
        return 72
    if normalized == "hipaa":
        return HIPAA_SLA_HOURS
    return None


def resolve_regulatory_sla_hours(framework: str | None, fallback_hours: int) -> int:
    resolved = get_framework_sla_hours(framework)
    if resolved is not None:
        return int(resolved)
    return int(fallback_hours)
