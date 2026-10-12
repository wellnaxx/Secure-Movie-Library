import datetime
import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{2,16}$")


def validate_username(username: str) -> str:
    """
    Validate username format.

    Rules:
    - 2-16 characters
    - letters, digits, underscore only
    - no leading/trailing spaces
    """

    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must be 2-16 characters long and contain only letters, digits, or underscores."
        )

    return username


def validate_password_strength(password: str) -> str:
    """Validate password meets security requirements."""
    errors: list[str] = []

    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if not re.search(r"\d", password):
        errors.append("at least one digit")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("at least one special character")

    if errors:
        raise ValueError(f"Password must contain {', '.join(errors)}")

    return password


def validate_movie_title(title: str) -> str:
    title = title.strip()
    if not title:
        raise ValueError("Title cannot be empty.")
    return title


def validate_release_year(year: int) -> int:
    current_year = datetime.date.today().year
    if year < 1888:
        raise ValueError("Release year must be >= 1888.")
    if year > current_year + 2:
        raise ValueError(f"Release year must be <= {current_year + 2}.")
    return year
