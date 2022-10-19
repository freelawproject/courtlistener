BEGIN;
--
-- Add field checked to emailflag
--
ALTER TABLE "users_emailflag" ADD COLUMN "checked" boolean DEFAULT false NOT NULL;
ALTER TABLE "users_emailflag" ALTER COLUMN "checked" DROP DEFAULT;
--
-- Create index users_email_flag_ty_5341fa_idx on field(s) flag_type, checked of model emailflag
--
CREATE INDEX "users_email_flag_ty_5341fa_idx" ON "users_emailflag" ("flag_type", "checked");
COMMIT;
