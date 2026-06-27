from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_classification import GuidedClassificationSubmitRequest
from app.ai_governance.schemas.ai_systems import AISystemCreate
from app.ai_governance.schemas.guardrails_envelopes import GuardrailCreate
from app.ai_governance.schemas.monitoring import MonitoringConfigCreate
from app.ai_governance.schemas.third_party_model_card_aibom import ModelCardCreate
from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.ai_governance.services.ai_risk_classification_service import AIRiskClassificationService
from app.ai_governance.services.ai_system_service import AISystemService
from app.ai_governance.services.guardrail_service import GuardrailService
from app.ai_governance.services.model_card_service import ModelCardService
from app.core.security import get_password_hash
from app.data_observability.schemas.data_assets import DataAssetCreate
from app.data_observability.schemas.lineage import LineageEdgeCreate, LineageNodeCreate
from app.data_observability.schemas.quality import DataQualityConfigCreate
from app.data_observability.schemas.retention import DataRetentionPolicyCreate
from app.data_observability.services.data_asset_service import DataAssetService
from app.data_observability.services.lineage_service import LineageService
from app.data_observability.services.quality_service import DataQualityService
from app.data_observability.services.retention_service import RetentionService
from app.db.session import get_session_maker
from app.db.base import Base
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_policy_guardrail import AIPolicyGuardrail
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem
from app.models.control import Control
from app.models.data_lineage_edge import DataLineageEdge
from app.models.data_lineage_node import DataLineageNode
from app.models.data_retention_policy import DataRetentionPolicy
from app.models.data_subject_request import DataSubjectRequest
from app.models.digest_config import DigestConfig
from app.models.dpa_agreement import DPAAgreement
from app.models.dpia import DPIA
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.issue import Issue
from app.models.lawful_basis_record import LawfulBasisRecord
from app.models.membership import Membership
from app.models.model_card import ModelCard
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.processing_activity import ProcessingActivity
from app.models.privacy_notice import PrivacyNotice
from app.models.risk import Risk
from app.models.role import Role
from app.models.subprocessor import Subprocessor
from app.models.task import Task
from app.models.user import User
from app.models.user_notification_preference import UserNotificationPreference
from app.models.vendor import Vendor
from app.privacy.schemas.consent import ConsentRecordCreate
from app.privacy.schemas.dpa import DPACreate
from app.privacy.schemas.dpia import DPIACreate
from app.privacy.schemas.dsar import DataSubjectRequestCreate
from app.privacy.schemas.lawful_basis import LawfulBasisCreate
from app.privacy.schemas.notices import PrivacyNoticeCreate
from app.privacy.schemas.ropa import ProcessingActivityCreate
from app.privacy.services.consent_service import ConsentService
from app.privacy.services.dpa_service import DPAService
from app.privacy.services.dpia_service import DPIAService
from app.privacy.services.dsar_service import DSARService
from app.privacy.services.lawful_basis_service import LawfulBasisService
from app.privacy.services.notice_service import NoticeService
from app.privacy.services.notification_preference_service import NotificationPreferenceService
from app.privacy.services.ropa_service import RopaService
from app.schemas.issue import IssueCreate
from app.schemas.subprocessor import SubprocessorCreate
from app.services.seed_service import SeedService
from app.compliance.services.digest_service import DigestService
from app.compliance.services.issue_service import IssueService
from app.core.config import get_settings
from app.db.session import get_engine


PASSWORD = "DemoPass2024!"
TODAY = datetime.now(UTC)


@dataclass
class OrgCtx:
    org: Organization
    users: dict[str, User]


def _get_or_create_org(db: Session, *, name: str, slug: str) -> Organization:
    org = db.execute(select(Organization).where(Organization.name == name)).scalar_one_or_none()
    if org is None:
        org = Organization(name=name, slug=slug, is_active=True, created_by=None)
        db.add(org)
        db.flush()
    elif not org.slug:
        org.slug = slug
        db.flush()
    return org


def _ensure_org_frameworks(db: Session, org: Organization, user_id) -> None:
    for code in ["ISO_27001", "SOC2", "GDPR", "CCPA"]:
        fw = db.execute(select(Framework).where(Framework.code == code)).scalar_one_or_none()
        if fw is None:
            continue
        row = db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == org.id,
                OrganizationFramework.framework_id == fw.id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = OrganizationFramework(
                organization_id=org.id,
                framework_id=fw.id,
                status="active",
                activated_by_user_id=user_id,
                activated_at=TODAY,
            )
            db.add(row)
        else:
            row.status = "active"
            row.activated_by_user_id = user_id
            row.activated_at = row.activated_at or TODAY
    db.flush()


def _get_or_create_user(
    db: Session,
    *,
    org_id,
    roles: dict[str, Role],
    email: str,
    full_name: str,
    role_name: str,
) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(PASSWORD),
            status="active",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()

    membership = db.execute(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = Membership(
            organization_id=org_id,
            user_id=user.id,
            role_id=roles[role_name].id,
            status="active",
            invited_by=user.id,
        )
        db.add(membership)
    else:
        membership.role_id = roles[role_name].id
        membership.status = "active"
    db.flush()
    return user


def _likelihood(score: str) -> int:
    return {"low": 2, "medium": 3, "high": 4}.get(score, 3)


def _create_controls_and_related(db: Session, ctx: OrgCtx) -> dict[str, int]:
    org_id = ctx.org.id
    admin = ctx.users["admin"]
    dpo = ctx.users["dpo"]

    controls_spec = [
        ("Access Control Policy", "policy", "Formal policy governing access to information systems and data assets.", "implemented"),
        ("Encryption at Rest", "technical", "All data at rest is encrypted using AES-256 or equivalent.", "implemented"),
        ("Vulnerability Management Program", "process", "Monthly vulnerability scans and quarterly penetration testing.", "needs_review"),
        ("Incident Response Plan", "process", "Documented and tested incident response procedures.", "implemented"),
        ("Data Backup and Recovery", "technical", "Daily automated backups with weekly recovery testing.", "implemented"),
    ]

    controls_by_title: dict[str, Control] = {}
    for title, ctype, desc, status in controls_spec:
        row = db.execute(select(Control).where(Control.organization_id == org_id, Control.title == title)).scalar_one_or_none()
        if row is None:
            row = Control(
                organization_id=org_id,
                title=title,
                description=desc,
                control_type=ctype,
                status=status,
                criticality="medium",
                owner_user_id=dpo.id,
                source="custom",
                created_by_user_id=admin.id,
            )
            db.add(row)
            db.flush()
        controls_by_title[title] = row

    evidence_spec = [
        ("SOC 2 Type II Report 2024", "Access Control Policy", "report", "verified", TODAY + timedelta(days=365)),
        ("Penetration Test Report Q4 2024", "Vulnerability Management Program", "report", "verified", TODAY + timedelta(days=90)),
        ("Encryption Configuration Screenshot", "Encryption at Rest", "screenshot", "needs_review", TODAY + timedelta(days=180)),
    ]
    for title, control_title, etype, review_status, valid_until in evidence_spec:
        ev = db.execute(select(EvidenceItem).where(EvidenceItem.organization_id == org_id, EvidenceItem.title == title)).scalar_one_or_none()
        if ev is None:
            ev = EvidenceItem(
                organization_id=org_id,
                title=title,
                description=title,
                evidence_type=etype,
                source="manual",
                status="active",
                review_status=review_status,
                freshness_status="current",
                valid_until=valid_until,
                uploaded_by_user_id=admin.id,
            )
            db.add(ev)
            db.flush()

        ctl = controls_by_title[control_title]
        link = db.execute(
            select(EvidenceControlLink).where(
                EvidenceControlLink.organization_id == org_id,
                EvidenceControlLink.evidence_item_id == ev.id,
                EvidenceControlLink.control_id == ctl.id,
            )
        ).scalar_one_or_none()
        if link is None:
            link = EvidenceControlLink(
                organization_id=org_id,
                evidence_item_id=ev.id,
                control_id=ctl.id,
                link_status="active",
                confidence="manual_confirmed",
                linked_by_user_id=admin.id,
                linked_at=TODAY,
            )
            db.add(link)

    risks_spec = [
        ("Data Breach via Compromised Credential", "critical", "medium", "identified", "security", "Risk of unauthorized data access through stolen or weak credentials.", dpo.id),
        ("Third-Party Vendor Data Exposure", "high", "low", "in_treatment", "third_party", "Vendor with access to PII may suffer its own breach.", dpo.id),
        ("AI Model Bias in Hiring Tool", "high", "medium", "identified", "other", "Algorithmic bias in candidate screening may cause discriminatory outcomes.", admin.id),
    ]
    for title, severity, likelihood_txt, status, category, desc, owner_id in risks_spec:
        risk = db.execute(select(Risk).where(Risk.organization_id == org_id, Risk.title == title)).scalar_one_or_none()
        if risk is None:
            likelihood = _likelihood(likelihood_txt)
            impact = 5 if severity == "critical" else 4
            risk = Risk(
                organization_id=org_id,
                title=title,
                description=desc,
                category=category,
                severity=severity,
                likelihood=likelihood,
                impact=impact,
                inherent_score=likelihood * impact,
                status=status,
                treatment_strategy="mitigate",
                owner_user_id=owner_id,
                created_by_user_id=admin.id,
            )
            db.add(risk)

    vendor_spec = [
        ("Stripe Inc.", "data_processor", "high"),
        ("Slack Technologies", "software", "medium"),
    ]
    for name, vendor_type, risk_tier in vendor_spec:
        v = db.execute(select(Vendor).where(Vendor.organization_id == org_id, Vendor.name == name)).scalar_one_or_none()
        if v is None:
            v = Vendor(
                organization_id=org_id,
                name=name,
                description=name,
                vendor_type=vendor_type,
                risk_tier=risk_tier,
                status="active",
                owner_user_id=dpo.id,
                data_access=True,
                processes_personal_data=True,
                sub_processor=False,
            )
            db.add(v)

    sub_svc = __import__("app.compliance.services.subprocessor_service", fromlist=["SubprocessorService"]).SubprocessorService(db)
    sub_spec = [
        (
            "Amazon Web Services",
            "Cloud infrastructure hosting and data storage",
            TODAY - timedelta(days=180),
            TODAY.date() + timedelta(days=185),
            "high",
        ),
        (
            "Google Cloud Platform",
            "Analytics and ML services",
            TODAY - timedelta(days=90),
            TODAY.date() + timedelta(days=275),
            "medium",
        ),
    ]
    for name, service_desc, dpa_signed, dpa_expiry, risk_level in sub_spec:
        row = db.execute(select(Subprocessor).where(Subprocessor.organization_id == org_id, Subprocessor.name == name)).scalar_one_or_none()
        if row is None:
            row = sub_svc.create_subprocessor(
                org_id,
                SubprocessorCreate(
                    name=name,
                    service_description=service_desc,
                    data_types_processed=["personal_data"],
                    legal_basis="contract",
                    geographic_locations=["US"],
                    data_transfer_mechanism="sccs",
                    dpa_status="signed",
                    dpa_signed_at=dpa_signed,
                    dpa_expiry_date=dpa_expiry,
                    dpa_document_ref="Standard Contractual Clauses",
                    controller_type="processor",
                    risk_level=risk_level,
                    status="active",
                    review_due_date=TODAY.date() + timedelta(days=365),
                ),
                admin.id,
            )

    issue_svc = IssueService(db)
    issue_spec = [
        (
            "Penetration Test Finding: SQL Injection",
            "security_incident",
            "high",
            "open",
            "High risk SQL injection finding from external penetration test.",
        ),
        (
            "GDPR Art. 30 Register Incomplete",
            "compliance_violation",
            "medium",
            "investigating",
            "Processing activity register is incomplete for multiple systems.",
        ),
    ]
    for title, issue_type, severity, target_status, desc in issue_spec:
        row = db.execute(select(Issue).where(Issue.organization_id == org_id, Issue.title == title)).scalar_one_or_none()
        if row is None:
            row = issue_svc.create_issue(
                org_id,
                IssueCreate(
                    title=title,
                    description=desc,
                    issue_type=issue_type,
                    severity=severity,
                    source_type="manual",
                    owner_id=dpo.id,
                    assigned_to=dpo.id,
                ),
                admin.id,
            )
            if target_status == "investigating":
                issue_svc.transition_issue(org_id, row.id, "investigating", admin.id, notes="Seed transition")

    task_spec = [
        ("Update Access Control Policy", "Review and update the access control policy for Q1.", TODAY + timedelta(days=14), dpo.id),
        ("Schedule Q1 Penetration Test", "", TODAY + timedelta(days=30), admin.id),
        ("Complete SOC 2 Evidence Collection", "", TODAY - timedelta(days=5), dpo.id),
    ]
    for title, desc, due, owner_id in task_spec:
        row = db.execute(select(Task).where(Task.organization_id == org_id, Task.title == title)).scalar_one_or_none()
        if row is None:
            row = Task(
                organization_id=org_id,
                title=title,
                description=desc or None,
                status="open",
                priority="normal",
                task_type="general",
                owner_user_id=owner_id,
                created_by_user_id=admin.id,
                due_date=due,
                source="manual",
                reminder_status="none",
            )
            db.add(row)

    db.flush()
    return {
        "controls": len(controls_spec),
        "evidence": len(evidence_spec),
        "risks": len(risks_spec),
        "vendors": len(vendor_spec),
        "subprocessors": len(sub_spec),
        "issues": len(issue_spec),
        "tasks": len(task_spec),
    }


def _seed_ai_governance(db: Session, ctx: OrgCtx) -> dict[str, int]:
    org_id = ctx.org.id
    admin = ctx.users["admin"]
    dpo = ctx.users["dpo"]

    ai_system_svc = AISystemService(db)
    classify_svc = AIRiskClassificationService(db)
    model_card_svc = ModelCardService(db)
    guardrail_svc = GuardrailService(db)
    monitoring_svc = AIMonitoringService(db)

    specs = [
        ("Customer Churn Predictor", "model", "production", "ML model predicting 90-day customer churn probability.", "Retention team prioritization", "limited", ["US", "GB", "DE"], dpo.id),
        ("Support Ticket Classifier", "application", "staging", "NLP classifier routing support tickets to appropriate teams.", "Support operations efficiency", None, None, admin.id),
        ("Contract Review Assistant", "agent", "development", "LLM-based contract analysis flagging non-standard clauses.", "Legal team review acceleration", None, None, admin.id),
    ]

    systems: dict[str, AISystem] = {}
    for name, system_type, dep_status, desc, purpose, risk_tier, geo, owner_id in specs:
        row = db.execute(select(AISystem).where(AISystem.organization_id == org_id, AISystem.name == name, AISystem.deleted_at.is_(None))).scalar_one_or_none()
        if row is None:
            row = ai_system_svc.create_system(
                org_id,
                AISystemCreate(
                    name=name,
                    system_type=system_type,
                    deployment_status=dep_status,
                    description=desc,
                    purpose=purpose,
                    risk_tier=risk_tier,
                    geographic_scope=geo,
                    owner_id=owner_id,
                ),
                admin.id,
            )
        systems[name] = row

    churn = systems["Customer Churn Predictor"]

    _ = classify_svc.start_guided_classification(org_id, churn.id, None, admin.id)
    current_class = db.execute(
        select(AIRiskClassification).where(
            AIRiskClassification.organization_id == org_id,
            AIRiskClassification.ai_system_id == churn.id,
        )
    ).scalar_one_or_none()
    if current_class is None:
        classify_svc.submit_guided_answers(
            org_id,
            churn.id,
            GuidedClassificationSubmitRequest(
                answers={
                    "critical_infrastructure": "no",
                    "employment_decisions": "no",
                    "biometric_data": "no",
                    "essential_services": "no",
                    "law_enforcement": "no",
                    "manipulation": "no",
                    "social_scoring": "no",
                    "realtime_biometric_public": "no",
                    "transparency_obligation": "no",
                }
            ).answers,
            admin.id,
        )

    existing_card = db.execute(
        select(ModelCard).where(
            ModelCard.organization_id == org_id,
            ModelCard.ai_system_id == churn.id,
            ModelCard.status == "draft",
        )
    ).scalar_one_or_none()
    if existing_card is None:
        model_card_svc.create_card(
            org_id,
            churn.id,
            ModelCardCreate(
                intended_purpose="Predict customer churn probability for retention prioritization.",
                known_limitations=[
                    "Model trained on US customers only",
                    "Performance degrades for customers < 90 days",
                ],
                contact_owner_id=dpo.id,
            ),
            admin.id,
        )

    existing_guardrail = db.execute(
        select(AIPolicyGuardrail).where(
            AIPolicyGuardrail.organization_id == org_id,
            AIPolicyGuardrail.ai_system_id == churn.id,
            AIPolicyGuardrail.guardrail_type == "financial_limit",
            AIPolicyGuardrail.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing_guardrail is None:
        guardrail_svc.create_guardrail(
            org_id,
            GuardrailCreate(
                ai_system_id=churn.id,
                guardrail_type="financial_limit",
                constraint_description="Retention offers capped at $500 per customer",
                constraint_value={"max_usd": 500},
                violation_action="block_and_alert",
            ),
            admin.id,
        )

    cfg = db.execute(
        select(AIMonitoringConfig).where(
            AIMonitoringConfig.organization_id == org_id,
            AIMonitoringConfig.ai_system_id == churn.id,
            AIMonitoringConfig.metric_type == "accuracy",
            AIMonitoringConfig.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if cfg is None:
        cfg = monitoring_svc.create_config(
            org_id,
            churn.id,
            MonitoringConfigCreate(
                metric_type="accuracy",
                threshold_value=Decimal("0.80"),
                comparison_direction="below",
                alert_on_breach=True,
                baseline_value=Decimal("0.87"),
                api_key="seed-monitoring-key-0001",
            ),
            admin.id,
        )
    monitoring_svc.submit_reading(org_id, cfg.id, Decimal("0.72"), "manual", "seed_script")

    db.flush()
    return {
        "ai_systems": len(specs),
        "risk_classifications": 1,
        "model_cards": 1,
        "guardrails": 1,
        "monitoring_configs": 1,
    }


def _seed_data_observability(db: Session, ctx: OrgCtx) -> dict[str, int]:
    org_id = ctx.org.id
    admin = ctx.users["admin"]
    dpo = ctx.users["dpo"]

    asset_svc = DataAssetService(db)
    quality_svc = DataQualityService(db)
    lineage_svc = LineageService(db)
    retention_svc = RetentionService(db)

    assets_spec = [
        (
            "Customer PII Database",
            "database",
            dpo.id,
            "restricted",
            "personal_data",
            True,
            ["US", "IE"],
            ["US", "IE", "GB"],
            1825,
            "AWS RDS us-east-1",
        ),
        (
            "Analytics Data Warehouse",
            "data_lake",
            admin.id,
            "internal",
            "operational_data",
            True,
            ["US"],
            ["US"],
            730,
            "Snowflake us-east-1",
        ),
        (
            "Payment Transaction Logs",
            "database",
            dpo.id,
            "restricted",
            "financial_data",
            True,
            ["US"],
            ["US"],
            2555,
            "AWS RDS us-east-1 (payments)",
        ),
        (
            "Employee HR Records",
            "file_store",
            admin.id,
            "confidential",
            "personal_data",
            False,
            ["US"],
            ["US"],
            None,
            None,
        ),
    ]

    assets: dict[str, object] = {}
    for name, atype, owner_id, sensitivity, class_type, confirmed, geo, perm, retention_days, source in assets_spec:
        row = db.execute(
            select(__import__("app.models.data_asset", fromlist=["DataAsset"]).DataAsset).where(
                __import__("app.models.data_asset", fromlist=["DataAsset"]).DataAsset.organization_id == org_id,
                __import__("app.models.data_asset", fromlist=["DataAsset"]).DataAsset.name == name,
                __import__("app.models.data_asset", fromlist=["DataAsset"]).DataAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            row = asset_svc.create_asset(
                org_id,
                DataAssetCreate(
                    name=name,
                    asset_type=atype,
                    owner_id=owner_id,
                    sensitivity_tier=sensitivity,
                    classification_type=class_type,
                    classification_confirmed=confirmed,
                    geographic_locations=geo,
                    permitted_regions=perm,
                    retention_policy_days=retention_days,
                    source_system=source,
                ),
                admin.id,
            )
            if confirmed:
                asset_svc.confirm_classification(org_id, row.id, class_type, sensitivity, admin.id)
        assets[name] = row

    customer_asset = assets["Customer PII Database"]
    cfg = quality_svc.create_config(
        org_id,
        customer_asset.id,
        DataQualityConfigCreate(
            data_asset_id=customer_asset.id,
            metric_type="freshness",
            threshold_value=Decimal("0.95"),
            comparison_direction="below",
            alert_on_breach=True,
        ),
        admin.id,
    ) if db.execute(select(func.count()).select_from(__import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig).where(
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.organization_id == org_id,
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.data_asset_id == customer_asset.id,
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.metric_type == "freshness",
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.deleted_at.is_(None),
    )).scalar_one() == 0 else db.execute(select(__import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig).where(
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.organization_id == org_id,
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.data_asset_id == customer_asset.id,
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.metric_type == "freshness",
        __import__("app.models.data_quality_config", fromlist=["DataQualityConfig"]).DataQualityConfig.deleted_at.is_(None),
    )).scalar_one()

    quality_svc.submit_reading(org_id, cfg.id, Decimal("0.72"), "manual", "seed_script", "seed breach reading")

    node_customer = db.execute(
        select(DataLineageNode).where(
            DataLineageNode.organization_id == org_id,
            DataLineageNode.data_asset_id == customer_asset.id,
            DataLineageNode.node_type == "data_asset",
            DataLineageNode.name == "Customer PII Database",
        )
    ).scalar_one_or_none()
    if node_customer is None:
        node_customer = lineage_svc.create_node(
            org_id,
            LineageNodeCreate(node_type="data_asset", data_asset_id=customer_asset.id, name="Customer PII Database"),
            admin.id,
        )

    node_sf = db.execute(
        select(DataLineageNode).where(
            DataLineageNode.organization_id == org_id,
            DataLineageNode.node_type == "external_source",
            DataLineageNode.name == "Salesforce CRM",
        )
    ).scalar_one_or_none()
    if node_sf is None:
        node_sf = lineage_svc.create_node(
            org_id,
            LineageNodeCreate(node_type="external_source", name="Salesforce CRM", system_name="Salesforce"),
            admin.id,
        )

    edge_exists = db.execute(
        select(DataLineageEdge).where(
            DataLineageEdge.organization_id == org_id,
            DataLineageEdge.upstream_node_id == node_sf.id,
            DataLineageEdge.downstream_node_id == node_customer.id,
            DataLineageEdge.source_method == "manual",
        )
    ).scalar_one_or_none()
    if edge_exists is None:
        lineage_svc.create_edge(
            org_id,
            node_sf.id,
            node_customer.id,
            LineageEdgeCreate(upstream_node_id=node_sf.id, downstream_node_id=node_customer.id, transformation_description="CRM sync"),
            source_method="manual",
            actor_user_id=admin.id,
        )

    policy = db.execute(
        select(DataRetentionPolicy).where(
            DataRetentionPolicy.organization_id == org_id,
            DataRetentionPolicy.name == "GDPR Standard Retention",
            DataRetentionPolicy.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if policy is None:
        policy = retention_svc.create_policy(
            org_id,
            DataRetentionPolicyCreate(
                name="GDPR Standard Retention",
                retention_days=1825,
                max_retention_days=2555,
                action_on_expiry="flag",
                legal_basis="GDPR Art. 5(1)(e)",
                applies_to_classification_types=["personal_data"],
            ),
            admin.id,
        )

    retention_svc.apply_policy_to_asset(org_id, customer_asset.id, policy.id, admin.id)

    db.flush()
    return {
        "data_assets": len(assets_spec),
        "quality_configs": 1,
        "lineage_nodes": 2,
        "lineage_edges": 1,
        "retention_policies": 1,
    }


def _seed_privacy(db: Session, ctx: OrgCtx) -> dict[str, int]:
    org_id = ctx.org.id
    admin = ctx.users["admin"]
    dpo = ctx.users["dpo"]

    ropa_svc = RopaService(db)
    dsar_svc = DSARService(db)
    consent_svc = ConsentService(db)
    notice_svc = NoticeService(db)
    dpia_svc = DPIAService(db)
    dpa_svc = DPAService(db)
    lawful_svc = LawfulBasisService(db)

    activities_spec = [
        (
            "Customer Account Management",
            "Managing customer accounts, subscriptions, and service delivery.",
            "contract",
            ["name", "email", "address", "payment_info"],
            ["customers"],
            "Duration of contract + 7 years",
            True,
            ["US"],
            "Standard Contractual Clauses",
            dpo.id,
        ),
        (
            "Marketing Analytics",
            "Analyzing user behavior to improve product and target marketing campaigns.",
            "consent",
            ["email", "usage_data", "device_info"],
            ["customers", "prospects"],
            "3 years from consent",
            False,
            [],
            None,
            admin.id,
        ),
        (
            "Employee Payroll Processing",
            "Processing employee compensation, tax filings, and benefit administration.",
            "legal_obligation",
            ["name", "tax_id", "bank_account", "salary"],
            ["employees"],
            "7 years per tax law",
            False,
            [],
            None,
            admin.id,
        ),
    ]

    activities: dict[str, ProcessingActivity] = {}
    for name, purpose, legal_basis, data_categories, subjects, retention_period, intl, destinations, safeguards, owner_id in activities_spec:
        row = db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.name == name,
                ProcessingActivity.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            row = ropa_svc.create_activity(
                org_id,
                ProcessingActivityCreate(
                    name=name,
                    purpose=purpose,
                    legal_basis=legal_basis,
                    data_categories=data_categories,
                    special_categories=[],
                    data_subject_types=subjects,
                    retention_period=retention_period,
                    international_transfers=intl,
                    transfer_destinations=destinations,
                    transfer_safeguards=safeguards,
                    status="active",
                    owner_id=owner_id,
                ),
                admin.id,
            )
        activities[name] = row

    basis_map = {
        "Customer Account Management": ("contract", "GDPR Art. 6(1)(b)"),
        "Marketing Analytics": ("consent", "GDPR Art. 6(1)(a)"),
        "Employee Payroll Processing": ("legal_obligation", "GDPR Art. 6(1)(c)"),
    }
    for act_name, (lawful_basis, article_ref) in basis_map.items():
        act = activities[act_name]
        existing = db.execute(
            select(LawfulBasisRecord).where(
                LawfulBasisRecord.organization_id == org_id,
                LawfulBasisRecord.processing_activity_id == act.id,
                LawfulBasisRecord.lawful_basis == lawful_basis,
            )
        ).scalar_one_or_none()
        if existing is None:
            lawful_svc.document_basis(
                org_id,
                act.id,
                LawfulBasisCreate(
                    processing_activity_id=act.id,
                    lawful_basis=lawful_basis,
                    basis_description=f"Documented basis for {act_name}",
                    applicable_frameworks=["gdpr"],
                    article_reference=article_ref,
                ),
                admin.id,
            )

    if db.execute(
        select(DataSubjectRequest).where(
            DataSubjectRequest.organization_id == org_id,
            DataSubjectRequest.subject_email == "jane.smith@example.com",
            DataSubjectRequest.request_type == "access",
            DataSubjectRequest.deleted_at.is_(None),
        )
    ).scalar_one_or_none() is None:
        r1 = dsar_svc.create_request(
            org_id,
            DataSubjectRequestCreate(
                request_type="access",
                subject_name="Jane Smith",
                subject_email="jane.smith@example.com",
                regulatory_framework="gdpr",
                assigned_handler_id=dpo.id,
            ),
            created_by=admin.id,
        )
        dsar_svc.verify_identity(org_id, r1.id, admin.id)
        if r1.status in {"received", "identity_verification"}:
            dsar_svc.transition_status(org_id, r1.id, "in_progress", admin.id)

    if db.execute(
        select(DataSubjectRequest).where(
            DataSubjectRequest.organization_id == org_id,
            DataSubjectRequest.subject_email == "bob.johnson@example.com",
            DataSubjectRequest.request_type == "erasure",
            DataSubjectRequest.deleted_at.is_(None),
        )
    ).scalar_one_or_none() is None:
        dsar_svc.create_request(
            org_id,
            DataSubjectRequestCreate(
                request_type="erasure",
                subject_name="Bob Johnson",
                subject_email="bob.johnson@example.com",
                regulatory_framework="gdpr",
            ),
            created_by=admin.id,
        )

    published_notice = db.execute(
        select(PrivacyNotice).where(
            PrivacyNotice.organization_id == org_id,
            PrivacyNotice.status == "published",
            PrivacyNotice.language == "en",
        )
    ).scalar_one_or_none()
    if published_notice is None:
        notice = notice_svc.create_notice(
            org_id,
            PrivacyNoticeCreate(
                title="Privacy Policy",
                content=(
                    "Nexaform Technologies Privacy Policy. We collect and process personal data as described "
                    "in our Record of Processing Activities. You have rights under GDPR including access, "
                    "erasure, portability, and objection. Contact: dpo@nexaform.example.com"
                ),
                language="en",
                frameworks=["gdpr", "ccpa"],
            ),
            admin.id,
        )
        notice_svc.publish_notice(org_id, notice.id, admin.id)

    marketing = activities["Marketing Analytics"]
    consent_svc.record_consent(
        org_id,
        marketing.id,
        ConsentRecordCreate(
            processing_activity_id=marketing.id,
            subject_identifier="customer_hash_001",
            consent_mechanism="cookie_banner",
            granted=True,
            consent_version="2.0",
        ),
        actor_user_id=admin.id,
    )
    consent_svc.record_consent(
        org_id,
        marketing.id,
        ConsentRecordCreate(
            processing_activity_id=marketing.id,
            subject_identifier="customer_hash_002",
            consent_mechanism="explicit_checkbox",
            granted=False,
            consent_version="2.0",
            metadata={"withdrawal_reason": "No longer want marketing"},
        ),
        actor_user_id=admin.id,
    )

    activity1 = activities["Customer Account Management"]
    if db.execute(
        select(DPIA).where(
            DPIA.organization_id == org_id,
            DPIA.processing_activity_id == activity1.id,
            DPIA.deleted_at.is_(None),
        )
    ).scalar_one_or_none() is None:
        dpia_svc.create_dpia(
            org_id,
            activity1.id,
            DPIACreate(
                processing_activity_id=activity1.id,
                title="DPIA — Customer Account Management System",
                nature_of_processing="Processing customer PII for account management and service delivery.",
                necessity_assessment="Processing is necessary for contract performance under GDPR Art. 6(1)(b).",
                residual_risk_level="low",
            ),
            admin.id,
        )

    dpa_specs = [
        (
            "Amazon Web Services, Inc.",
            "processor",
            "active",
            (TODAY - timedelta(days=180)).date(),
            (TODAY + timedelta(days=185)).date(),
            True,
            ["gdpr"],
            True,
            True,
            [str(activity1.id), str(activities["Employee Payroll Processing"].id)],
        ),
        (
            "Stripe, Inc.",
            "processor",
            "active",
            (TODAY - timedelta(days=90)).date(),
            (TODAY + timedelta(days=275)).date(),
            False,
            ["gdpr", "ccpa"],
            True,
            None,
            [str(activity1.id)],
        ),
    ]
    for name, ctype, status_value, signed, expiry, auto_renews, regulations, a28, sccs, activity_ids in dpa_specs:
        existing = db.execute(
            select(DPAAgreement).where(
                DPAAgreement.organization_id == org_id,
                DPAAgreement.counterparty_name == name,
                DPAAgreement.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is None:
            dpa_svc.create_dpa(
                org_id,
                DPACreate(
                    counterparty_name=name,
                    counterparty_type=ctype,
                    status=status_value,
                    signed_date=signed,
                    expiry_date=expiry,
                    auto_renews=auto_renews,
                    governing_regulation=regulations,
                    article28_compliant=a28,
                    sccs_included=sccs,
                    processing_activity_ids=activity_ids,
                    owner_id=dpo.id,
                ),
                admin.id,
            )

    pref_svc = NotificationPreferenceService(db)
    digest_svc = DigestService(db)

    pref_svc.get_or_create_preferences(org_id, dpo.id)
    pref_svc.update_preference(org_id, dpo.id, "digest_daily", "email", True, None)
    pref_svc.update_preference(org_id, dpo.id, "digest_weekly", "email", True, None)
    pref_svc.update_preference(org_id, dpo.id, "sla_breach", "email", True, "high")

    digest_svc.get_or_create_configs(org_id, dpo.id)
    digest_svc.update_daily_config(org_id, dpo.id, True, "08:00")
    digest_svc.update_weekly_config(org_id, dpo.id, True, 0)

    db.flush()
    return {
        "processing_activities": len(activities_spec),
        "lawful_basis_records": 3,
        "dsr_requests": 2,
        "privacy_notices": 1,
        "consent_records": 2,
        "dpias": 1,
        "dpa_agreements": 2,
        "notification_preferences": db.execute(
            select(func.count(UserNotificationPreference.id)).where(
                UserNotificationPreference.organization_id == org_id,
                UserNotificationPreference.user_id == dpo.id,
            )
        ).scalar_one(),
        "digest_configs": db.execute(
            select(func.count(DigestConfig.id)).where(
                DigestConfig.organization_id == org_id,
                DigestConfig.user_id == dpo.id,
            )
        ).scalar_one(),
    }


def main() -> None:
    started = time.perf_counter()
    settings = get_settings()
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=get_engine())
    SessionLocal = get_session_maker()

    with SessionLocal() as db:
        SeedService.ensure_permissions(db)
        SeedService.ensure_framework_catalog(db)
        SeedService.ensure_starter_obligations(db)
        SeedService.ensure_framework_versions(db)
        SeedService.ensure_policy_templates(db)
        SeedService.ensure_questionnaire_scoring_rules(db)
        SeedService.ensure_eu_act_annex_mappings(db)

        org_specs = [
            ("Nexaform Technologies", "nexaform"),
            ("PulseHealth Analytics", "pulsehealth"),
        ]

        org_contexts: dict[str, OrgCtx] = {}
        for org_name, slug in org_specs:
            org = _get_or_create_org(db, name=org_name, slug=slug)
            roles = SeedService.ensure_roles_for_organization(db, org.id)

            users = {
                "admin": _get_or_create_user(
                    db,
                    org_id=org.id,
                    roles=roles,
                    email=f"admin@{slug}.example.com",
                    full_name="Alex Admin",
                    role_name="admin",
                ),
                "dpo": _get_or_create_user(
                    db,
                    org_id=org.id,
                    roles=roles,
                    email=f"dpo@{slug}.example.com",
                    full_name="Dana Compliance",
                    role_name="compliance_manager",
                ),
                "auditor": _get_or_create_user(
                    db,
                    org_id=org.id,
                    roles=roles,
                    email=f"auditor@{slug}.example.com",
                    full_name="Riley Reviewer",
                    role_name="reviewer",
                ),
                "readonly": _get_or_create_user(
                    db,
                    org_id=org.id,
                    roles=roles,
                    email=f"readonly@{slug}.example.com",
                    full_name="Sam Readonly",
                    role_name="readonly",
                ),
            }

            _ensure_org_frameworks(db, org, users["admin"].id)
            SeedService.ensure_issue_sla_policies(db, org.id)
            SeedService.ensure_default_data_access_anomaly_rules(db, org.id, users["admin"].id)

            org_contexts[slug] = OrgCtx(org=org, users=users)

        p1 = _create_controls_and_related(db, org_contexts["nexaform"])
        p2 = _seed_ai_governance(db, org_contexts["nexaform"])
        p3 = _seed_data_observability(db, org_contexts["nexaform"])
        p4 = _seed_privacy(db, org_contexts["nexaform"])

        db.commit()

    elapsed = time.perf_counter() - started

    print(f"✅ Organizations created/verified: {len(org_specs)}")
    print("✅ Users created/verified: 8")
    print(f"✅ Controls: {p1['controls']}")
    print(f"✅ Evidence: {p1['evidence']}")
    print(f"✅ Risks: {p1['risks']}")
    print(f"✅ Vendors: {p1['vendors']}")
    print(f"✅ Subprocessors: {p1['subprocessors']}")
    print(f"✅ Issues: {p1['issues']}")
    print(f"✅ Tasks: {p1['tasks']} (including 1 overdue)")
    print(f"✅ AI Systems: {p2['ai_systems']}")
    print(f"✅ Risk Classifications: {p2['risk_classifications']}")
    print(f"✅ Model Cards: {p2['model_cards']}")
    print(f"✅ Guardrails: {p2['guardrails']}")
    print(f"✅ Monitoring Configs: {p2['monitoring_configs']} (with 1 breach reading)")
    print(f"✅ Data Assets: {p3['data_assets']} (including 1 unconfirmed)")
    print(f"✅ Quality Configs: {p3['quality_configs']} (with 1 breach reading)")
    print(f"✅ Lineage Nodes: {p3['lineage_nodes']}")
    print(f"✅ Lineage Edges: {p3['lineage_edges']}")
    print(f"✅ Retention Policies: {p3['retention_policies']}")
    print(f"✅ Processing Activities: {p4['processing_activities']}")
    print(f"✅ Lawful Basis Records: {p4['lawful_basis_records']}")
    print(f"✅ DSR Requests: {p4['dsr_requests']}")
    print("✅ Privacy Notices: 1 (1 published)")
    print(f"✅ Consent Records: {p4['consent_records']}")
    print(f"✅ DPIAs: {p4['dpias']}")
    print(f"✅ DPA Agreements: {p4['dpa_agreements']}")
    print(f"✅ Notification Preferences: {p4['notification_preferences']}")
    print(f"✅ Digest Configs: {p4['digest_configs']}")
    print(f"Seed complete in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
