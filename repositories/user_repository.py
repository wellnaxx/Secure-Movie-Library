from data.database import read_query_one, insert_query, write_query


def create_user(username: str, password_hash: str, role: str = "USER") -> int:
    sql = """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    """
    return insert_query(sql, (username, password_hash, role))


def get_user_by_username(username: str) -> dict | None:
    sql = "SELECT * FROM users WHERE username = ?"
    return read_query_one(sql, (username,))


def get_user_by_id(user_id: int) -> dict | None:
    sql = "SELECT * FROM users WHERE id = ?"
    return read_query_one(sql, (user_id,))


def update_password(user_id: int, password_hash: str) -> int:
    sql = """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """
    return write_query(sql, (password_hash, user_id))


def update_role(user_id: int, role: str) -> int:
    sql = """
        UPDATE users
        SET role = ?
        WHERE id = ?
    """
    return write_query(sql, (role, user_id))


def bump_token_version(user_id: int) -> int:
    sql = """
        UPDATE users
        SET token_version = token_version + 1
        WHERE id = ?
    """
    return write_query(sql, (user_id,))
