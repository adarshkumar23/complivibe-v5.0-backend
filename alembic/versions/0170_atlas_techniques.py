"""atlas techniques

Revision ID: 0170_atlas_techniques
Revises: 0169_secure_report_sharing
Create Date: 2026-06-29 08:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0170_atlas_techniques"
down_revision: str | None = "0169_secure_report_sharing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _seed_atlas_techniques(bind: sa.Connection) -> None:
    rows: list[dict[str, object]] = [
        {
            "atlas_id": "AML.T0000",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-RECON",
            "name": "Search for Victim's Publicly Available ML Artifacts",
            "description": "Adversaries search for ML artifacts (weights, datasets, configs) exposed publicly on model hubs, code repos, or documentation.",
            "is_subtechnique": False,
            "mitigations": [
                "Audit public model repositories",
                "Remove sensitive artifacts from public repos",
                "Monitor model hub for unauthorized uploads",
            ],
            "detection_signals": [
                "Unusual download patterns from model hubs",
                "Scraping of ML documentation",
            ],
            "case_studies": [],
            "severity_indicator": "medium",
        },
        {
            "atlas_id": "AML.T0000.000",
            "parent_atlas_id": "AML.T0000",
            "tactic_code": "ATLAS-RECON",
            "name": "Search Hugging Face",
            "description": "Search Hugging Face Hub for target organization's uploaded models.",
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
            "mitigations": [
                "Limit public disclosure of AI capabilities",
                "Review job postings for AI stack disclosure",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "low",
        },
        {
            "atlas_id": "AML.T0002",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-RECON",
            "name": "Search Application Repositories",
            "description": "Search GitHub/GitLab for target organization's ML code, configs, and accidentally committed model artifacts.",
            "is_subtechnique": False,
            "mitigations": [
                "Secret scanning in CI/CD",
                "Pre-commit hooks to detect model artifacts",
                "Regular audit of public repos",
            ],
            "detection_signals": [
                "Cloning of AI repos",
                "Enumeration of org repositories",
            ],
            "case_studies": [],
            "severity_indicator": "medium",
        },
        {
            "atlas_id": "AML.T0007",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-RD",
            "name": "Acquire Public ML Artifacts",
            "description": "Download publicly available foundation models or datasets to build attack capabilities against victim systems.",
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
            "description": "Build custom ML attack tools including adversarial example generators and model extraction frameworks.",
            "is_subtechnique": False,
            "mitigations": [
                "Adversarial robustness testing",
                "Input validation at inference endpoints",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0017",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-RD",
            "name": "Develop Adversarial ML Attack Capabilities",
            "description": "Specifically develop or adapt adversarial machine learning attack tools for white-box or black-box attacks.",
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
            "description": "Compromise ML supply chain through malicious models, poisoned datasets, or compromised ML frameworks/libraries.",
            "is_subtechnique": False,
            "mitigations": [
                "Verify model provenance",
                "Sign and verify model artifacts",
                "SBOM for ML dependencies",
            ],
            "detection_signals": [
                "Unexpected model behavior post-update",
                "Hash mismatch on model files",
            ],
            "case_studies": ["SolarWinds-style ML pipeline compromise scenario"],
            "severity_indicator": "critical",
        },
        {
            "atlas_id": "AML.T0010.000",
            "parent_atlas_id": "AML.T0010",
            "tactic_code": "ATLAS-IA",
            "name": "Publish Poisoned Datasets to Public Repositories",
            "description": "Upload poisoned training datasets to public data repositories knowing targets will incorporate them into training.",
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
            "description": "Introduce malicious code into ML framework packages (PyPI, conda) that activates during model training or inference.",
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
            "description": "Adversary relies on user to execute malicious ML artifact (e.g. loading a pickled model that executes code).",
            "is_subtechnique": False,
            "mitigations": [
                "Avoid pickle for model storage",
                "Use safetensors format",
                "Sandbox model loading",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0012",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-IA",
            "name": "Valid Accounts",
            "description": "Use compromised credentials to access ML platforms, model registries, and training infrastructure.",
            "is_subtechnique": False,
            "mitigations": [
                "MFA on ML platforms",
                "Privileged access management",
                "Audit ML platform access logs",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0019",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-ML-ATK",
            "name": "Publish Poisoned Datasets",
            "description": "Introduce poisoned data into the training pipeline to cause model misbehavior at inference time.",
            "is_subtechnique": False,
            "mitigations": [
                "Data provenance tracking",
                "Statistical anomaly detection on datasets",
                "Dataset versioning and signing",
            ],
            "detection_signals": [
                "Unusual data distributions",
                "Unexpected model behavior after retraining",
            ],
            "case_studies": [
                "ImageNet poisoning research",
                "NLP backdoor attacks via data poisoning",
            ],
            "severity_indicator": "critical",
        },
        {
            "atlas_id": "AML.T0020",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-ML-ATK",
            "name": "Backdoor ML Model",
            "description": "Insert a backdoor trigger into an ML model so it misclassifies when a specific input pattern is present.",
            "is_subtechnique": False,
            "mitigations": [
                "Neural cleanse",
                "Activation clustering",
                "Model inspection before deployment",
            ],
            "detection_signals": [
                "Trigger pattern analysis",
                "Anomalous accuracy on specific inputs",
            ],
            "case_studies": [
                "BadNets research paper",
                "Trojan attack on neural networks",
            ],
            "severity_indicator": "critical",
        },
        {
            "atlas_id": "AML.T0040",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-ML-ATK",
            "name": "ML Model Inference API Access",
            "description": "Gain access to victim's ML inference API to probe and attack the model through repeated queries.",
            "is_subtechnique": False,
            "mitigations": [
                "API authentication",
                "Rate limiting on inference endpoints",
                "Query logging and anomaly detection",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "medium",
        },
        {
            "atlas_id": "AML.T0043",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-ML-ATK",
            "name": "Craft Adversarial Data",
            "description": "Create input samples specifically engineered to cause model misclassification. Includes white-box (gradient-based) and black-box attacks.",
            "is_subtechnique": False,
            "mitigations": ["Adversarial training", "Certified defenses", "Input preprocessing"],
            "detection_signals": [
                "Statistical anomalies in input distributions",
                "High-frequency similar queries",
            ],
            "case_studies": ["Stop sign adversarial patches", "Spam filter evasion attacks"],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0043.000",
            "parent_atlas_id": "AML.T0043",
            "tactic_code": "ATLAS-ML-ATK",
            "name": "White-Box Attack",
            "description": "Craft adversarial examples using full knowledge of model architecture and weights (FGSM, PGD attacks).",
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
            "description": "Craft adversarial examples through repeated queries without access to model internals.",
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
            "description": "Extract model information through systematic API queries to reconstruct the model (model extraction/stealing).",
            "is_subtechnique": False,
            "mitigations": [
                "Rate limiting on inference API",
                "Output perturbation",
                "Query monitoring and anomaly detection",
            ],
            "detection_signals": [
                "High volume systematic queries",
                "Unusual input patterns",
                "Coverage-seeking query distribution",
            ],
            "case_studies": ["Model stealing attacks on commercial ML APIs"],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0025",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-EXFIL",
            "name": "Model Inversion",
            "description": "Use model queries to reconstruct training data or extract private information encoded in model parameters.",
            "is_subtechnique": False,
            "mitigations": [
                "Differential privacy in training",
                "Output perturbation",
                "Membership inference defenses",
            ],
            "detection_signals": [],
            "case_studies": [
                "Face recognition model inversion",
                "Medical data reconstruction from model",
            ],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0035",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-EXFIL",
            "name": "ML Artifact Collection",
            "description": "Collect ML artifacts from victim systems including model weights, configs, and training data for exfiltration.",
            "is_subtechnique": False,
            "mitigations": [
                "Encrypt model artifacts at rest",
                "DLP controls on model files",
                "Monitor unusual file access patterns",
            ],
            "detection_signals": [],
            "case_studies": [],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0029",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-IMPACT",
            "name": "Denial of ML Service",
            "description": "Degrade or deny availability of ML systems through resource exhaustion, adversarial inputs, or model degradation.",
            "is_subtechnique": False,
            "mitigations": [
                "Input validation and filtering",
                "Rate limiting",
                "Model redundancy",
                "Graceful degradation design",
            ],
            "detection_signals": [
                "Response time anomalies",
                "Error rate spikes",
                "Resource utilization alerts",
            ],
            "case_studies": [],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0031",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-IMPACT",
            "name": "Evade ML Model",
            "description": "Cause ML-based detection or classification systems to misclassify malicious inputs as benign.",
            "is_subtechnique": False,
            "mitigations": [
                "Ensemble detection",
                "Behavioral analysis alongside ML",
                "Continuous model retraining",
            ],
            "detection_signals": [],
            "case_studies": ["Malware evasion of ML AV", "Network IDS evasion"],
            "severity_indicator": "high",
        },
        {
            "atlas_id": "AML.T0048",
            "parent_atlas_id": None,
            "tactic_code": "ATLAS-IMPACT",
            "name": "Erode ML Model Integrity",
            "description": "Gradually degrade ML model performance over time through data poisoning, concept drift exploitation, or continuous adversarial input.",
            "is_subtechnique": False,
            "mitigations": [
                "Continuous model monitoring",
                "Data quality checks in production",
                "Model versioning and rollback",
            ],
            "detection_signals": [
                "Gradual accuracy decline",
                "Distribution shift in inputs",
                "Increasing error rates over time",
            ],
            "case_studies": [],
            "severity_indicator": "high",
        },
    ]

    stmt = sa.text(
        """
        INSERT INTO atlas_techniques (
            atlas_id,
            parent_id,
            tactic_code,
            name,
            description,
            is_subtechnique,
            mitigations,
            detection_signals,
            case_studies,
            severity_indicator
        ) VALUES (
            :atlas_id,
            (SELECT id FROM atlas_techniques WHERE atlas_id = :parent_atlas_id),
            :tactic_code,
            :name,
            :description,
            :is_subtechnique,
            CAST(:mitigations AS jsonb),
            CAST(:detection_signals AS jsonb),
            CAST(:case_studies AS jsonb),
            :severity_indicator
        )
        ON CONFLICT (atlas_id) DO NOTHING
        """
    )

    import json

    for row in rows:
        bind.execute(
            stmt,
            {
                "atlas_id": row["atlas_id"],
                "parent_atlas_id": row["parent_atlas_id"],
                "tactic_code": row["tactic_code"],
                "name": row["name"],
                "description": row["description"],
                "is_subtechnique": row["is_subtechnique"],
                "mitigations": json.dumps(row["mitigations"]),
                "detection_signals": json.dumps(row["detection_signals"]),
                "case_studies": json.dumps(row["case_studies"]),
                "severity_indicator": row["severity_indicator"],
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "atlas_techniques"):
        op.create_table(
            "atlas_techniques",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("atlas_id", sa.String(length=20), nullable=False, unique=True),
            sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("atlas_techniques.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tactic_code", sa.String(length=30), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("is_subtechnique", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("mitigations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("detection_signals", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("case_studies", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("severity_indicator", sa.String(length=10), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "severity_indicator IS NULL OR severity_indicator IN ('low', 'medium', 'high', 'critical')",
                name="ck_atlas_techniques_severity",
            ),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_tactic_code"):
        op.create_index("ix_atlas_techniques_tactic_code", "atlas_techniques", ["tactic_code"], unique=False)
    if not _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_parent_id"):
        op.create_index("ix_atlas_techniques_parent_id", "atlas_techniques", ["parent_id"], unique=False)
    if not _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_atlas_id"):
        op.create_index("ix_atlas_techniques_atlas_id", "atlas_techniques", ["atlas_id"], unique=False)

    _seed_atlas_techniques(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "atlas_techniques"):
        if _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_atlas_id"):
            op.drop_index("ix_atlas_techniques_atlas_id", table_name="atlas_techniques")
        if _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_parent_id"):
            op.drop_index("ix_atlas_techniques_parent_id", table_name="atlas_techniques")
        if _has_index(inspector, "atlas_techniques", "ix_atlas_techniques_tactic_code"):
            op.drop_index("ix_atlas_techniques_tactic_code", table_name="atlas_techniques")
        op.drop_table("atlas_techniques")
