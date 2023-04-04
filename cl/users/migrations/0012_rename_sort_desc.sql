BEGIN;
--
-- Remove trigger snapshot_insert from model userprofile
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_31610 ON "users_userprofile";
--
-- Remove trigger snapshot_update from model userprofile
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_74231 ON "users_userprofile";
--
-- Rename field sort_desc on userprofile to docket_default_order_desc
--
ALTER TABLE "users_userprofile" RENAME COLUMN "sort_desc" TO "docket_default_order_desc";
--
-- Rename field sort_desc on userprofileevent to docket_default_order_desc
--
ALTER TABLE "users_userprofileevent" RENAME COLUMN "sort_desc" TO "docket_default_order_desc";
--
-- Create trigger snapshot_insert on model userprofile
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_31610()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe", NEW."avatar", NEW."city", NEW."docket_default_order_desc", NEW."email_confirmed", NEW."employer", NEW."id", NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email", NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts", NEW."user_id", NEW."wants_newsletter", NEW."zip_code"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_31610 ON "users_userprofile";
            CREATE  TRIGGER pgtrigger_snapshot_insert_31610
                AFTER INSERT ON "users_userprofile"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_31610();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_31610 ON "users_userprofile" IS '2199693910e840c406dd5edb72796bca1a60fffd';
        ;
--
-- Create trigger snapshot_update on model userprofile
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_74231()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2", "auto_subscribe", "avatar", "city", "docket_default_order_desc", "email_confirmed", "employer", "id", "is_tester", "key_expires", "notes", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plaintext_preferred", "recap_email", "state", "stub_account", "unlimited_docket_alerts", "user_id", "wants_newsletter", "zip_code") VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe", NEW."avatar", NEW."city", NEW."docket_default_order_desc", NEW."email_confirmed", NEW."employer", NEW."id", NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email", NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts", NEW."user_id", NEW."wants_newsletter", NEW."zip_code"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_74231 ON "users_userprofile";
            CREATE  TRIGGER pgtrigger_snapshot_update_74231
                AFTER UPDATE ON "users_userprofile"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_74231();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_74231 ON "users_userprofile" IS '79bb81397f216ff67c082a92d7ecce765a6d209d';
        ;
COMMIT;
