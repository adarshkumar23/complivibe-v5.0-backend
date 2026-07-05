from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

IP_ASSET_TYPES = ("patent", "trademark", "model_license", "dataset_license")
IP_ASSET_TYPE_PATTERN = "^(" + "|".join(IP_ASSET_TYPES) + ")$"

IP_ASSET_STATUSES = ("active", "expired", "terminated", "pending_renewal")
IP_ASSET_STATUS_PATTERN = "^(" + "|".join(IP_ASSET_STATUSES) + ")$"

# Common SPDX license identifiers (https://spdx.org/licenses/) plus a handful
# of widely-used non-SPDX "open weights" AI model license identifiers. This is
# a deliberately curated subset (the full SPDX list has 600+ entries), broad
# enough to cover what actually shows up in AI model/dataset licensing, while
# still forcing anything not recognized through an explicit non-OSS bucket
# rather than silently accepting arbitrary freeform text.
SPDX_LICENSE_IDS = frozenset(
    {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSD-3-Clause-Clear",
        "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
        "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
        "AGPL-3.0-only", "AGPL-3.0-or-later", "MPL-2.0", "ISC", "Unlicense",
        "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
        "EPL-2.0", "0BSD", "Zlib", "BSL-1.0", "Artistic-2.0", "WTFPL", "Python-2.0",
        "OFL-1.1",
        # Widely-used non-SPDX "open weights" AI model license identifiers.
        "OpenRAIL", "OpenRAIL-M", "OpenRAIL-S", "Llama-2-Community", "Llama-3-Community",
        "Gemma-Terms-Of-Use",
    }
)

# Non-open-source business terms: still a *recognized* bucket rather than
# arbitrary freeform text, required when the license isn't one of the
# taxonomy identifiers above (e.g. a bespoke commercial vendor contract).
NON_OSS_LICENSE_TERMS = frozenset({"Proprietary", "Custom", "Commercial", "Not-Applicable", "Public-Domain"})

KNOWN_LICENSE_IDENTIFIERS = SPDX_LICENSE_IDS | NON_OSS_LICENSE_TERMS
_KNOWN_LICENSE_LOOKUP = {value.lower(): value for value in KNOWN_LICENSE_IDENTIFIERS}


def _validate_terms_license_id(terms: dict | None) -> dict | None:
    """Reject an unrecognized `terms.license_id` instead of accepting freeform text.

    `terms` is otherwise an open JSON bag (seat counts, contract references,
    etc.), but `license_id` specifically identifies the licensing regime
    governing a model/dataset/IP asset. It is validated (case-insensitively,
    then normalized to canonical casing) against a known SPDX + common
    AI-model-license taxonomy, falling back to an explicit non-OSS bucket like
    "Proprietary"/"Custom", so it can be relied on for real compliance
    reporting instead of silently storing typos or made-up license names.
    """
    if not terms or "license_id" not in terms or terms["license_id"] is None:
        return terms
    raw = terms["license_id"]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("terms.license_id must be a non-empty string")
    canonical = _KNOWN_LICENSE_LOOKUP.get(raw.strip().lower())
    if canonical is None:
        raise ValueError(
            f"terms.license_id '{raw}' is not a recognized SPDX or license identifier. "
            "Use a known identifier (e.g. 'MIT', 'Apache-2.0', 'GPL-3.0-only') or, if the "
            "license isn't in the standard taxonomy, use 'Custom' or 'Proprietary' and record "
            "the actual license name/text in terms.license_name."
        )
    terms = dict(terms)
    terms["license_id"] = canonical
    return terms


class IPAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(pattern=IP_ASSET_TYPE_PATTERN)
    licensor: str | None = Field(default=None, max_length=255)
    licensee: str | None = Field(default=None, max_length=255)
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str = Field(default="active", pattern=IP_ASSET_STATUS_PATTERN)

    @field_validator("terms")
    @classmethod
    def _validate_terms(cls, value: dict | None) -> dict | None:
        return _validate_terms_license_id(value)


class IPAssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: str | None = Field(default=None, pattern=IP_ASSET_TYPE_PATTERN)
    licensor: str | None = Field(default=None, max_length=255)
    licensee: str | None = Field(default=None, max_length=255)
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str | None = Field(default=None, pattern=IP_ASSET_STATUS_PATTERN)

    @field_validator("terms")
    @classmethod
    def _validate_terms(cls, value: dict | None) -> dict | None:
        return _validate_terms_license_id(value)


class IPAssetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    asset_type: str
    licensor: str | None = None
    licensee: str | None = None
    terms: dict | None = None
    expiry_date: datetime | None = None
    linked_ai_system_id: UUID | None = None
    status: str
    created_by: UUID | None = None
    is_expiring_soon: bool = False
    is_expired: bool = False
    days_until_expiry: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AtRiskAISystem(BaseModel):
    id: UUID
    name: str
    lifecycle_status: str
    still_active: bool


class ExpiringIPAssetResponse(IPAssetResponse):
    at_risk_ai_system: AtRiskAISystem | None = None


class IPAssetSettingsResponse(BaseModel):
    id: UUID
    organization_id: UUID
    expiring_soon_window_days: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IPAssetSettingsUpdate(BaseModel):
    expiring_soon_window_days: int = Field(gt=0, le=3650)
