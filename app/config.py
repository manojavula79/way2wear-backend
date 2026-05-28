from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Way2Wear"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    SECRET_KEY: str = "change-this-in-production-minimum-32-chars"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:4200"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://way2wear:way2wear123@localhost:5432/way2wear_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_MAX_TOKENS: int = 1500

    # JWT
    JWT_SECRET_KEY: str = "jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Amazon
    AMAZON_AFFILIATE_TAG: str = "way2wear-20"

    # App Limits
    MAX_SESSIONS_PER_USER: int = 10
    MAX_MESSAGES_PER_SESSION: int = 100
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW: int = 60

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL for Alembic migrations"""
        return self.DATABASE_URL.replace("+asyncpg", "")

        FIREBASE_PROJECT_ID: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

    # # SMS
SMS_PROVIDER: str = ""
FAST2SMS_API_KEY: str = ""
MSG91_AUTH_KEY: str = ""
MSG91_SENDER_ID: str = "W2WEAR"
MSG91_TEMPLATE_ID: str = ""
TWILIO_ACCOUNT_SID: str = ""
TWILIO_AUTH_TOKEN: str = ""
TWILIO_FROM_NUMBER: str = ""
