ESG_TEMPLATE_TYPES = {"csrd_esrs", "gri", "tcfd", "issb"}


ESG_DISCLOSURE_TEMPLATES: dict[str, dict] = {
    "csrd_esrs": {
        "system_template_key": "esg-csrd-esrs",
        "name": "CSRD ESRS Disclosure Template",
        "standard": "CSRD ESRS",
        "sections": [
            {
                "key": "esrs_2_general_disclosures",
                "title": "ESRS 2 General Disclosures",
                "disclosure_points": [
                    {
                        "code": "BP-1",
                        "title": "General basis for preparation",
                        "expected_data": "Reporting boundary, consolidation basis, value-chain scope, and time horizons used in the sustainability statement.",
                    },
                    {
                        "code": "GOV-1",
                        "title": "Administrative, management and supervisory bodies",
                        "expected_data": "Composition, roles, sustainability competence, and oversight responsibilities of governance bodies.",
                    },
                    {
                        "code": "IRO-1",
                        "title": "Material impacts, risks and opportunities process",
                        "expected_data": "Methodology for identifying and assessing material impacts, risks, opportunities, thresholds, and stakeholder inputs.",
                    },
                ],
            },
            {
                "key": "environment",
                "title": "Environmental Topics",
                "disclosure_points": [
                    {
                        "code": "E1",
                        "title": "Climate change",
                        "expected_data": "Transition plan, Scope 1/2/3 greenhouse gas emissions, energy consumption, decarbonisation levers, climate risks, and targets.",
                    },
                    {
                        "code": "E2",
                        "title": "Pollution",
                        "expected_data": "Pollutants to air, water, and soil; substances of concern; policies, actions, targets, and incident controls.",
                    },
                    {
                        "code": "E5",
                        "title": "Resource use and circular economy",
                        "expected_data": "Material inflows, outflows, waste, circularity measures, resource efficiency targets, and product lifecycle actions.",
                    },
                ],
            },
            {
                "key": "social_and_governance",
                "title": "Social and Governance Topics",
                "disclosure_points": [
                    {
                        "code": "S1",
                        "title": "Own workforce",
                        "expected_data": "Workforce characteristics, working conditions, equal treatment, training, health and safety, and worker engagement.",
                    },
                    {
                        "code": "S2",
                        "title": "Workers in the value chain",
                        "expected_data": "Material impacts on value-chain workers, due-diligence processes, grievance channels, actions, and targets.",
                    },
                    {
                        "code": "G1",
                        "title": "Business conduct",
                        "expected_data": "Business conduct policies, anti-corruption and bribery controls, political engagement, payment practices, and supplier conduct.",
                    },
                ],
            },
        ],
    },
    "gri": {
        "system_template_key": "esg-gri-standards",
        "name": "GRI Standards Disclosure Template",
        "standard": "GRI Standards",
        "sections": [
            {
                "key": "universal_standards",
                "title": "Universal Standards",
                "disclosure_points": [
                    {
                        "code": "GRI 2",
                        "title": "General disclosures",
                        "expected_data": "Organizational details, entities included, reporting period, governance, strategy, policies, practices, and stakeholder engagement.",
                    },
                    {
                        "code": "GRI 3",
                        "title": "Material topics",
                        "expected_data": "Process to determine material topics, list of material topics, and management approach for each material topic.",
                    },
                ],
            },
            {
                "key": "topic_standards_environment",
                "title": "Environmental Topic Standards",
                "disclosure_points": [
                    {
                        "code": "GRI 302",
                        "title": "Energy",
                        "expected_data": "Energy consumption within and outside the organization, energy intensity, reductions, and product energy requirements.",
                    },
                    {
                        "code": "GRI 305",
                        "title": "Emissions",
                        "expected_data": "Scope 1, Scope 2, relevant Scope 3 emissions, emissions intensity, reductions, and ozone-depleting substances.",
                    },
                    {
                        "code": "GRI 306",
                        "title": "Waste",
                        "expected_data": "Waste generation, significant waste impacts, waste diverted from disposal, waste directed to disposal, and management actions.",
                    },
                ],
            },
            {
                "key": "topic_standards_social_governance",
                "title": "Social and Governance Topic Standards",
                "disclosure_points": [
                    {
                        "code": "GRI 403",
                        "title": "Occupational health and safety",
                        "expected_data": "Health and safety management system, hazard identification, worker participation, training, incidents, and work-related injuries.",
                    },
                    {
                        "code": "GRI 405",
                        "title": "Diversity and equal opportunity",
                        "expected_data": "Governance-body and employee diversity by category, age group, gender, and other diversity indicators.",
                    },
                    {
                        "code": "GRI 205",
                        "title": "Anti-corruption",
                        "expected_data": "Operations assessed for corruption risks, anti-corruption communication and training, and confirmed incidents and actions.",
                    },
                ],
            },
        ],
    },
    "tcfd": {
        "system_template_key": "esg-tcfd",
        "name": "TCFD Climate Disclosure Template",
        "standard": "TCFD",
        "sections": [
            {
                "key": "governance",
                "title": "Governance",
                "disclosure_points": [
                    {
                        "code": "TCFD-GOV-A",
                        "title": "Board oversight",
                        "expected_data": "Board oversight of climate-related risks and opportunities, committee responsibilities, cadence, and decision inputs.",
                    },
                    {
                        "code": "TCFD-GOV-B",
                        "title": "Management role",
                        "expected_data": "Management responsibilities for assessing and managing climate-related risks and opportunities.",
                    },
                ],
            },
            {
                "key": "strategy",
                "title": "Strategy",
                "disclosure_points": [
                    {
                        "code": "TCFD-STR-A",
                        "title": "Climate risks and opportunities",
                        "expected_data": "Short-, medium-, and long-term climate-related risks and opportunities identified for the organization.",
                    },
                    {
                        "code": "TCFD-STR-C",
                        "title": "Scenario resilience",
                        "expected_data": "Resilience of strategy under climate scenarios, including a 2C or lower scenario where relevant.",
                    },
                ],
            },
            {
                "key": "risk_management",
                "title": "Risk Management",
                "disclosure_points": [
                    {
                        "code": "TCFD-RM-A",
                        "title": "Risk identification and assessment",
                        "expected_data": "Processes for identifying and assessing climate-related risks and their relative significance.",
                    },
                    {
                        "code": "TCFD-RM-C",
                        "title": "Integration into enterprise risk management",
                        "expected_data": "How climate risk processes are integrated into overall risk management.",
                    },
                ],
            },
            {
                "key": "metrics_targets",
                "title": "Metrics and Targets",
                "disclosure_points": [
                    {
                        "code": "TCFD-MT-A",
                        "title": "Climate metrics",
                        "expected_data": "Metrics used to assess climate-related risks and opportunities in line with strategy and risk process.",
                    },
                    {
                        "code": "TCFD-MT-B",
                        "title": "Greenhouse gas emissions",
                        "expected_data": "Scope 1, Scope 2, and if appropriate Scope 3 emissions and related risks.",
                    },
                ],
            },
        ],
    },
    "issb": {
        "system_template_key": "esg-issb-s1-s2",
        "name": "ISSB IFRS S1/S2 Disclosure Template",
        "standard": "ISSB IFRS S1/S2",
        "sections": [
            {
                "key": "ifrs_s1_general_sustainability",
                "title": "IFRS S1 General Sustainability-related Disclosures",
                "disclosure_points": [
                    {
                        "code": "S1-GOV",
                        "title": "Governance",
                        "expected_data": "Governance body or individual oversight of sustainability-related risks and opportunities and management's role.",
                    },
                    {
                        "code": "S1-STR",
                        "title": "Strategy",
                        "expected_data": "Sustainability-related risks and opportunities that could reasonably affect prospects, business model, value chain, and financial planning.",
                    },
                    {
                        "code": "S1-MET",
                        "title": "Metrics and targets",
                        "expected_data": "Metrics required by applicable standards, entity-specific metrics, and progress toward sustainability targets.",
                    },
                ],
            },
            {
                "key": "ifrs_s2_climate",
                "title": "IFRS S2 Climate-related Disclosures",
                "disclosure_points": [
                    {
                        "code": "S2-GHG",
                        "title": "Greenhouse gas emissions",
                        "expected_data": "Absolute Scope 1, Scope 2, and Scope 3 emissions, measurement approach, categories, and financed emissions where applicable.",
                    },
                    {
                        "code": "S2-TRANSITION",
                        "title": "Climate transition planning",
                        "expected_data": "Climate-related transition plans, assumptions, dependencies, resources, and progress against plans.",
                    },
                    {
                        "code": "S2-RESILIENCE",
                        "title": "Climate resilience",
                        "expected_data": "Climate resilience assessment, scenario analysis inputs, time horizons, and implications for strategy and financial position.",
                    },
                ],
            },
        ],
    },
}
