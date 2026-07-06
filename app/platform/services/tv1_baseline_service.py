from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from fastapi import HTTPException, status
from sqlalchemy import func, select
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
            .order_by(Obligation.criticality.desc(), Obligation.reference_code.asc())
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
        uncovered = sorted(uncovered, key=lambda row: (row.criticality or "", row.reference_code or ""), reverse=True)

        coverage_pct = 0.0 if total_obligations == 0 else round((len(evidence_obligation_ids) / total_obligations) * 100, 2)
        report = {
            "generated_at": self.utcnow().isoformat(),
            "frameworks_in_scope": [str(fid) for fid in framework_ids],
            "obligations_total": total_obligations,
            "obligations_with_control_mapping": len(mapped_obligation_ids),
            "obligations_with_evidence_signal": len(evidence_obligation_ids),
            "coverage_pct": coverage_pct,
            "intake_questions_total": len(intake_items),
            "intake_questions_answered": answered,
            "intake_questions_needing_review": needs_review,
            "top_uncovered_obligations": [
                {
                    "obligation_id": str(row.id),
                    "reference_code": row.reference_code,
                    "title": row.title,
                    "criticality": row.criticality,
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
        self.db.flush()
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
                target_control_uuid = uuid.UUID(str(target_control_id))
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
            run_row.status = "failed"
            run_row.failed_at = self.utcnow()
            run_row.failure_reason = str(exc)[:500]
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
