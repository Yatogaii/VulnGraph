from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # app
    app_name: str = "MyApp"
    debug_mode: bool = False
    debug: bool = False
    max_plan_iterations: int = 1
    max_step_num: int = 3
    enable_background_investigation: bool = True
    enable_clarification: Optional[bool] = None
    max_clarification_rounds: Optional[int] = None


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# create a singleton settings instance to import across the project
settings = Settings()