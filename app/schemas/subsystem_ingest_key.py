from typing import Literal

from pydantic import BaseModel, Field


class SubsystemIngestKeyProvisionRequest(BaseModel):
    key_type: Literal["lineage", "cookies", "consent", "security", "access_monitoring", "pam"] = Field(
        description="Which inbound machine-ingest subsystem this key authenticates.",
    )


class SubsystemIngestKeyProvisionResponse(BaseModel):
    api_key: str = Field(description="The raw ingest API key -- shown only once, store it securely.")
    key_type: str
    header_name: str = "X-CompliVibe-Key"


class SubsystemIngestKeyListResponse(BaseModel):
    provisioned_key_types: list[str]
