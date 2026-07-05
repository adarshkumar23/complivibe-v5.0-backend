from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_system_service import AISystemService
from app.models.atlas_technique import AtlasTechnique
from app.services.audit_service import AuditService


ATLAS_TACTICS: list[str] = [
    "ATLAS-RECON",
    "ATLAS-RD",
    "ATLAS-IA",
    "ATLAS-ML-ATK",
    "ATLAS-EXFIL",
    "ATLAS-IMPACT",
]

ATLAS_TECHNIQUE_SEED: list[dict[str, object]] = [
    {
        "atlas_id": "AML.T0000",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RECON",
        "name": "Search for Victim's Publicly Available ML Artifacts",
        "description": "Adversaries search for ML artifacts exposed publicly on model hubs, repos, or docs.",
        "is_subtechnique": False,
        "mitigations": [
            "Audit public model repositories",
            "Remove sensitive artifacts from public repos",
            "Monitor model hub for unauthorized uploads",
        ],
        "detection_signals": ["Unusual download patterns from model hubs", "Scraping of ML documentation"],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0000.000",
        "parent_atlas_id": "AML.T0000",
        "tactic_code": "ATLAS-RECON",
        "name": "Search Hugging Face",
        "description": "Search Hugging Face Hub for target organization models.",
        "is_subtechnique": True,
        "mitigations": [],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0001",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RECON",
        "name": "Search Victim-Owned Websites",
        "description": "Adversaries enumerate victim websites for clues about AI systems in use.",
        "is_subtechnique": False,
        "mitigations": ["Limit public disclosure of AI capabilities", "Review job postings for AI stack disclosure"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "low",
    },
    {
        "atlas_id": "AML.T0002",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RECON",
        "name": "Search Application Repositories",
        "description": "Search repos for ML code, configs, and accidentally committed model artifacts.",
        "is_subtechnique": False,
        "mitigations": ["Secret scanning in CI/CD", "Pre-commit hooks to detect model artifacts", "Regular audit of public repos"],
        "detection_signals": ["Cloning of AI repos", "Enumeration of org repositories"],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0007",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RD",
        "name": "Acquire Public ML Artifacts",
        "description": "Download public models or datasets to build attack capabilities.",
        "is_subtechnique": False,
        "mitigations": ["Monitor for use of public models as attack proxies"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0008",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RD",
        "name": "Develop Capabilities",
        "description": "Build custom ML attack tools including adversarial generators and extraction frameworks.",
        "is_subtechnique": False,
        "mitigations": ["Adversarial robustness testing", "Input validation at inference endpoints"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0017",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-RD",
        "name": "Develop Adversarial ML Attack Capabilities",
        "description": "Develop or adapt adversarial ML attack tools for white-box or black-box attacks.",
        "is_subtechnique": False,
        "mitigations": ["Adversarial training", "Input preprocessing defenses"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0010",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IA",
        "name": "ML Supply Chain Compromise",
        "description": "Compromise ML supply chains via malicious models, poisoned datasets, or compromised frameworks.",
        "is_subtechnique": False,
        "mitigations": ["Verify model provenance", "Sign and verify model artifacts", "SBOM for ML dependencies"],
        "detection_signals": ["Unexpected model behavior post-update", "Hash mismatch on model files"],
        "case_studies": ["SolarWinds-style ML pipeline compromise scenario"],
        "severity_indicator": "critical",
    },
    {
        "atlas_id": "AML.T0010.000",
        "parent_atlas_id": "AML.T0010",
        "tactic_code": "ATLAS-IA",
        "name": "Publish Poisoned Datasets to Public Repositories",
        "description": "Upload poisoned training datasets to public repositories for downstream victims.",
        "is_subtechnique": True,
        "mitigations": [],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "critical",
    },
    {
        "atlas_id": "AML.T0010.001",
        "parent_atlas_id": "AML.T0010",
        "tactic_code": "ATLAS-IA",
        "name": "Inject Malicious Code into ML Tools and Frameworks",
        "description": "Introduce malicious code in ML framework packages that activates during training or inference.",
        "is_subtechnique": True,
        "mitigations": [],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "critical",
    },
    {
        "atlas_id": "AML.T0011",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IA",
        "name": "User Execution",
        "description": "Rely on user execution of malicious ML artifacts.",
        "is_subtechnique": False,
        "mitigations": ["Avoid pickle for model storage", "Use safetensors format", "Sandbox model loading"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0012",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IA",
        "name": "Valid Accounts",
        "description": "Use compromised credentials to access ML platforms and registries.",
        "is_subtechnique": False,
        "mitigations": ["MFA on ML platforms", "Privileged access management", "Audit ML platform access logs"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0019",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-ML-ATK",
        "name": "Publish Poisoned Datasets",
        "description": "Introduce poisoned data to cause model misbehavior at inference time.",
        "is_subtechnique": False,
        "mitigations": ["Data provenance tracking", "Statistical anomaly detection on datasets", "Dataset versioning and signing"],
        "detection_signals": ["Unusual data distributions", "Unexpected model behavior after retraining"],
        "case_studies": ["ImageNet poisoning research", "NLP backdoor attacks via data poisoning"],
        "severity_indicator": "critical",
    },
    {
        "atlas_id": "AML.T0020",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-ML-ATK",
        "name": "Backdoor ML Model",
        "description": "Insert a backdoor trigger so the model misclassifies when a specific pattern appears.",
        "is_subtechnique": False,
        "mitigations": ["Neural cleanse", "Activation clustering", "Model inspection before deployment"],
        "detection_signals": ["Trigger pattern analysis", "Anomalous accuracy on specific inputs"],
        "case_studies": ["BadNets research paper", "Trojan attack on neural networks"],
        "severity_indicator": "critical",
    },
    {
        "atlas_id": "AML.T0040",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-ML-ATK",
        "name": "ML Model Inference API Access",
        "description": "Gain access to inference APIs for probing and attacks via repeated queries.",
        "is_subtechnique": False,
        "mitigations": ["API authentication", "Rate limiting on inference endpoints", "Query logging and anomaly detection"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0043",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-ML-ATK",
        "name": "Craft Adversarial Data",
        "description": "Create adversarial inputs causing misclassification in white-box and black-box settings.",
        "is_subtechnique": False,
        "mitigations": ["Adversarial training", "Certified defenses", "Input preprocessing"],
        "detection_signals": ["Statistical anomalies in input distributions", "High-frequency similar queries"],
        "case_studies": ["Stop sign adversarial patches", "Spam filter evasion attacks"],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0043.000",
        "parent_atlas_id": "AML.T0043",
        "tactic_code": "ATLAS-ML-ATK",
        "name": "White-Box Attack",
        "description": "Craft adversarial examples with full model architecture and weight knowledge.",
        "is_subtechnique": True,
        "mitigations": [],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0043.001",
        "parent_atlas_id": "AML.T0043",
        "tactic_code": "ATLAS-ML-ATK",
        "name": "Black-Box Attack",
        "description": "Craft adversarial examples by repeated queries without model internals.",
        "is_subtechnique": True,
        "mitigations": [],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "medium",
    },
    {
        "atlas_id": "AML.T0024",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-EXFIL",
        "name": "Exfiltration via ML Inference API",
        "description": "Extract model information through systematic API queries (model extraction).",
        "is_subtechnique": False,
        "mitigations": ["Rate limiting on inference API", "Output perturbation", "Query monitoring and anomaly detection"],
        "detection_signals": ["High volume systematic queries", "Unusual input patterns", "Coverage-seeking query distribution"],
        "case_studies": ["Model stealing attacks on commercial ML APIs"],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0025",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-EXFIL",
        "name": "Model Inversion",
        "description": "Reconstruct training data or private information from model outputs.",
        "is_subtechnique": False,
        "mitigations": ["Differential privacy in training", "Output perturbation", "Membership inference defenses"],
        "detection_signals": [],
        "case_studies": ["Face recognition model inversion", "Medical data reconstruction from model"],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0035",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-EXFIL",
        "name": "ML Artifact Collection",
        "description": "Collect model weights, configs, and training data for exfiltration.",
        "is_subtechnique": False,
        "mitigations": ["Encrypt model artifacts at rest", "DLP controls on model files", "Monitor unusual file access patterns"],
        "detection_signals": [],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0029",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IMPACT",
        "name": "Denial of ML Service",
        "description": "Deny availability of ML systems via exhaustion, adversarial input, or degradation.",
        "is_subtechnique": False,
        "mitigations": ["Input validation and filtering", "Rate limiting", "Model redundancy", "Graceful degradation design"],
        "detection_signals": ["Response time anomalies", "Error rate spikes", "Resource utilization alerts"],
        "case_studies": [],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0031",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IMPACT",
        "name": "Evade ML Model",
        "description": "Cause ML-based detection systems to classify malicious inputs as benign.",
        "is_subtechnique": False,
        "mitigations": ["Ensemble detection", "Behavioral analysis alongside ML", "Continuous model retraining"],
        "detection_signals": [],
        "case_studies": ["Malware evasion of ML AV", "Network IDS evasion"],
        "severity_indicator": "high",
    },
    {
        "atlas_id": "AML.T0048",
        "parent_atlas_id": None,
        "tactic_code": "ATLAS-IMPACT",
        "name": "Erode ML Model Integrity",
        "description": "Gradually degrade model performance over time through poisoning, drift exploitation, or continuous adversarial input.",
        "is_subtechnique": False,
        "mitigations": ["Continuous model monitoring", "Data quality checks in production", "Model versioning and rollback"],
        "detection_signals": ["Gradual accuracy decline", "Distribution shift in inputs", "Increasing error rates over time"],
        "case_studies": [],
        "severity_indicator": "high",
    },
]


class AtlasAssessmentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _ensure_seed_data(self) -> None:
        count = self.db.execute(select(func.count(AtlasTechnique.id))).scalar_one()
        if int(count) > 0:
            return

        by_atlas_id: dict[str, AtlasTechnique] = {}
        for item in ATLAS_TECHNIQUE_SEED:
            parent_atlas_id = item["parent_atlas_id"]
            parent_id = by_atlas_id[str(parent_atlas_id)].id if parent_atlas_id else None
            row = AtlasTechnique(
                atlas_id=str(item["atlas_id"]),
                parent_id=parent_id,
                tactic_code=str(item["tactic_code"]),
                name=str(item["name"]),
                description=str(item["description"]),
                is_subtechnique=bool(item["is_subtechnique"]),
                mitigations=list(item["mitigations"]),
                detection_signals=list(item["detection_signals"]),
                case_studies=list(item["case_studies"]),
                severity_indicator=str(item["severity_indicator"]),
            )
            self.db.add(row)
            self.db.flush()
            by_atlas_id[row.atlas_id] = row

    def list_techniques(
        self,
        tactic_code: str | None = None,
        include_subtechniques: bool = True,
    ) -> list[AtlasTechnique]:
        self._ensure_seed_data()
        stmt = select(AtlasTechnique)
        if tactic_code:
            stmt = stmt.where(AtlasTechnique.tactic_code == tactic_code)
        if not include_subtechniques:
            stmt = stmt.where(AtlasTechnique.is_subtechnique.is_(False))
        return self.db.execute(stmt.order_by(AtlasTechnique.atlas_id.asc())).scalars().all()

    def get_techniques_by_tactic(
        self,
        tactic_code: str,
        include_subtechniques: bool = True,
    ) -> list[AtlasTechnique]:
        self._ensure_seed_data()
        stmt = select(AtlasTechnique).where(AtlasTechnique.tactic_code == tactic_code)
        if not include_subtechniques:
            stmt = stmt.where(AtlasTechnique.is_subtechnique.is_(False))
        return self.db.execute(stmt.order_by(AtlasTechnique.atlas_id.asc())).scalars().all()

    def get_technique(self, technique_id: uuid.UUID) -> AtlasTechnique:
        self._ensure_seed_data()
        row = self.db.execute(select(AtlasTechnique).where(AtlasTechnique.id == technique_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATLAS technique not found")
        return row

    def tactics_summary(self) -> list[dict[str, object]]:
        self._ensure_seed_data()
        counts = {
            row[0]: int(row[1])
            for row in self.db.execute(
                select(AtlasTechnique.tactic_code, func.count(AtlasTechnique.id)).group_by(AtlasTechnique.tactic_code)
            ).all()
        }
        return [{"tactic_code": tactic, "technique_count": counts.get(tactic, 0)} for tactic in ATLAS_TACTICS]

    def assess_system_exposure(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
    ) -> dict:
        system = AISystemService(self.db).get_system(org_id, system_id)

        exposure: dict[str, dict[str, int]] = {}
        for tactic in ATLAS_TACTICS:
            techniques = self.get_techniques_by_tactic(tactic, include_subtechniques=False)
            critical_count = sum(1 for item in techniques if item.severity_indicator == "critical")
            high_count = sum(1 for item in techniques if item.severity_indicator == "high")
            exposure[tactic] = {
                "technique_count": len(techniques),
                "critical": critical_count,
                "high": high_count,
                "risk_score": critical_count * 10 + high_count * 5,
            }

        total_score = sum(item["risk_score"] for item in exposure.values())
        if total_score >= 60:
            risk_level = "critical"
        elif total_score >= 30:
            risk_level = "high"
        elif total_score >= 15:
            risk_level = "medium"
        else:
            risk_level = "low"

        system.atlas_risk_score = total_score
        self.db.flush()

        assessment_event = {
            "total_risk_score": total_score,
            "risk_level": risk_level,
            "tactic_scores": {tactic: values["risk_score"] for tactic, values in exposure.items()},
        }
        AIGovernanceEventService.log(
            self.db,
            org_id,
            "atlas.assessment_completed",
            actor_type="system",
            ai_system_id=system_id,
            event_data=assessment_event,
        )
        AuditService(self.db).write_audit_log(
            action="atlas.assessment_completed",
            entity_type="ai_system",
            entity_id=system_id,
            organization_id=org_id,
            after_json=assessment_event,
            metadata_json={"source": "atlas_assessment"},
        )

        return {
            "system_id": str(system_id),
            "system_name": system.name,
            "tactic_exposure": exposure,
            "total_risk_score": total_score,
            "risk_level": risk_level,
            "assessed_at": self.utcnow().isoformat(),
        }

    def get_mitigations_for_system(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
    ) -> dict:
        self._ensure_seed_data()
        AISystemService(self.db).get_system(org_id, system_id)

        all_techniques = self.db.execute(select(AtlasTechnique).where(AtlasTechnique.is_subtechnique.is_(False))).scalars().all()

        all_mitigations: set[str] = set()
        for tech in all_techniques:
            for mitigation in (tech.mitigations or []):
                all_mitigations.add(str(mitigation))

        by_tactic: dict[str, list[str]] = {}
        for tactic in ATLAS_TACTICS:
            tactic_mitigations: set[str] = set()
            for tech in all_techniques:
                if tech.tactic_code != tactic:
                    continue
                for mitigation in (tech.mitigations or []):
                    tactic_mitigations.add(str(mitigation))
            by_tactic[tactic] = sorted(tactic_mitigations)

        return {
            "system_id": str(system_id),
            "total_mitigations": len(all_mitigations),
            "mitigations": sorted(all_mitigations),
            "by_tactic": by_tactic,
        }
