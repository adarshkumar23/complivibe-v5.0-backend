from __future__ import annotations

FIDES_CATEGORY_MAP = {
    "user.email": "personal_data",
    "user.name": "personal_data",
    "user.phone_number": "personal_data",
    "user.address": "personal_data",
    "user.date_of_birth": "personal_data",
    "user.unique_id": "personal_data",
    "user.government_id": "sensitive_personal_data",
    "user.financial": "financial_data",
    "user.payment": "financial_data",
    "user.bank_account": "financial_data",
    "user.credit_card": "financial_data",
    "user.health_and_medical": "health_data",
    "user.medical_condition": "health_data",
    "user.genetic": "sensitive_personal_data",
    "user.biometric": "sensitive_personal_data",
    "user.race": "sensitive_personal_data",
    "user.ethnicity": "sensitive_personal_data",
    "user.religious_belief": "sensitive_personal_data",
    "user.sexual_orientation": "sensitive_personal_data",
    "user.political_opinion": "sensitive_personal_data",
    "system": "operational_data",
    "system.operations": "operational_data",
    "system.authentication": "operational_data",
    "business": "intellectual_property",
}

FIDES_SENSITIVITY_MAP = {
    "personal_data": "confidential",
    "sensitive_personal_data": "restricted",
    "financial_data": "restricted",
    "health_data": "restricted",
    "operational_data": "internal",
    "intellectual_property": "confidential",
}


class FidesParser:
    def parse(self, payload: dict | list) -> list[dict]:
        if isinstance(payload, dict):
            datasets = payload.get("dataset") or payload.get("datasets") or []
        elif isinstance(payload, list):
            datasets = payload
        else:
            return []

        assets: list[dict] = []
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            fides_key = str(ds.get("fides_key") or "").strip()
            name = str(ds.get("name") or fides_key or "Unnamed Dataset").strip()
            description = str(ds.get("description") or "").strip()

            categories = set(ds.get("data_categories") or [])
            for collection in ds.get("collections") or []:
                if not isinstance(collection, dict):
                    continue
                for field in collection.get("fields") or []:
                    if not isinstance(field, dict):
                        continue
                    for category in field.get("data_categories") or []:
                        categories.add(category)

            cv_classes: set[str] = set()
            for category in categories:
                if category in FIDES_CATEGORY_MAP:
                    cv_classes.add(FIDES_CATEGORY_MAP[category])
                    continue
                for known, mapped in FIDES_CATEGORY_MAP.items():
                    if category.startswith(known.split(".")[0]):
                        cv_classes.add(mapped)
                        break

            priority = [
                "sensitive_personal_data",
                "health_data",
                "financial_data",
                "personal_data",
                "intellectual_property",
                "operational_data",
            ]
            classification_type = "unclassified"
            for value in priority:
                if value in cv_classes:
                    classification_type = value
                    break

            assets.append(
                {
                    "name": name,
                    "description": description,
                    "fides_key": fides_key,
                    "classification_type": classification_type,
                    "sensitivity_tier": FIDES_SENSITIVITY_MAP.get(classification_type),
                    "raw_categories": sorted(str(item) for item in categories),
                    "collection_count": len(ds.get("collections") or []),
                }
            )

        return assets
