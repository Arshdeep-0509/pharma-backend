from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Set in backend/.env; points at the local PostgreSQL server.
    database_url: str
    # Comma-separated list of origins allowed to call the API (the Next.js frontend).
    cors_origins: str = "http://localhost:3000"

    # Signs login tokens. Must be a long random secret; changing it logs everyone out.
    jwt_secret: str
    session_hours: int = 12
    # Set true in production (HTTPS) so the session cookie is only sent over TLS.
    cookie_secure: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
