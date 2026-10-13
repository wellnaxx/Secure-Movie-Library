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
- Use parameterized MariaDB queries without an ORM, with connection cleanup and write rollback on failure.

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

Generate a signing secret with:

```shell
python -c "import secrets; print(secrets.token_hex(32))"
```

Database and JWT settings are loaded lazily and cached; restart the process after changing them. `LOG_LEVEL` appears in `.env.example`, but the application currently does not read it to configure logging.

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

[data/seed_data.sql](data/seed_data.sql) is currently out of sync with the schema: its admin insert includes `users.updated_at`, which does not exist in `schema.sql`. It also truncates both tables. Use the registration/admin setup above; reconcile the script before using it against a disposable database.

The bundled Postman smoke-test collection defaults to `http://localhost:8000`, username `admin`, and password `SecurePass123!`. Prepare that account first and check the collection variables against your environment. The collection changes passwords and token state and creates test data; reset credentials, token variables, and database state before repeating a run. The seed script is not currently a working reset procedure.

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

### Rating enrichment

Creation returns the movie before the background lookup completes. Enrichment uses an OMDb title lookup with a 10-second HTTP timeout and stores a rating between 0 and 10 when available. Updating a title does not automatically rerun enrichment.

Movie responses expose `enrichment_status`:

| Status | Derived from stored values |
|---|---|
| `pending` | No rating, completion timestamp, or error |
| `success` | A rating exists |
| `not_found` | Error exactly equals `Movie not found in OMDb.` |
| `failed` | Other completed lookups without a rating, or other errors |

The internal `enrichment_error` is excluded from responses. OMDb error text is stored as returned, so a differently worded not-found message is reported as `failed`. Fetch and persistence failures are logged without undoing movie creation. Tasks run in the API process; there is no durable queue or automatic retry.

## Testing and development checks

The suite uses `unittest`, including asynchronous service tests and FastAPI `TestClient` HTTP tests:

```shell
python -m unittest discover -s tests -v
python -m ruff check
python -m pyright --pythonpath .venv/Scripts/python.exe
```

On Linux/macOS, use `.venv/bin/python` for Pyright's interpreter path. Select the same environment in VS Code/Pylance so it can find runtime packages and type stubs. Ruff configuration is stored in `pyproject.toml`; strict Pyright settings are not currently committed there.

The current suite contains **118 tests** covering database helpers, JWT handling and configuration, movie/user repositories, movie/user services, OMDb enrichment, and movie HTTP routes. Router tests exercise real JWT and role checks while mocking database access. Database, repository, and enrichment tests use mocks rather than live MariaDB or OMDb services; there is no dedicated users-router HTTP suite yet.

For coverage, install the separate optional measurement tool:

```shell
python -m pip install coverage
python -m coverage run --branch --source=auth,data,dependencies,repositories,routers,services,utils -m unittest discover -s tests
python -m coverage report -m
```

Coverage measures exercised code, not every possible input or live database behavior.

## Project structure

```text
├── main.py                       # FastAPI app and router registration
├── pyproject.toml                # Dependencies, development tools, Ruff settings
├── requirements.txt              # Pinned runtime installation requirements
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
│   ├── models.py                 # Pydantic schemas, validators, update types, status
│   ├── schema.sql                # Database schema
│   └── seed_data.sql             # Legacy seed/reset script; see compatibility note
├── auth/
│   ├── jwt_handler.py            # Typed JWT creation and validation
│   └── hashing.py                # Password hashing
├── dependencies/
│   └── auth.py                   # Bearer-token authentication and admin authorization
├── utils/
│   ├── errors.py                 # Domain exceptions
│   ├── validators.py             # Shared field validation
│   └── env_vars.py               # Environment variable access
└── tests/
    ├── test_database.py          # Cleanup, transactions, result handling
    ├── test_jwt_handler.py       # JWT validation, expiration, settings, caching
    ├── test_movie_repository.py  # Movie queries, sorting, validation, failures
    ├── test_user_repository.py   # User queries, validation, parameter binding
    ├── test_movies_router.py     # HTTP behavior, JWT/roles, background failures
    ├── test_movies_service.py    # Movie business rules
    ├── test_rating_service.py    # OMDb parsing, HTTP errors, persistence
    └── test_user_service.py      # Registration, authentication, account changes
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
