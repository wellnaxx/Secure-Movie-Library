"""Load and cache SQL files independently of the process working directory."""

from functools import cache
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent / "sql"


@cache
def load_sql(relative_path: str) -> str:
    """Read UTF-8 SQL relative to data/sql and cache successful reads.

    Paths must stay inside the SQL directory and identify a .sql file. Missing
    files raise FileNotFoundError; invalid paths and empty files raise ValueError.
    Reads strip surrounding whitespace but retain SQL comments and placeholders.
    Failed reads are not cached. Clearing load_sql.cache_clear() does not replace
    query groups already cached by QueryRegistry; restart to reload both layers.
    """
    path = (SQL_DIR / relative_path).resolve()
    if not path.is_relative_to(SQL_DIR.resolve()) or path.suffix != ".sql":
        raise ValueError("SQL query paths must identify a .sql file inside the SQL directory.")
    if not path.is_file():
        raise FileNotFoundError(f"SQL query file not found: {path}")
    sql = path.read_text(encoding="utf-8").strip()
    if not sql:
        raise ValueError(f"SQL query file is empty: {path}")
    return sql
