"""
database.py - Low-level database access layer.

All read functions return dicts keyed by column name so callers always
access results by name, never by positional index.

Public API
----------
read_query(sql, params)     -> list[dict]
read_query_one(sql, params) -> dict | None
insert_query(sql, params)   -> int   (last inserted row id)
write_query(sql, params)    -> int   (affected row count)
"""

from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass
from dotenv import load_dotenv
from utils.env_vars import get_env_var
from utils.errors import DatabaseError

logger = logging.getLogger(__name__)

load_dotenv()

if TYPE_CHECKING:  # pragma: no cover
    from mariadb.connections import Connection  # type: ignore
else:  # pragma: no cover
    Connection = Any  # noqa: N816


@dataclass(frozen=True)
class DBConfig:
    host: str
    name: str
    user: str
    password: str
    port: int = 3306
    connect_timeout: int = 5


def load_db_config() -> DBConfig:
    return DBConfig(
        host=get_env_var("DB_HOST"),
        name=get_env_var("DB_NAME"),
        user=get_env_var("DB_USER"),
        password=get_env_var("DB_PASSWORD"),
        port=int(get_env_var("DB_PORT", "3306")),
        connect_timeout=int(get_env_var("DB_CONNECT_TIMEOUT", "5")),
    )


_DB_CONFIG: DBConfig | None = None


def _get_db_config() -> DBConfig:
    """Return the DB config, loading it lazily on first use."""
    global _DB_CONFIG
    if _DB_CONFIG is None:
        _DB_CONFIG = load_db_config()
    return _DB_CONFIG


def set_db_config(config: DBConfig) -> None:
    """Override DB config (useful for tests)."""
    global _DB_CONFIG
    _DB_CONFIG = config


def _get_connection(config: DBConfig) -> "Connection":
    """Create a new DB connection.

    Imports the MariaDB driver lazily so unit tests that mock repositories can
    run without requiring a native DB connector.
    """
    try:
        from mariadb import connect  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise DatabaseError(
            "MariaDB driver not installed. Install 'mariadb' (and the system C connector) to run the app."
        ) from exc

    return connect(
        user=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.name,
        connect_timeout=config.connect_timeout,
    )


def _cursor_to_dicts(cursor) -> list[dict]:
    """Convert all cursor rows to column-name-keyed dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def read_query(sql: str, sql_params: tuple = ()) -> list[dict]:
    """Execute a SELECT and return all rows as dicts."""
    logger.debug("SELECT %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        return _cursor_to_dicts(cursor)
    except Exception as exc:
        logger.exception("Database read failed")
        raise DatabaseError(f"Database read failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()



def read_query_one(sql: str, sql_params: tuple = ()) -> dict | None:
    """Execute a SELECT and return the first row as a dict, or None."""
    logger.debug("SELECT (one) %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        return dict(zip(columns, row)) if row else None
    except Exception as exc:
        logger.exception("Database read failed")
        raise DatabaseError(f"Database read failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()



def insert_query(sql: str, sql_params: tuple = ()) -> int:
    """Execute an INSERT and return the new row's id."""
    logger.debug("INSERT %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        conn.commit()
        return int(cursor.lastrowid)
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("Database insert failed")
        raise DatabaseError(f"Database insert failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def write_query(sql: str, sql_params: tuple = ()) -> int:
    """Execute an UPDATE or DELETE and return the affected row count."""
    logger.debug("WRITE %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        conn.commit()
        return int(cursor.rowcount)
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("Database write failed")
        raise DatabaseError(f"Database write failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
