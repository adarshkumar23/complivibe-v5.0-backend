import uuid

from sqlalchemy.orm import Session

from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_REGISTRY
from app.privacy.services.ropa_service import RopaService


class GDPRArticle30Builder:
    report_type = "gdpr_ropa"

    @staticmethod
    def build(org_id: uuid.UUID, db: Session) -> dict:
        payload = RopaService(db).generate_article30_report(org_id)
        payload["report_type"] = "gdpr_ropa"
        return payload


REGULATORY_REPORT_REGISTRY[GDPRArticle30Builder.report_type] = GDPRArticle30Builder
