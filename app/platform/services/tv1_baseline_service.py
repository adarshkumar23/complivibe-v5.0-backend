from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.compliance.services.inbound_questionnaire_service import InboundQuestionnaireService
from app.models.compliance_baseline_evidence_sync_run import ComplianceBaselineEvidenceSyncRun
from app.models.compliance_baseline_run import ComplianceBaselineRun
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.inbound_questionnaire_item import InboundQuestionnaireItem
from app.models.inbound_questionnaire_session import InboundQuestionnaireSession
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.user import User
from app.schemas.questionnaire import InboundQuestionnaireItemCreate, InboundQuestionnaireSessionCreate
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService


# GitHub endpoint references (verified July 2026):
# - Repositories list:
#   https://docs.github.com/en/rest/repos/repos#list-organization-repositories
# - Branch protection:
#   https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection
# - Dependabot alerts:
#   https://docs.github.com/en/rest/dependabot/alerts#list-dependabot-alerts-for-a-repository
# - Secret scanning alerts:
#   https://docs.github.com/en/rest/secret-scanning/secret-scanning#list-secret-scanning-alerts-for-a-repository


class TV1BaselineService:
    ROADMAP_INTEGRATIONS = [
        {"provider": "aws", "status": "roadmap", "notes": "Add IAM/S3/CloudTrail evidence auto-collection next."},
        {"provider": "okta", "status": "roadmap", "notes": "Add MFA/SSO/user lifecycle evidence auto-collection next."},
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_aware_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _require_user_in_org(self, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active organization membership required")
        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active user required")
        return user

    def _active_frameworks(self, org_id: uuid.UUID, framework_ids: list[uuid.UUID] | None) -> list[Framework]:
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
        rows = self.db.execute(stmt).scalars().all()
        if framework_ids:
            allowed = {str(v) for v in framework_ids}
            rows = [row for row in rows if str(row.id) in allowed]
        if not rows:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No active frameworks selected")
        return rows

    def _require_no_running_baseline(self, org_id: uuid.UUID) -> None:
        running_count = int(
            self.db.execute(
                select(func.count(ComplianceBaselineRun.id)).where(
                    ComplianceBaselineRun.organization_id == org_id,
                    ComplianceBaselineRun.status == "running",
                )
            ).scalar_one()
        )
        if running_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A baseline run is already in progress for this organization",
            )

    def _parse_questions_payload(self, text: str) -> list[dict]:
        cleaned = str(text).strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("\n", 1)[0]
        payload = json.loads(cleaned)
        if not isinstance(payload, list):
            raise ValueError("question payload is not a list")
        parsed: list[dict] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            question_text = str(item.get("question_text") or "").strip()
            if not question_text:
                continue
            question_type = str(item.get("question_type") or "text").strip().lower()
            if question_type not in {"yes_no", "text", "multiple_choice", "numeric"}:
                question_type = "text"
            parsed.append(
                {
                    "question_text": question_text[:2000],
                    "question_type": question_type,
                    "category_tag": str(item.get("category_tag") or "baseline").strip()[:100] or "baseline",
                    "framework_ref": str(item.get("framework_ref") or "").strip()[:255] or None,
                }
            )
        return parsed

    def _fallback_questions(self, frameworks: list[Framework]) -> list[dict]:
        framework_ids = [row.id for row in frameworks]
        obligations = self.db.execute(
            select(Obligation)
            .where(
                Obligation.framework_id.in_(framework_ids),
                Obligation.status == "active",
            )
            .order_by(Obligation.reference_code.asc())
            .limit(200)
        ).scalars().all()
        questions: list[dict] = []
        for row in obligations:
            prompt = f"What process and evidence prove compliance with {row.reference_code} ({row.title})?"
            questions.append(
                {
                    "question_text": prompt,
                    "question_type": "text",
                    "category_tag": str(row.obligation_type or "obligation")[:100],
                    "framework_ref": row.reference_code,
                }
            )
            if len(questions) >= 30:
                break
        while len(questions) < 30:
            idx = len(questions) + 1
            framework = frameworks[idx % len(frameworks)]
            questions.append(
                {
                    "question_text": f"Question {idx}: Describe current control coverage and evidence quality for {framework.name}.",
                    "question_type": "text",
                    "category_tag": "framework_coverage",
                    "framework_ref": framework.code,
                }
            )
        return questions[:30]

    def _generate_intake_questions(self, org_id: uuid.UUID, frameworks: list[Framework]) -> tuple[list[dict], str]:
        framework_context = [
            {"framework_id": str(row.id), "code": row.code, "name": row.name}
            for row in frameworks
        ]
        prompt = (
            "Generate exactly 30 compliance-baseline intake questions for this organization. "
            "Return JSON array only. Every item must include question_text, question_type, category_tag, framework_ref. "
            "question_type must be one of yes_no,text,multiple_choice,numeric. "
            f"Framework context: {framework_context}."
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a compliance onboarding analyst. Produce high-signal intake questions "
                    "that uncover control, evidence, ownership, and risk gaps quickly."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        try:
            text, provider_name, _ = AIProviderService(self.db)._run_provider_chain(
                org_id=org_id,
                messages=messages,
                failure_context="TV1 intake question generation unavailable",
            )
            parsed = self._parse_questions_payload(text)
            if len(parsed) < 30:
                raise ValueError("insufficient generated questions")
            return parsed[:30], f"ai_{provider_name}"
        except Exception:
            return self._fallback_questions(frameworks), "deterministic_fallback"

    def _github_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _github_get(self, *, base_url: str, path: str, token: str, params: dict | None = None) -> tuple[int, Any]:
        response = requests.get(
            f"{base_url.rstrip('/')}{path}",
            headers=self._github_headers(token),
            params=params,
            timeout=25,
        )
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        return response.status_code, body

    def _collect_github_evidence(
        self,
        *,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        baseline_run_id: uuid.UUID,
        owner: str,
        token: str,
        api_base_url: str | None,
        repo_limit: int,
        target_control_id: uuid.UUID | None,
    ) -> dict:
        started_at = self.utcnow()
        sync_row = ComplianceBaselineEvidenceSyncRun(
            organization_id=org_id,
            baseline_run_id=baseline_run_id,
            provider="github",
            status="running",
            collected_evidence_count=0,
            details_json={},
            started_at=started_at,
        )
        self.db.add(sync_row)
        self.db.flush()
        self.audit.write_audit_log(
            action="tv1.github_evidence_sync_started",
            entity_type="compliance_baseline_evidence_sync_run",
            entity_id=sync_row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"provider": "github", "status": sync_row.status},
            metadata_json={"source": "tv1", "baseline_run_id": str(baseline_run_id)},
        )

        base_url = api_base_url or "https://api.github.com"
        code, repos_payload = self._github_get(
            base_url=base_url,
            path=f"/orgs/{owner}/repos",
            token=token,
            params={"per_page": min(max(repo_limit, 1), 100), "sort": "updated"},
        )
        if code == 404:
            code, repos_payload = self._github_get(
                base_url=base_url,
                path=f"/users/{owner}/repos",
                token=token,
                params={"per_page": min(max(repo_limit, 1), 100), "sort": "updated"},
            )
        if code >= 400:
            sync_row.status = "failed"
            sync_row.failed_at = self.utcnow()
            sync_row.failure_reason = f"github repos request failed: {code}"
            sync_row.details_json = {"http_status": code, "error": repos_payload}
            self.db.flush()
            self.audit.write_audit_log(
                action="tv1.github_evidence_sync_failed",
                entity_type="compliance_baseline_evidence_sync_run",
                entity_id=sync_row.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={"status": sync_row.status, "failure_reason": sync_row.failure_reason},
                metadata_json={"source": "tv1", "baseline_run_id": str(baseline_run_id)},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub evidence collection failed")

        repos = repos_payload if isinstance(repos_payload, list) else []
        repos = repos[: min(max(repo_limit, 1), 100)]
        evidence_service = EvidenceService(self.db)
        if target_control_id is not None:
            evidence_service.require_control_in_org(org_id, target_control_id)

        created = 0
        repo_summaries: list[dict] = []
        for repo in repos:
            repo_name = str(repo.get("name") or "")
            if not repo_name:
                continue
            default_branch = str(repo.get("default_branch") or "main")

            branch_code, branch_protection_payload = self._github_get(
                base_url=base_url,
                path=f"/repos/{owner}/{repo_name}/branches/{default_branch}/protection",
                token=token,
            )
            has_branch_protection = branch_code == 200 and isinstance(branch_protection_payload, dict)

            dep_code, dep_payload = self._github_get(
                base_url=base_url,
                path=f"/repos/{owner}/{repo_name}/dependabot/alerts",
                token=token,
                params={"state": "open", "per_page": 100},
            )
            dependabot_open = len(dep_payload) if dep_code == 200 and isinstance(dep_payload, list) else None

            secret_code, secret_payload = self._github_get(
                base_url=base_url,
                path=f"/repos/{owner}/{repo_name}/secret-scanning/alerts",
                token=token,
                params={"state": "open", "per_page": 100},
            )
            secret_open = len(secret_payload) if secret_code == 200 and isinstance(secret_payload, list) else None

            description = (
                f"Repository {repo_name}: default branch '{default_branch}', "
                f"branch_protection={'enabled' if has_branch_protection else 'missing'}, "
                f"open_dependabot_alerts={dependabot_open if dependabot_open is not None else 'unknown'}, "
                f"open_secret_alerts={secret_open if secret_open is not None else 'unknown'}."
            )
            metadata_json = {
                "provider": "github",
                "owner": owner,
                "repository": repo_name,
                "default_branch": default_branch,
                "branch_protection_enabled": has_branch_protection,
                "open_dependabot_alerts": dependabot_open,
                "open_secret_scanning_alerts": secret_open,
                "api_base_url": base_url,
                "baseline_run_id": str(baseline_run_id),
            }
            evidence_service.create_evidence_item(
                organization_id=org_id,
                actor_user_id=actor_user_id,
                title=f"GitHub Security Snapshot: {repo_name}",
                description=description,
                evidence_type="system_export",
                source="integration",
                metadata_json=metadata_json,
                target_control_id=target_control_id,
                link_confidence="automated_high",
                link_rationale="Collected from GitHub repository security APIs during TV1 baseline run.",
                audit_metadata={"source": "tv1_github_collector", "baseline_run_id": str(baseline_run_id)},
            )
            created += 1
            repo_summaries.append(
                {
                    "repository": repo_name,
                    "default_branch": default_branch,
                    "branch_protection_enabled": has_branch_protection,
                    "open_dependabot_alerts": dependabot_open,
                    "open_secret_scanning_alerts": secret_open,
                }
            )

        sync_row.status = "completed"
        sync_row.collected_evidence_count = created
        sync_row.completed_at = self.utcnow()
        sync_row.details_json = {
            "owner": owner,
            "repo_count_scanned": len(repos),
            "evidence_items_created": created,
            "repositories": repo_summaries,
        }
        self.db.flush()
        self.audit.write_audit_log(
            action="tv1.github_evidence_collected",
            entity_type="compliance_baseline_evidence_sync_run",
            entity_id=sync_row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"repo_count_scanned": len(repos), "evidence_items_created": created},
            metadata_json={"source": "tv1"},
        )
        return sync_row.details_json

    def _compute_gap_report(
        self,
        *,
        org_id: uuid.UUID,
        baseline_run_id: uuid.UUID,
        framework_ids: list[uuid.UUID],
        intake_session_id: uuid.UUID,
    ) -> dict:
        obligations = self.db.execute(
            select(Obligation)
            .where(
                Obligation.framework_id.in_(framework_ids),
                Obligation.status == "active",
            )
        ).scalars().all()
        obligation_ids = [row.id for row in obligations]
        total_obligations = len(obligations)

        mapped_obligation_ids = set(
            self.db.execute(
                select(ControlObligationMapping.obligation_id).where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    ControlObligationMapping.obligation_id.in_(obligation_ids),
                )
            ).scalars().all()
        )

        evidence_obligation_ids = set(
            self.db.execute(
                select(ControlObligationMapping.obligation_id)
                .join(Control, Control.id == ControlObligationMapping.control_id)
                .join(EvidenceControlLink, EvidenceControlLink.control_id == Control.id)
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    ControlObligationMapping.obligation_id.in_(obligation_ids),
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status.in_(["verified", "needs_review"]),
                )
            ).scalars().all()
        )

        intake_items = self.db.execute(
            select(InboundQuestionnaireItem).where(
                InboundQuestionnaireItem.organization_id == org_id,
                InboundQuestionnaireItem.session_id == intake_session_id,
            )
        ).scalars().all()
        answered = sum(1 for row in intake_items if row.suggested_answer_text)
        needs_review = sum(1 for row in intake_items if row.status in {"needs_review", "rejected"})

        uncovered = [row for row in obligations if row.id not in evidence_obligation_ids]
        uncovered = sorted(uncovered, key=lambda row: (row.reference_code or ""))

        framework_rows = self.db.execute(
            select(Framework).where(Framework.id.in_(framework_ids))
        ).scalars().all()
        framework_by_id = {row.id: row for row in framework_rows}
        obligations_by_framework: dict[uuid.UUID, list[Obligation]] = {}
        for row in obligations:
            obligations_by_framework.setdefault(row.framework_id, []).append(row)

        framework_coverage_summary: list[dict[str, Any]] = []
        for framework_id in framework_ids:
            framework_obligations = obligations_by_framework.get(framework_id, [])
            framework_total = len(framework_obligations)
            framework_with_signal = sum(1 for row in framework_obligations if row.id in evidence_obligation_ids)
            framework_coverage_pct = (
                round((framework_with_signal / framework_total) * 100, 2) if framework_total > 0 else 0.0
            )
            framework_row = framework_by_id.get(framework_id)
            framework_coverage_summary.append(
                {
                    "framework_id": str(framework_id),
                    "framework_code": framework_row.code if framework_row else None,
                    "framework_name": framework_row.name if framework_row else None,
                    "obligations_total": framework_total,
                    "obligations_with_evidence_signal": framework_with_signal,
                    "coverage_pct": framework_coverage_pct,
                }
            )
        weakest_frameworks = sorted(
            [row for row in framework_coverage_summary if int(row["obligations_total"]) > 0],
            key=lambda row: (float(row["coverage_pct"]), str(row.get("framework_name") or "")),
        )[:3]

        latest_sync_run = self.db.execute(
            select(ComplianceBaselineEvidenceSyncRun)
            .where(
                ComplianceBaselineEvidenceSyncRun.organization_id == org_id,
                ComplianceBaselineEvidenceSyncRun.baseline_run_id == baseline_run_id,
            )
            .order_by(ComplianceBaselineEvidenceSyncRun.started_at.desc())
        ).scalars().first()
        sync_reference = None
        if latest_sync_run is not None:
            sync_reference = self._as_aware_utc(latest_sync_run.completed_at or latest_sync_run.started_at)
        now = self.utcnow()
        evidence_sync_age_hours = None
        evidence_sync_stale = False
        if sync_reference is not None:
            evidence_sync_age_hours = round(max(0.0, (now - sync_reference).total_seconds() / 3600), 2)
            evidence_sync_stale = evidence_sync_age_hours > 24

        coverage_pct = 0.0 if total_obligations == 0 else round((len(evidence_obligation_ids) / total_obligations) * 100, 2)
        if coverage_pct < 25:
            coverage_band = "critical"
        elif coverage_pct < 50:
            coverage_band = "low"
        elif coverage_pct < 80:
            coverage_band = "moderate"
        else:
            coverage_band = "high"

        context_flags: list[str] = []
        if total_obligations == 0:
            context_flags.append("no_obligations_in_scope")
        if total_obligations > 0 and len(evidence_obligation_ids) == 0:
            context_flags.append("no_evidence_signal")
        if coverage_band in {"critical", "low"} and total_obligations > 0:
            context_flags.append(f"coverage_{coverage_band}")
        if answered == 0 and intake_items:
            context_flags.append("intake_unanswered")
        elif intake_items and answered < len(intake_items):
            context_flags.append("intake_partially_answered")
        if needs_review > 0:
            context_flags.append("intake_needs_review")
        if evidence_sync_stale:
            context_flags.append("github_evidence_sync_stale")
        if any(int(row["obligations_total"]) == 0 for row in framework_coverage_summary):
            context_flags.append("framework_without_obligations")

        report = {
            "generated_at": now.isoformat(),
            "frameworks_in_scope": [str(fid) for fid in framework_ids],
            "obligations_total": total_obligations,
            "obligations_with_control_mapping": len(mapped_obligation_ids),
            "obligations_with_evidence_signal": len(evidence_obligation_ids),
            "coverage_pct": coverage_pct,
            "coverage_band": coverage_band,
            "intake_questions_total": len(intake_items),
            "intake_questions_answered": answered,
            "intake_questions_needing_review": needs_review,
            "framework_coverage_summary": framework_coverage_summary,
            "weakest_frameworks": weakest_frameworks,
            "data_freshness": {
                "evidence_sync_reference_at": sync_reference.isoformat() if sync_reference else None,
                "evidence_sync_age_hours": evidence_sync_age_hours,
                "evidence_sync_stale": evidence_sync_stale,
            },
            "context_flags": context_flags,
            "top_uncovered_obligations": [
                {
                    "obligation_id": str(row.id),
                    "reference_code": row.reference_code,
                    "title": row.title,
                    "framework_id": str(row.framework_id),
                }
                for row in uncovered[:15]
            ],
        }
        return report

    def start_24h_baseline(
        self,
        *,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        framework_ids: list[uuid.UUID] | None,
        github_payload: dict,
    ) -> ComplianceBaselineRun:
        user = self._require_user_in_org(org_id, actor_user_id)
        self._require_no_running_baseline(org_id)
        frameworks = self._active_frameworks(org_id, framework_ids)
        now = self.utcnow()

        run_row = ComplianceBaselineRun(
            organization_id=org_id,
            status="running",
            selected_framework_ids_json=[str(row.id) for row in frameworks],
            intake_session_id=None,
            integration_provider="github",
            gap_report_json={},
            started_at=now,
            created_by=actor_user_id,
        )
        self.db.add(run_row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A baseline run is already in progress for this organization",
            ) from exc
        self.audit.write_audit_log(
            action="tv1.baseline_started",
            entity_type="compliance_baseline_run",
            entity_id=run_row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"framework_count": len(frameworks), "integration_provider": "github"},
            metadata_json={"source": "onboarding"},
        )

        try:
            session = InboundQuestionnaireService(self.db).create_session(
                org_id,
                InboundQuestionnaireSessionCreate(
                    title="24-Hour Compliance Baseline Intake",
                    sender_name=user.full_name or user.email,
                    sender_email=user.email,
                    description="Auto-generated baseline questionnaire based on selected frameworks.",
                    due_date=(now + timedelta(days=1)).date(),
                ),
                created_by=actor_user_id,
            )
            questions, question_source = self._generate_intake_questions(org_id, frameworks)
            InboundQuestionnaireService(self.db).bulk_add_items(
                org_id,
                session.id,
                [InboundQuestionnaireItemCreate(**item) for item in questions],
                actor_user_id=actor_user_id,
            )
            draft_result = InboundQuestionnaireService(self.db).draft_all_items(
                org_id,
                session.id,
                actor_user_id=actor_user_id,
            )
            draft_summary = {
                "drafted": int(draft_result.get("drafted", 0)),
                "needs_review": int(draft_result.get("needs_review", 0)),
                "no_source": int(draft_result.get("no_source", 0)),
                "session_id": str(draft_result.get("session_id")),
            }

            owner = str(github_payload.get("owner") or "").strip()
            token = str(github_payload.get("token") or "").strip()
            if not owner or not token:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="github owner and token are required")
            target_control_id = github_payload.get("target_control_id")
            if isinstance(target_control_id, uuid.UUID):
                target_control_uuid = target_control_id
            elif target_control_id:
                try:
                    target_control_uuid = uuid.UUID(str(target_control_id))
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="github.target_control_id must be a valid UUID",
                    ) from exc
            else:
                target_control_uuid = None
            github_details = self._collect_github_evidence(
                org_id=org_id,
                actor_user_id=actor_user_id,
                baseline_run_id=run_row.id,
                owner=owner,
                token=token,
                api_base_url=github_payload.get("api_base_url"),
                repo_limit=int(github_payload.get("repo_limit") or 20),
                target_control_id=target_control_uuid,
            )

            gap_report = self._compute_gap_report(
                org_id=org_id,
                baseline_run_id=run_row.id,
                framework_ids=[row.id for row in frameworks],
                intake_session_id=session.id,
            )
            gap_report["intake_question_source"] = question_source
            gap_report["draft_all_summary"] = draft_summary
            gap_report["github_collection_summary"] = github_details
            gap_report["integration_roadmap"] = self.ROADMAP_INTEGRATIONS

            run_row.intake_session_id = session.id
            run_row.gap_report_json = gap_report
            run_row.status = "completed"
            run_row.completed_at = self.utcnow()
            self.db.flush()
            self.audit.write_audit_log(
                action="tv1.baseline_completed",
                entity_type="compliance_baseline_run",
                entity_id=run_row.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                after_json={
                    "intake_session_id": str(session.id),
                    "coverage_pct": gap_report.get("coverage_pct"),
                    "obligations_total": gap_report.get("obligations_total"),
                },
                metadata_json={"source": "onboarding"},
            )
            return run_row
        except Exception as exc:
            # The get_db dependency closes (and implicitly rolls back) the session on an
            # unhandled exception, so the failure record must be committed here -- otherwise
            # the failed run vanishes and callers/the audit trail lose all evidence the
            # baseline was attempted, which is the opposite of the transparency this endpoint
            # promises. Only genuine application-raised HTTPExceptions reach this branch
            # without corrupting the session, so a plain flush+commit is safe here; if the
            # session itself is unusable (a real DB error), fall back to re-raising untouched.
            try:
                run_row.status = "failed"
                run_row.failed_at = self.utcnow()
                run_row.failure_reason = (
                    str(exc.detail)[:500] if isinstance(exc, HTTPException) else str(exc)[:500]
                )
                self.db.flush()
                self.audit.write_audit_log(
                    action="tv1.baseline_failed",
                    entity_type="compliance_baseline_run",
                    entity_id=run_row.id,
                    organization_id=org_id,
                    actor_user_id=actor_user_id,
                    after_json={"failure_reason": run_row.failure_reason},
                    metadata_json={"source": "onboarding"},
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TV1 baseline run failed") from exc

    def get_baseline_run(self, *, org_id: uuid.UUID, run_id: uuid.UUID) -> ComplianceBaselineRun:
        row = self.db.execute(
            select(ComplianceBaselineRun).where(
                ComplianceBaselineRun.organization_id == org_id,
                ComplianceBaselineRun.id == run_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline run not found")
        return row

    def build_run_freshness_context(self, *, org_id: uuid.UUID, run: ComplianceBaselineRun) -> dict:
        """Compute read-time freshness signals for a baseline run snapshot.

        The gap report stored on a run is a point-in-time snapshot; this augments it with
        signals about whether that snapshot is still representative of current org state.
        """
        now = self.utcnow()
        started_at = self._as_aware_utc(run.started_at)
        run_age_hours = round(max(0.0, (now - started_at).total_seconds() / 3600), 2) if started_at else None

        latest_run = self.db.execute(
            select(ComplianceBaselineRun)
            .where(
                ComplianceBaselineRun.organization_id == org_id,
                ComplianceBaselineRun.status == "completed",
            )
            .order_by(ComplianceBaselineRun.completed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        is_latest_completed_run = bool(
            run.status == "completed" and latest_run is not None and latest_run.id == run.id
        )
        superseded_by_run_id = (
            latest_run.id if (run.status == "completed" and latest_run is not None and latest_run.id != run.id) else None
        )

        context_flags: list[str] = list((run.gap_report_json or {}).get("context_flags") or [])
        obligations_changed_since_run = False

        if run.status == "completed":
            framework_ids_raw = run.gap_report_json.get("frameworks_in_scope") if run.gap_report_json else None
            framework_ids: list[uuid.UUID] = []
            for value in framework_ids_raw or []:
                try:
                    framework_ids.append(uuid.UUID(str(value)))
                except (ValueError, TypeError):
                    continue
            if framework_ids:
                current_obligations_total = int(
                    self.db.execute(
                        select(func.count(Obligation.id)).where(
                            Obligation.framework_id.in_(framework_ids),
                            Obligation.status == "active",
                        )
                    ).scalar_one()
                    or 0
                )
                snapshot_total = int((run.gap_report_json or {}).get("obligations_total") or 0)
                if current_obligations_total != snapshot_total:
                    obligations_changed_since_run = True
                    context_flags.append("obligations_changed_since_generation")

            completed_at = self._as_aware_utc(run.completed_at)
            if completed_at is not None and (now - completed_at) > timedelta(hours=24):
                context_flags.append("run_snapshot_older_than_24h")
            if superseded_by_run_id is not None:
                context_flags.append("superseded_by_newer_run")

        if run.status == "failed":
            context_flags.append("run_failed")
        if run.status == "running" and run_age_hours is not None and run_age_hours > 2:
            context_flags.append("run_taking_longer_than_expected")

        return {
            "run_age_hours": run_age_hours,
            "is_latest_completed_run": is_latest_completed_run,
            "superseded_by_run_id": superseded_by_run_id,
            "obligations_changed_since_generation": obligations_changed_since_run,
            "context_flags": sorted(set(context_flags)),
        }
