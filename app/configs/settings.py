from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_ENV: str = "dev"
    APP_NAME: str = "domainforge"

    # LLM
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    FALLBACK_LLM_PROVIDER: str = ""
    FALLBACK_LLM_MODEL: str = ""

    # Embedding
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BATCH_SIZE: int = 10  # DashScope 等厂商限制单批 ≤10

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://domainforge:domainforge@localhost:5432/domainforge"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Observability
    OTEL_SERVICE_NAME: str = "domainforge"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    # Security
    JWT_SECRET: str = "change-me-in-production"
    ADMIN_API_KEY: str = ""

    # Memory
    SHORT_TERM_MEMORY_SIZE: int = 20

    # RAG
    RAG_TOP_K: int = 5
    EMBEDDING_DIMENSION: int = 1024

    # Knowledge upload
    MAX_UPLOAD_FILES: int = 10
    MAX_UPLOAD_SIZE_MB: int = 20
    PREVIEW_SESSION_TTL: int = 600

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
