from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class TPRMIntelligenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Confirmed pending no/low-cost keys. Services must skip keyed signals when empty.
    HIBP_API_KEY: str = ""
    ALIENVAULT_OTX_API_KEY: str = ""
    OPENCORPORATES_API_KEY: str = ""

    # AbuseIPDB is free-tier but requires registration; kept separate from the confirmed three-key list.
    ABUSEIPDB_API_KEY: str = ""

    HTTP_TIMEOUT_SECONDS: float = 10.0


@lru_cache(maxsize=1)
def get_tprm_intelligence_settings() -> TPRMIntelligenceSettings:
    return TPRMIntelligenceSettings()
