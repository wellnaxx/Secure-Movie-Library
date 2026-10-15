"""Shared validation for configuration values and environment parsing."""

from utils.env_vars import get_env_var


def require_text(name: str, value: str) -> None:
    """Reject blank settings without including their values in the error."""
    if not value.strip():
        raise ValueError(f"{name} must not be blank.")


def require_positive(name: str, value: int) -> None:
    """Require a strictly positive integer setting."""
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")


def read_int(name: str, default: str) -> int:
    """Read an integer environment setting with a descriptive parse error."""
    try:
        return int(get_env_var(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
