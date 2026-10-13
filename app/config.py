import os
from typing import List
from pydantic_settings import BaseSettings


_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = os.path.join(_backend_dir, "footwear_erp.db").replace("\\", "/")


class Settings(BaseSettings):
    PROJECT_NAME: str = "MK Footwear Planning"
    COMPANY_NAME: str = "MK Footwear Planning"
    APP_TAGLINE: str = "Plan • Produce • Deliver"
    DESCRIPTION: str = "Footwear Production Planning & Management"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        f"sqlite:///{_default_db}"  # Default fallback for standalone / test
    )
    
    # Security
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", 
        "footwear-erp-production-planning-secret-key-change-in-prod-2026"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours for factory shift
    
    # Timezone & Cutoff
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Dhaka")
    DEFAULT_CUTOFF_HOUR: int = 18
    DEFAULT_CUTOFF_MINUTE: int = 0
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
