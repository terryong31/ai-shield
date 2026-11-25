from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway configuration, read from the environment and an optional ``.env``.

    Supabase is required in every environment (spec 0046). Model providers are
    optional; the gateway degrades instead of failing. See
    docs/reference/configuration.md for the full table.
    """

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "AI S.H.I.E.L.D."
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    # Interactive docs and the schema route exist only in development (API-DOCS-001).
    # Unset means production, so a deployment never exposes them by accident.
    APP_ENV: Literal["development", "production"] = "production"

    GROQ_API_KEY: SecretStr | None = None
    GROQ_CHAT_MODEL: str = "openai/gpt-oss-120b"

    GOOGLE_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    TYPESAFE_API_KEY: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TYPESAFE_API_KEY", "JEV_API_KEY")
    )
    # Game AI Agent models per level tier (spec 0021). Standard defaults to the Gemini
    # model (or GROQ_CHAT_MODEL without a Google key); budget runs on Groq.
    GAME_MODEL_STANDARD: str | None = None
    GAME_MODEL_BUDGET: str = "openai/gpt-oss-20b"

    SUPABASE_URL: str = ""
    # Server-side key. The anon-key alias keeps older .env files working.
    SUPABASE_KEY: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_ANON_KEY")
    )

    # Public origin of the web client; confirmation emails link to
    # <WEB_BASE_URL>/auth/confirmed (spec 0027). Must be in Supabase's Redirect URLs.
    WEB_BASE_URL: str = "http://localhost:3000"

    # Clearance sessions (spec 0012). Admins are Supabase users with
    # app_metadata.role "admin"; without Supabase nobody can obtain clearance.
    SESSION_TTL_MINUTES: int = Field(default=480, gt=0)
    # Browsers accept Secure cookies on http://localhost; disable only for other plain-HTTP hosts.
    SESSION_COOKIE_SECURE: bool = True
    ALLOW_SELF_UPGRADE: bool = False
    TRUSTED_CLIENT_IP_HEADER: str | None = None
    TRUSTED_PROXY_SECRET: SecretStr | None = None
    CLEARANCE_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    CLEARANCE_WINDOW_MINUTES: int = Field(default=10, gt=0)

    # Optional Redis URL for sub-millisecond leaderboard caching (spec 0044);
    # required in production.
    REDIS_URL: SecretStr | None = None
    # Server secret for HMAC-signing temporary trained ML models (spec 0045);
    # required in production for POST /game/train.
    MODEL_SIGNING_KEY: SecretStr | None = None
    # Comma-separated in the environment. Includes IPv4/IPv6 loopback variants
    # that local dev servers (e.g. `nuxt dev` under Bun) may print.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
        "http://[::]:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _no_wildcard(cls, value: list[str]) -> list[str]:
        # CORS runs with credentials for the session cookie, which a wildcard would expose.
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins, not '*'")
        return value
