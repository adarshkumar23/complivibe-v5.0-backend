from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bcm import BusinessProcess
from app.models.crisis_management import CrisisActivation, CrisisPlaybook
from app.models.risk import Risk

# Keyword map used to tighten the risk cross-reference for a given crisis
# scenario_type: any risk whose category/title/description case-insensitively
# contains one of these keywords is considered scenario-relevant.
SCENARIO_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cyber_incident": ("cyber", "security", "data", "breach", "ransomware", "malware"),
    "natural_disaster": ("disaster", "natural", "weather", "flood", "earthquake", "climate"),
    "pandemic": ("pandemic", "health", "epidemic", "workforce"),
    "financial_crisis": ("financial", "liquidity", "credit", "market", "solvency"),
    "supply_chain_disruption": ("supply", "vendor", "third party", "third-party", "logistics", "concentration"),
    "data_breach": ("data", "breach", "privacy", "security", "cyber"),
    "regulatory_action": ("regulatory", "compliance", "legal", "sanction", "fine"),
    "reputational_crisis": ("reputation", "brand", "media", "public relations"),
    "other": (),
}

# Risk statuses considered "open"/active per repo convention (mirrors
# app/services/risk_service.py's open-risk filtering).
OPEN_RISK_STATUSES = ("identified", "assessing", "treatment_planned", "in_treatment", "monitored")

RELEVANT_PROCESS_TIERS = ("tier_1_critical", "tier_2_high")


class CrisisManagementService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Playbooks
    # ------------------------------------------------------------------
    def create_playbook(
        self, organization_id: uuid.UUID, *, data: dict, created_by_user_id: uuid.UUID | None
    ) -> CrisisPlaybook:
        playbook = CrisisPlaybook(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            **data,
        )
        self.db.add(playbook)
        self.db.flush()
        return playbook

    def get_playbook(self, organization_id: uuid.UUID, playbook_id: uuid.UUID) -> CrisisPlaybook:
        playbook = self.db.execute(
            select(CrisisPlaybook).where(
                CrisisPlaybook.id == playbook_id, CrisisPlaybook.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if playbook is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crisis playbook not found in this organization")
        return playbook

    def list_playbooks(self, organization_id: uuid.UUID) -> list[CrisisPlaybook]:
        return list(
            self.db.execute(
                select(CrisisPlaybook)
                .where(CrisisPlaybook.organization_id == organization_id)
                .order_by(CrisisPlaybook.created_at.desc())
            ).scalars()
        )

    def update_playbook(self, organization_id: uuid.UUID, playbook_id: uuid.UUID, *, data: dict) -> CrisisPlaybook:
        playbook = self.get_playbook(organization_id, playbook_id)
        for key, value in data.items():
            setattr(playbook, key, value)
        self.db.flush()
        return playbook

    # ------------------------------------------------------------------
    # Cross-referencing helpers
    # ------------------------------------------------------------------
    def _find_relevant_processes(self, organization_id: uuid.UUID, playbook: CrisisPlaybook) -> list[dict]:
        processes = list(
            self.db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.organization_id == organization_id,
                    BusinessProcess.status == "active",
                    BusinessProcess.criticality_tier.in_(RELEVANT_PROCESS_TIERS),
                )
            ).scalars()
        )

        snapshot = [
            {
                "process_id": str(process.id),
                "name": process.name,
                "criticality_tier": process.criticality_tier,
            }
            for process in processes
        ]
        return snapshot

    def _find_relevant_risks(self, organization_id: uuid.UUID, playbook: CrisisPlaybook) -> list[dict]:
        risks = list(
            self.db.execute(
                select(Risk).where(
                    Risk.organization_id == organization_id,
                    Risk.status.in_(OPEN_RISK_STATUSES),
                )
            ).scalars()
        )

        keywords = SCENARIO_RISK_KEYWORDS.get(playbook.scenario_type, ())
        selected: dict[uuid.UUID, Risk] = {}
        for risk in risks:
            haystack = " ".join(
                filter(None, [risk.category, risk.title, risk.description])
            ).lower()
            keyword_match = any(keyword in haystack for keyword in keywords)
            top_severity = risk.severity in ("critical", "high")
            if keyword_match or top_severity:
                selected[risk.id] = risk

        snapshot = [
            {
                "risk_id": str(risk.id),
                "title": risk.title,
                "severity": risk.severity,
            }
            for risk in selected.values()
        ]
        return snapshot

    # ------------------------------------------------------------------
    # Activations
    # ------------------------------------------------------------------
    def activate_playbook(
        self, organization_id: uuid.UUID, playbook_id: uuid.UUID, *, activated_by_user_id: uuid.UUID | None
    ) -> CrisisActivation:
        playbook = self.get_playbook(organization_id, playbook_id)
        if playbook.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot activate a playbook with status '{playbook.status}'; only 'active' playbooks may be activated",
            )

        activation = CrisisActivation(
            organization_id=organization_id,
            playbook_id=playbook.id,
            activated_by_user_id=activated_by_user_id,
            status="active",
            linked_processes_json=self._find_relevant_processes(organization_id, playbook),
            linked_risks_json=self._find_relevant_risks(organization_id, playbook),
        )
        self.db.add(activation)
        self.db.flush()
        return activation

    def get_activation(self, organization_id: uuid.UUID, activation_id: uuid.UUID) -> CrisisActivation:
        activation = self.db.execute(
            select(CrisisActivation).where(
                CrisisActivation.id == activation_id, CrisisActivation.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if activation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crisis activation not found in this organization")
        return activation

    def resolve_activation(
        self,
        organization_id: uuid.UUID,
        activation_id: uuid.UUID,
        *,
        resolved_by_user_id: uuid.UUID | None,
        resolution_notes: str | None,
    ) -> CrisisActivation:
        activation = self.get_activation(organization_id, activation_id)
        if activation.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resolve an activation with status '{activation.status}'; only 'active' activations may be resolved",
            )
        activation.status = "resolved"
        activation.resolved_at = datetime.now(timezone.utc)
        activation.resolved_by_user_id = resolved_by_user_id
        activation.resolution_notes = resolution_notes
        self.db.flush()
        return activation

    def list_active_activations(self, organization_id: uuid.UUID) -> list[CrisisActivation]:
        return list(
            self.db.execute(
                select(CrisisActivation)
                .where(CrisisActivation.organization_id == organization_id, CrisisActivation.status == "active")
                .order_by(CrisisActivation.activated_at.desc())
            ).scalars()
        )
