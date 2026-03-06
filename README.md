# Secure Movie Library

## Overview

A secure REST API built with FastAPI for managing a personal movie catalog. When a movie is added, the API automatically fetches its IMDb rating from OMDb in the background, enriching the record without making the client wait. All endpoints are protected with JWT-based authentication and role-based access control.

## Features

- Full CRUD for movies — create, list (with title search and sort), fetch, update, and delete.
- Background rating enrichment — OMDb is queried automatically after creation; the client gets an immediate response without waiting.
- JWT authentication with short-lived access tokens and long-lived refresh tokens.
- Role-based access control — `ADMIN` users can write; `USER` accounts are read-only.
- Token invalidation — changing your password immediately revokes all outstanding tokens via a version counter.
- Input validation — enforced on titles, release years (1888–present+2), usernames, and passwords (strength rules).
- Graceful external API failure handling — enrichment errors are logged and stored per movie record without affecting the API.

## Technologies Used

- **Python 3.13 / FastAPI** — web framework and async background tasks
- **MariaDB** — relational database, queried with raw SQL (no ORM)
- **python-jose** — JWT encoding and decoding (HS256)
- **Passlib / bcrypt** — password hashing
- **httpx** — async HTTP client for OMDb requests
- **Pydantic v2** — request/response validation and serialisation

## Installation

Follow these steps to set up and run the application locally:

1. **Clone the repository and install dependencies**
    ```bash
    git clone <repo-url>
    cd Secure-Movie-Library
    pip install -r requirements.txt
    ```

2. **Set up the database**

    Create a MariaDB database and run the schema:
    ```bash
    mysql -u <user> -p < data/schema.sql
    ```

3. **Configure environment variables**

    Copy `.env.example` to `.env` and fill in your values:
    ```bash
    cp .env.example .env
    ```

    | Variable | Description |
    |---|---|
    | `DB_HOST` | MariaDB host (e.g. `localhost`) |
    | `DB_PORT` | MariaDB port (default `3306`) |
    | `DB_NAME` | Database name (e.g. `movie_library`) |
    | `DB_USER` | Database user |
    | `DB_PASSWORD` | Database password |
    | `JWT_SECRET_KEY` | Secret key, minimum 32 characters — generate with `openssl rand -hex 32` |
    | `JWT_EXPIRATION_MINUTES` | Access token lifetime (default `30`) |
    | `JWT_REFRESH_EXPIRATION_DAYS` | Refresh token lifetime (default `7`) |
    | `OMDB_API_KEY` | Free API key from [omdbapi.com](https://www.omdbapi.com/apikey.aspx) |
    | `OMDB_BASE_URL` | OMDb endpoint (default `https://www.omdbapi.com/`) |

4. **Run the application**
    ```bash
    uvicorn main:app --reload
    ```

    The interactive API docs will be available at `http://localhost:8000/docs`.

5. **Run the tests**
    ```bash
    python -m pytest tests/
    ```

## API Reference

#### Authentication endpoints (`/users`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/users/register` | None | Register a new account |
| `POST` | `/users/login` | None | Log in, receive access + refresh tokens |
| `POST` | `/users/refresh` | None | Exchange a refresh token for a new token pair |
| `POST` | `/users/change-password` | Any | Change your password (invalidates all tokens) |
| `GET` | `/users/me` | Any | Get your own profile |
| `PATCH` | `/users/{id}/role` | Admin | Promote or demote a user |

#### Movie endpoints (`/movies`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/movies` | Admin | Create a movie (rating enriched in background) |
| `GET` | `/movies` | Any | List all movies (filter by `?q=`, sort by `?sort_by=`, `?order=`) |
| `GET` | `/movies/{id}` | Any | Get a single movie |
| `PUT` | `/movies/{id}` | Admin | Update a movie |
| `DELETE` | `/movies/{id}` | Admin | Delete a movie |

## Project Structure

```
├── main.py                  # FastAPI app, router registration
├── routers/
│   ├── movies.py            # Movie endpoints
│   └── users.py             # Auth and user endpoints
├── services/
│   ├── movies_service.py    # Movie business logic
│   ├── rating_service.py    # OMDb enrichment background task
│   └── user_service.py      # Auth and user business logic
├── repositories/
│   ├── movie_repository.py  # Movie SQL queries
│   └── user_repository.py   # User SQL queries
├── data/
│   ├── database.py          # DB connection and query helpers
│   ├── models.py            # Pydantic request/response models
│   └── schema.sql           # Database schema
├── auth/
│   ├── jwt_handler.py       # Token creation and decoding
│   └── hashing.py           # Password hashing
├── dependencies/
│   └── auth.py              # FastAPI auth dependencies
├── utils/
│   ├── errors.py            # Custom exception classes
│   ├── validators.py        # Field validation logic
│   └── env_vars.py          # Environment variable helper
└── tests/
    ├── test_movies_service.py
    ├── test_rating_service.py
    └── test_user_service.py
```

## Database Diagram

```
┌──────────────────────────────────┐     ┌──────────────────────────────────┐
│              users               │     │              movies              │
├──────────────────────────────────┤     ├──────────────────────────────────┤
│ id              INT PK           │     │ id              INT PK           │
│ username        VARCHAR(64)      │     │ title           VARCHAR(255)     │
│ password_hash   VARCHAR(255)     │     │ director        VARCHAR(255)     │
│ role            ENUM(ADMIN,USER) │     │ release_year    SMALLINT         │
│ token_version   INT              │     │ rating          DECIMAL(4,2)     │
│ created_at      DATETIME         │     │ rating_source   VARCHAR(50)      │
└──────────────────────────────────┘     │ rating_updated_at DATETIME       │
                                         │ enrichment_error  VARCHAR(512)   │
                                         │ created_at      DATETIME         │
                                         │ updated_at      DATETIME         │
                                         └──────────────────────────────────┘
```

## Contributors

| Author | GitHub |
|---|---|
| Zdravko Kalchev| [@wellnaxx](https://github.com/wellnaxx) |