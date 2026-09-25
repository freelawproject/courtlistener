--
-- Create index oauth2_prov_token_f_996e8a_idx on field(s) token_family of model refreshtoken
--
-- Built CONCURRENTLY so the refresh token table stays writable while the
-- index is created. CONCURRENTLY cannot run inside a transaction, so this
-- file has no BEGIN/COMMIT. django-oauth-toolkit's own migration uses a plain
-- CREATE INDEX; run this file by hand first and `migrate --fake` if the table
-- is too busy to lock.
--
CREATE INDEX CONCURRENTLY "oauth2_prov_token_f_996e8a_idx" ON "oauth2_provider_refreshtoken" ("token_family");
