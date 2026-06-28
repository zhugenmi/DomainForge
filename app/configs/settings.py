from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

_DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    # App
    APP_ENV: Literal["dev", "prod"] = "dev"
    APP_NAME: str = "domainforge"

    # LLM
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    FALLBACK_LLM_PROVIDER: str = ""
    FALLBACK_LLM_MODEL: str = ""
    # 可用模型列表（逗号分隔），供 agent 表单下拉；为空则回退到 [DEFAULT_LLM_MODEL]
    AVAILABLE_MODELS: str = ""

    # Embedding
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BATCH_SIZE: int = 10  # DashScope 等厂商限制单批 ≤10
    EMBEDDING_BATCH_INTERVAL: float = 0.2  # 批次间节流（秒），规避账户级 RPM 限制

    # Rerank
    RERANK_BASE_URL: str = ""
    RERANK_API_KEY: str = ""
    RERANK_MODEL: str = "bge-reranker-base"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://domainforge:domainforge@localhost:5432/domainforge"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True

    # Observability
    OTEL_SERVICE_NAME: str = "domainforge"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_TRACES_SAMPLER_RATIO: float = 1.0  # 1.0 全量采样，生产建议 0.1

    # Evals
    EVALS_LLM_JUDGE: bool = False  # LLM-as-judge 指标开关（每次 eval 多 2 次 LLM 调用）

    # MCP（可选）：配置后启动时拉取远端工具注册到 ToolRegistry
    MCP_SERVER_URL: str = ""
    MCP_LIST_TIMEOUT: float = 5.0  # 启动时 list_tools 超时，失败跳过不阻塞

    # 敏感工具二次确认
    SENSITIVE_TOOL_CONFIRM_TIMEOUT: int = 60  # 流式确认超时（秒），超时跳过该 tool_call

    # Security
    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_SECRET_OVERRIDE: bool = False  # 紧急回滚：跳过生产强密钥校验
    ADMIN_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Memory
    SHORT_TERM_MEMORY_SIZE: int = 20

    # RAG
    RAG_TOP_K: int = 5
    EMBEDDING_DIMENSION: int = 1024

    # Knowledge upload
    MAX_UPLOAD_FILES: int = 10
    MAX_UPLOAD_SIZE_MB: int = 20
    PREVIEW_SESSION_TTL: int = 600

    # Chat input enhancements
    CHAT_ATTACHMENT_TTL: int = 600       # 聊天附件 store TTL（秒）
    MAX_CHAT_ATTACHMENTS: int = 5        # 单次聊天附件数上限
    MAX_CHAT_ATTACHMENT_MB: int = 20     # 单文件大小上限（MB）

    # Skills
    SKILLS_INSTALLED_ROOT: str = "skills/installed"
    SKILLS_MARKETPLACE_ROOT: str = "skills/marketplace"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        # 支持 env 里逗号分隔："http://a,http://b"
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _check_secrets(self):
        # 生产模式强制强 JWT 密钥，除非显式 override
        if self.APP_ENV == "prod" and not self.JWT_SECRET_OVERRIDE:
            if self.JWT_SECRET == _DEFAULT_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET 仍是默认值，生产环境必须替换。"
                    "用 `openssl rand -hex 32` 生成 32+ 字节随机串，或设 JWT_SECRET_OVERRIDE=true 紧急跳过。"
                )
            if len(self.JWT_SECRET) < 32:
                raise ValueError(
                    f"JWT_SECRET 长度 {len(self.JWT_SECRET)} < 32 字节，不满足 HS256 安全要求。"
                    "用 `openssl rand -hex 32` 生成，或设 JWT_SECRET_OVERRIDE=true 紧急跳过。"
                )
        return self

    def is_secret_default(self, key: str) -> bool:
        """启动检查用：某密钥是否仍为默认/空值。"""
        if key == "JWT_SECRET":
            return self.JWT_SECRET == _DEFAULT_JWT_SECRET
        if key == "ADMIN_API_KEY":
            return self.ADMIN_API_KEY == ""
        if key == "LLM_API_KEY":
            return self.LLM_API_KEY == ""
        return False


settings = Settings()
