from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    APP_NAME: str = "Multibagger Bot"
    DB_NAME: str = "stocks.db"
    DEBUG: bool = False
    
    # Screener Config
    MIN_MARKET_CAP_CR: float = 100.0
    MAX_MARKET_CAP_CR: float = 5000.0
    MIN_PROMOTER_HOLDING: float = 50.0
    MIN_SALES_GROWTH: float = 15.0
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
