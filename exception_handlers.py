"""Central HTTP exception mapping, adapted from FleetFlow's HTTP adapter."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from utils.errors import (
    AuthenticationError,
    AuthorizationError,
    DuplicateKeyError,
    EmptyMovieUpdateError,
    IncorrectOldPasswordError,
    MovieCreationError,
    MovieDeleteError,
    MovieNotFoundError,
    MovieServiceError,
    RepositoryError,
    UserCreationError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
    UserServiceError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Install shared handlers before the app starts serving requests.

    Specific application errors retain their existing status codes and public
    messages. Repository and unexpected failures return sanitized JSON. FastAPI's
    built-in HTTPException and request-validation handlers remain installed.
    """
    app.add_exception_handler(AuthenticationError, authentication_error_handler)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(UsernameAlreadyExistsError, conflict_error_handler)
    app.add_exception_handler(DuplicateKeyError, duplicate_key_error_handler)
    for error in (MovieNotFoundError, UserNotFoundError):
        app.add_exception_handler(error, not_found_error_handler)
    for error in (EmptyMovieUpdateError, IncorrectOldPasswordError):
        app.add_exception_handler(error, bad_request_error_handler)
    for error in (MovieCreationError, MovieDeleteError, UserCreationError):
        app.add_exception_handler(error, operation_error_handler)
    app.add_exception_handler(RepositoryError, repository_error_handler)
    for error in (UserServiceError, MovieServiceError, Exception):
        app.add_exception_handler(error, unexpected_error_handler)


def _log_failure(request: Request, exc: Exception) -> None:
    """Record traceback and safe request metadata outside an except block."""
    logger.error(
        "Application error while handling %s %r.",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


async def authentication_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return a bearer challenge for failed authentication."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def authorization_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Reject authenticated users who lack permission without a new challenge."""
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


async def conflict_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return the application's public username-conflict message."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


async def duplicate_key_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Sanitize repository-level conflicts not translated by a service."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "A record with the same unique key already exists."},
    )


async def not_found_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return an application's missing-resource message."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


async def bad_request_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map expected invalid operations to a bad-request response."""
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


async def operation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log failed operations and retain their application-defined public message."""
    _log_failure(request, exc)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": str(exc)})


async def repository_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log persistence failures without exposing SQL, driver text, or credentials."""
    _log_failure(request, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Database operation failed."},
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return a stable JSON server-error response."""
    _log_failure(request, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )
