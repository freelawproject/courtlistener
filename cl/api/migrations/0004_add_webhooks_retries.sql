BEGIN;
--
-- Add field debug to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "debug" boolean DEFAULT false NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "debug" DROP DEFAULT;
--
-- Add field error_message to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "error_message" text DEFAULT '' NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "error_message" DROP DEFAULT;
--
-- Add field event_id to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "event_id" uuid DEFAULT '962a3abe-713f-497e-b660-83bf9763efdd'::uuid NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "event_id" DROP DEFAULT;
--
-- Add field event_status to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "event_status" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "event_status" DROP DEFAULT;
--
-- Add field next_retry_date to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "next_retry_date" timestamp with time zone NULL;
--
-- Add field retry_counter to webhookevent
--
ALTER TABLE "api_webhookevent" ADD COLUMN "retry_counter" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "api_webhookevent" ALTER COLUMN "retry_counter" DROP DEFAULT;
--
-- Alter field content on webhookevent
--
ALTER TABLE "api_webhookevent" ALTER COLUMN "content" DROP NOT NULL;
--
-- Alter field response on webhookevent
--
--
-- Alter field status_code on webhookevent
--
ALTER TABLE "api_webhookevent" ALTER COLUMN "status_code" TYPE smallint USING "status_code"::smallint, ALTER COLUMN "status_code" DROP NOT NULL;
--
-- Create index api_webhook_next_re_3e78b7_idx on field(s) next_retry_date, event_status of model webhookevent
--
CREATE INDEX "api_webhook_next_re_3e78b7_idx" ON "api_webhookevent" ("next_retry_date", "event_status");
COMMIT;
