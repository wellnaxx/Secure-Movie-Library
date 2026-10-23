# Test suite guide

Run commands from the repository root in an environment containing runtime
dependencies and development tools. Tests use `unittest`, `unittest.mock`, and
FastAPI's `TestClient`; no live MariaDB instance or OMDb key is required.

```shell
python -m unittest discover -s tests -t . -v
python -m unittest discover -s tests/services -t . -v
python -m unittest tests.services.test_user_service -v
python -m ruff check
python -m ruff check data/database.py data/loader.py data/queries.py data/models.py
python -m ruff check tests/data/test_database.py tests/data/test_sql_loader.py
python -m pyright --pythonpath .venv/Scripts/python.exe
```

On Linux/macOS, use `.venv/bin/python` for the Pyright interpreter. `data/` is
excluded from the normal Ruff traversal, so check modified files there explicitly.
The existing exclusions and rule settings live in `pyproject.toml`. Strict
Pyright settings are not committed; the command uses the analyzer's configured
mode. Use the same interpreter in the editor to resolve packages and type stubs.
The `data` exclusion also applies to `tests/data/`, so check those files explicitly.

## Folder layout and discovery

Tests follow the boundary they exercise. `auth/`, `config/`, `data/`,
`repositories/`, `services/`, and `utils/` mirror application layers. `http/`
groups routers, exception handlers, and request middleware because their tests
exercise the FastAPI/ASGI boundary.

Every test directory contains `__init__.py` so unittest discovers nested modules.
Keep `-t .` when discovering from a subdirectory: this imports modules as
`tests.services.test_user_service`, for example, and prevents test folders named
`config`, `auth`, or `data` from shadowing the application's packages. Run commands
from the repository root. The plain `python -m unittest discover` command also
discovers the complete suite from that root.

## Coverage by boundary

The suite currently has 210 discovered test methods. Many use subtests for input
matrices; that count is not a count of all inputs exercised.

| Module | Contract exercised |
|---|---|
| [config/test_config.py](config/test_config.py) | Immutable database/JWT/OMDb settings, required values, defaults, validation, independent caches, overrides and resets |
| [utils/test_logging.py](utils/test_logging.py) | Logging settings, accepted levels, output formatting, root-handler replacement, rotation, file failures and cache lifecycle |
| [data/test_sql_loader.py](data/test_sql_loader.py) | Real temporary SQL files, UTF-8, whitespace, path boundaries, failures/retries, cached reads, lazy immutable groups and registry completeness |
| [data/test_database.py](data/test_database.py) | Mocked driver connections/cursors, named rows, generated IDs, parameter binding, transaction calls, duplicate classification and resource cleanup |
| [repositories/test_movie_repository.py](repositories/test_movie_repository.py) | Movie row validation, missing results, Decimal ratings, filter/sort templates, update allowlists, bindings and propagated errors |
| [repositories/test_user_repository.py](repositories/test_user_repository.py) | User row validation, missing results, roles, bindings, atomic password/revocation statement, commit/rollback and propagated errors |
| [auth/test_jwt_handler.py](auth/test_jwt_handler.py) | Real local signing/decoding, expiration, purpose separation, malformed claims, required identity, configuration and caching |
| [services/test_movies_service.py](services/test_movies_service.py) | Response models, create/reload failures, list forwarding, missing movies, partial updates, explicit NULL and delete failures |
| [services/test_user_service.py](services/test_user_service.py) | Registration conflicts and races, credential checks, refresh/revocation, password changes and role changes with mocked persistence/hashing |
| [services/test_rating_service.py](services/test_rating_service.py) | Rating parsing/range boundaries, mocked HTTP responses/timeouts and persistence of enrichment results/errors |
| [http/test_movies_router.py](http/test_movies_router.py) | HTTP validation/statuses, serializers, query options, authentication/roles, background failures and real JWT checks with mocked persistence |
| [http/test_users_router.py](http/test_users_router.py) | Registration success/conflicts, translated database failures, and password-change JWT revocation with mocked persistence |
| [http/test_exception_handlers.py](http/test_exception_handlers.py) | Shared error mappings, public messages, bearer challenges, sanitization, framework defaults, user-operation failure context and main-app integration |
| [http/test_request_logging.py](http/test_request_logging.py) | Request privacy, timings, streaming, handled/unhandled errors, background failures, non-HTTP scopes and startup logging |

## Isolation and fixtures

Patch dependencies where the module under test imports them: for example,
`services.user_service.get_user_by_id`, not only its repository definition.
Repository tests replace database helpers; database tests replace the driver
connection boundary. This lets each layer's own validation and translations run.

Configuration tests patch `.env` loading and the environment, reset process-local
caches, and register cleanup for overrides. Restore caches after tests that call
`set_*_config`; otherwise results depend on test order. JWT tests use disposable
local signing secrets, not application credentials.

HTTP test apps must call `register_exception_handlers(app)` when mounting routers
directly. Set `raise_server_exceptions=False` when asserting a fallback HTTP 500
body; the default client re-raises unexpected server failures. Dependency
overrides isolate authorization in route tests; dedicated scenarios exercise the
real JWT dependencies with mocked database lookups. TestClient executes response
background tasks before returning, so it can verify scheduling and persistence
without treating their duration as production response time.

Logging tests capture output and restore root handlers and logger levels. SQL
loader and file logging tests use temporary directories/files and need filesystem
write access. No tests run the schema or destructive seed script against a server.

## Optional coverage measurement

```shell
python -m pip install coverage
python -m coverage run --branch --source=exception_handlers,auth,config,data,dependencies,middleware,repositories,routers,services,utils -m unittest discover -s tests -t .
python -m coverage report -m
```

Coverage measures executed lines and branches, not correctness for every input.
The suite does not establish live-driver SQL compatibility, database isolation
under concurrent transactions, real OMDb availability, or durable background-task
delivery. Database row tests verify validation with representative Python values;
they do not execute the SQL on MariaDB. Password/revocation tests verify one
combined statement, commit/rollback calls, missing users, and real JWT rejection
after a successful change. HTTP scenarios use simulated repository state; they
do not establish live-database transaction behavior under concurrent requests.

When adding behavior, extend the test at the boundary that owns the rule. Add
HTTP assertions when status codes, public messages, headers, validation, or
serialization change. Keep test names descriptive; module, class, and fixture
docstrings explain the setup and isolation rather than repeating each assertion.
