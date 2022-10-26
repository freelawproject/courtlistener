BEGIN;
--
-- Add field checked to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "checked" timestamp with time zone NULL;
--
-- Create index users_email_flag_ty_5341fa_idx on field(s) flag_type, checked of model emailflag
--
CREATE INDEX "users_email_flag_ty_5341fa_idx" ON "users_emailflag" ("flag_type", "checked");
COMMIT;
