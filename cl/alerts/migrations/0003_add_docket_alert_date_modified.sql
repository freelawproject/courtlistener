BEGIN;
--
-- Add field date_modified to docketalert
--
ALTER TABLE "alerts_docketalert" ADD COLUMN "date_modified" timestamp with time zone DEFAULT '2022-12-30T05:23:48.494350+00:00'::timestamptz NOT NULL;
ALTER TABLE "alerts_docketalert" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on docketalert
--
CREATE INDEX "alerts_docketalert_date_modified_97e6b9de" ON "alerts_docketalert" ("date_modified");
COMMIT;
