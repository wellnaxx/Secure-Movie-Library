"""Immutable, validated settings loaded lazily for each application component.

Each module exposes load, get, and set functions. Load reads the environment;
get caches the result; set overrides it or clears the cache when passed None.

Database, JWT, OMDb, and logging caches are independent and process-local.
load_dotenv preserves existing environment variables. Missing required values
raise OSError; field validation raises ValueError, except a short JWT secret
raises RuntimeError. Failed loads are not cached. Settings are immutable, but
cache overrides are shared mutable process state: use them during setup/tests,
not as request-specific configuration. Replacing logging settings alone does
not replace installed handlers; configure_logging performs that step at startup.
"""
