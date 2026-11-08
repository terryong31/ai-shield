from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway configuration, read from the environment and an optional ``.env``.

    Every provider is optional; the gateway degrades instead of failing.
    See docs/reference/configuration.md for the full table.
    """

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "AI S.H.I.E.L.D."
    VERSION: str = "0.2.0"
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    GROQ_API_KEY: SecretStr | None = None
    GROQ_GUARD_MODEL: str = "llama-guard-3-8b"
    GROQ_DEBATE_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_CHAT_MODEL: str = "llama-3.3-70b-versatile"

    GOOGLE_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # Game AI Agent models per level tier (spec 0021). Standard defaults to the Gemini
    # model (or GROQ_CHAT_MODEL without a Google key); budget runs on Groq.
    GAME_MODEL_STANDARD: str | None = None
    GAME_MODEL_BUDGET: str = "llama-3.1-8b-instant"

    SUPABASE_URL: str = ""
    # Server-side key. The anon-key alias keeps older .env files working.
    SUPABASE_KEY: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_ANON_KEY")
    )

    # Demo stand-in for RBAC. Unset means nobody can obtain GRANTED clearance.
    SECURE_PASSPHRASE: SecretStr | None = None

    # Clearance sessions (spec 0012), stored in SQLITE_PATH.
    SESSION_TTL_MINUTES: int = Field(default=480, gt=0)
    # Browsers accept Secure cookies on http://localhost; disable only for other plain-HTTP hosts.
    SESSION_COOKIE_SECURE: bool = True
    CLEARANCE_MAX_ATTEMPTS: int = Field(default=5, gt=0)
    CLEARANCE_WINDOW_MINUTES: int = Field(default=10, gt=0)

    # Audit log file used whenever Supabase is not configured.
    SQLITE_PATH: Path = Path("var/shield.db")

    FEEDBACK_PATH: Path = Path("var/feedback.csv")

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
