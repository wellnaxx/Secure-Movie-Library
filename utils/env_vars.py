import os


def get_env_var(key: str, default: str | None = None) -> str:
    """
    Get environment variable with proper error handling.

    Args:
        key: Environment variable name
        default: Default value if not set (optional)

    Returns:
        str: Environment variable value

    Raises:
        EnvironmentError: If variable not set and no default provided
    """
    value = os.getenv(key, default)

    if value is None:
        raise OSError(f"Required environment variable '{key}' is not set!")

    return value
