from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/pulseup.db"

    # Application
    base_url: str = "http://localhost:8001"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
