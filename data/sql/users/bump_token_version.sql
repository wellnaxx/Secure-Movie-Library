UPDATE users
SET token_version = token_version + 1
WHERE id = ?
