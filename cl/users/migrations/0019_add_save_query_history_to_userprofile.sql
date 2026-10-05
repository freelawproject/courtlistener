BEGIN;
--
-- Add field save_query_history to userprofile
--
ALTER TABLE "users_userprofile" ADD COLUMN "save_query_history" boolean DEFAULT true NOT NULL;
ALTER TABLE "users_userprofile" ALTER COLUMN "save_query_history" DROP DEFAULT;
--
-- Add field save_query_history to userprofileevent
--
ALTER TABLE "users_userprofileevent" ADD COLUMN "save_query_history" boolean DEFAULT true NOT NULL;
ALTER TABLE "users_userprofileevent" ALTER COLUMN "save_query_history" DROP DEFAULT;

COMMIT;
