-- Development reset: run after schema.sql against a disposable movie_library.
-- Truncates both tables, resets their IDs, and inserts only the admin account.
-- The movie catalog is intentionally empty; admin password is SecurePass123!.
USE movie_library;

-- ------------------------------------
-- Reset tables
-- ------------------------------------

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE movies;
TRUNCATE TABLE users;

SET FOREIGN_KEY_CHECKS = 1;

-- ------------------------------------
-- Seed admin user
-- ------------------------------------

-- Password example: SecurePass123!
-- Replace the hash if your hashing settings differ.

INSERT INTO users (
    username,
    password_hash,
    role,
    token_version,
    created_at
)
VALUES (
    'admin',
    '$2b$12$fXXYZLRXw5sO6h9mofbF5uBLhpts900d5ObYXWbaUI45jIajiq9ha',
    'ADMIN',
    0,
    NOW()
);
