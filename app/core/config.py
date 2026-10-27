"""Application settings, read once from environment variables.

Nothing here is required to boot: the placeholders let the service start before
any broker credentials exist. See .env.example for the supported variables.
"""

import os
from dataclasses import dataclass, field


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Trade Agent"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    paper_trading: bool = field(default_factory=lambda: _flag("PAPER_TRADING"))
    broker_api_key: str = field(default_factory=lambda: os.getenv("BROKER_API_KEY", ""))
    broker_api_secret: str = field(default_factory=lambda: os.getenv("BROKER_API_SECRET", ""))

    @property
    def broker_configured(self) -> bool:
        return bool(self.broker_api_key and self.broker_api_secret)


settings = Settings()
