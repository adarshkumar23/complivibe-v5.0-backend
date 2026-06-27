import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.questionnaire_scoring_service import QuestionnaireScoringService
from app.ai_governance.services.shadow_ai_service import ShadowAIService
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.questionnaire_template_section import QuestionnaireTemplateSection
from app.models.vendor import Vendor
from app.models.vendor_questionnaire_answer import VendorQuestionnaireAnswer
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.services.audit_service import AuditService


class QuestionnaireTemplateService:
    ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
        "draft": {"sent"},
        "sent": {"in_progress", "expired"},
        "in_progress": {"submitted", "expired"},
        "submitted": {"under_review"},
        "under_review": {"completed"},
        "completed": set(),
        "expired": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.scoring_service = QuestionnaireScoringService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _template_access_filter(self, org_id: uuid.UUID):
        return (QuestionnaireTemplate.organization_id == org_id) | QuestionnaireTemplate.organization_id.is_(None)

    def require_visible_template(self, org_id: uuid.UUID, template_id: uuid.UUID) -> QuestionnaireTemplate:
        row = self.db.execute(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.id == template_id,
                self._template_access_filter(org_id),
                QuestionnaireTemplate.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")
        return row

    def require_org_template(self, org_id: uuid.UUID, template_id: uuid.UUID) -> QuestionnaireTemplate:
        row = self.db.execute(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.id == template_id,
                QuestionnaireTemplate.organization_id == org_id,
                QuestionnaireTemplate.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")
        return row

    def require_response(self, org_id: uuid.UUID, response_id: uuid.UUID) -> VendorQuestionnaireResponse:
        row = self.db.execute(
            select(VendorQuestionnaireResponse).where(
                VendorQuestionnaireResponse.id == response_id,
                VendorQuestionnaireResponse.organization_id == org_id,
                VendorQuestionnaireResponse.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire response not found")
        return row

    def list_templates(
        self,
        org_id: uuid.UUID,
        *,
        template_type: str | None = None,
        include_system: bool = True,
    ) -> list[QuestionnaireTemplate]:
        stmt = select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.deleted_at.is_(None),
            QuestionnaireTemplate.is_active.is_(True),
        )
        if include_system:
            stmt = stmt.where(self._template_access_filter(org_id))
        else:
            stmt = stmt.where(QuestionnaireTemplate.organization_id == org_id)
        if template_type is not None:
            stmt = stmt.where(QuestionnaireTemplate.template_type == template_type)
        return self.db.execute(stmt.order_by(QuestionnaireTemplate.is_system_template.desc(), QuestionnaireTemplate.name.asc())).scalars().all()

    def get_template(self, org_id: uuid.UUID, template_id: uuid.UUID) -> tuple[QuestionnaireTemplate, list[QuestionnaireTemplateSection], list[QuestionnaireTemplateQuestion]]:
        template = self.require_visible_template(org_id, template_id)
        sections = self.db.execute(
            select(QuestionnaireTemplateSection).where(
                QuestionnaireTemplateSection.template_id == template.id,
            ).order_by(QuestionnaireTemplateSection.order_index.asc(), QuestionnaireTemplateSection.created_at.asc())
        ).scalars().all()
        questions = self.db.execute(
            select(QuestionnaireTemplateQuestion).where(
                QuestionnaireTemplateQuestion.template_id == template.id,
            ).order_by(QuestionnaireTemplateQuestion.order_index.asc(), QuestionnaireTemplateQuestion.created_at.asc())
        ).scalars().all()
        return template, sections, questions

    def create_custom_template(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> QuestionnaireTemplate:
        row = QuestionnaireTemplate(
            organization_id=org_id,
            template_type="custom",
            name=data.name,
            version=data.version or "1.0",
            description=data.description,
            is_system_template=False,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_template.created",
            entity_type="questionnaire_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "template_type": row.template_type,
                "name": row.name,
                "version": row.version,
            },
            metadata_json={"source": "api"},
        )
        return row

    def clone_template(self, org_id: uuid.UUID, template_id: uuid.UUID, new_name: str, created_by: uuid.UUID) -> QuestionnaireTemplate:
        source = self.require_visible_template(org_id, template_id)
        if source.organization_id is not None and source.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")

        cloned = QuestionnaireTemplate(
            organization_id=org_id,
            template_type="custom",
            name=new_name,
            version=source.version,
            description=source.description,
            is_system_template=False,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(cloned)
        self.db.flush()

        section_rows = self.db.execute(
            select(QuestionnaireTemplateSection).where(QuestionnaireTemplateSection.template_id == source.id)
            .order_by(QuestionnaireTemplateSection.order_index.asc(), QuestionnaireTemplateSection.created_at.asc())
        ).scalars().all()
        section_id_map: dict[uuid.UUID, uuid.UUID] = {}
        for section in section_rows:
            new_section = QuestionnaireTemplateSection(
                template_id=cloned.id,
                title=section.title,
                description=section.description,
                order_index=section.order_index,
            )
            self.db.add(new_section)
            self.db.flush()
            section_id_map[section.id] = new_section.id

        question_rows = self.db.execute(
            select(QuestionnaireTemplateQuestion).where(QuestionnaireTemplateQuestion.template_id == source.id)
            .order_by(QuestionnaireTemplateQuestion.order_index.asc(), QuestionnaireTemplateQuestion.created_at.asc())
        ).scalars().all()
        for question in question_rows:
            self.db.add(
                QuestionnaireTemplateQuestion(
                    template_id=cloned.id,
                    section_id=section_id_map[question.section_id],
                    question_text=question.question_text,
                    question_type=question.question_type,
                    category_tag=question.category_tag,
                    framework_ref=question.framework_ref,
                    allowed_values=question.allowed_values,
                    expected_answer=question.expected_answer,
                    is_required=question.is_required,
                    order_index=question.order_index,
                    help_text=question.help_text,
                )
            )

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_template.cloned",
            entity_type="questionnaire_template",
            entity_id=cloned.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "source_template_id": str(source.id),
                "name": cloned.name,
                "template_type": cloned.template_type,
            },
            metadata_json={"source": "api"},
        )
        return cloned

    def add_section(self, org_id: uuid.UUID, template_id: uuid.UUID, data) -> QuestionnaireTemplateSection:
        template = self.require_visible_template(org_id, template_id)
        if template.is_system_template:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="System templates cannot be modified")
        if template.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")

        row = QuestionnaireTemplateSection(
            template_id=template.id,
            title=data.title,
            description=data.description,
            order_index=data.order_index,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def add_question(self, org_id: uuid.UUID, template_id: uuid.UUID, section_id: uuid.UUID, data) -> QuestionnaireTemplateQuestion:
        template = self.require_visible_template(org_id, template_id)
        if template.is_system_template:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="System templates cannot be modified")
        if template.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")

        section = self.db.execute(
            select(QuestionnaireTemplateSection).where(
                QuestionnaireTemplateSection.id == section_id,
                QuestionnaireTemplateSection.template_id == template.id,
            )
        ).scalar_one_or_none()
        if section is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template section not found")

        row = QuestionnaireTemplateQuestion(
            template_id=template.id,
            section_id=section_id,
            question_text=data.question_text,
            question_type=data.question_type,
            category_tag=data.category_tag,
            framework_ref=data.framework_ref,
            allowed_values=data.allowed_values,
            expected_answer=data.expected_answer,
            is_required=data.is_required,
            order_index=data.order_index,
            help_text=data.help_text,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def soft_delete_template(self, org_id: uuid.UUID, template_id: uuid.UUID, user_id: uuid.UUID) -> QuestionnaireTemplate:
        row = self.require_visible_template(org_id, template_id)
        if row.is_system_template:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="System templates cannot be deleted")
        if row.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire template not found")

        row.deleted_at = self.utcnow()
        row.is_active = False
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_template.deleted",
            entity_type="questionnaire_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat(), "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def create_response(self, org_id: uuid.UUID, vendor_id: uuid.UUID, template_id: uuid.UUID, data, created_by: uuid.UUID) -> VendorQuestionnaireResponse:
        vendor = self.db.execute(
            select(Vendor).where(
                Vendor.organization_id == org_id,
                Vendor.id == vendor_id,
            )
        ).scalar_one_or_none()
        if vendor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

        template = self.require_visible_template(org_id, template_id)
        if not template.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template is not active")

        response = VendorQuestionnaireResponse(
            organization_id=org_id,
            vendor_id=vendor_id,
            template_id=template.id,
            title=data.title or template.name,
            status="draft",
            due_date=data.due_date,
            created_by=created_by,
        )
        self.db.add(response)
        self.db.flush()

        questions = self.db.execute(
            select(QuestionnaireTemplateQuestion).where(QuestionnaireTemplateQuestion.template_id == template.id)
            .order_by(QuestionnaireTemplateQuestion.order_index.asc(), QuestionnaireTemplateQuestion.created_at.asc())
        ).scalars().all()
        for question in questions:
            self.db.add(
                VendorQuestionnaireAnswer(
                    organization_id=org_id,
                    response_id=response.id,
                    question_id=question.id,
                    answer_text=None,
                    answer_value=None,
                    score_contribution=None,
                    is_answered=False,
                )
            )
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_response.created",
            entity_type="vendor_questionnaire_response",
            entity_id=response.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "vendor_id": str(vendor_id),
                "template_id": str(template.id),
                "status": response.status,
                "question_count": len(questions),
            },
            metadata_json={"source": "api"},
        )
        return response

    def submit_answer(
        self,
        org_id: uuid.UUID,
        response_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_text: str | None,
        answer_value: str | None,
        user_id: uuid.UUID,
    ) -> VendorQuestionnaireAnswer:
        response = self.require_response(org_id, response_id)
        if response.status in {"completed", "expired"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot update answers for closed questionnaire response")

        answer = self.db.execute(
            select(VendorQuestionnaireAnswer).where(
                VendorQuestionnaireAnswer.organization_id == org_id,
                VendorQuestionnaireAnswer.response_id == response.id,
                VendorQuestionnaireAnswer.question_id == question_id,
            )
        ).scalar_one_or_none()
        if answer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question answer row not found")

        answer.answer_text = answer_text
        answer.answer_value = answer_value
        answer.is_answered = True

        if response.status in {"draft", "sent"}:
            response.status = "in_progress"
        if response.responded_at is None:
            response.responded_at = self.utcnow()

        self.db.flush()
        score = self.scoring_service.recalculate_on_answer(org_id, response.id, actor_user_id=user_id)
        if answer_text:
            ShadowAIService(self.db).scan_and_create(org_id, answer_text, reported_by=user_id)

        AuditService(self.db).write_audit_log(
            action="questionnaire_response.answer_submitted",
            entity_type="vendor_questionnaire_response",
            entity_id=response.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "question_id": str(question_id),
                "is_answered": answer.is_answered,
                "score": score,
            },
            metadata_json={"source": "api"},
        )
        return answer

    def bulk_submit_answers(self, org_id: uuid.UUID, response_id: uuid.UUID, answers: list, user_id: uuid.UUID) -> dict:
        updated = 0
        for payload in answers:
            self.submit_answer(
                org_id,
                response_id,
                payload.question_id,
                payload.answer_text,
                payload.answer_value,
                user_id,
            )
            updated += 1

        response = self.require_response(org_id, response_id)
        final_score = int(response.calculated_risk_score or 0)

        AuditService(self.db).write_audit_log(
            action="questionnaire_response.bulk_answers_submitted",
            entity_type="vendor_questionnaire_response",
            entity_id=response.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"updated": updated, "score": final_score},
            metadata_json={"source": "api"},
        )
        return {"updated": updated, "score": final_score}

    def transition_response_status(
        self,
        org_id: uuid.UUID,
        response_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
    ) -> VendorQuestionnaireResponse:
        response = self.require_response(org_id, response_id)
        allowed = self.ALLOWED_STATUS_TRANSITIONS.get(response.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {response.status} to {new_status}",
            )

        before_status = response.status
        response.status = new_status
        now = self.utcnow()
        if new_status == "sent":
            response.sent_at = now
        if new_status == "submitted" and response.responded_at is None:
            response.responded_at = now
        if new_status == "completed":
            response.completed_at = now
            self.scoring_service.compute_response_score(org_id, response.id, actor_user_id=user_id)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="questionnaire_response.status_transitioned",
            entity_type="vendor_questionnaire_response",
            entity_id=response.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json={"status": before_status},
            after_json={"status": response.status},
            metadata_json={"source": "api"},
        )
        return response

    def list_responses(
        self,
        org_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        status_value: str | None = None,
        template_id: uuid.UUID | None = None,
    ) -> list[VendorQuestionnaireResponse]:
        stmt = select(VendorQuestionnaireResponse).where(
            VendorQuestionnaireResponse.organization_id == org_id,
            VendorQuestionnaireResponse.deleted_at.is_(None),
        )
        if vendor_id is not None:
            stmt = stmt.where(VendorQuestionnaireResponse.vendor_id == vendor_id)
        if status_value is not None:
            stmt = stmt.where(VendorQuestionnaireResponse.status == status_value)
        if template_id is not None:
            stmt = stmt.where(VendorQuestionnaireResponse.template_id == template_id)

        return self.db.execute(stmt.order_by(VendorQuestionnaireResponse.created_at.desc())).scalars().all()

    def get_response_with_answers(
        self,
        org_id: uuid.UUID,
        response_id: uuid.UUID,
    ) -> tuple[VendorQuestionnaireResponse, list[tuple[VendorQuestionnaireAnswer, QuestionnaireTemplateQuestion]]]:
        response = self.require_response(org_id, response_id)
        rows = self.db.execute(
            select(VendorQuestionnaireAnswer, QuestionnaireTemplateQuestion)
            .join(QuestionnaireTemplateQuestion, QuestionnaireTemplateQuestion.id == VendorQuestionnaireAnswer.question_id)
            .where(
                VendorQuestionnaireAnswer.organization_id == org_id,
                VendorQuestionnaireAnswer.response_id == response.id,
            )
            .order_by(QuestionnaireTemplateQuestion.order_index.asc(), QuestionnaireTemplateQuestion.created_at.asc())
        ).all()
        return response, rows
