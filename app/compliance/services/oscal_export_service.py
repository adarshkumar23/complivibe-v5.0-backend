import json
import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.common_control_mapping import CommonControlMapping
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.oscal_export_job import OscalExportJob
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService


class OSCALExportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def isoformat_z(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def slugify_framework(framework: Framework) -> str:
        source = framework.code or framework.name
        slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
        return slug or str(framework.id)

    @staticmethod
    def map_control_status(value: str | None) -> str:
        if value == "active":
            return "operational"
        if value == "inactive":
            return "disposition"
        if value == "draft":
            return "under-development"
        if value == "failed":
            return "other"
        return "other"

    @staticmethod
    def map_test_result(value: str | None) -> str:
        if value == "passed":
            return "satisfied"
        return "not-satisfied"

    @staticmethod
    def map_risk_score_band(value: int | None) -> str:
        v = int(value or 0)
        if v <= 2:
            return "low"
        if v == 3:
            return "moderate"
        return "high"

    def require_job_in_org(self, job_id: uuid.UUID, org_id: uuid.UUID) -> OscalExportJob:
        row = self.db.execute(
            select(OscalExportJob).where(
                OscalExportJob.id == job_id,
                OscalExportJob.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OSCAL export job not found")
        return row

    def create_job(
        self,
        export_type: str,
        framework_id: uuid.UUID | None,
        org_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
    ) -> OscalExportJob:
        row = OscalExportJob(
            organization_id=org_id,
            export_type=export_type,
            framework_id=framework_id,
            status="pending",
            oscal_version="1.1.2",
            requested_by_user_id=requested_by_user_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="oscal_export.job_created",
            entity_type="oscal_export_job",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=requested_by_user_id,
            after_json={
                "export_type": row.export_type,
                "framework_id": str(row.framework_id) if row.framework_id else None,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_jobs(
        self,
        org_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        export_type: str | None = None,
    ) -> list[OscalExportJob]:
        stmt = select(OscalExportJob).where(OscalExportJob.organization_id == org_id)
        if status_filter is not None:
            stmt = stmt.where(OscalExportJob.status == status_filter)
        if export_type is not None:
            stmt = stmt.where(OscalExportJob.export_type == export_type)
        return self.db.execute(stmt.order_by(OscalExportJob.created_at.desc())).scalars().all()

    def summary(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(OscalExportJob).where(OscalExportJob.organization_id == org_id)
        ).scalars().all()
        by_type = {
            "ssp": 0,
            "assessment_plan": 0,
            "assessment_results": 0,
            "full_package": 0,
        }
        by_status = {
            "pending": 0,
            "processing": 0,
            "complete": 0,
            "failed": 0,
        }
        last_export_at: datetime | None = None
        last_successful_export_at: datetime | None = None

        for row in rows:
            by_type[row.export_type] = by_type.get(row.export_type, 0) + 1
            by_status[row.status] = by_status.get(row.status, 0) + 1
            if last_export_at is None or row.created_at > last_export_at:
                last_export_at = row.created_at
            if row.status == "complete" and row.completed_at is not None:
                if last_successful_export_at is None or row.completed_at > last_successful_export_at:
                    last_successful_export_at = row.completed_at

        return {
            "total_exports": len(rows),
            "by_type": by_type,
            "by_status": by_status,
            "last_export_at": last_export_at,
            "last_successful_export_at": last_successful_export_at,
        }

    def _load_frameworks(self, org_id: uuid.UUID, framework_id: uuid.UUID | None) -> list[Framework]:
        stmt = (
            select(Framework)
            .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
                Framework.status == "active",
            )
            .order_by(Framework.name.asc())
        )
        if framework_id is not None:
            stmt = stmt.where(Framework.id == framework_id)
        rows = self.db.execute(stmt).scalars().all()
        if framework_id is not None and not rows:
            raise ValueError("Framework not found or not active for organization")
        return rows

    def _oscal_metadata(self, org: Organization, framework: Framework | None, *, doc_type: str) -> dict:
        if framework is not None:
            title = f"{org.name} - {framework.name} {doc_type}"
        else:
            title = f"{org.name} - All Frameworks {doc_type}"
        return {
            "title": title,
            "last-modified": self.isoformat_z(self.utcnow()),
            "version": "1.0.0",
            "oscal-version": "1.1.2",
            "remarks": "Generated by CompliVibe v5.0",
        }

    def _obligation_control_pairs(
        self,
        org_id: uuid.UUID,
        framework_ids: list[uuid.UUID],
        scoped_control_ids: set[uuid.UUID] | None,
    ) -> list[tuple[Obligation, Control, str | None]]:
        if not framework_ids:
            return []

        common_rows = self.db.execute(
            select(CommonControlMapping, Obligation, Control)
            .join(Obligation, Obligation.id == CommonControlMapping.obligation_id)
            .join(Control, Control.id == CommonControlMapping.control_id)
            .where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.status == "active",
                CommonControlMapping.framework_id.in_(framework_ids),
                Control.organization_id == org_id,
            )
            .order_by(Obligation.reference_code.asc(), Control.title.asc())
        ).all()

        mapping_rows = self.db.execute(
            select(ControlObligationMapping, Obligation, Control)
            .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
            .join(Control, Control.id == ControlObligationMapping.control_id)
            .where(
                ControlObligationMapping.organization_id == org_id,
                ControlObligationMapping.status == "active",
                Obligation.framework_id.in_(framework_ids),
                Control.organization_id == org_id,
            )
            .order_by(Obligation.reference_code.asc(), Control.title.asc())
        ).all()

        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        pairs: list[tuple[Obligation, Control, str | None]] = []

        for common, obligation, control in common_rows:
            if scoped_control_ids is not None and control.id not in scoped_control_ids:
                continue
            key = (obligation.id, control.id)
            if key in seen:
                continue
            seen.add(key)
            section_ref = common.section_reference or obligation.reference_code
            pairs.append((obligation, control, section_ref))

        for mapping, obligation, control in mapping_rows:
            if scoped_control_ids is not None and control.id not in scoped_control_ids:
                continue
            key = (obligation.id, control.id)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((obligation, control, obligation.reference_code))

        return pairs

    def _control_ids_for_frameworks(self, org_id: uuid.UUID, framework_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not framework_ids:
            return set()

        ids: set[uuid.UUID] = set(
            self.db.execute(
                select(CommonControlMapping.control_id).where(
                    CommonControlMapping.organization_id == org_id,
                    CommonControlMapping.status == "active",
                    CommonControlMapping.framework_id.in_(framework_ids),
                )
            ).scalars().all()
        )

        ids.update(
            self.db.execute(
                select(ControlObligationMapping.control_id)
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id.in_(framework_ids),
                )
            ).scalars().all()
        )

        ids.update(
            self.db.execute(
                select(Control.id)
                .join(Obligation, Obligation.id == Control.obligation_id)
                .where(
                    Control.organization_id == org_id,
                    Obligation.framework_id.in_(framework_ids),
                )
            ).scalars().all()
        )

        return ids

    def _build_ssp(
        self,
        *,
        org: Organization,
        framework: Framework | None,
        controls: list[Control],
        members: list[tuple[Membership, Role, User]],
        obligation_control_pairs: list[tuple[Obligation, Control, str | None]],
    ) -> dict:
        framework_slug = self.slugify_framework(framework) if framework is not None else "all-frameworks"
        framework_name = framework.name if framework is not None else "All Active Frameworks"

        users = [
            {
                "uuid": str(uuid.uuid4()),
                "title": user.email,
                "role-ids": [role.name],
                "props": [{"name": "type", "value": "internal"}],
            }
            for membership, role, user in members
            if membership.status == "active"
        ]

        components = [
            {
                "uuid": str(control.id),
                "type": "software",
                "title": control.title,
                "description": control.description or "",
                "status": {"state": self.map_control_status(control.status)},
                "props": [{"name": "control-type", "value": control.control_type or "technical"}],
            }
            for control in controls
        ]

        implemented_requirements: list[dict] = []
        for obligation, control, section_reference in obligation_control_pairs:
            implemented_requirements.append(
                {
                    "uuid": str(uuid.uuid4()),
                    "control-id": section_reference or str(obligation.id),
                    "description": obligation.title,
                    "remarks": obligation.description or "",
                    "by-components": [
                        {
                            "component-uuid": str(control.id),
                            "uuid": str(uuid.uuid4()),
                            "description": f"Implemented by: {control.title}",
                            "implementation-status": {"state": self.map_control_status(control.status)},
                        }
                    ],
                }
            )

        return {
            "system-security-plan": {
                "uuid": str(uuid.uuid4()),
                "metadata": self._oscal_metadata(org, framework, doc_type="SSP"),
                "import-profile": {
                    "href": f"#{framework_slug}",
                    "remarks": framework_name,
                },
                "system-characteristics": {
                    "system-name": org.name,
                    "description": getattr(org, "description", "") or "",
                    "security-sensitivity-level": "moderate",
                    "system-information": {
                        "information-types": [
                            {
                                "uuid": str(uuid.uuid4()),
                                "title": "Organizational Data",
                                "description": "Data processed by org",
                                "confidentiality-impact": {"selected": "moderate"},
                                "integrity-impact": {"selected": "moderate"},
                                "availability-impact": {"selected": "moderate"},
                            }
                        ]
                    },
                    "security-impact-level": {
                        "security-objective-confidentiality": "moderate",
                        "security-objective-integrity": "moderate",
                        "security-objective-availability": "moderate",
                    },
                    "status": {"state": "operational"},
                    "authorization-boundary": {"description": "System authorization boundary"},
                },
                "system-implementation": {
                    "users": users,
                    "components": components,
                },
                "control-implementation": {
                    "description": "Control implementations",
                    "implemented-requirements": implemented_requirements,
                },
            }
        }

    def _build_ap(
        self,
        *,
        org: Organization,
        framework: Framework | None,
        obligations: list[Obligation],
        control_tests: list[ControlTestDefinition],
    ) -> dict:
        include_controls = [
            {"control-id": obligation.reference_code or str(obligation.id)}
            for obligation in obligations
        ]

        tasks = [
            {
                "uuid": str(uuid.uuid4()),
                "type": "action",
                "title": f"Test: {test.name}",
                "description": test.description or "",
                "associated-activities": [
                    {
                        "activity-uuid": str(uuid.uuid4()),
                        "subjects": [{"type": "component", "include-all": {}}],
                    }
                ],
            }
            for test in control_tests
        ]

        return {
            "assessment-plan": {
                "uuid": str(uuid.uuid4()),
                "metadata": self._oscal_metadata(org, framework, doc_type="Assessment Plan"),
                "import-ssp": {"href": "#system-security-plan", "remarks": "SSP for this system"},
                "reviewed-controls": {
                    "control-selections": [
                        {
                            "include-controls": include_controls,
                        }
                    ]
                },
                "assessment-subjects": [{"type": "component", "include-all": {}}],
                "assessment-assets": {
                    "assessment-platforms": [
                        {
                            "uuid": str(uuid.uuid4()),
                            "title": "CompliVibe Assessment Platform",
                            "props": [{"name": "type", "value": "automated"}],
                        }
                    ]
                },
                "tasks": tasks,
            }
        }

    def _build_ar(
        self,
        *,
        org: Organization,
        framework: Framework | None,
        obligations: list[Obligation],
        evidence_items: list[EvidenceItem],
        evidence_links_by_item: dict[uuid.UUID, list[EvidenceControlLink]],
        latest_runs_by_control: dict[uuid.UUID, ControlTestRun],
        tests_by_id: dict[uuid.UUID, ControlTestDefinition],
        obligation_refs_by_control: dict[uuid.UUID, str],
        risks: list[Risk],
        risk_control_links: dict[uuid.UUID, list[RiskControlLink]],
    ) -> dict:
        include_controls = [{"control-id": obligation.reference_code or str(obligation.id)} for obligation in obligations]

        observation_uuid_by_control: dict[uuid.UUID, str] = {}
        observations: list[dict] = []
        for evidence in evidence_items:
            links = evidence_links_by_item.get(evidence.id, [])
            subject_control_id = evidence.legacy_control_id
            if subject_control_id is None and links:
                subject_control_id = links[0].control_id

            observation_uuid = str(uuid.uuid4())
            if subject_control_id is not None and subject_control_id not in observation_uuid_by_control:
                observation_uuid_by_control[subject_control_id] = observation_uuid

            collected = self.isoformat_z(evidence.created_at)
            expires = None
            if evidence.valid_until is not None:
                valid_until = evidence.valid_until
                if valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=UTC)
                expires = valid_until.astimezone(UTC).date().isoformat() + "T00:00:00Z"

            obs = {
                "uuid": observation_uuid,
                "title": evidence.title,
                "description": evidence.description or "",
                "methods": ["EXAMINE"],
                "types": ["finding"],
                "subjects": [
                    {
                        "subject-uuid": str(subject_control_id) if subject_control_id is not None else str(uuid.uuid4()),
                        "type": "component",
                    }
                ],
                "collected": collected,
                "remarks": f"Status: {evidence.status}",
            }
            if expires is not None:
                obs["expires"] = expires
            observations.append(obs)

        findings: list[dict] = []
        for control_id, run in latest_runs_by_control.items():
            test_name = run.check_key
            if run.control_test_definition_id in tests_by_id:
                test_name = tests_by_id[run.control_test_definition_id].name
            related: list[dict] = []
            if control_id in observation_uuid_by_control:
                related.append({"observation-uuid": observation_uuid_by_control[control_id]})

            findings.append(
                {
                    "uuid": str(uuid.uuid4()),
                    "title": f"Finding: {test_name}",
                    "description": run.result_reason or "",
                    "target": {
                        "type": "objective-id",
                        "target-id": obligation_refs_by_control.get(control_id, str(control_id)),
                        "status": {"state": self.map_test_result(run.result)},
                    },
                    "related-observations": related,
                }
            )

        risks_payload: list[dict] = []
        for risk in risks:
            linked_controls = risk_control_links.get(risk.id, [])
            if not linked_controls:
                continue
            score_value = risk.residual_score if risk.residual_score is not None else risk.inherent_score
            risks_payload.append(
                {
                    "uuid": str(risk.id),
                    "title": risk.title,
                    "description": risk.description or "",
                    "statement": f"Risk score: {score_value}",
                    "status": "open",
                    "characterizations": [
                        {
                            "origin": {
                                "actors": [
                                    {
                                        "type": "tool",
                                        "actor-uuid": str(uuid.uuid4()),
                                        "title": "CompliVibe",
                                    }
                                ]
                            },
                            "facets": [
                                {
                                    "name": "likelihood",
                                    "system": "http://csrc.nist.gov/ns/oscal",
                                    "value": self.map_risk_score_band(risk.likelihood),
                                },
                                {
                                    "name": "impact",
                                    "system": "http://csrc.nist.gov/ns/oscal",
                                    "value": self.map_risk_score_band(risk.impact),
                                },
                            ],
                        }
                    ],
                }
            )

        time_points: list[datetime] = [self.utcnow()]
        time_points.extend([self.to_utc(e.created_at) for e in evidence_items if e.created_at is not None])
        time_points.extend([self.to_utc(r.created_at) for r in latest_runs_by_control.values() if r.created_at is not None])
        start = min(time_points)
        end = max(time_points)

        return {
            "assessment-results": {
                "uuid": str(uuid.uuid4()),
                "metadata": self._oscal_metadata(org, framework, doc_type="Assessment Results"),
                "import-ap": {"href": "#assessment-plan"},
                "results": [
                    {
                        "uuid": str(uuid.uuid4()),
                        "title": f"Assessment Results - {self.utcnow().date().isoformat()}",
                        "description": "CompliVibe assessment run",
                        "start": self.isoformat_z(start),
                        "end": self.isoformat_z(end),
                        "reviewed-controls": {
                            "control-selections": [
                                {
                                    "include-controls": include_controls,
                                }
                            ]
                        },
                        "observations": observations,
                        "findings": findings,
                        "risks": risks_payload,
                    }
                ],
            }
        }

    def build(self, job_id: uuid.UUID, org_id: uuid.UUID) -> OscalExportJob:
        job = self.require_job_in_org(job_id, org_id)
        started_at = self.utcnow()
        job.status = "processing"
        job.started_at = started_at
        job.error_message = None
        self.db.flush()

        try:
            org = self.db.execute(
                select(Organization).where(
                    Organization.id == org_id,
                    Organization.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if org is None:
                raise ValueError("Organization not found")

            frameworks = self._load_frameworks(org_id, job.framework_id)
            framework_ids = [framework.id for framework in frameworks]

            scoped_control_ids: set[uuid.UUID] | None = None
            if job.framework_id is not None:
                scoped_control_ids = self._control_ids_for_frameworks(org_id, framework_ids)

            controls_stmt = select(Control).where(
                Control.organization_id == org_id,
                Control.status != "archived",
            )
            if scoped_control_ids is not None:
                if scoped_control_ids:
                    controls_stmt = controls_stmt.where(Control.id.in_(scoped_control_ids))
                else:
                    controls_stmt = controls_stmt.where(Control.id == uuid.uuid4())
            controls = self.db.execute(controls_stmt.order_by(Control.title.asc())).scalars().all()
            control_ids = {control.id for control in controls}

            obligations: list[Obligation] = []
            if framework_ids:
                obligations = self.db.execute(
                    select(Obligation)
                    .where(
                        Obligation.framework_id.in_(framework_ids),
                        Obligation.status == "active",
                    )
                    .order_by(Obligation.reference_code.asc())
                ).scalars().all()

            obligation_control_pairs = self._obligation_control_pairs(org_id, framework_ids, scoped_control_ids)

            members = self.db.execute(
                select(Membership, Role, User)
                .join(Role, Role.id == Membership.role_id)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                    User.is_active.is_(True),
                    User.status == "active",
                )
                .order_by(User.email.asc())
            ).all()

            tests_stmt = select(ControlTestDefinition).where(
                ControlTestDefinition.organization_id == org_id,
                ControlTestDefinition.status != "archived",
            )
            if control_ids:
                tests_stmt = tests_stmt.where(ControlTestDefinition.control_id.in_(control_ids))
            else:
                tests_stmt = tests_stmt.where(ControlTestDefinition.id == uuid.uuid4())
            control_tests = self.db.execute(tests_stmt.order_by(ControlTestDefinition.name.asc())).scalars().all()
            tests_by_id = {test.id: test for test in control_tests}

            runs_stmt = select(ControlTestRun).where(ControlTestRun.organization_id == org_id)
            if control_ids:
                runs_stmt = runs_stmt.where(ControlTestRun.control_id.in_(control_ids))
            else:
                runs_stmt = runs_stmt.where(ControlTestRun.id == uuid.uuid4())
            all_runs = self.db.execute(
                runs_stmt.order_by(ControlTestRun.control_id.asc(), ControlTestRun.created_at.desc())
            ).scalars().all()
            latest_runs_by_control: dict[uuid.UUID, ControlTestRun] = {}
            for run in all_runs:
                if run.control_id not in latest_runs_by_control:
                    latest_runs_by_control[run.control_id] = run

            evidence_stmt = select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.review_status == "approved",
            )
            evidence_links_by_item: dict[uuid.UUID, list[EvidenceControlLink]] = {}
            if control_ids:
                linked_ids = self.db.execute(
                    select(EvidenceControlLink.evidence_item_id)
                    .where(
                        EvidenceControlLink.organization_id == org_id,
                        EvidenceControlLink.link_status == "active",
                        EvidenceControlLink.control_id.in_(control_ids),
                    )
                    .group_by(EvidenceControlLink.evidence_item_id)
                ).scalars().all()
                evidence_stmt = evidence_stmt.where(
                    (EvidenceItem.legacy_control_id.in_(control_ids)) | (EvidenceItem.id.in_(linked_ids))
                ) if job.framework_id is not None else evidence_stmt

                evidence_link_rows = self.db.execute(
                    select(EvidenceControlLink)
                    .where(
                        EvidenceControlLink.organization_id == org_id,
                        EvidenceControlLink.link_status == "active",
                        EvidenceControlLink.control_id.in_(control_ids),
                    )
                    .order_by(EvidenceControlLink.created_at.desc())
                ).scalars().all()
            else:
                evidence_stmt = evidence_stmt.where(EvidenceItem.id == uuid.uuid4()) if job.framework_id is not None else evidence_stmt
                evidence_link_rows = []

            for link in evidence_link_rows:
                evidence_links_by_item.setdefault(link.evidence_item_id, []).append(link)

            evidence_items = self.db.execute(
                evidence_stmt.order_by(EvidenceItem.created_at.desc())
            ).scalars().all()

            risk_links_stmt = select(RiskControlLink).where(
                RiskControlLink.organization_id == org_id,
                RiskControlLink.status == "active",
            )
            if control_ids:
                risk_links_stmt = risk_links_stmt.where(RiskControlLink.control_id.in_(control_ids))
            elif job.framework_id is not None:
                risk_links_stmt = risk_links_stmt.where(RiskControlLink.id == uuid.uuid4())
            risk_links = self.db.execute(risk_links_stmt).scalars().all()
            risk_ids = {link.risk_id for link in risk_links}

            risks: list[Risk] = []
            if risk_ids:
                risks = self.db.execute(
                    select(Risk)
                    .where(
                        Risk.organization_id == org_id,
                        Risk.id.in_(risk_ids),
                        Risk.status.not_in(["closed", "resolved", "archived"]),
                    )
                    .order_by(Risk.created_at.desc())
                ).scalars().all()

            risk_links_by_risk: dict[uuid.UUID, list[RiskControlLink]] = {}
            for link in risk_links:
                risk_links_by_risk.setdefault(link.risk_id, []).append(link)

            obligation_refs_by_control: dict[uuid.UUID, str] = {}
            for obligation, control, section_ref in obligation_control_pairs:
                if control.id not in obligation_refs_by_control:
                    obligation_refs_by_control[control.id] = section_ref or obligation.reference_code or str(obligation.id)

            primary_framework = frameworks[0] if len(frameworks) == 1 else None

            if job.export_type == "ssp":
                result_json = self._build_ssp(
                    org=org,
                    framework=primary_framework,
                    controls=controls,
                    members=members,
                    obligation_control_pairs=obligation_control_pairs,
                )
            elif job.export_type == "assessment_plan":
                result_json = self._build_ap(
                    org=org,
                    framework=primary_framework,
                    obligations=obligations,
                    control_tests=control_tests,
                )
            elif job.export_type == "assessment_results":
                result_json = self._build_ar(
                    org=org,
                    framework=primary_framework,
                    obligations=obligations,
                    evidence_items=evidence_items,
                    evidence_links_by_item=evidence_links_by_item,
                    latest_runs_by_control=latest_runs_by_control,
                    tests_by_id=tests_by_id,
                    obligation_refs_by_control=obligation_refs_by_control,
                    risks=risks,
                    risk_control_links=risk_links_by_risk,
                )
            else:
                ssp = self._build_ssp(
                    org=org,
                    framework=primary_framework,
                    controls=controls,
                    members=members,
                    obligation_control_pairs=obligation_control_pairs,
                )
                ap = self._build_ap(
                    org=org,
                    framework=primary_framework,
                    obligations=obligations,
                    control_tests=control_tests,
                )
                ar = self._build_ar(
                    org=org,
                    framework=primary_framework,
                    obligations=obligations,
                    evidence_items=evidence_items,
                    evidence_links_by_item=evidence_links_by_item,
                    latest_runs_by_control=latest_runs_by_control,
                    tests_by_id=tests_by_id,
                    obligation_refs_by_control=obligation_refs_by_control,
                    risks=risks,
                    risk_control_links=risk_links_by_risk,
                )
                result_json = {
                    "oscal-complete": {
                        "system-security-plan": ssp["system-security-plan"],
                        "assessment-plan": ap["assessment-plan"],
                        "assessment-results": ar["assessment-results"],
                    }
                }

            payload_bytes = json.dumps(result_json).encode("utf-8")
            completed_at = self.utcnow()
            job.result_json = result_json
            job.result_size_bytes = len(payload_bytes)
            job.status = "complete"
            job.completed_at = completed_at
            job.error_message = None
            self.db.flush()

            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            AuditService(self.db).write_audit_log(
                action="oscal_export.job_completed",
                entity_type="oscal_export_job",
                entity_id=job.id,
                organization_id=org_id,
                actor_user_id=job.requested_by_user_id,
                after_json={
                    "status": job.status,
                    "export_type": job.export_type,
                    "framework_id": str(job.framework_id) if job.framework_id else None,
                },
                metadata_json={
                    "source": "service",
                    "export_type": job.export_type,
                    "framework_id": str(job.framework_id) if job.framework_id else None,
                    "result_size_bytes": job.result_size_bytes,
                    "duration_ms": duration_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = self.utcnow()
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="oscal_export.job_failed",
                entity_type="oscal_export_job",
                entity_id=job.id,
                organization_id=org_id,
                actor_user_id=job.requested_by_user_id,
                after_json={
                    "status": job.status,
                    "export_type": job.export_type,
                },
                metadata_json={
                    "source": "service",
                    "export_type": job.export_type,
                    "error_message": job.error_message,
                },
            )

        return job

    @staticmethod
    def _has_path(document: dict, dotted_path: str) -> bool:
        current: object = document
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return True

    def validate_oscal_structure(self, document: dict, export_type: str) -> list[str]:
        errors: list[str] = []

        required_by_type = {
            "ssp": [
                "system-security-plan.uuid",
                "system-security-plan.metadata",
                "system-security-plan.system-characteristics",
                "system-security-plan.control-implementation",
            ],
            "assessment_plan": [
                "assessment-plan.uuid",
                "assessment-plan.metadata",
                "assessment-plan.reviewed-controls",
            ],
            "assessment_results": [
                "assessment-results.uuid",
                "assessment-results.metadata",
                "assessment-results.results",
            ],
        }

        if export_type == "full_package":
            if "oscal-complete" not in document or not isinstance(document["oscal-complete"], dict):
                return ["Missing required key: oscal-complete"]

            complete_doc = document["oscal-complete"]
            for key in ["system-security-plan", "assessment-plan", "assessment-results"]:
                if key not in complete_doc:
                    errors.append(f"Missing required key: oscal-complete.{key}")

            ssp_errors = self.validate_oscal_structure(
                {"system-security-plan": complete_doc.get("system-security-plan", {})},
                "ssp",
            )
            ap_errors = self.validate_oscal_structure(
                {"assessment-plan": complete_doc.get("assessment-plan", {})},
                "assessment_plan",
            )
            ar_errors = self.validate_oscal_structure(
                {"assessment-results": complete_doc.get("assessment-results", {})},
                "assessment_results",
            )
            errors.extend(ssp_errors)
            errors.extend(ap_errors)
            errors.extend(ar_errors)
            return errors

        required_keys = required_by_type.get(export_type, [])
        for key in required_keys:
            if not self._has_path(document, key):
                errors.append(f"Missing required key: {key}")
        return errors
