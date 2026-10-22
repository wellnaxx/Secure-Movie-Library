# SQL statement contracts

These files are application queries, not schema migrations. `data/loader.py`
loads UTF-8 text relative to this directory; `data/queries.py` exposes it through
the lazy `QUERIES` registry. Repositories supply values separately to the MariaDB
driver using positional `?` placeholders. The query helpers open a connection
per call and commit each write independently.

## Movie queries

Paths below are relative to this directory. Parameter order must match the
repository's argument tuple.

| File | Bound parameters, in order | Result or use |
|---|---|---|
| `movies/create.sql` | title, director, release_year | Insert a movie; helper returns its generated ID |
| `movies/get_by_id.sql` | movie_id | One movie row or no match |
| `movies/list.sql` | Parameters contributed by `where_clause` | Movie rows after filtering and sorting |
| `movies/filter_by_title.sql` | `%<stripped query>%` | Optional `WHERE title LIKE ?` fragment |
| `movies/order_by.sql` | None | Order by an allowed column and direction, then ID ascending |
| `movies/order_by_rating.sql` | None | Put NULL ratings last, sort by rating, then ID ascending |
| `movies/update.sql` | Assignment values, then movie_id | Apply supplied movie fields |
| `movies/update_assignment.sql` | One field value | Reusable `<column> = ?` fragment |
| `movies/update_rating.sql` | rating, source, updated_at, enrichment_error, movie_id | Store the result of an enrichment attempt |
| `movies/delete.sql` | movie_id | Delete a movie; helper returns affected-row count |

The movie repository formats only these structural slots:

| Template | Slots | Allowed source |
|---|---|---|
| `list.sql` | `where_clause`, `order_clause` | Empty filter or the registered filter fragment; registered ordering fragments |
| `order_by.sql` | `column`, `direction` | Allowlisted column; fixed `ASC` or `DESC` |
| `order_by_rating.sql` | `direction` | Fixed `ASC` or `DESC` |
| `update.sql` | `assignments` | Comma-joined registered assignment fragments |
| `update_assignment.sql` | `column` | `title`, `director`, or `release_year`, checked before formatting |

Never insert request values into template slots. LIKE values remain bound, but
`%` and `_` retain their SQL wildcard meaning. The schema's collation determines
case sensitivity. An empty update returns zero without loading or executing SQL.
The service distinguishes an omitted field from an explicitly supplied NULL.

## User queries

| File | Bound parameters, in order | Result or use |
|---|---|---|
| `users/create.sql` | username, password_hash, role | Insert a user; helper returns its generated ID |
| `users/get_by_username.sql` | username | One user row or no match |
| `users/get_by_id.sql` | user_id | One user row or no match |
| `users/update_password.sql` | password_hash, user_id | Atomically replace the hash and increment token_version to revoke existing tokens |
| `users/update_role.sql` | role, user_id | Replace the role after caller validation/authorization |
| `users/bump_token_version.sql` | user_id | Revoke existing access and refresh tokens by incrementing the version |

The database unique constraint enforces username uniqueness. The database helper
translates MariaDB `1062` / SQL state `23000` into `DuplicateKeyError`; registration
translates that into `UsernameAlreadyExistsError`. Other failures are not username
conflicts. Hashing, role authorization, and public response shaping belong above
the SQL layer.

Password changes use one UPDATE for `password_hash` and
`token_version = token_version + 1`, sharing one connection and commit. A failed
write cannot leave a committed new password with an unchanged token version.
Zero affected rows means the user is missing. The standalone version-bump query
remains available for logout; password changes do not call it separately.

## Editing or adding a query

1. Add a `.sql` file within the appropriate group and use `?` for data values.
2. Register it in the frozen query dataclass and its `QueryRegistry` property.
3. Keep each repository argument tuple in placeholder order. Allowlist any new
   identifier used in a structural slot.
4. Update repository binding tests and this reference. `test_sql_loader.py`
   checks that the registry covers all query files.
5. Run the SQL-loader and affected repository tests from the repository root.

Successful file reads and query groups are cached separately. Failed loads can
be retried; clearing `load_sql.cache_clear()` alone does not refresh a query group
already loaded by `QUERIES`. Restart after changing deployed SQL files and include
this directory alongside the Python modules.

The separate [schema.sql](../schema.sql) bootstraps the two tables and does not
upgrade existing table definitions. [seed_data.sql](../seed_data.sql) truncates
both tables and creates a development admin; it leaves the catalog empty.
