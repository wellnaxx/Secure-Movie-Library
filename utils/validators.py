"""Shared Pydantic field rules; invalid values raise ValueError.

Length constraints belong to request schemas. Helpers normalize usernames and
titles but preserve password contents; release-year limits use the current date.
"""

import datetime
import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{2,16}$")


def validate_username(username: str) -> str:
    """
    Validate username format.

    Rules:
    - 2-16 characters
    - letters, digits, underscore only
    - surrounding whitespace is stripped before validating

    Returns the normalized username or raises ValueError for a format mismatch.
    Schema length checks can reject input before this field validator runs.
    """

    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must be 2-16 characters long and contain only letters, digits, or underscores."
        )

    return username


def validate_password_strength(password: str) -> str:
    """Return an unchanged password containing all required character groups.

    Require an ASCII uppercase letter, an ASCII lowercase letter, a digit, and
    one of the special characters accepted by the regex below. Missing groups
    are reported together in ValueError. The caller enforces length limits.
    """
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
    """Strip surrounding whitespace; raise ValueError if no title remains.

    Maximum length is enforced by the calling Pydantic field, not this helper.
    """
    title = title.strip()
    if not title:
        raise ValueError("Title cannot be empty.")
    return title


def validate_release_year(year: int) -> int:
    """Accept years from 1888 through the current year plus two, inclusive.

    Return the unchanged year or raise ValueError outside the allowed interval.
    Optional-field callers handle None before invoking this validator.
    """
    current_year = datetime.date.today().year
    if year < 1888:
        raise ValueError("Release year must be >= 1888.")
    if year > current_year + 2:
        raise ValueError(f"Release year must be <= {current_year + 2}.")
    return year
