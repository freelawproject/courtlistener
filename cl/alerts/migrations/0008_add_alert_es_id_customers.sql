BEGIN;
-- Add field es_id to alert
--
ALTER TABLE "alerts_alert" ADD COLUMN "es_id" varchar(128) DEFAULT '' NOT NULL;
ALTER TABLE "alerts_alert" ALTER COLUMN "es_id" DROP DEFAULT;
--
-- Create index alerts_aler_es_id_b61e27_idx on field(s) es_id of model alert
--
CREATE INDEX "alerts_aler_es_id_b61e27_idx" ON "alerts_alert" ("es_id");
COMMIT;
