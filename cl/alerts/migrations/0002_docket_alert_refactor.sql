BEGIN;
--
-- Add field alert_type to docketalert
--
ALTER TABLE "alerts_docketalert" ADD COLUMN "alert_type" smallint DEFAULT 1 NOT NULL;
ALTER TABLE "alerts_docketalert" ALTER COLUMN "alert_type" DROP DEFAULT;
--
-- Delete model DocketSubscription
--
DROP TABLE "alerts_docketsubscription" CASCADE;
COMMIT;
