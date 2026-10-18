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
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol, cast

from config.database import DBConfig as DBConfig
from config.database import get_db_config as _get_db_config
from config.database import load_db_config as load_db_config
from config.database import set_db_config as set_db_config
from utils.errors import DatabaseError, DuplicateKeyError, RepositoryError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import NoReturn

logger = logging.getLogger(__name__)


class Cursor(Protocol):
    """Database cursor operations used by this module."""

    @property
    def description(self) -> Sequence[tuple[str, *tuple[Any, ...]]] | None: ...

    @property
    def lastrowid(self) -> int | None: ...

    @property
    def rowcount(self) -> int: ...

    def execute(self, statement: str, data: tuple[Any, ...] = ()) -> None: ...

    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def fetchone(self) -> Sequence[Any] | None: ...

    def close(self) -> None: ...


class Connection(Protocol):
    """Database connection operations used by this module."""

    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


def _get_connection(config: DBConfig) -> Connection:
    """Create a new DB connection.

    Imports the MariaDB driver lazily so unit tests that mock repositories can
    run without requiring a native DB connector.
    """
    try:
        driver = import_module("mariadb")
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise DatabaseError(
            "MariaDB driver not installed. Install 'mariadb' (and the system C connector) to run the app."
        ) from exc

    # MariaDB's annotations are incomplete; type its interface at this boundary.
    connect_driver = cast("Callable[..., Connection]", driver.connect)
    return connect_driver(
        user=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.name,
        connect_timeout=config.connect_timeout,
    )


def _cursor_columns(cursor: Cursor) -> list[str]:
    """Return column names for a cursor with a result set."""
    description = cursor.description
    if description is None:
        raise DatabaseError("Database query did not return column metadata.")
    return [column[0] for column in description]


def _cursor_to_dicts(cursor: Cursor) -> list[dict[str, Any]]:
    """Convert all cursor rows to column-name-keyed dicts."""
    columns = _cursor_columns(cursor)
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _inserted_row_id(cursor: Cursor) -> int:
    """Require a generated row ID before committing an insert."""
    lastrowid = cursor.lastrowid
    if lastrowid is None:
        raise DatabaseError("Database insert did not return a row ID.")
    return lastrowid


def _raise_repository_error(exc: Exception, operation: str) -> NoReturn:
    """Translate MariaDB duplicate keys and other failures without parsing messages.

    MariaDB error 1062 with SQL state 23000 identifies a duplicate unique key.
    Other integrity, connection, and execution errors remain DatabaseError.
    Existing repository errors retain their identity and cause. Driver details
    stay in the chained exception and diagnostic logs, not in public messages.
    """
    if isinstance(exc, RepositoryError):
        if not isinstance(exc, DuplicateKeyError):
            logger.exception("Database %s failed", operation)
        raise exc
    if getattr(exc, "errno", None) == 1062 and getattr(exc, "sqlstate", None) == "23000":
        logger.debug("Database %s rejected a duplicate key", operation)
        raise DuplicateKeyError("A record with the same unique key already exists.") from exc
    logger.exception("Database %s failed", operation)
    raise DatabaseError(f"Database {operation} failed.") from exc


def read_query(sql: str, sql_params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a SELECT and return all rows as dicts."""
    logger.debug("SELECT %s", sql)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        return _cursor_to_dicts(cursor)
    except Exception as exc:
        _raise_repository_error(exc, "read")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def read_query_one(sql: str, sql_params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute a SELECT and return the first row as a dict, or None."""
    logger.debug("SELECT (one) %s", sql)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        columns = _cursor_columns(cursor)
        row = cursor.fetchone()
        return dict(zip(columns, row, strict=True)) if row else None
    except Exception as exc:
        _raise_repository_error(exc, "read")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def insert_query(sql: str, sql_params: tuple[Any, ...] = ()) -> int:
    """Insert a row, raising DuplicateKeyError for unique-key conflicts.

    Other failures raise DatabaseError. Failed writes are rolled back and their
    cursor and connection are closed before control returns to the caller.
    """
    logger.debug("INSERT %s", sql)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        lastrowid = _inserted_row_id(cursor)
        conn.commit()
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        _raise_repository_error(exc, "insert")
    else:
        return lastrowid
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def write_query(sql: str, sql_params: tuple[Any, ...] = ()) -> int:
    """Update/delete rows, raising DuplicateKeyError for unique-key conflicts.

    Other failures raise DatabaseError. Failed writes are rolled back and their
    cursor and connection are closed before control returns to the caller.
    """
    logger.debug("WRITE %s", sql)
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
        _raise_repository_error(exc, "write")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
