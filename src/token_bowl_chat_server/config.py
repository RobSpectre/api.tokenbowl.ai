"""Configuration settings for the chat server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    reload: bool = True  # Auto-reload on code changes (disable in production)

    # Webhook settings
    webhook_timeout: float = 10.0
    webhook_max_retries: int = 3

    # Message settings
    message_history_limit: int = 100

    # Stytch settings
    stytch_project_id: str | None = None
    stytch_secret: str | None = None
    stytch_environment: str = "test"  # 'test' or 'live'

    # Frontend URL for magic link redirects
    frontend_url: str = "http://localhost:3000"

    # Centrifugo settings (always enabled)
    centrifugo_api_url: str = "http://localhost:8001/api"
    centrifugo_api_key: str = "your-api-key-change-in-production"
    centrifugo_token_secret: str = "your-secret-key-change-in-production"
    centrifugo_ws_url: str = "ws://localhost:8001/connection/websocket"

    @property
    def stytch_enabled(self) -> bool:
        """Check if Stytch is configured and enabled."""
        return bool(self.stytch_project_id and self.stytch_secret)

    @property
    def stytch_env_normalized(self) -> str:
        """Get normalized Stytch environment (test or live only)."""
        env = self.stytch_environment.lower()
        # Handle cases like "test-eaxh" -> "test"
        if env.startswith("test"):
            return "test"
        elif env.startswith("live"):
            return "live"
        return "test"  # Default to test


# Global settings instance
settings = Settings()
