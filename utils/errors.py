class DatabaseError(RuntimeError):
    """Raised when a database operation fails."""

class UserServiceError(Exception):
    """Base auth/service error."""


class UsernameAlreadyExistsError(UserServiceError):
    pass


class InvalidCredentialsError(UserServiceError):
    pass


class InvalidRefreshTokenError(UserServiceError):
    pass


class UserNotFoundError(UserServiceError):
    pass


class PasswordUpdateError(UserServiceError):
    pass


class IncorrectOldPasswordError(UserServiceError):
    pass


class RoleUpdateError(UserServiceError):
    pass


class MovieServiceError(Exception):
    """Base movie service error."""


class MovieNotFoundError(MovieServiceError):
    pass


class MovieCreationError(MovieServiceError):
    pass


class MovieUpdateError(MovieServiceError):
    pass


class MovieDeleteError(MovieServiceError):
    pass


class EmptyMovieUpdateError(MovieServiceError):
    pass