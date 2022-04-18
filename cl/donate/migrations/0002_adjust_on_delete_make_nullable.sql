BEGIN;
--
-- Alter field donor on donation
--
SET CONSTRAINTS "donate_donation_donor_id_10c373812695e216_fk_auth_user_id" IMMEDIATE;
ALTER TABLE "donate_donation" DROP CONSTRAINT "donate_donation_donor_id_10c373812695e216_fk_auth_user_id";
ALTER TABLE "donate_donation" ALTER COLUMN "donor_id" DROP NOT NULL;
ALTER TABLE "donate_donation" ADD CONSTRAINT "donate_donation_donor_id_0096b8d1_fk_auth_user_id" FOREIGN KEY ("donor_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Alter field donor on monthlydonation
--
SET CONSTRAINTS "donate_monthlydonatio_donor_id_737d44ca41edb50c_fk_auth_user_id" IMMEDIATE;
ALTER TABLE "donate_monthlydonation" DROP CONSTRAINT "donate_monthlydonatio_donor_id_737d44ca41edb50c_fk_auth_user_id";
ALTER TABLE "donate_monthlydonation" ALTER COLUMN "donor_id" DROP NOT NULL;
ALTER TABLE "donate_monthlydonation" ADD CONSTRAINT "donate_monthlydonation_donor_id_a39a8a36_fk_auth_user_id" FOREIGN KEY ("donor_id") REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
COMMIT;
