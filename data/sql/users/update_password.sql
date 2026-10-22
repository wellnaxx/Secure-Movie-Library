UPDATE users
SET password_hash = ?, token_version = token_version + 1
WHERE id = ?
