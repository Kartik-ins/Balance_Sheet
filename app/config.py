"""
Application Configuration
"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "Financial Assurance Platform"
    app_env: str = "development"
    debug: bool = True
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/assurance.db"
    
    # OpenRouter API (https://openrouter.ai)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-3-27b-it:free"  # Free Gemma 3 model
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Agent Thresholds
    auto_approve_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    escalation_risk_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    variance_zscore_threshold: float = Field(default=2.5, ge=0.0)
    variance_percent_threshold: float = Field(default=0.25, ge=0.0)
    
    # Materiality Thresholds
    materiality_high_threshold: float = 1_000_000
    materiality_medium_threshold: float = 100_000
    materiality_low_threshold: float = 10_000
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Redis (optional - for task queue)
    redis_url: str = "redis://localhost:6379/0"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
