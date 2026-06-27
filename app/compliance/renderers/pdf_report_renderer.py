import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.compliance.renderers.report_section_mapper import ReportSectionMapper
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.organization import Organization
from app.repositories.report_repository import ReportRepository
from app.services.report_service import REPORT_CAVEAT


class PDFReportRenderer:
    @staticmethod
    def _fallback_pdf_bytes(text: str) -> bytes:
        # Minimal syntactically-valid PDF fallback when reportlab is unavailable at runtime.
        safe_text = text.replace("(", "[").replace(")", "]")
        body = f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET"
        pdf = (
            "%PDF-1.4\n"
            "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
            "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
            f"4 0 obj<< /Length {len(body)} >>stream\n{body}\nendstream endobj\n"
            "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
            "xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n0000000275 00000 n \n0000000368 00000 n \n"
            "trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF"
        )
        return pdf.encode("utf-8")

    def _load(self, report_id: uuid.UUID, org_id: uuid.UUID, db: Session) -> tuple[ComplianceReport, Organization, list[ComplianceReportSection]]:
        report = ReportRepository(db).get_report(report_id)
        if report is None or report.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        org = db.get(Organization, org_id)
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        sections = ReportRepository(db).list_sections(org_id, report_id)
        return report, org, sections

    @staticmethod
    def _extract_content(report: ComplianceReport, sections: list[ComplianceReportSection]) -> dict[str, Any]:
        if isinstance(report.inputs_summary_json, dict) and report.inputs_summary_json:
            return report.inputs_summary_json

        content = report.content_json if isinstance(report.content_json, dict) else {}
        if content and any(key != "sections" for key in content):
            return content

        assembled: dict[str, Any] = {}
        for section in sections:
            assembled[section.section_key] = section.data_json if section.data_json else section.body_markdown
        return assembled

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return str(value)
        return str(value)

    @staticmethod
    def _draw_footer(canvas, doc, org_name: str, report_date: str, page_size) -> None:  # noqa: ANN001
        footer = f"CompliVibe Compliance Report | {org_name} | {report_date} | Page {canvas.getPageNumber()}"
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColorRGB(0.5, 0.5, 0.5)
        canvas.drawCentredString(page_size[0] / 2, 20, footer)
        canvas.restoreState()

    def render(self, report_id: uuid.UUID, org_id: uuid.UUID, db: Session) -> bytes:
        report, org, sections = self._load(report_id, org_id, db)
        content = self._extract_content(report, sections)

        report_date = (report.generated_at if report.generated_at else datetime.now(UTC)).date().isoformat()
        title = report.title or report.report_type.replace("_", " ").title()

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception:  # noqa: BLE001
            return self._fallback_pdf_bytes(f"CompliVibe report {report_id}")

        buffer = BytesIO()
        styles = getSampleStyleSheet()
        cover_h1 = ParagraphStyle("cover_h1", parent=styles["Title"], alignment=1, fontSize=28, leading=34)
        cover_h2 = ParagraphStyle("cover_h2", parent=styles["Heading2"], alignment=1, fontSize=18, leading=22)
        centered_body = ParagraphStyle("centered_body", parent=styles["BodyText"], alignment=1)
        italic = ParagraphStyle("italic", parent=styles["BodyText"], fontName="Helvetica-Oblique")

        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        story = [
            Spacer(1, 130),
            Paragraph(org.name, cover_h1),
            Spacer(1, 24),
            Paragraph(title, cover_h2),
            Spacer(1, 16),
            Paragraph(f"Generated: {report_date}", centered_body),
            Spacer(1, 274),
            Paragraph("Powered by CompliVibe", ParagraphStyle("watermark", parent=centered_body, textColor=colors.lightgrey)),
            PageBreak(),
        ]

        for key, value in content.items():
            if key == "caveat":
                continue
            story.append(Paragraph(ReportSectionMapper.get_title(key), styles["Heading2"]))
            if isinstance(value, dict):
                rows = [["Field", "Value"]]
                for k, v in value.items():
                    rows.append([str(k).replace("_", " ").title(), self._stringify(v)])
                table = Table(rows, colWidths=[165, 330])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f2f5")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ]
                    )
                )
                story.append(table)
            elif isinstance(value, list):
                bullets = [ListItem(Paragraph(self._stringify(item), styles["BodyText"])) for item in value]
                story.append(ListFlowable(bullets, bulletType="bullet", start="circle"))
            elif isinstance(value, (int, float, str)):
                story.append(Paragraph(self._stringify(value), styles["BodyText"]))
            else:
                story.append(Paragraph(self._stringify(value), styles["BodyText"]))
            story.append(Spacer(1, 10))

        caveat_text = self._stringify(content.get("caveat")) or REPORT_CAVEAT
        story.extend([PageBreak(), Paragraph("Disclaimer", styles["Heading2"]), Paragraph(caveat_text, italic)])

        def on_later_pages(canvas, _doc):  # noqa: ANN001
            self._draw_footer(canvas, _doc, org.name, report_date, A4)

        doc.build(story, onFirstPage=lambda _c, _d: None, onLaterPages=on_later_pages)
        return buffer.getvalue()

    def render_coverage_matrix(self, *, org_name: str, framework_name: str, matrix_payload: dict) -> bytes:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception:  # noqa: BLE001
            return self._fallback_pdf_bytes(f"Coverage matrix for {framework_name}")

        buffer = BytesIO()
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        story = [
            Paragraph(f"{org_name} - Framework Coverage Matrix", styles["Title"]),
            Spacer(1, 8),
            Paragraph(f"Framework: {framework_name}", styles["Heading2"]),
            Spacer(1, 12),
            Paragraph(
                f"Total: {matrix_payload.get('total_obligations', 0)} | Covered: {matrix_payload.get('covered', 0)} | "
                f"Partial: {matrix_payload.get('partial', 0)} | Uncovered: {matrix_payload.get('uncovered', 0)} | "
                f"Coverage: {matrix_payload.get('coverage_pct', 0)}%",
                styles["BodyText"],
            ),
            Spacer(1, 14),
        ]

        for section in matrix_payload.get("sections", []):
            story.append(Paragraph(section.get("section_title", "Section"), styles["Heading3"]))
            rows = [["Reference", "Title", "Controls", "Evidence", "Status"]]
            for item in section.get("obligations", []):
                rows.append(
                    [
                        str(item.get("reference") or ""),
                        str(item.get("title") or ""),
                        str(item.get("controls_count") or 0),
                        str(item.get("evidence_count") or 0),
                        str(item.get("coverage_status") or ""),
                    ]
                )

            table = Table(rows, colWidths=[70, 280, 60, 60, 70])
            style_ops = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f2f5")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
            for idx, row in enumerate(rows[1:], start=1):
                status_value = (row[4] or "").lower()
                if status_value == "covered":
                    style_ops.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#e8f6ec")))
                elif status_value == "partial":
                    style_ops.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fff4df")))
                else:
                    style_ops.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fdecea")))
            table.setStyle(TableStyle(style_ops))
            story.extend([table, Spacer(1, 10)])

        story.extend([PageBreak(), Paragraph("Disclaimer", styles["Heading2"]), Paragraph(REPORT_CAVEAT, styles["BodyText"])])
        doc.build(story)
        return buffer.getvalue()
