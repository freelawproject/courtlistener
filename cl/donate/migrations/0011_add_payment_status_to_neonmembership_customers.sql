BEGIN;
--
-- Add field payment_status to neonmembership
--
ALTER TABLE "donate_neonmembership" ADD COLUMN "payment_status" smallint DEFAULT 0 NOT NULL;
ALTER TABLE "donate_neonmembership" ALTER COLUMN "payment_status" DROP DEFAULT;
COMMIT;
