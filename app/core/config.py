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
    # SQLAlchemy connection-pool sizing (per process). The library defaults
    # (pool_size=5, max_overflow=10 -> 15) saturate under concurrent load and
    # cascade into 30s QueuePool timeouts. Sized so 2 gunicorn workers stay well
    # under Postgres max_connections (100). Override via env for other topologies.
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    SECRET_KEY: str = Field(min_length=16)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    BASE_URL: str = "http://localhost:8000"
    SSO_ENABLED: bool = True
    # Client-IP extraction for the org IP allowlist and session/audit records.
    # Both default SAFE: with the defaults, only the raw socket peer is trusted and
    # no forwarded header (X-Forwarded-For / CF-Connecting-IP) is ever believed.
    #
    # BEHIND_CLOUDFLARE_TUNNEL: set True only when this backend is reachable solely
    #   through a Cloudflare tunnel/proxy. When set, CF-Connecting-IP (which the
    #   Cloudflare edge sets to the real client and rejects if a client tries to
    #   supply it -- verified empirically) is trusted, but only after the immediate
    #   upstream hop is confirmed to be Cloudflare or a local tunnel hop.
    # TRUSTED_PROXY_COUNT: number of trusted reverse proxies in front of the app for
    #   non-Cloudflare deployments. The client IP is taken as the Nth value from the
    #   RIGHT of X-Forwarded-For (parts[-N]), so client-prepended spoof values are
    #   never read. 0 means never trust X-Forwarded-For.
    BEHIND_CLOUDFLARE_TUNNEL: bool = False
    TRUSTED_PROXY_COUNT: int = 0
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REDIS_URL: str | None = None
    # Per-org RateLimitConfig lookups are cached in-process for this many seconds
    # so the hot request path does not hit the DB on every org-scoped request.
    # A config change via the admin API invalidates its own cache entry
    # immediately in-process; this TTL only bounds staleness across worker
    # processes (each has its own cache). See app/core/rate_limiter.py.
    RATE_LIMIT_CONFIG_CACHE_TTL_SECONDS: int = 45
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
    # Azure OpenAI is the fallback provider (Groq is primary). ENDPOINT is the
    # OpenAI-compatible "v1" base, e.g. https://<resource>.services.ai.azure.com/openai/v1
    # (the SDK appends /responses). DEPLOYMENT_NAME is the model id passed to the
    # Responses API (e.g. gpt-5.1) -- env-configurable so a model change is config,
    # not code. No api-version is needed on the v1 surface.
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str = ""
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None
    # gpt-5.1 is a reasoning model: reasoning tokens are spent before the visible
    # answer, so this must be generous or structured output truncates to empty
    # (which raises and fails the chain). Mirrors the GROQ_MAX_TOKENS rationale.
    AZURE_OPENAI_MAX_TOKENS: int = 8192
    # Cloudflare R2 object storage for evidence files (S3-compatible API). Follows
    # the same env-configurable, gracefully-inert discipline as the Azure leg above:
    # the feature is active ONLY when all four of ACCOUNT_ID/ACCESS_KEY_ID/
    # SECRET_ACCESS_KEY/BUCKET_NAME are populated; otherwise file upload/retrieval
    # returns a clear "storage not configured" error and the existing metadata/URL
    # evidence path keeps working untouched. Never hardcode credentials.
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    # Optional explicit endpoint override; if blank it is derived as
    # https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com (standard R2 S3 endpoint).
    R2_ENDPOINT_URL: str | None = None
    # Retrieval is via short-lived presigned GET URLs only (never public objects).
    R2_SIGNED_URL_TTL_SECONDS: int = 300
    # Max evidence file size. 25 MiB comfortably covers compliance artifacts
    # (PDFs, screenshots, spreadsheets, signed policy docs); env-tunable.
    EVIDENCE_MAX_UPLOAD_BYTES: int = 26_214_400
    GROQ_API_KEY: str = ""
    # Groq chat model. Env-configurable so a Groq model deprecation is a config
    # change, not a code change. Default is Groq's current production-tier
    # reasoning flagship; do NOT point this at preview-only models (e.g. qwen).
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # gpt-oss is a reasoning model: reasoning tokens are consumed from the
    # completion budget BEFORE the visible answer, so the cap must leave room for
    # both or the visible text is silently truncated to empty. 8192 gives ample
    # headroom for reasoning + a policy/risk draft while staying well under the
    # model's 65,536 max-completion ceiling.
    GROQ_MAX_TOKENS: int = 8192
    MLOPS_CONFIG_ENCRYPTION_KEY: str | None = None
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "complivibe-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    MEILISEARCH_ENABLED: bool = True
    MEILISEARCH_URL: str = "http://127.0.0.1:7700"
    MEILISEARCH_API_KEY: str | None = None
    MEILISEARCH_TIMEOUT_SECONDS: int = 3
    VAULT_ADDR: str = ""
    VAULT_TOKEN: str = ""
    VAULT_TRANSIT_KEY_NAME: str = "complivibe-secrets"
    VAULT_REQUEST_TIMEOUT_SECONDS: float = 5.0

    # Open Policy Agent (OPA) for agentic policy-derivation / guardrail checks
    # (patent P3). This is real new infrastructure, in the same class as Redis
    # and Vault: OPA_SERVER_URL points at a running OPA HTTP server used for
    # runtime allow/deny evaluation of the check-action endpoint; OPA_BINARY_PATH
    # is the `opa` CLI used at guardrail-creation time to compile-check the
    # derived Rego (`opa check --strict`). Both degrade gracefully when unset:
    # guardrail creation returns a clear "OPA not configured" error and the
    # check-action endpoint fails closed (deny), rather than 500-ing or silently
    # allowing. See app/ai_governance/services/policy_derivation/.
    OPA_SERVER_URL: str | None = None
    OPA_BINARY_PATH: str = "opa"
    OPA_REQUEST_TIMEOUT_SECONDS: float = 2.0

    # P2 governance knowledge-graph: max hops for the obligation-derivation
    # recursive CTE (config, not a patent claim element).
    GOVERNANCE_GRAPH_MAX_TRAVERSAL_DEPTH: int = 6

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
