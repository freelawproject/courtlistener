BEGIN;
--
-- Remove constraint unique_user_throttle_type from model apithrottle
--
ALTER TABLE "api_apithrottle" DROP CONSTRAINT "unique_user_throttle_type";
--
-- Create constraint unique_user_throttle_type_rate on model apithrottle
--
ALTER TABLE "api_apithrottle" ADD CONSTRAINT "unique_user_throttle_type_rate" UNIQUE ("user_id", "throttle_type", "rate");
COMMIT;
