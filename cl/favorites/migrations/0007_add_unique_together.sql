BEGIN;
--
-- Alter unique_together for usertag (1 constraint(s))
--
ALTER TABLE "favorites_usertag" ADD CONSTRAINT "favorites_usertag_user_id_name_54aef6fe_uniq" UNIQUE ("user_id", "name");
COMMIT;
