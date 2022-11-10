BEGIN;
--
-- Add field debug to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "debug" boolean DEFAULT false NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "debug" DROP DEFAULT;
COMMIT;
