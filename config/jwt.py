"""JWT signing settings and their lazy, replaceable cache."""

from dataclasses import dataclass, field

from dotenv import load_dotenv

from config._validation import read_int, require_positive
from utils.env_vars import get_env_var


@dataclass(frozen=True, slots=True)
class JWTConfig:
    """Signing secret and token lifetimes; HS256 remains fixed in the handler."""

    secret_key: str = field(repr=False)
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    def __post_init__(self) -> None:
        """Require a usable signing secret and positive token lifetimes."""
        if len(self.secret_key.strip()) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 non-padding characters long.")
        require_positive("JWT_EXPIRATION_MINUTES", self.access_token_expire_minutes)
        require_positive("JWT_REFRESH_EXPIRATION_DAYS", self.refresh_token_expire_days)


_jwt_config: JWTConfig | None = None


def load_jwt_config() -> JWTConfig:
    """Read .env and the environment, validating a fresh configuration."""
    load_dotenv()
    return JWTConfig(
        secret_key=get_env_var("JWT_SECRET_KEY"),
        access_token_expire_minutes=read_int("JWT_EXPIRATION_MINUTES", "30"),
        refresh_token_expire_days=read_int("JWT_REFRESH_EXPIRATION_DAYS", "7"),
    )


def get_jwt_config() -> JWTConfig:
    """Return cached settings, loading them only after the first successful read."""
    global _jwt_config
    if _jwt_config is None:
        _jwt_config = load_jwt_config()
    return _jwt_config


def set_jwt_config(config: JWTConfig | None) -> None:
    """Replace cached settings, or clear them with None for a later reload."""
    global _jwt_config
    _jwt_config = config
