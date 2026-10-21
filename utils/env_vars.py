"""Environment lookup that distinguishes an unset variable from an empty value."""

import os


def get_env_var(key: str, default: str | None = None) -> str:
    """
    Return a variable or its default without trimming or rejecting empty strings.

    This helper reads os.environ only; configuration loaders own .env loading
    and setting-specific validation. An explicitly empty variable wins over the
    default and is returned unchanged.

    Args:
        key: Environment variable name
        default: Default value if not set (optional)

    Returns:
        str: Environment variable value

    Raises:
        OSError: If the variable is unset and no non-None default is provided.
    """
    value = os.getenv(key, default)

    if value is None:
        raise OSError(f"Required environment variable '{key}' is not set!")

    return value
