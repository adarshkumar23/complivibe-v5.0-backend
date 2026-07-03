from __future__ import annotations

import logging
from html import escape
from io import BytesIO

from app.exports.services.export_content_builder import ExportDocumentContent

logger = logging.getLogger(__name__)


class PDFRenderer:
    def build_html(self, content: ExportDocumentContent) -> str:
        branding = content.branding
        section_html: list[str] = []
        for section in content.sections:
            block = [f"<h2>{escape(section.title)}</h2>"]
            if section.rows:
                block.append("<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>")
                for key, value in section.rows:
                    block.append(f"<tr><td>{escape(key)}</td><td>{escape(value)}</td></tr>")
                block.append("</tbody></table>")
            for paragraph in section.paragraphs:
                block.append(f"<p>{escape(paragraph)}</p>")
            if section.items:
                block.append("<ul>")
                for item in section.items:
                    block.append(f"<li>{escape(item)}</li>")
                block.append("</ul>")
            section_html.append("\n".join(block))

        logo_html = f'<img src="{escape(branding.logo_url)}" class="logo" alt="logo" />' if branding.logo_url else ""
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <style>
      @page {{ size: A4; margin: 24mm 16mm 20mm 16mm; }}
      body {{ font-family: sans-serif; color: #1e293b; font-size: 12px; }}
      h1 {{ color: {branding.primary_color_hex}; margin: 0 0 6px 0; font-size: 24px; }}
      h2 {{ color: {branding.primary_color_hex}; margin: 18px 0 8px 0; font-size: 16px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }}
      .meta {{ color: #475569; margin-bottom: 12px; }}
      .logo {{ max-height: 60px; max-width: 220px; margin-bottom: 12px; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
      th, td {{ border: 1px solid #d1d5db; padding: 6px; text-align: left; vertical-align: top; }}
      th {{ background: #f8fafc; }}
      footer {{ margin-top: 20px; font-size: 10px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 6px; }}
    </style>
  </head>
  <body>
    {logo_html}
    <h1>{escape(content.title)}</h1>
    <div class=\"meta\">{escape(branding.company_display_name)} | Generated at {escape(content.generated_at.isoformat())}</div>
    {''.join(section_html)}
    <footer>{escape(branding.footer_text)}</footer>
  </body>
</html>
"""

    def render(self, content: ExportDocumentContent) -> bytes:
        html = self.build_html(content)
        try:
            from weasyprint import HTML  # type: ignore

            return HTML(string=html).write_pdf()
        except Exception:
            logger.exception(
                "weasyprint PDF render failed for export %r; falling back to reportlab renderer",
                content.title,
            )
            return self._render_with_reportlab(content)

    @staticmethod
    def _render_with_reportlab(content: ExportDocumentContent) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        branding = content.branding
        buffer = BytesIO()
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "export_title", parent=styles["Title"], textColor=colors.HexColor(branding.primary_color_hex)
        )
        heading_style = ParagraphStyle(
            "export_heading", parent=styles["Heading2"], textColor=colors.HexColor(branding.primary_color_hex)
        )
        meta_style = ParagraphStyle("export_meta", parent=styles["BodyText"], textColor=colors.HexColor("#475569"))

        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        story: list = [
            Paragraph(escape(content.title), title_style),
            Paragraph(
                escape(f"{branding.company_display_name} | Generated at {content.generated_at.isoformat()}"),
                meta_style,
            ),
            Spacer(1, 12),
        ]

        for section in content.sections:
            story.append(Paragraph(escape(section.title), heading_style))
            if section.rows:
                table_rows = [["Field", "Value"]] + [[escape(key), escape(value)] for key, value in section.rows]
                table = Table(table_rows, colWidths=[165, 330])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f2f5")),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
            for paragraph in section.paragraphs:
                story.append(Paragraph(escape(paragraph), styles["BodyText"]))
            if section.items:
                bullets = [ListItem(Paragraph(escape(item), styles["BodyText"])) for item in section.items]
                story.append(ListFlowable(bullets, bulletType="bullet", start="circle"))
            story.append(Spacer(1, 14))

        story.append(Paragraph(escape(branding.footer_text), styles["BodyText"]))
        doc.build(story)
        return buffer.getvalue()
