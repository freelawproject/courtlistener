--
-- Raw SQL operation
--
CREATE INDEX CONCURRENTLY "auth_user_email_lower_idx" ON "auth_user" (LOWER("email"));
