from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # app
    app_name: str = "MyApp"
    debug_mode: bool = False
    debug: bool = False
    max_plan_iterations: int = 3
    max_step_num: int = 3
    enable_background_investigation: bool = True
    enable_clarification: Optional[bool] = None
    max_clarification_rounds: Optional[int] = None

    # --- API keys ---
    KIMI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    DEEPSEEK_KEY: str = ""
    HF_TOKEN: str = ""

    OLLAMA_API_URL: str = "http://localhost:11434"
    
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# create a singleton settings instance to import across the project
settings = Settings()