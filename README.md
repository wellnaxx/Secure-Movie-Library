# Secure Movie Library

A FastAPI REST API for a shared movie catalog with JWT authentication, admin-only
writes, and background IMDb rating enrichment through OMDb.

## Features

- Create, search, sort, update, and delete movies.
- Issue access/refresh tokens and check permissions against current account roles.
- Revoke existing tokens on logout or password change; password and token-version
  updates commit atomically.
- Validate requests and database rows with Pydantic.
- Use parameterized MariaDB queries, centralized error handlers, and request logging.

## Requirements

- Python 3.13 or newer.
- MariaDB, plus Connector/C if required by the Python driver's installation.
- An OMDb API key for rating enrichment.

Dependencies and development tools are listed in [pyproject.toml](pyproject.toml).

## Setup

Run commands from the repository root.

### 1. Install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux/macOS, activate with `source .venv/bin/activate`.
For tests and checks, also install:

```shell
python -m pip install types-passlib types-python-jose ruff pyright
```

### 2. Create the database

Run [data/schema.sql](data/schema.sql) in the MariaDB/MySQL interactive client:

```sql
SOURCE C:/path/to/Secure-Movie-Library/data/schema.sql;
```

The script creates `movie_library` and its tables. It does not migrate existing tables.

### 3. Configure the environment

```powershell
Copy-Item .env.example .env
```

On Linux/macOS, use `cp .env.example .env`.

| Variable | Purpose / default |
|---|---|
| `DB_HOST` | Required database host |
| `DB_NAME` | Required database name; schema uses `movie_library` |
| `DB_USER` | Required database username |
| `DB_PASSWORD` | Required; an empty password is allowed |
| `DB_PORT` | `3306`; range 1-65535 |
| `DB_CONNECT_TIMEOUT` | `5` seconds; positive integer |
| `JWT_SECRET_KEY` | Required; at least 32 characters excluding surrounding whitespace |
| `JWT_EXPIRATION_MINUTES` | Access lifetime: `30` minutes; positive integer |
| `JWT_REFRESH_EXPIRATION_DAYS` | Refresh lifetime: `7` days; positive integer |
| `OMDB_API_KEY` | Required for enrichment |
| `OMDB_BASE_URL` | `https://www.omdbapi.com/`; absolute HTTP(S) URL |
| `OMDB_TIMEOUT_SECONDS` | `10` seconds; finite and positive |
| `LOG_LEVEL` | `INFO`; accepts standard names from `NOTSET` through `CRITICAL` |
| `LOG_FILE` | Optional path; blank means stdout only |

Generate a signing secret with:

```shell
python -c "import secrets; print(secrets.token_hex(32))"
```

Settings load independently on first use and are cached. Restart after changing
configuration or SQL files.

### 4. Start the API

```shell
python -m uvicorn main:app --reload
```

API documentation: [Swagger UI](http://localhost:8000/docs),
[ReDoc](http://localhost:8000/redoc), and `/openapi.json`.

### 5. Create an admin

Register through `POST /users/register`:

```json
{"username": "admin", "password": "SecurePass123!"}
```

Registration creates a `USER`. Promote the first admin through the database:

```sql
USE movie_library;
UPDATE users SET role = 'ADMIN' WHERE username = 'admin';
```

Admins can then change roles through the API.

### Seed data and smoke tests

[data/seed_data.sql](data/seed_data.sql) **deletes all users and movies**, then
creates `admin` / `SecurePass123!` with role `ADMIN`. The catalog stays empty.
Run it after the schema against a disposable development database:

```sql
SOURCE C:/path/to/Secure-Movie-Library/data/seed_data.sql;
```

The bundled Postman collection uses that account and `http://localhost:8000`.
It changes passwords, tokens, and movie data. Before repeating a run, reseed the
database, reset `adminPassword`, and clear token and movie-ID variables.

## API

Login uses form fields `username` and `password`; other request bodies use JSON.
Send access tokens as `Authorization: Bearer <access_token>`.

### Authentication and users

| Method | Path | Access | Success | Purpose |
|---|---|---|---|---|
| `POST` | `/users/register` | Public | `201` | Register a `USER` |
| `POST` | `/users/login` | Public | `200` | Exchange credentials for a token pair |
| `POST` | `/users/refresh` | Refresh token in JSON | `200` | Renew with `{"refresh_token": "..."}` |
| `POST` | `/users/change-password` | Access token | `204` | Change password and revoke existing tokens |
| `GET` | `/users/me` | Access token | `200` | Read the current profile |
| `PATCH` | `/users/{user_id}/role` | Admin | `200` | Set `{"role": "ADMIN"}` or `{"role": "USER"}` |
| `POST` | `/users/logout` | Access token | `204` | Revoke all existing tokens for the account |

Tokens use HS256 and a shared signing secret. Refreshing does not invalidate the
previous refresh token; it remains usable until expiry or token-version revocation.

### Movies

| Method | Path | Access | Success | Purpose |
|---|---|---|---|---|
| `POST` | `/movies` | Admin | `201` | Create and schedule enrichment |
| `GET` | `/movies` | Access token | `200` | List, filter, and sort |
| `GET` | `/movies/{movie_id}` | Access token | `200` | Fetch one movie |
| `PUT` | `/movies/{movie_id}` | Admin | `200` | Update supplied fields |
| `DELETE` | `/movies/{movie_id}` | Admin | `204` | Delete a movie |

List parameters:

- `q`: title substring using SQL `LIKE`; `%` and `_` retain wildcard meaning.
- `sort_by`: `rating` (default), `title`, `release_year`, or `created_at`.
- `order`: `desc` (default) or `asc`.

Null ratings sort last; ID breaks ties. Lists are not paginated.

### Validation and updates

Usernames contain 2-16 ASCII letters, digits, or underscores. Passwords are 8-64
characters with uppercase/lowercase letters, a digit, and an accepted special
character. A new password must differ from the old one.

Movie titles are trimmed, nonempty, and limited to 255 input characters. Directors
are optional and limited to 255 characters. Release years are optional, from 1888
through the current year plus two.

`PUT` applies only supplied fields. For example:

```json
{"director": null, "release_year": null}
```

This clears those values and preserves the title. A null title returns `422`;
an empty update returns `400`.

### Rating enrichment

Creation returns before the in-process OMDb lookup completes. Responses expose
`enrichment_status`: `pending`, `success`, `not_found`, or `failed`. Internal error
text is not returned; `not_found` requires the stored message `Movie not found in OMDb.`.

Ratings range from 0 to 10. Failures are logged without undoing creation. There is
no durable queue or automatic retry, and title changes do not rerun enrichment.

### Errors

[exception_handlers.py](exception_handlers.py) maps application errors centrally.

| Status | Meaning |
|---|---|
| `400` | Empty movie update or incorrect old password |
| `401` | Missing, invalid, expired, or revoked authentication; includes a bearer challenge |
| `403` | Authenticated user lacks admin permission |
| `404` | Requested resource is missing |
| `409` | Duplicate username or unique-key conflict |
| `422` | Request validation failed |
| `500` | Failed operation, database failure, or unexpected error |

Database failures return `{"detail": "Database operation failed."}`; unexpected
failures return `{"detail": "Internal server error."}`. Details are logged server-side.

## Development

Routers enforce access and call services; services apply business rules;
repositories execute SQL and validate rows. Each database helper uses its own
connection and commits writes independently. Password replacement and token
revocation share one statement; read/write/reload sequences are separate operations.

SQL lives in `data/sql/` and must be deployed with the Python source. See the
[SQL reference](data/sql/README.md) for bindings and template rules.

Logging starts with the application. Output goes to stdout and optionally
`LOG_FILE`, rotating at 10 MiB with five backups. Request records contain method,
path, status, and response time, excluding background work. They omit query
strings, headers, and bodies; database debug records omit bound values.

Run the suite with:

```shell
python -m unittest discover -s tests -t .
```

See the [test guide](tests/README.md) for focused runs, lint/type checks, and coverage.
Tests use mocks for MariaDB and OMDb; they do not verify live-service behavior.

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
│   │   ├── README.md                # SQL bindings and template contracts
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
    ├── __init__.py                 # Test package for recursive discovery
    ├── README.md                   # Coverage boundaries, isolation, test commands
    ├── auth/                       # JWT handling
    │   ├── __init__.py
    │   └── test_jwt_handler.py
    ├── config/                     # Typed settings and cache lifecycle
    │   ├── __init__.py
    │   └── test_config.py
    ├── data/                       # Database helpers and SQL loading
    │   ├── __init__.py
    │   ├── test_database.py
    │   └── test_sql_loader.py
    ├── http/                       # Routers, handlers, request middleware
    │   ├── __init__.py
    │   ├── test_exception_handlers.py
    │   ├── test_movies_router.py
    │   ├── test_request_logging.py
    │   └── test_users_router.py
    ├── repositories/               # SQL bindings and row validation
    │   ├── __init__.py
    │   ├── test_movie_repository.py
    │   └── test_user_repository.py
    ├── services/                   # Business rules and OMDb enrichment
    │   ├── __init__.py
    │   ├── test_movies_service.py
    │   ├── test_rating_service.py
    │   └── test_user_service.py
    └── utils/                      # Logging configuration and output
        ├── __init__.py
        └── test_logging.py
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

The tables have no foreign keys or per-user movie ownership.

## Contributors

| Author | GitHub |
|---|---|
| Zdravko Kalchev | [wellnaxx](https://github.com/wellnaxx) |
