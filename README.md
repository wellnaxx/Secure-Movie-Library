# Secure Movie Library

A FastAPI REST API for a shared movie catalog, with JWT authentication, role-based access, and background IMDb rating enrichment through OMDb. Movie reads require authentication; movie writes require an `ADMIN` account. Registration, login, and refresh are public endpoints.

## Features

- Create, search, sort, fetch, update, and delete movies.
- Fetch OMDb ratings after creation using FastAPI background tasks.
- Issue HS256 access and refresh tokens with validated, typed payloads.
- Revoke all of a user's existing tokens on logout or password change by incrementing `token_version`.
- Validate usernames, password strength, movie titles, and release years with Pydantic.
- Distinguish omitted movie update fields from explicit null values.
- Validate database rows with Pydantic `TypeAdapter` and `TypedDict` schemas.
- Distinguish unique-key conflicts from other persistence errors, including racing username registrations.
- Map application and repository errors centrally to consistent HTTP responses with sanitized server failures.
- Use parameterized MariaDB queries without an ORM, with connection cleanup and write rollback on failure.
- Configure application logging to stdout and optional rotating files, with HTTP status and response-time records.

Movies are shared across accounts; the schema has no movie ownership relationship.

## Requirements and dependencies

- Python **3.13 or newer**.
- A running MariaDB server and a database user with access to the application tables.
- MariaDB Connector/C when required by the Python driver's installation on your platform.
- An OMDb API key for rating enrichment.

Runtime dependencies are listed in both [requirements.txt](requirements.txt) and [pyproject.toml](pyproject.toml): FastAPI, Uvicorn, python-dotenv, Pydantic, python-jose with cryptography, Passlib, bcrypt, mariadb, httpx, and python-multipart.

`pyproject.toml` also lists development tools and type stubs. Its Ruff configuration targets Python 3.13 with a 112-character line limit; `data/` is excluded from Ruff checks by the current configuration.

## Local setup

Run commands from the repository root.

### 1. Create a virtual environment and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux/macOS, activate with `source .venv/bin/activate` instead.

For development, also install the requirements listed under `project.optional-dependencies.dev`:

```shell
python -m pip install "types-passlib>=1.7.7" "types-python-jose>=3.3.4" "mypy>=1.15" "pyright>=1.1" "pytest>=8.3" "ruff>=0.11" "pymetrica>=1.5.6"
```

The current setup runs directly from the repository using `main:app`; the installation commands above do not require packaging the project.

### 2. Create the database tables

Run [data/schema.sql](data/schema.sql) through your database client. The script creates and selects `movie_library`, then creates the `users` and `movies` tables.

From a shell supporting input redirection:

```shell
mysql -u <database-user> -p < data/schema.sql
```

Alternatively, in the MariaDB/MySQL interactive client:

```sql
SOURCE C:/path/to/Secure-Movie-Library/data/schema.sql;
```

### 3. Configure the environment

```powershell
Copy-Item .env.example .env
```

On Linux/macOS, use `cp .env.example .env`. Set the values in `.env` to match your database and OMDb account.

| Variable | Purpose / default |
|---|---|
| `DB_HOST` | Required database host |
| `DB_NAME` | Required database name; schema uses `movie_library` |
| `DB_USER` | Required database username |
| `DB_PASSWORD` | Required database password |
| `DB_PORT` | `3306` |
| `DB_CONNECT_TIMEOUT` | `5` seconds |
| `JWT_SECRET_KEY` | Required signing secret, at least 32 characters |
| `JWT_EXPIRATION_MINUTES` | Access lifetime: `30` minutes |
| `JWT_REFRESH_EXPIRATION_DAYS` | Refresh lifetime: `7` days |
| `OMDB_API_KEY` | Required when running rating enrichment |
| `OMDB_BASE_URL` | `https://www.omdbapi.com/` |
| `OMDB_TIMEOUT_SECONDS` | HTTP timeout: `10` seconds; finite and greater than zero |
| `LOG_LEVEL` | `INFO`; accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, or `NOTSET` (case-insensitive) |
| `LOG_FILE` | Optional file path; blank or unset means stdout only |

Generate a signing secret with:

```shell
python -c "import secrets; print(secrets.token_hex(32))"
```

Database, JWT, and OMDb settings use immutable typed configuration objects in `config/`. Each group loads `.env` and environment variables on first use, validates its settings, and caches the successful result. Database ports must be in the range 1-65535; connection timeouts and token lifetimes must be positive. Blank database hosts, names, usernames, signing secrets, and OMDb API keys are rejected. An empty database password is allowed. Signing secrets require at least 32 characters after excluding surrounding whitespace. OMDb endpoints must be absolute HTTP(S) URLs. Secrets are excluded from configuration object representations.

Restart the process after changing environment settings. Tests and embedding applications can also replace or reset individual caches:

```python
from config.jwt import JWTConfig, get_jwt_config, load_jwt_config, set_jwt_config

settings = get_jwt_config()        # Load once, then reuse the same object.
fresh = load_jwt_config()          # Read fresh settings without changing the cache.
set_jwt_config(JWTConfig(secret_key="a-development-only-secret-at-least-32-characters"))
set_jwt_config(None)              # Reload from the environment on the next get.
```

`config.database`, `config.omdb`, and `config.logging` expose the same load/get/set pattern for `DBConfig`, `OMDbConfig`, and `LoggingConfig`. Configuration groups load independently, so JWT operations do not require database or OMDb settings. The existing `data.database.DBConfig`, `load_db_config`, and `set_db_config` imports remain available. The JWT signing algorithm remains HS256 and the existing `JWT_SECRET_KEY` environment variable is unchanged.

### 4. Start the API and create an admin account

```shell
python -m uvicorn main:app --reload
```

Interactive documentation: [Swagger UI](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc). The OpenAPI schema is at `/openapi.json`.

Register an account through `POST /users/register`, for example:

```json
{"username": "admin", "password": "SecurePass123!"}
```

Registration always creates a `USER` account. Bootstrap the first admin through your database client:

```sql
USE movie_library;
UPDATE users SET role = 'ADMIN' WHERE username = 'admin';
```

Afterward, admins can change roles through the API. Login accepts form fields `username` and `password` using `application/x-www-form-urlencoded`; other request bodies use JSON. Send access tokens as `Authorization: Bearer <access_token>`.

### Seed script and Postman collection

[data/seed_data.sql](data/seed_data.sql) resets both tables and inserts an `admin` account with role `ADMIN`, password `SecurePass123!`, and token version `0`. Run it after `schema.sql` against a disposable development database; it deletes existing users and movies. It leaves the movie catalog empty.

From the MariaDB/MySQL interactive client:

```sql
SOURCE C:/path/to/Secure-Movie-Library/data/seed_data.sql;
```

The bundled Postman smoke-test collection defaults to `http://localhost:8000`, username `admin`, and password `SecurePass123!`. Seed or create that account first and check the collection variables against your environment. The collection changes passwords and token state and creates test data. To repeat a run against a disposable database, rerun `seed_data.sql`, reset `adminPassword` to `SecurePass123!`, and clear token and movie-ID variables.

## API reference

### Authentication and users

| Method | Path | Access | Success | Purpose |
|---|---|---|---|---|
| `POST` | `/users/register` | Public | `201` | Register a `USER` account |
| `POST` | `/users/login` | Public | `200` | Exchange form credentials for an access/refresh pair |
| `POST` | `/users/refresh` | Refresh token in JSON | `200` | Exchange `{"refresh_token": "..."}` for a new pair |
| `POST` | `/users/change-password` | Access token | `204` | Change password and invalidate existing tokens |
| `GET` | `/users/me` | Access token | `200` | Read the current user's public profile |
| `PATCH` | `/users/{user_id}/role` | Admin | `200` | Set `{"role": "ADMIN"}` or `{"role": "USER"}` |
| `POST` | `/users/logout` | Access token | `204` | Invalidate all existing tokens for the current user |

Refresh tokens are checked against the current database token version. Refreshing issues a new pair but does not invalidate the previous refresh token; it remains usable until expiration or token-version invalidation. Authorization uses the user's current database role.

### Movies

| Method | Path | Access | Success | Purpose |
|---|---|---|---|---|
| `POST` | `/movies` | Admin | `201` | Create a movie and schedule rating enrichment |
| `GET` | `/movies` | Access token | `200` | List movies with optional filtering and sorting |
| `GET` | `/movies/{movie_id}` | Access token | `200` | Fetch one movie |
| `PUT` | `/movies/{movie_id}` | Admin | `200` | Apply supplied movie fields |
| `DELETE` | `/movies/{movie_id}` | Admin | `204` | Delete a movie; response body is empty |

List options:

- `q`: title substring filter, parameterized as SQL `LIKE` (SQL wildcard characters retain their meaning).
- `sort_by`: `rating` (default), `title`, `release_year`, or `created_at`.
- `order`: `desc` (default) or `asc`.

Rating sorting puts null ratings last and uses `id` to break ties. Invalid sort values produce `422`.

### Validation and update behavior

Usernames contain 2-16 letters, digits, or underscores. Passwords are 8-64 characters and must contain uppercase and lowercase letters, a digit, and an accepted special character. A new password must differ from the old one.

Movie titles are stripped of surrounding whitespace, must be nonempty, and have a maximum input length of 255 characters. Director names are optional and limited to 255 characters. Release years are optional and must be between 1888 and the current year plus two.

Although updates use `PUT`, they apply only supplied fields:

```json
{"director": null, "release_year": null}
```

This clears those two values and leaves the title unchanged. An omitted field stays unchanged. Explicit `title: null` is rejected with `422`; an empty update produces `400`.

Missing movies produce `404`. Invalid or expired authentication produces `401`; authenticated non-admin movie writes produce `403`. Request validation errors produce `422`.

Registering a username that already exists produces `409`, including when concurrent registrations both pass the initial availability check. Other database failures remain server errors rather than username conflicts.

### Rating enrichment

Creation returns the movie before the background lookup completes. Enrichment uses an OMDb title lookup with a configurable HTTP timeout (10 seconds by default) and stores a rating between 0 and 10 when available. Updating a title does not automatically rerun enrichment.

Movie responses expose `enrichment_status`:

| Status | Derived from stored values |
|---|---|
| `pending` | No rating, completion timestamp, or error |
| `success` | A rating exists |
| `not_found` | Error exactly equals `Movie not found in OMDb.` |
| `failed` | Other completed lookups without a rating, or other errors |

The internal `enrichment_error` is excluded from responses. OMDb error text is stored as returned, so a differently worded not-found message is reported as `failed`. Fetch and persistence failures are logged without undoing movie creation. Tasks run in the API process; there is no durable queue or automatic retry.

## SQL query files

Repository queries live in `data/sql/movies/` and `data/sql/users/`. The loader and typed query registry follow FleetFlow's pattern:

- `data/loader.py` reads UTF-8 SQL relative to its own directory, strips surrounding whitespace, and caches successful reads. Paths must remain inside `data/sql/`; missing and empty files raise descriptive errors.
- `data/queries.py` exposes `QUERIES.movies` and `QUERIES.users` as immutable typed query groups, loaded independently on first access and cached afterward.
- Repositories select statements from the registry and pass values separately using MariaDB's `?` placeholders. Movie filtering, sorting, and partial updates use file-backed templates; only whitelisted columns, fixed sort directions, and trusted SQL fragments are formatted into them.

For example, `create_user()` executes `QUERIES.users.create` from `data/sql/users/create.sql` with a separate tuple of username, password hash, and role. Restart the application after editing query files so both loader and registry caches are rebuilt. Deploy the SQL files alongside the Python modules.

## Repository error types

Persistence errors are driver-independent classes defined in `utils/errors.py`:

| Type | Meaning |
|---|---|
| `RepositoryError` | Common base for repository failures; retains `RuntimeError` compatibility |
| `DuplicateKeyError` | Unique-key conflict, identified by MariaDB error `1062` and SQL state `23000` |
| `DatabaseError` | Other database execution or connection failure |

`DuplicateKeyError` and `DatabaseError` are separate subclasses of `RepositoryError`. The database helpers chain the original driver exception and preserve existing repository errors unchanged. Failed inserts and updates roll back and close their resources. General driver details are logged server-side; translated error messages do not embed them. Duplicate-key conflicts produce a generic debug record rather than an unexpected-failure traceback.

Repositories propagate these errors to services. Registration catches `DuplicateKeyError` from the insert and translates it into `UsernameAlreadyExistsError`, which the shared conflict handler maps to `409`. The initial username check remains an early rejection; the database unique constraint handles concurrent inserts. Foreign-key, nullability, syntax, and connection errors are not translated into username conflicts.

## Centralized HTTP exception handling

`exception_handlers.py` owns HTTP error mapping. `main.py` registers it before serving requests; routers call services directly, and authentication dependencies raise typed application errors. When embedding the routers in a separate FastAPI app, call `register_exception_handlers(app)` on that app too.

| Error | HTTP behavior |
|---|---|
| `AuthenticationError`, including invalid credentials/access/refresh tokens | `401` with `WWW-Authenticate: Bearer` |
| `AuthorizationError` | `403` |
| `UsernameAlreadyExistsError` | `409` with the application's public message |
| `DuplicateKeyError` | `409` with a generic unique-key conflict message |
| `MovieNotFoundError`, `UserNotFoundError` | `404` |
| `EmptyMovieUpdateError`, `IncorrectOldPasswordError` | `400` |
| `UserCreationError`, `MovieCreationError`, `MovieDeleteError` | `500` with the application-defined public message |
| Other `RepositoryError` subclasses, including `DatabaseError` | `500`, `{"detail": "Database operation failed."}` |
| Unexpected exceptions or unclassified service errors | `500`, `{"detail": "Internal server error."}` |

Server failures are logged with explicit traceback information and method/path metadata. Generic repository and unexpected-error responses exclude driver/internal details. FastAPI's built-in `HTTPException` handling and `422` request-validation responses remain intact.

User errors distinguish operation context: a registration reload failure raises `UserCreationError` (`500`), a refresh token belonging to a deleted user raises `InvalidRefreshTokenError` (`401`), and an account-management target that does not exist raises `UserNotFoundError` (`404`). Handlers do not infer these meanings from URL paths.

## Application and request logging

The FastAPI lifespan configures logging at startup, so the standard `python -m uvicorn main:app --reload` command enables it automatically. Application startup/shutdown and service records use a timestamp, severity, logger name, and message. `LOG_LEVEL` controls the minimum severity; invalid settings or an unwritable `LOG_FILE` destination fail startup.

For optional file output, set:

```dotenv
LOG_LEVEL=INFO
LOG_FILE=logs/application.log
```

File paths are relative to the working directory unless absolute. Parent directories are created automatically. File output uses UTF-8 and rotates at **10 MiB**, retaining **five backups**, alongside stdout output. Restart after changing settings; replacing the cached `LoggingConfig` alone does not reconfigure installed handlers.

The request middleware records method, path, status, and elapsed milliseconds, for example:

```text
2026-10-17 12:00:00 | INFO     | middleware.request_logging | GET '/movies' -> 200 (3.2ms)
```

Response timing ends when the last body chunk has been sent, including streamed responses, and excludes subsequent background work. Handled errors keep their HTTP status. Unhandled failures include a traceback and propagate normally; failures after response completion are identified separately and retain the status already delivered to the client. WebSocket and lifespan messages pass through without HTTP request records.

Request records exclude query strings, authorization headers, and request bodies; control characters in paths are escaped. Database debug records omit bound parameter values. Routine HTTP client URL logs are suppressed to avoid recording OMDb API keys, and Uvicorn's duplicate access records are disabled at ordinary INFO/DEBUG severity. Uvicorn's error logger remains available.

## Testing and development checks

The suite uses `unittest`, including asynchronous service tests and FastAPI `TestClient` HTTP tests:

```shell
python -m unittest discover -s tests -v
python -m ruff check
python -m pyright --pythonpath .venv/Scripts/python.exe
```

On Linux/macOS, use `.venv/bin/python` for Pyright's interpreter path. Select the same environment in VS Code/Pylance so it can find runtime packages and type stubs. Ruff configuration is stored in `pyproject.toml`; strict Pyright settings are not currently committed there.

The current suite contains **204 tests** covering typed configuration, centralized exception handlers, application/request logging, SQL loading, database helpers, JWT handling, movie/user repositories, movie/user services, OMDb enrichment, and HTTP routes. Handler tests cover status mapping, bearer challenges, sanitization, framework validation, contextual user errors, and main-app/request-logging integration. Typed-error tests cover duplicate classification, unrelated integrity/connection failures, rollback and cleanup, original exception causes, and registration conflicts after a successful pre-check. Logging tests cover startup, level filtering, rotating files, cache lifecycle, request privacy, streaming, and exception handling. SQL-loader tests cover real files, caching, missing/empty files, path validation, working-directory independence, and lazy query groups. Configuration tests cover defaults, validation, immutability, secret-safe representations, cache overrides/resets, and independent loading. Movie-router tests exercise real JWT and role checks while mocking database access. Users-router HTTP tests cover registration and failure handling for login, refresh, password changes, role updates, and logout. Database, repository, and enrichment tests use mocks rather than live MariaDB or OMDb services.

For coverage, install the separate optional measurement tool:

```shell
python -m pip install coverage
python -m coverage run --branch --source=exception_handlers,auth,config,data,dependencies,middleware,repositories,routers,services,utils -m unittest discover -s tests
python -m coverage report -m
```

Coverage measures exercised code, not every possible input or live database behavior.

## Project structure

```text
├── main.py                       # FastAPI app, lifespan logging, router registration
├── exception_handlers.py         # Central HTTP error mapping and sanitized server failures
├── pyproject.toml                # Dependencies, development tools, Ruff settings
├── requirements.txt              # Pinned runtime installation requirements
├── config/
│   ├── __init__.py               # Configuration lifecycle documentation
│   ├── _validation.py            # Shared environment parsing and validation
│   ├── database.py               # Immutable DBConfig and load/get/set functions
│   ├── jwt.py                    # Immutable JWTConfig and load/get/set functions
│   ├── logging.py                # Immutable LoggingConfig and load/get/set functions
│   └── omdb.py                   # Immutable OMDbConfig and load/get/set functions
├── middleware/
│   ├── __init__.py
│   └── request_logging.py        # ASGI request status, response timing, failure logs
├── routers/
│   ├── movies.py                 # Movie endpoints
│   └── users.py                  # Authentication and user endpoints
├── services/
│   ├── movies_service.py         # Movie business rules
│   ├── rating_service.py         # OMDb background enrichment
│   └── user_service.py           # Authentication and user business rules
├── repositories/
│   ├── movie_repository.py       # Movie SQL and validated MovieRow results
│   └── user_repository.py        # User SQL and validated UserRow results
├── data/
│   ├── database.py               # Lazy settings, typed driver interfaces, query helpers
│   ├── loader.py                 # Cached UTF-8 SQL file loader
│   ├── queries.py                # Lazy typed movie/user query registry
│   ├── models.py                 # Pydantic schemas, validators, update types, status
│   ├── sql/
│   │   ├── movies/
│   │   │   ├── create.sql
│   │   │   ├── delete.sql
│   │   │   ├── filter_by_title.sql
│   │   │   ├── get_by_id.sql
│   │   │   ├── list.sql
│   │   │   ├── order_by.sql
│   │   │   ├── order_by_rating.sql
│   │   │   ├── update.sql
│   │   │   ├── update_assignment.sql
│   │   │   └── update_rating.sql
│   │   └── users/
│   │       ├── bump_token_version.sql
│   │       ├── create.sql
│   │       ├── get_by_id.sql
│   │       ├── get_by_username.sql
│   │       ├── update_password.sql
│   │       └── update_role.sql
│   ├── schema.sql                # Database schema
│   └── seed_data.sql             # Development reset and seeded admin account
├── auth/
│   ├── jwt_handler.py            # Typed JWT creation and validation
│   └── hashing.py                # Password hashing
├── dependencies/
│   └── auth.py                   # Bearer-token authentication and admin authorization
├── utils/
│   ├── errors.py                 # Typed repository failures and service exceptions
│   ├── validators.py             # Shared field validation
│   ├── logging_config.py         # Stdout and rotating-file logging setup
│   └── env_vars.py               # Environment variable access
└── tests/
    ├── test_config.py            # Settings validation, defaults, cache lifecycle
    ├── test_database.py          # Cleanup, transactions, result handling
    ├── test_exception_handlers.py # HTTP mappings, headers, sanitization, app integration
    ├── test_jwt_handler.py       # JWT validation, expiration, settings, caching
    ├── test_logging.py           # Logging settings, levels, handlers, file rotation
    ├── test_movie_repository.py  # Movie queries, sorting, validation, failures
    ├── test_user_repository.py   # User queries, validation, parameter binding
    ├── test_movies_router.py     # HTTP behavior, JWT/roles, background failures
    ├── test_movies_service.py    # Movie business rules
    ├── test_rating_service.py    # OMDb parsing, HTTP errors, persistence
    ├── test_request_logging.py   # HTTP logs, streaming, privacy, lifespan setup
    ├── test_sql_loader.py        # SQL loading, cache, paths, lazy registry
    ├── test_user_service.py      # Registration, authentication, account changes
    └── test_users_router.py      # Registration HTTP success and typed-error mapping
```

## Database diagram

```text
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│                users                │     │               movies                │
├─────────────────────────────────────┤     ├─────────────────────────────────────┤
│ id              INT PK              │     │ id                INT PK            │
│ username        VARCHAR(64) UNIQUE   │     │ title             VARCHAR(255)      │
│ password_hash   VARCHAR(255)         │     │ director          VARCHAR(255) NULL │
│ role            ENUM(ADMIN,USER)     │     │ release_year      SMALLINT NULL     │
│ token_version   INT                 │     │ rating            DECIMAL(4,2) NULL │
│ created_at      DATETIME            │     │ rating_source     VARCHAR(50) NULL  │
└─────────────────────────────────────┘     │ rating_updated_at DATETIME NULL     │
                                            │ enrichment_error  VARCHAR(512) NULL │
                                            │ created_at        DATETIME          │
                                            │ updated_at        DATETIME          │
                                            └─────────────────────────────────────┘
```

The database contains independent `users` and `movies` tables. Users store password hashes, roles, token versions, and creation timestamps. Movies store descriptive fields, rating/enrichment state, and creation/update timestamps. There are no foreign keys between these tables.

## Contributors

| Author | GitHub |
|---|---|
| Zdravko Kalchev | [wellnaxx](https://github.com/wellnaxx) |
