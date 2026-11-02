# Tests

Run from the repository root with runtime dependencies and development tools installed.
Tests use `unittest` and FastAPI `TestClient`; no live MariaDB or OMDb key is required.

## Commands

```shell
python -m unittest discover -s tests -t .
python -m unittest discover -s tests/services -t .
python -m unittest tests.services.test_user_service
python -m ruff check
python -m ruff check data/database.py data/loader.py data/queries.py data/models.py
python -m ruff check tests/data/test_database.py tests/data/test_sql_loader.py
python -m pyright --pythonpath .venv/Scripts/python.exe
```

Keep `-t .` for subdirectory discovery so test packages do not shadow application
packages. Each test directory needs `__init__.py` for recursive discovery.

Ruff excludes directories named `data`, including `tests/data`; check those files
explicitly. Strict Pyright settings are not committed. On Linux/macOS, use
`.venv/bin/python`; select the same interpreter in the editor.

## Organization

| Folder | Coverage |
|---|---|
| [auth/](auth/) | JWT signing, claims, expiry, and token configuration |
| [config/](config/) | Settings validation, defaults, immutability, and caches |
| [data/](data/) | SQL loading, query registry, database helpers, rollback, and cleanup |
| [http/](http/) | Routes, permissions, validation, serialization, error handling, request logging, and JWT revocation |
| [repositories/](repositories/) | Row validation, SQL bindings, sorting, and atomic password updates |
| [services/](services/) | Account/movie rules and OMDb enrichment |
| [utils/](utils/) | Logging settings, handlers, rotation, and output |

## Writing tests

- Patch dependencies where they are imported, such as
  `services.user_service.get_user_by_id`.
- Restore configuration caches, environment patches, logging handlers, and
  dependency overrides after each test.
- Register shared exception handlers on standalone test apps. Use
  `raise_server_exceptions=False` to assert unexpected-error responses.
- TestClient runs background tasks before returning. Its total call duration is
  not the production response time.
- SQL-loader and logging tests need write access for temporary files.

Persistence and HTTP-client tests use mocks. They do not establish live MariaDB
compatibility, concurrent transaction behavior, or OMDb availability.

## Coverage

```shell
python -m pip install coverage
python -m coverage run --branch --source=exception_handlers,auth,config,data,dependencies,middleware,repositories,routers,services,utils -m unittest discover -s tests -t .
python -m coverage report -m
```
