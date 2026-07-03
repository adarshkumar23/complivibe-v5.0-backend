from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "CompliVibe Backend"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+psycopg://complivibe_user:change_me@localhost:5432/complivibe"
    SECRET_KEY: str = Field(min_length=16)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    BASE_URL: str = "http://localhost:8000"
    SSO_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REDIS_URL: str | None = None
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    WEBHOOK_URL: str = "https://complivibe.in/api/webhook/razorpay"
    TRIAL_DAYS: int = 14
    FRONTEND_URL: str = "https://app.complivibe.in"
    AWS_SES_ACCESS_KEY_ID: str = ""
    AWS_SES_SECRET_ACCESS_KEY: str = ""
    AWS_SES_REGION: str = "ap-south-1"
    AWS_SES_FROM_EMAIL: str = ""
    AWS_SES_FROM_NAME: str = "CompliVibe"
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    FERNET_SECRET_KEY: str = ""
    ACTIVATION_TOKEN_EXPIRE_HOURS: int = 72
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    FILE_STORAGE_PATH: str = "/tmp/complivibe_exports/"
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str = ""
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None
    GROQ_API_KEY: str = ""
    MLOPS_CONFIG_ENCRYPTION_KEY: str | None = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
