"""Driver-independent repository failures and application business errors."""


class RepositoryError(RuntimeError):
    """Base class for expected persistence failures exposed to services."""


class DuplicateKeyError(RepositoryError):
    """A write violated a unique constraint; callers may translate the conflict."""


class DatabaseError(RepositoryError):
    """A non-conflict database operation failed; the original cause is chained."""


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


class IncorrectOldPasswordError(UserServiceError):
    pass


class MovieServiceError(Exception):
    """Base movie service error."""


class MovieNotFoundError(MovieServiceError):
    pass


class MovieCreationError(MovieServiceError):
    pass


class MovieDeleteError(MovieServiceError):
    pass


class EmptyMovieUpdateError(MovieServiceError):
    pass
