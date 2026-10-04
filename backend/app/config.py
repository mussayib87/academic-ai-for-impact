from pathlib import Path
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / '.env', env_file_encoding='utf-8', extra='ignore', populate_by_name=True)

    app_name: str = 'Academic AI for Impact'
    api_v1_prefix: str = '/api/v1'
    database_url: str = f"sqlite:///{(BASE_DIR / 'backend' / 'data' / 'academic_ai.db').as_posix()}"
    jwt_secret: str = 'replace-this-development-secret-before-deploying'
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = Field(default=480, ge=1, le=10080)
    cors_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'
    upload_directory: Path = BASE_DIR / 'data' / 'uploads'
    max_upload_size: int = Field(default=10 * 1024 * 1024, ge=1)
    llm_model_name: str = Field(default='ollama:qwen3:8b', validation_alias=AliasChoices('LLM_MODEL_NAME'))
    llm_provider: str = Field(default='ollama', validation_alias=AliasChoices('LLM_PROVIDER'))
    ollama_base_url: str = Field(default='http://127.0.0.1:11434', validation_alias=AliasChoices('OLLAMA_BASE_URL', 'LLM_BASE_URL'))
    gemini_api_key: str = Field(default='', validation_alias=AliasChoices('GEMINI_API_KEY'))
    gemini_model_name: str = Field(default='gemini-2.0-flash', validation_alias=AliasChoices('GEMINI_MODEL_NAME'))
    llm_timeout_seconds: int = Field(default=300, ge=1, validation_alias=AliasChoices('LLM_TIMEOUT_SECONDS'))
    embedding_model_name: str = 'sentence-transformers/all-MiniLM-L6-v2'
    vector_store_path: Path = BASE_DIR / 'knowledge_base' / 'vector_store'

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if any(marker in value.lower() for marker in ('change-me', 'replace-this', 'your-secret')) and not _is_development():
            raise ValueError('Set JWT_SECRET to a unique secret outside development')
        return value

    @field_validator('cors_origins')
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        if '*' in value:
            raise ValueError('CORS_ORIGINS cannot contain a wildcard when credentials are enabled')
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def selected_llm_provider(self) -> str:
        return self.llm_provider.strip().lower()

    @property
    def llm_base_url(self) -> str:
        return self.ollama_base_url.rstrip('/')


def _is_development() -> bool:
    import os

    return os.getenv('APP_ENV', 'development').lower() in {'development', 'test'}


def get_settings() -> Settings:
    return Settings()
