class ReportSectionMapper:
    SECTION_TITLE_MAP = {
        "score": "Compliance Score",
        "score_delta": "Score Change vs Last Quarter",
        "risks_summary": "Top Open Risks",
        "issues_summary": "Critical Issues",
        "certifications": "Certifications Summary",
        "upcoming_deadlines": "Upcoming Deadlines",
        "coverage_improvements": "Coverage Improvements",
        "sections": "Report Sections",
        "data_summary": "Data Summary",
        "narrative": "Executive Summary",
        "caveat": "Disclaimer",
    }

    @staticmethod
    def get_title(key: str) -> str:
        return ReportSectionMapper.SECTION_TITLE_MAP.get(key, key.replace("_", " ").title())
