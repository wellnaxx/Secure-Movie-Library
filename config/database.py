"""Database connection settings and their lazy, replaceable cache."""

from dataclasses import dataclass, field

from dotenv import load_dotenv

from config._validation import read_int, require_positive, require_text
from utils.env_vars import get_env_var


@dataclass(frozen=True, slots=True)
class DBConfig:
    """MariaDB connection identity, TCP port, and timeout in seconds.

    Host, database name, and username must be nonblank; password may be empty and
    is excluded from repr. Port is 1-65535 and connect_timeout must be positive.
    Values are validated without trimming the credentials passed to the driver.
    """

    host: str
    name: str
    user: str
    password: str = field(repr=False)
    port: int = 3306
    connect_timeout: int = 5

    def __post_init__(self) -> None:
        """Validate connection identity, port range, and timeout."""
        require_text("DB_HOST", self.host)
        require_text("DB_NAME", self.name)
        require_text("DB_USER", self.user)
        if not 1 <= self.port <= 65535:
            raise ValueError("DB_PORT must be between 1 and 65535.")
        require_positive("DB_CONNECT_TIMEOUT", self.connect_timeout)


_db_config: DBConfig | None = None


def load_db_config() -> DBConfig:
    """Read .env and the environment, validating a fresh configuration."""
    load_dotenv()
    return DBConfig(
        host=get_env_var("DB_HOST"),
        name=get_env_var("DB_NAME"),
        user=get_env_var("DB_USER"),
        password=get_env_var("DB_PASSWORD"),
        port=read_int("DB_PORT", "3306"),
        connect_timeout=read_int("DB_CONNECT_TIMEOUT", "5"),
    )


def get_db_config() -> DBConfig:
    """Return cached settings, loading them only after the first successful read."""
    global _db_config
    if _db_config is None:
        _db_config = load_db_config()
    return _db_config


def set_db_config(config: DBConfig | None) -> None:
    """Replace cached settings, or clear them with None for a later reload."""
    global _db_config
    _db_config = config
