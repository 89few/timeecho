from __future__ import annotations

import os
from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TimeEcho"
    app_env: str = "dev"
    debug: bool = Field(default=True, validation_alias="TIMEECHO_DEBUG")
    api_prefix: str = "/api"
    app_static_ui: bool = True

    database_url: str = "postgresql+asyncpg://timeecho:timeecho@localhost:5432/timeecho"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-this-jwt-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 14

    server_salt: str = "change-this-server-salt"
    encryption_secret: str = "change-this-encryption-secret-at-least-32-chars"
    encryption_key_version: int = Field(default=1, ge=1)

    dev_sms_code: str = "123456"
    phone_auto_registration_enabled: bool = False
    # Email verification is deliberately controlled by explicit switches.
    # Development can use the fixed code without SMTP.  In production, set
    # EMAIL_VERIFICATION_REQUIRED=true, EMAIL_ALLOW_UNVERIFIED_REGISTRATION=false
    # and provide the SMTP settings below.
    email_verification_required: bool = False
    email_allow_unverified_registration: bool = True
    email_dev_code_enabled: bool = True
    dev_email_code: str = "123456"
    email_code_expire_minutes: int = 10
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "TimeEcho"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    daily_letter_limit: int = 3
    daily_salvage_limit: int = 5
    daily_complaint_limit: int = 10
    chat_message_limit_per_minute: int = 3
    room_ttl_hours: int = 24
    dormant_after_days: int = 7
    rate_limits_enabled: bool = True
    community_simulation_enabled: bool = False
    community_simulation_min_seconds: int = 150
    community_simulation_max_seconds: int = 420

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self):
        if self.app_env.lower() != "prod":
            return self
        insecure = {
            "JWT_SECRET_KEY": self.jwt_secret_key.startswith("change-this")
            or self.jwt_secret_key.startswith("local-dev"),
            "SERVER_SALT": self.server_salt.startswith("change-this")
            or self.server_salt.startswith("local-dev"),
            "ENCRYPTION_SECRET": self.encryption_secret.startswith("change-this")
            or self.encryption_secret.startswith("local-dev"),
            "EMAIL_DEV_CODE_ENABLED": self.email_dev_code_enabled,
            "PHONE_AUTO_REGISTRATION_ENABLED": self.phone_auto_registration_enabled,
        }
        invalid = [name for name, failed in insecure.items() if failed]
        if invalid:
            raise ValueError(
                "production configuration is insecure: " + ", ".join(invalid)
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # Pytest sets APP_ENV=test before importing the application.  In that mode
    # settings must come only from the explicit test environment and defaults;
    # loading backend/.env could silently enable production SMTP or, more
    # importantly, replace other test assumptions with developer settings.
    env_file = None if os.environ.get("APP_ENV", "").lower() == "test" else ".env"
    return Settings(_env_file=env_file)


settings = get_settings()
