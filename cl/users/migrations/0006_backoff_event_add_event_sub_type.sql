BEGIN;
--
-- Add field event_sub_type to backoffevent
--
ALTER TABLE "users_backoffevent" ADD COLUMN "event_sub_type" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "users_backoffevent" ALTER COLUMN "event_sub_type" DROP DEFAULT;
COMMIT;
