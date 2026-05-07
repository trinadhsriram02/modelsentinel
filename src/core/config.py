from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    groq_api_key: str = ""
    jwt_secret_key: str = "modelsentinel-secret-change-in-production"
    upload_dir: str = "uploaded_models"
    db_path: str = "src/data/scans.db"
    frontend_url: str = "http://localhost:8501"
    max_file_size_mb: int = 500
    risk_threshold: int = 40
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 100

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()