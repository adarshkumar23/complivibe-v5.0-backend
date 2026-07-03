from __future__ import annotations

ISO_31000_SECTIONS: list[dict[str, int | str]] = [
    {"code": "ISO31K-4", "title": "Principles", "order": 1},
    {"code": "ISO31K-5", "title": "Framework", "order": 2},
    {"code": "ISO31K-6", "title": "Process", "order": 3},
]

# (reference_code, title, description, section_code, evidence_hints)
ISO_31000_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("ISO31K-4.1", "Value creation and protection", "Risk management creates and protects value by contributing to objectives and improving performance outcomes.", "ISO31K-4", ["risk_management_policy", "value_creation_metrics"]),
    ("ISO31K-4.2", "Integrated", "Risk management is integrated into organizational activities and decision-making processes.", "ISO31K-4", ["risk_integration_evidence", "governance_documentation"]),
    ("ISO31K-4.3", "Structured and comprehensive", "A structured and comprehensive approach improves consistency and comparability of risk outcomes.", "ISO31K-4", ["risk_methodology", "assessment_templates"]),
    ("ISO31K-4.4", "Customized", "Risk management must be tailored to the organization context, mandate, and objectives.", "ISO31K-4", ["context_profile", "customized_risk_criteria"]),
    ("ISO31K-4.5", "Inclusive", "Timely stakeholder involvement ensures diverse knowledge and perspectives are considered.", "ISO31K-4", ["stakeholder_engagement_records", "consultation_log"]),
    ("ISO31K-4.6", "Dynamic", "Risk management should adapt as risks emerge, evolve, or disappear with changing context.", "ISO31K-4", ["emerging_risk_reviews", "change_monitoring"]),
    ("ISO31K-4.7", "Best available information", "Risk inputs should use timely, reliable data while acknowledging uncertainty and limitations.", "ISO31K-4", ["risk_data_sources", "assumption_register"]),
    ("ISO31K-4.8", "Human and cultural factors", "Human behavior and organizational culture materially influence risk management effectiveness.", "ISO31K-4", ["culture_assessment", "training_records"]),
    ("ISO31K-4.9", "Continual improvement", "Risk management should be continuously improved through monitoring, learning, and lessons learned.", "ISO31K-4", ["improvement_plan", "lessons_learned_log"]),
    ("ISO31K-5.2", "Leadership and commitment", "Leadership must demonstrate commitment and ensure risk management is embedded in governance.", "ISO31K-5", ["board_risk_policy", "management_commitment_evidence"]),
    ("ISO31K-5.3", "Integration", "Integration requires understanding context and embedding risk management across activities.", "ISO31K-5", ["integration_plan", "process_mapping"]),
    ("ISO31K-5.4.2", "Understanding organization and context", "The organization defines and documents internal and external context relevant to risk.", "ISO31K-5", ["context_documentation", "stakeholder_analysis"]),
    ("ISO31K-5.4.3", "Articulating risk management commitment", "Commitment to risk management should be formally documented and communicated.", "ISO31K-5", ["risk_commitment_statement", "communication_records"]),
    ("ISO31K-5.5", "Designing the framework", "Framework design should define policy, roles, resources, communication, and integration.", "ISO31K-5", ["framework_design_document", "roles_matrix"]),
    ("ISO31K-5.6", "Implementing the framework", "Organizations implement the risk framework through a defined execution plan.", "ISO31K-5", ["implementation_plan", "execution_status_reports"]),
    ("ISO31K-5.7", "Evaluating the framework", "Organizations periodically evaluate framework performance against purpose and plans.", "ISO31K-5", ["framework_kpis", "evaluation_reports"]),
    ("ISO31K-5.8", "Improving the framework", "Organizations continuously monitor and improve framework suitability and effectiveness.", "ISO31K-5", ["framework_improvement_log", "review_minutes"]),
    ("ISO31K-6.3", "Scope, context, and criteria", "Risk process scope and criteria should be set with internal and external context.", "ISO31K-6", ["risk_scope_document", "context_analysis"]),
    ("ISO31K-6.4", "Risk assessment", "Risk assessment comprises identification, analysis, and evaluation of risk.", "ISO31K-6", ["risk_register", "risk_assessment_reports"]),
    ("ISO31K-6.5", "Risk treatment", "Risk treatment selects and implements options to avoid, reduce, share, or retain risk.", "ISO31K-6", ["risk_treatment_plans", "treatment_option_records"]),
    ("ISO31K-6.6", "Monitoring and review", "Monitoring and review improve process design, implementation quality, and outcomes.", "ISO31K-6", ["monitoring_records", "review_minutes"]),
    ("ISO31K-6.7", "Recording and reporting", "Risk activities and outcomes should be recorded and reported through appropriate channels.", "ISO31K-6", ["risk_reports", "communication_records"]),
]

ISO_31000_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "uses_formal_risk_framework",
        "question_text": "Does your organization operate a formal enterprise risk management framework?",
        "help_text": "ISO 31000 applies broadly across sectors and organization sizes.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "board_oversees_risk",
        "question_text": "Is risk governance formally overseen by leadership or the board?",
        "help_text": "Leadership commitment is a core element of ISO 31000 framework design.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

OECD_AI_SECTIONS: list[dict[str, int | str]] = [
    {"code": "OECD-P", "title": "AI Principles", "order": 1},
    {"code": "OECD-R", "title": "Policy Recommendations", "order": 2},
]

OECD_AI_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("OECD-P1.1", "Inclusive growth, sustainable development, wellbeing", "AI should benefit people and the planet through inclusive growth, sustainability, and wellbeing outcomes.", "OECD-P", ["ai_impact_statement", "sustainability_metrics"]),
    ("OECD-P1.2", "Human-centred values and fairness", "AI actors should respect rule of law, human rights, and fairness while mitigating discriminatory outcomes.", "OECD-P", ["fairness_policy", "bias_assessment"]),
    ("OECD-P1.3", "Transparency and explainability", "AI actors should provide transparent disclosures and explainability commensurate with stakeholder needs.", "OECD-P", ["model_cards", "explainability_report", "transparency_documentation"]),
    ("OECD-P1.4", "Robustness, security, and safety", "AI systems should remain robust, secure, and safe throughout their lifecycle with ongoing risk management.", "OECD-P", ["ai_risk_assessment", "security_testing_records", "incident_records"]),
    ("OECD-P1.5", "Accountability", "AI actors remain accountable for system outcomes and conformance to responsible AI principles.", "OECD-P", ["governance_documentation", "accountability_framework", "audit_records"]),
    ("OECD-R2.1", "Investing in AI R&D", "Governments should support responsible AI research and development investment.", "OECD-R", ["r_and_d_portfolio", "investment_plan"]),
    ("OECD-R2.2", "Fostering an accessible AI ecosystem", "Governments should foster accessible infrastructure and ecosystems for beneficial AI innovation.", "OECD-R", ["ecosystem_strategy", "infrastructure_programs"]),
    ("OECD-R2.3", "Shaping an enabling policy environment", "Governments should develop policy and regulatory environments that support trustworthy AI.", "OECD-R", ["policy_framework", "regulatory_mapping"]),
    ("OECD-R2.4", "Building human capacity and skills", "Governments should develop AI workforce capabilities and transition support programs.", "OECD-R", ["skills_program", "training_strategy"]),
    ("OECD-R2.5", "International co-operation", "Governments should cooperate internationally on AI governance and interoperability.", "OECD-R", ["international_mou", "cross_border_coordination_records"]),
]

OECD_AI_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "uses_ai_systems",
        "question_text": "Does your organization develop, deploy, or operate AI systems?",
        "help_text": "OECD AI principles are broadly applicable to public and private AI actors.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "cross_border_ai_operations",
        "question_text": "Does your organization operate AI systems across multiple countries?",
        "help_text": "Cross-border operation increases importance of interoperability and transparency.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

IEEE_7000_SECTIONS: list[dict[str, int | str]] = [
    {"code": "IEEE7000", "title": "Ethics in System Design", "order": 1},
    {"code": "IEEE7001", "title": "Transparency Standards", "order": 2},
    {"code": "IEEE7009", "title": "Fail-Safe Design", "order": 3},
]

IEEE_7000_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("IEEE7000-5.1", "Ethical values identification", "Organizations should identify and document ethical values relevant to systems and stakeholders.", "IEEE7000", ["ethics_documentation", "stakeholder_analysis", "values_mapping"]),
    ("IEEE7000-5.2", "Value identification process", "Organizations should operate a formal process for identifying and prioritizing ethical values.", "IEEE7000", ["value_identification_procedure", "process_records"]),
    ("IEEE7000-6.1", "Risk identification for ethical concerns", "Organizations should identify design-time and operational risks arising from ethical concerns.", "IEEE7000", ["ethics_risk_assessment", "value_conflict_analysis"]),
    ("IEEE7000-7.1", "Ethical requirement specification", "Organizations should specify measurable ethical requirements derived from values.", "IEEE7000", ["ethical_requirements_document", "design_review_records"]),
    ("IEEE7000-8.1", "Value verification and validation", "Organizations should verify and validate that system behavior reflects identified values.", "IEEE7000", ["validation_plan", "verification_results"]),
    ("IEEE7001-4.1", "Transparency levels defined", "Developers should define and document transparency levels for relevant stakeholder groups.", "IEEE7001", ["transparency_policy", "stakeholder_communication_plan"]),
    ("IEEE7001-5.1", "Transparency metrics", "Organizations should define measurable transparency criteria and monitor outcomes.", "IEEE7001", ["transparency_metrics", "measurement_records"]),
    ("IEEE7001-6.1", "User transparency", "Autonomous systems should disclose capabilities and limitations to users.", "IEEE7001", ["user_documentation", "system_disclosure_records"]),
    ("IEEE7009-5.1", "Fail-safe requirements", "Safety-critical AI systems should be designed to fail safely and minimize harm.", "IEEE7009", ["fail_safe_design_docs", "safety_testing_records"]),
    ("IEEE7009-6.1", "Override mechanisms", "Safety-critical AI systems should provide tested human override mechanisms.", "IEEE7009", ["override_mechanism_docs", "human_override_testing"]),
]

IEEE_7000_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "autonomous_or_ai_systems",
        "question_text": "Does your organization build or deploy autonomous or AI-enabled systems?",
        "help_text": "IEEE 7000-series controls are relevant when ethics, transparency, and safety are design concerns.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "safety_critical_context",
        "question_text": "Do your AI systems operate in safety-critical contexts?",
        "help_text": "Safety-critical use cases require stronger fail-safe and override controls.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

UNESCO_SECTIONS: list[dict[str, int | str]] = [
    {"code": "UNESCO-V", "title": "Values and Principles", "order": 1},
    {"code": "UNESCO-PA", "title": "Policy Action Areas", "order": 2},
]

UNESCO_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("UNESCO-V1", "Proportionality and do no harm", "AI systems should serve legitimate aims and minimize harm proportionate to intended benefits.", "UNESCO-V", ["impact_assessment", "harm_mitigation_plan"]),
    ("UNESCO-V2", "Safety and security", "AI risks and unwanted harms should be prevented through lifecycle safety and security safeguards.", "UNESCO-V", ["safety_assessment", "security_controls"]),
    ("UNESCO-V3", "Fairness and non-discrimination", "AI systems should avoid discrimination and include proactive bias detection and mitigation.", "UNESCO-V", ["bias_assessment", "fairness_metrics", "discrimination_testing"]),
    ("UNESCO-V4", "Sustainability", "AI development should support environmental sustainability and ecological integrity.", "UNESCO-V", ["sustainability_assessment", "energy_usage_metrics"]),
    ("UNESCO-V5", "Right to privacy and data protection", "Privacy and robust data governance should be maintained throughout the AI lifecycle.", "UNESCO-V", ["privacy_assessment", "data_governance_documentation"]),
    ("UNESCO-V6", "Human oversight and determination", "Critical decisions should retain meaningful human oversight and accountability.", "UNESCO-V", ["human_oversight_documentation", "control_mechanisms"]),
    ("UNESCO-V7", "Transparency and explainability", "Ethical AI deployment should include transparency and explainability of systems and outputs.", "UNESCO-V", ["model_cards", "explainability_evidence"]),
    ("UNESCO-V8", "Responsibility and accountability", "AI responsibilities should be clearly allocated with effective remedy pathways for harms.", "UNESCO-V", ["accountability_framework", "governance_structure"]),
    ("UNESCO-V9", "Awareness and literacy", "Organizations should promote AI literacy and awareness among users and impacted groups.", "UNESCO-V", ["ai_literacy_program", "awareness_materials"]),
    ("UNESCO-V10", "Multi-stakeholder governance", "AI governance should include diverse stakeholders and affected communities.", "UNESCO-V", ["stakeholder_governance_model", "consultation_records"]),
    ("UNESCO-V11", "Adaptive governance and collaboration", "Governance mechanisms should adapt to technological change and support collaboration.", "UNESCO-V", ["governance_review_cycle", "collaboration_mous"]),
    ("UNESCO-PA1", "Ethical impact assessment", "Organizations should perform ethical impact assessments before deployment of significant AI systems.", "UNESCO-PA", ["ethical_impact_assessment", "pre_deployment_review"]),
    ("UNESCO-PA2", "Data governance", "Data governance for AI should protect privacy and support fairness, quality, and accountability.", "UNESCO-PA", ["data_governance_policy", "data_quality_assessment"]),
    ("UNESCO-PA3", "Development and international cooperation", "Organizations and states should cooperate on responsible AI development and shared benefits.", "UNESCO-PA", ["cooperation_plan", "international_partnership_records"]),
]

UNESCO_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "high_impact_ai_use",
        "question_text": "Does your organization use AI in high-impact or rights-sensitive contexts?",
        "help_text": "UNESCO principles are especially important where fundamental rights impacts are possible.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "global_user_impact",
        "question_text": "Do your AI systems affect users across multiple jurisdictions?",
        "help_text": "Cross-jurisdiction deployment increases governance and transparency requirements.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

SINGAPORE_SECTIONS: list[dict[str, int | str]] = [
    {"code": "SING-1", "title": "Internal Governance", "order": 1},
    {"code": "SING-2", "title": "Human Involvement", "order": 2},
    {"code": "SING-3", "title": "Operations Management", "order": 3},
    {"code": "SING-4", "title": "Stakeholder Interaction", "order": 4},
]

SINGAPORE_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("SING-1.1", "Organizational structures and policies", "Organizations should define governance structures, policies, and accountability for AI deployment.", "SING-1", ["ai_governance_policy", "accountability_matrix"]),
    ("SING-1.2", "Determining level of human involvement", "Organizations should set risk-based human involvement thresholds for AI-assisted decisions.", "SING-1", ["risk_classification", "human_oversight_documentation"]),
    ("SING-1.3", "Operations management and risk assessment", "Organizations should assess AI risks holistically across lifecycle stages.", "SING-1", ["ai_risk_assessment", "lifecycle_documentation"]),
    ("SING-2.1", "Minimum human involvement", "High-risk AI decisions should include minimum human oversight and correction controls.", "SING-2", ["human_review_records", "override_mechanism"]),
    ("SING-2.2", "Ethical values in system design", "AI system design should incorporate fairness, transparency, and accountability values.", "SING-2", ["ethics_design_standard", "design_review_evidence"]),
    ("SING-2.3", "Training personnel", "Personnel should be trained on AI capabilities, limitations, and responsible use.", "SING-2", ["training_records", "ai_literacy_program"]),
    ("SING-3.1", "Risk assessment for data collection", "Organizations should assess risks in data collection, storage, and use for AI systems.", "SING-3", ["data_risk_assessment", "data_governance_documentation"]),
    ("SING-3.2", "Algorithmic model documentation", "AI models should be documented with training data, metrics, limitations, and intended use.", "SING-3", ["model_documentation", "model_cards", "performance_metrics"]),
    ("SING-3.3", "Testing and monitoring", "AI systems should be tested pre-deployment and monitored for drift, bias, and errors.", "SING-3", ["testing_records", "monitoring_configuration", "bias_testing"]),
    ("SING-4.1", "Transparency to stakeholders", "Organizations should provide meaningful disclosures to stakeholders about AI usage.", "SING-4", ["disclosure_documentation", "stakeholder_communications"]),
    ("SING-4.2", "Feedback channels", "Organizations should maintain channels for stakeholder feedback and issue escalation.", "SING-4", ["feedback_mechanism", "complaint_records"]),
    ("SING-4.3", "Review and redress pathways", "Organizations should provide review and redress pathways for materially adverse AI outcomes.", "SING-4", ["appeal_procedure", "redress_records"]),
]

SINGAPORE_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "deploys_customer_facing_ai",
        "question_text": "Does your organization deploy AI systems that materially affect customers or end users?",
        "help_text": "Customer-facing AI increases emphasis on transparency, redress, and governance controls.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "high_risk_decisions_automated",
        "question_text": "Are high-risk decisions partially or fully automated using AI?",
        "help_text": "If yes, stronger human oversight and monitoring obligations apply.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

G7_SECTIONS: list[dict[str, int | str]] = [
    {"code": "G7-HAP", "title": "Hiroshima AI Principles", "order": 1},
]

G7_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("G7-HAP-1", "Take appropriate measures for safety", "Developers and operators should identify, evaluate, and mitigate lifecycle AI risks.", "G7-HAP", ["ai_risk_assessment", "safety_evaluation_records"]),
    ("G7-HAP-2", "Identify and mitigate vulnerabilities", "Developers should identify vulnerabilities and misuse paths and implement mitigations.", "G7-HAP", ["vulnerability_assessment", "red_team_testing_records"]),
    ("G7-HAP-3", "Invest in responsible AI research", "Developers should invest in responsible AI research including safety and privacy-preserving methods.", "G7-HAP", ["responsible_ai_research_plan", "research_portfolio"]),
    ("G7-HAP-4", "Third-party discovery of vulnerabilities", "Developers should support mechanisms for third-party vulnerability disclosure and incident reports.", "G7-HAP", ["vulnerability_disclosure_policy", "responsible_disclosure_mechanism"]),
    ("G7-HAP-5", "Publish transparency reports", "Developers should publish regular transparency and safety evaluation reports for advanced AI systems.", "G7-HAP", ["transparency_report", "model_cards", "safety_evaluation_publication"]),
    ("G7-HAP-6", "Develop technical safety standards", "Developers and operators should support development and adoption of technical AI safety standards.", "G7-HAP", ["safety_standards_adoption", "standards_participation_records"]),
    ("G7-HAP-7", "Implement data governance", "Developers and operators should implement robust data governance including provenance controls.", "G7-HAP", ["data_governance_policy", "aibom", "data_provenance_documentation"]),
    ("G7-HAP-8", "Facilitate AI literacy", "Developers should implement mechanisms that inform users when interacting with AI systems.", "G7-HAP", ["ai_disclosure_mechanism", "user_documentation"]),
    ("G7-HAP-9", "Advance responsible AI among stakeholders", "Developers should promote responsible AI practices among ecosystem stakeholders.", "G7-HAP", ["stakeholder_program", "partner_guidance"]),
    ("G7-HAP-10", "Develop and deploy AI for global challenges", "Developers and operators should prioritize AI solutions for global societal challenges.", "G7-HAP", ["public_interest_use_cases", "impact_reports"]),
    ("G7-HAP-11", "Advance international cooperation", "Developers should support interoperable international standards and governance alignment.", "G7-HAP", ["international_standards_engagement", "cooperation_records"]),
]

G7_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "develops_advanced_ai",
        "question_text": "Does your organization develop or deploy advanced AI models?",
        "help_text": "The Hiroshima AI Process focuses on advanced AI developers and operators.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "publishes_safety_transparency",
        "question_text": "Does your organization publish AI safety or transparency reports?",
        "help_text": "Regular public reporting is a core expectation under G7 principles.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

ATLAS_SECTIONS: list[dict[str, int | str]] = [
    {"code": "ATLAS-RECON", "title": "Reconnaissance", "order": 1},
    {"code": "ATLAS-RD", "title": "Resource Development", "order": 2},
    {"code": "ATLAS-IA", "title": "Initial Access", "order": 3},
    {"code": "ATLAS-ML-ATK", "title": "ML Attack Staging", "order": 4},
    {"code": "ATLAS-EXFIL", "title": "Exfiltration", "order": 5},
    {"code": "ATLAS-IMPACT", "title": "Impact", "order": 6},
]

ATLAS_OBLIGATIONS: list[tuple[str, str, str, str, list[str]]] = [
    ("ATLAS-T0000", "Search for Victim's Publicly Available ML Artifacts", "Adversaries may search public sources for model weights, datasets, and ML documentation.", "ATLAS-RECON", ["ml_artifact_inventory", "public_disclosure_review"]),
    ("ATLAS-T0001", "Search Victim-Owned Websites", "Adversaries may inspect victim websites for AI system exposure details.", "ATLAS-RECON", ["public_surface_monitoring", "web_exposure_review"]),
    ("ATLAS-T0002", "Search Application Repositories", "Adversaries may search code and model repositories for exposed ML artifacts.", "ATLAS-RECON", ["repository_access_controls", "public_artifact_audit"]),
    ("ATLAS-T0007", "Acquire Public ML Artifacts", "Adversaries may obtain public ML artifacts to prepare attacks on victim systems.", "ATLAS-RD", ["artifact_access_logging", "artifact_integrity_checks"]),
    ("ATLAS-T0008", "Develop Capabilities", "Adversaries may develop bespoke tooling to target ML systems.", "ATLAS-RD", ["threat_intelligence", "ml_attack_simulation"]),
    ("ATLAS-T0010", "ML Supply Chain Compromise", "Adversaries may compromise model or data supply chains to gain access.", "ATLAS-IA", ["supply_chain_security_controls", "model_provenance_verification"]),
    ("ATLAS-T0012", "Valid Accounts", "Adversaries may use compromised accounts to access ML platforms and registries.", "ATLAS-IA", ["identity_controls", "privileged_access_reviews"]),
    ("ATLAS-T0019", "Publish Poisoned Datasets", "Adversaries may poison training data to manipulate model behavior.", "ATLAS-ML-ATK", ["dataset_integrity_controls", "training_data_validation"]),
    ("ATLAS-T0020", "Backdoor ML Model", "Adversaries may implant backdoors in models that activate under triggers.", "ATLAS-ML-ATK", ["model_integrity_verification", "backdoor_testing"]),
    ("ATLAS-T0043", "Craft Adversarial Data", "Adversaries may craft adversarial inputs to induce inference-time errors.", "ATLAS-ML-ATK", ["adversarial_robustness_testing", "input_validation_controls"]),
    ("ATLAS-T0024", "Exfiltration via ML Inference API", "Adversaries may perform model extraction via repeated inference queries.", "ATLAS-EXFIL", ["api_rate_limiting", "query_monitoring", "model_extraction_detection"]),
    ("ATLAS-T0025", "Model Inversion", "Adversaries may recover sensitive training information from model outputs.", "ATLAS-EXFIL", ["privacy_preserving_training", "differential_privacy_controls"]),
    ("ATLAS-T0029", "Denial of ML Service", "Adversaries may degrade AI availability through resource exhaustion or malformed inputs.", "ATLAS-IMPACT", ["availability_controls", "input_validation", "rate_limiting"]),
    ("ATLAS-T0031", "Evade ML Model", "Adversaries may evade detection or classification models at inference time.", "ATLAS-IMPACT", ["model_robustness_evaluation", "adversarial_testing_records"]),
    ("ATLAS-T0048", "Erode ML Model Integrity", "Adversaries may gradually reduce model integrity via poisoning or manipulation.", "ATLAS-IMPACT", ["model_monitoring_controls", "integrity_checking"]),
]

ATLAS_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "deploys_ml_systems",
        "question_text": "Does your organization deploy machine learning or AI models in production?",
        "help_text": "MITRE ATLAS is most applicable where production ML systems are used.",
        "triggers_scope": "all",
        "order_index": 1,
        "answer_type": "boolean",
    },
    {
        "question_key": "exposes_ml_apis",
        "question_text": "Does your organization expose ML model inference APIs to external parties?",
        "help_text": "External ML APIs increase exposure to extraction and adversarial attack patterns.",
        "triggers_scope": "partial",
        "order_index": 2,
        "answer_type": "boolean",
    },
]

OECD_EUAI_MAPPINGS: list[tuple[str, str, str]] = [
    ("OECD-P1.3", "EUAI-04", "related"),
    ("OECD-P1.4", "EUAI-07", "related"),
    ("OECD-P1.5", "EUAI-02", "related"),
]

IEEE_EUAI_MAPPINGS: list[tuple[str, str, str]] = [
    ("IEEE7001-6.1", "EUAI-10", "related"),
]

G7_EUAI_MAPPINGS: list[tuple[str, str, str]] = [
    ("G7-HAP-1", "EUAI-02", "related"),
    ("G7-HAP-2", "EUAI-07", "related"),
    ("G7-HAP-5", "EUAI-10", "related"),
    ("G7-HAP-7", "EUAI-03", "related"),
]

G7_OECD_MAPPINGS: list[tuple[str, str, str]] = [
    ("G7-HAP-1", "OECD-P1.4", "equivalent"),
    ("G7-HAP-5", "OECD-P1.3", "equivalent"),
    ("G7-HAP-11", "OECD-R2.5", "equivalent"),
]

ATLAS_NIST_AIRMF_MAPPINGS: list[tuple[str, str, str]] = [
    ("ATLAS-T0019", "GOVERN-6.2", "related"),
    ("ATLAS-T0020", "MEASURE-2.7", "related"),
    ("ATLAS-T0043", "MEASURE-2.8", "related"),
]
