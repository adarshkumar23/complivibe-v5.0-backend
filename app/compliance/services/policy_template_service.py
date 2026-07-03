import uuid
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.policy_template import PolicyTemplate
from app.models.policy_template_clone import PolicyTemplateClone
from app.schemas.policy_template import PolicyTemplateCloneRequest
from app.services.compliance_policy_service import CompliancePolicyService
from app.services.audit_service import AuditService


class PolicyTemplateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _policy_type_for_template(slug: str) -> str:
        slug_map = {
            "acceptable-use": "acceptable_use",
            "data-retention": "data_retention",
            "incident-response": "incident_response",
            "access-control": "access_control",
            "change-management": "change_management",
            "business-continuity": "business_continuity",
        }
        return slug_map.get(slug, "other")

    def _get_template(self, template_id: uuid.UUID, *, active_only: bool) -> PolicyTemplate:
        stmt = select(PolicyTemplate).where(PolicyTemplate.id == template_id)
        if active_only:
            stmt = stmt.where(PolicyTemplate.is_active.is_(True))
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy template not found")
        return row

    def _get_template_by_slug(self, slug: str, *, active_only: bool) -> PolicyTemplate:
        stmt = select(PolicyTemplate).where(PolicyTemplate.slug == slug)
        if active_only:
            stmt = stmt.where(PolicyTemplate.is_active.is_(True))
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy template not found")
        return row

    def list_templates(
        self,
        *,
        org_id: uuid.UUID | None = None,
        policy_type: str | None = None,
        include_system: bool = True,
        include_org_custom: bool = True,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        framework_tag: str | None = None,
        search: str | None = None,
        is_active: bool = True,
    ) -> list[dict]:
        stmt = select(PolicyTemplate)
        if is_active:
            stmt = stmt.where(PolicyTemplate.is_active.is_(True))
        if org_id is not None:
            clauses = []
            if include_system:
                clauses.append(or_(PolicyTemplate.is_system.is_(True), PolicyTemplate.organization_id.is_(None)))
            if include_org_custom:
                clauses.append(PolicyTemplate.organization_id == org_id)
            if not clauses:
                return []
            stmt = stmt.where(or_(*clauses))
        if policy_type is not None:
            stmt = stmt.where(PolicyTemplate.policy_type == policy_type)
        if category is not None:
            stmt = stmt.where(PolicyTemplate.category == category)
        if search is not None and search.strip():
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PolicyTemplate.name.ilike(like),
                    PolicyTemplate.title.ilike(like),
                    PolicyTemplate.description.ilike(like),
                )
            )

        rows = self.db.execute(
            stmt.order_by(PolicyTemplate.is_system.desc(), PolicyTemplate.name.asc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        ).scalars().all()

        normalized_framework = framework_tag.lower().strip() if framework_tag else None
        if normalized_framework:
            rows = [
                row
                for row in rows
                if any(str(tag).lower() == normalized_framework for tag in (row.framework_tags or []))
            ]

        if not rows:
            return []

        template_ids = [row.id for row in rows]
        clone_rows = self.db.execute(
            select(PolicyTemplateClone.template_id, func.count(PolicyTemplateClone.id))
            .where(PolicyTemplateClone.template_id.in_(template_ids))
            .group_by(PolicyTemplateClone.template_id)
        ).all()
        clone_counts = {template_id: int(count) for template_id, count in clone_rows}

        return [
            {
                "id": row.id,
                "slug": row.slug,
                "title": row.title or row.name,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "policy_type": row.policy_type,
                "organization_id": row.organization_id,
                "is_system": row.is_system,
                "framework_tags": list(row.framework_tags or []),
                "version": row.version,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "content": row.content,
                "clone_count": clone_counts.get(row.id, 0),
            }
            for row in rows
        ]

    def list_categories(self) -> list[dict]:
        rows = self.db.execute(
            select(PolicyTemplate.category, func.count(PolicyTemplate.id))
            .where(PolicyTemplate.is_active.is_(True))
            .group_by(PolicyTemplate.category)
            .order_by(PolicyTemplate.category.asc())
        ).all()
        return [{"category": str(category), "template_count": int(count)} for category, count in rows]

    def list_framework_tags(self) -> list[dict]:
        templates = self.db.execute(
            select(PolicyTemplate.framework_tags).where(PolicyTemplate.is_active.is_(True))
        ).scalars().all()
        counts: Counter[str] = Counter()
        for tags in templates:
            for tag in tags or []:
                counts[str(tag)] += 1

        return [
            {"framework_tag": key, "template_count": int(counts[key])}
            for key in sorted(counts)
        ]

    def get_template(self, template_id: uuid.UUID) -> dict:
        row = self._get_template(template_id, active_only=True)
        clone_count = int(
            self.db.execute(
                select(func.count(PolicyTemplateClone.id)).where(PolicyTemplateClone.template_id == row.id)
            ).scalar_one()
        )
        return {
            "id": row.id,
            "slug": row.slug,
            "title": row.title or row.name,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "policy_type": row.policy_type,
            "organization_id": row.organization_id,
            "is_system": row.is_system,
            "framework_tags": list(row.framework_tags or []),
            "version": row.version,
            "is_active": row.is_active,
            "created_at": row.created_at,
            "content": row.content,
            "clone_count": clone_count,
        }

    def get_template_by_slug(self, slug: str) -> dict:
        row = self._get_template_by_slug(slug, active_only=True)
        return self.get_template(row.id)

    def get_template_for_org(self, template_id: uuid.UUID, org_id: uuid.UUID) -> PolicyTemplate:
        row = self.db.execute(
            select(PolicyTemplate).where(
                PolicyTemplate.id == template_id,
                PolicyTemplate.is_active.is_(True),
                or_(
                    PolicyTemplate.is_system.is_(True),
                    PolicyTemplate.organization_id.is_(None),
                    PolicyTemplate.organization_id == org_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy template not found")
        return row

    def apply_template(
        self,
        *,
        template_id: uuid.UUID,
        org_id: uuid.UUID,
        applied_by: uuid.UUID,
        override_title: str | None = None,
    ) -> tuple[CompliancePolicy, uuid.UUID]:
        template = self.get_template_for_org(template_id, org_id)
        policy_service = CompliancePolicyService(self.db)
        policy = policy_service.create_policy(
            organization_id=org_id,
            title=(override_title or f"{(template.title or template.name)} (from template)"),
            description=template.description,
            policy_type=(template.policy_type or self._policy_type_for_template(template.slug)),
            owner_user_id=applied_by,
            policy_status="draft",
            version=template.version,
            content_url=None,
            tags_json={
                "template_id": str(template.id),
                "template_slug": template.slug,
                "template_title": template.title or template.name,
                "framework_tags": template.framework_tags or [],
            },
            notes=template.content,
        )

        # The template body must be persisted through the real versioning system, not just
        # the notes field, so template-applied policies get a proper CompliancePolicyVersion
        # like every other policy-content-creation path (AI drafts, manual version creation).
        content_snapshot = {
            "content": template.content,
            "source": "policy_template",
            "source_template_id": str(template.id),
        }
        version = CompliancePolicyVersion(
            organization_id=org_id,
            policy_id=policy.id,
            version_number=template.version or "1.0",
            content_snapshot_json=content_snapshot,
            change_summary=f"Applied from template: {template.title or template.name}",
            status="draft",
            content_sha256=policy_service.content_sha256_hexdigest(content_snapshot),
        )
        self.db.add(version)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_template.applied",
            entity_type="compliance_policy",
            entity_id=policy.id,
            organization_id=org_id,
            actor_user_id=applied_by,
            metadata_json={
                "template_id": str(template.id),
                "template_title": template.title or template.name,
                "new_policy_id": str(policy.id),
                "policy_version_id": str(version.id),
            },
        )
        return policy, version.id

    def create_org_template(
        self,
        *,
        org_id: uuid.UUID,
        title: str,
        description: str | None,
        policy_type: str | None,
        content: str,
        created_by: uuid.UUID,
    ) -> PolicyTemplate:
        slug_base = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")
        slug_base = "-".join(part for part in slug_base.split("-") if part) or "template"
        slug = slug_base
        seq = 1
        while self.db.execute(select(PolicyTemplate.id).where(PolicyTemplate.slug == slug)).scalar_one_or_none() is not None:
            seq += 1
            slug = f"{slug_base}-{seq}"

        row = PolicyTemplate(
            organization_id=org_id,
            slug=slug,
            title=title,
            name=title,
            description=description or "",
            category="Compliance",
            policy_type=policy_type,
            framework_tags=[],
            content=content,
            version="1.0",
            is_system=False,
            is_active=True,
        )
        self.db.add(row)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="policy_template.created",
            entity_type="policy_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            metadata_json={"policy_type": policy_type},
        )
        return row

    def clone_template(
        self,
        org_id: uuid.UUID,
        template_id: uuid.UUID,
        payload: PolicyTemplateCloneRequest,
        cloned_by: uuid.UUID,
    ) -> tuple[PolicyTemplateClone, PolicyTemplate, CompliancePolicy]:
        template = self._get_template(template_id, active_only=True)

        policy = CompliancePolicy(
            organization_id=org_id,
            title=(payload.policy_name or template.name),
            description=template.description,
            policy_type=self._policy_type_for_template(template.slug),
            status="draft",
            owner_user_id=cloned_by,
            version=template.version,
            notes=template.content,
            tags_json={"template_slug": template.slug, "template_name": template.name, "framework_tags": template.framework_tags or []},
        )
        self.db.add(policy)
        self.db.flush()

        clone = PolicyTemplateClone(
            organization_id=org_id,
            template_id=template.id,
            cloned_policy_id=policy.id,
            cloned_by=cloned_by,
            customization_notes=payload.customization_notes,
        )
        self.db.add(clone)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_template.cloned",
            entity_type="policy_template_clone",
            entity_id=clone.id,
            organization_id=org_id,
            actor_user_id=cloned_by,
            after_json={
                "template_id": str(template.id),
                "template_slug": template.slug,
                "cloned_policy_id": str(policy.id),
                "policy_name": policy.title,
            },
            metadata_json={"source": "api"},
        )

        return clone, template, policy

    def list_org_clones(
        self,
        org_id: uuid.UUID,
        *,
        template_id: uuid.UUID | None = None,
    ) -> list[tuple[PolicyTemplateClone, PolicyTemplate, CompliancePolicy]]:
        stmt = (
            select(PolicyTemplateClone, PolicyTemplate, CompliancePolicy)
            .join(PolicyTemplate, PolicyTemplate.id == PolicyTemplateClone.template_id)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyTemplateClone.cloned_policy_id)
            .where(PolicyTemplateClone.organization_id == org_id)
        )
        if template_id is not None:
            stmt = stmt.where(PolicyTemplateClone.template_id == template_id)

        return self.db.execute(stmt.order_by(PolicyTemplateClone.cloned_at.desc())).all()

    def get_clone_stats(self, template_id: uuid.UUID) -> dict:
        template = self._get_template(template_id, active_only=False)

        stats = self.db.execute(
            select(
                func.count(PolicyTemplateClone.id),
                func.count(func.distinct(PolicyTemplateClone.organization_id)),
                func.max(PolicyTemplateClone.cloned_at),
            ).where(PolicyTemplateClone.template_id == template.id)
        ).one()

        total_clones, unique_orgs, most_recent = stats
        return {
            "template_id": template.id,
            "template_name": template.name,
            "total_clones": int(total_clones or 0),
            "unique_orgs": int(unique_orgs or 0),
            "most_recent_clone_at": most_recent,
        }
