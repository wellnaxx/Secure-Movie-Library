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
    """Registration conflicts with an existing username."""


class AuthenticationError(UserServiceError):
    """Credentials or tokens do not establish a valid authenticated user."""


class InvalidCredentialsError(AuthenticationError):
    """Login credentials are invalid."""


class InvalidAccessTokenError(AuthenticationError):
    """An access token is invalid, revoked, or belongs to a deleted user."""


class InvalidRefreshTokenError(AuthenticationError):
    """A refresh token is invalid, revoked, or belongs to a deleted user."""


class AuthorizationError(UserServiceError):
    """An authenticated user lacks permission for an operation."""


class UserCreationError(UserServiceError):
    """Registration could not load the user after the insert succeeded."""


class UserNotFoundError(UserServiceError):
    """A user targeted by an account-management operation does not exist."""


class IncorrectOldPasswordError(UserServiceError):
    """The supplied old password does not match the stored hash."""


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
