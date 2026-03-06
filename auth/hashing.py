"""Password hashing utilities.

Primary implementation uses Passlib (bcrypt scheme). A small bcrypt-only
fallback is provided so unit tests that mock hashing can run even if Passlib is
not installed in the execution environment.
"""

from __future__ import annotations

try:
    from passlib.context import CryptContext

    context_for_passwords = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        return context_for_passwords.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return context_for_passwords.verify(plain_password, hashed_password)

except ModuleNotFoundError:  # pragma: no cover
    import bcrypt

    def hash_password(password: str) -> str:
        """Hash a password using bcrypt (Passlib fallback)."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash (Passlib fallback)."""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )