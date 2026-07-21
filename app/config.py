from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG_SQL: bool = False
    PORT: int = 3000
    DB_PATH: str = "./storage/data.db"
    REDIS_URL: str | None = None
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX: int = 100
    RATE_LIMIT_WINDOW_MS: int = 60000
    ADMIN_KEY: str = ""
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100
    MAX_BODY_SIZE: int = 1048576
    TRUSTED_PROXIES: list[str] = ["127.0.0.1", "::1"]
    SEED_API_BASE_URL: str = "https://jsonplaceholder.typicode.com"

    @property
    def rate_limit_window_sec(self) -> int:
        return -(-self.RATE_LIMIT_WINDOW_MS // 1000)

    @property
    def redis_opts(self) -> dict:
        if self.REDIS_URL:
            return {"url": self.REDIS_URL}
        return {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "db": self.REDIS_DB,
            "password": self.REDIS_PASSWORD,
        }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
