# SQL queries

`data/queries.py` exposes these files through `QUERIES`. The loader reads UTF-8
relative to this directory and caches successful reads. Deploy SQL files with
the source and restart after editing them; clearing the file cache alone does
not refresh loaded query groups.

Bind values with MariaDB `?` placeholders. Template slots accept only trusted SQL
structure, never request values. Each database helper uses a separate connection
and commits its write.

## Movie queries

| File | Bound values, in order | Template slots |
|---|---|---|
| `movies/create.sql` | title, director, release_year | None |
| `movies/get_by_id.sql` | movie_id | None |
| `movies/list.sql` | Values from the filter, if present | where_clause, order_clause |
| `movies/filter_by_title.sql` | `%<stripped query>%` | None |
| `movies/order_by.sql` | None | column, direction |
| `movies/order_by_rating.sql` | None | direction |
| `movies/update.sql` | Assignment values, then movie_id | assignments |
| `movies/update_assignment.sql` | Field value | column |
| `movies/update_rating.sql` | rating, source, updated_at, enrichment_error, movie_id | None |
| `movies/delete.sql` | movie_id | None |

Filter, ordering, and assignment slots use registered fragments. Columns are
allowlisted; directions are fixed `ASC`/`DESC`. Updates allow only `title`,
`director`, and `release_year`. An empty update runs no SQL. LIKE wildcards keep
their meaning; collation determines case sensitivity. Rating sorting puts NULL
last, with ID breaking ties.

## User queries

| File | Bound values, in order |
|---|---|
| `users/create.sql` | username, password_hash, role |
| `users/get_by_username.sql` | username |
| `users/get_by_id.sql` | user_id |
| `users/update_password.sql` | password_hash, user_id |
| `users/update_role.sql` | role, user_id |
| `users/bump_token_version.sql` | user_id |

`update_password.sql` replaces the hash and increments `token_version` in one
statement and commit. Zero affected rows means the account is missing. Logout
uses the standalone version-bump query.

## Adding a query

1. Add a `.sql` file and register it in the query dataclass and `QueryRegistry`.
2. Match the repository argument tuple to placeholder order. Allowlist formatted identifiers.
3. Update binding tests and this reference. [SQL-loader tests](../../tests/data/test_sql_loader.py)
   check that every query file is registered.

[schema.sql](../schema.sql) bootstraps tables; it does not migrate them.
[seed_data.sql](../seed_data.sql) truncates both tables and creates a development admin.
