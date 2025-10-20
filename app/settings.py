from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    HA_URL: str = "http://homeassistant.local:8123"
    HA_TOKEN: str
    DB_URL: str = "sqlite:///./data/bridge.db"
    LOG_LEVEL: str = "INFO"

settings = Settings()