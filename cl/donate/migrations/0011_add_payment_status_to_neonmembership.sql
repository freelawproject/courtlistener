BEGIN;
--
-- Add field payment_status to neonmembership
--
ALTER TABLE "donate_neonmembership" ADD COLUMN "payment_status" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "donate_neonmembership" ALTER COLUMN "payment_status" DROP DEFAULT;
--
-- Add field payment_status to neonmembershipevent
--
ALTER TABLE "donate_neonmembershipevent" ADD COLUMN "payment_status" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "donate_neonmembershipevent" ALTER COLUMN "payment_status" DROP DEFAULT;
COMMIT;
