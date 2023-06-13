BEGIN;
--
-- Remove trigger update_or_delete_snapshot_delete from model opinioncluster
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_58fe8 ON "search_opinioncluster";
--
-- Remove trigger update_or_delete_snapshot_update from model opinioncluster
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_6a181 ON "search_opinioncluster";
--
-- Add field arguments to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "arguments" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "arguments" DROP DEFAULT;
--
-- Add field headmatter to opinioncluster
--
ALTER TABLE "search_opinioncluster" ADD COLUMN "headmatter" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "headmatter" DROP DEFAULT;
--
-- Add field arguments to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "arguments" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinionclusterevent" ALTER COLUMN "arguments" DROP DEFAULT;
--
-- Add field headmatter to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "headmatter" text DEFAULT '' NOT NULL;
ALTER TABLE "search_opinionclusterevent" ALTER COLUMN "headmatter" DROP DEFAULT;
--
-- Create trigger update_or_delete_snapshot_update on model opinioncluster
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_6a181()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterevent" ("arguments", "attorneys", "blocked", "case_name", "case_name_full", "case_name_short", "citation_count", "correction", "cross_reference", "date_blocked", "date_created", "date_filed", "date_filed_is_approximate", "date_modified", "disposition", "docket_id", "filepath_json_harvard", "headmatter", "headnotes", "history", "id", "judges", "nature_of_suit", "other_dates", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "posture", "precedential_status", "procedural_history", "scdb_decision_direction", "scdb_id", "scdb_votes_majority", "scdb_votes_minority", "slug", "source", "summary", "syllabus") VALUES (OLD."arguments", OLD."attorneys", OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short", OLD."citation_count", OLD."correction", OLD."cross_reference", OLD."date_blocked", OLD."date_created", OLD."date_filed", OLD."date_filed_is_approximate", OLD."date_modified", OLD."disposition", OLD."docket_id", OLD."filepath_json_harvard", OLD."headmatter", OLD."headnotes", OLD."history", OLD."id", OLD."judges", OLD."nature_of_suit", OLD."other_dates", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."posture", OLD."precedential_status", OLD."procedural_history", OLD."scdb_decision_direction", OLD."scdb_id", OLD."scdb_votes_majority", OLD."scdb_votes_minority", OLD."slug", OLD."source", OLD."summary", OLD."syllabus"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_6a181 ON "search_opinioncluster";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_6a181
                AFTER UPDATE ON "search_opinioncluster"


                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."docket_id" IS DISTINCT FROM (NEW."docket_id") OR OLD."judges" IS DISTINCT FROM (NEW."judges") OR OLD."date_filed" IS DISTINCT FROM (NEW."date_filed") OR OLD."date_filed_is_approximate" IS DISTINCT FROM (NEW."date_filed_is_approximate") OR OLD."slug" IS DISTINCT FROM (NEW."slug") OR OLD."case_name_short" IS DISTINCT FROM (NEW."case_name_short") OR OLD."case_name" IS DISTINCT FROM (NEW."case_name") OR OLD."case_name_full" IS DISTINCT FROM (NEW."case_name_full") OR OLD."scdb_id" IS DISTINCT FROM (NEW."scdb_id") OR OLD."scdb_decision_direction" IS DISTINCT FROM (NEW."scdb_decision_direction") OR OLD."scdb_votes_majority" IS DISTINCT FROM (NEW."scdb_votes_majority") OR OLD."scdb_votes_minority" IS DISTINCT FROM (NEW."scdb_votes_minority") OR OLD."source" IS DISTINCT FROM (NEW."source") OR OLD."procedural_history" IS DISTINCT FROM (NEW."procedural_history") OR OLD."attorneys" IS DISTINCT FROM (NEW."attorneys") OR OLD."nature_of_suit" IS DISTINCT FROM (NEW."nature_of_suit") OR OLD."posture" IS DISTINCT FROM (NEW."posture") OR OLD."syllabus" IS DISTINCT FROM (NEW."syllabus") OR OLD."headnotes" IS DISTINCT FROM (NEW."headnotes") OR OLD."summary" IS DISTINCT FROM (NEW."summary") OR OLD."disposition" IS DISTINCT FROM (NEW."disposition") OR OLD."history" IS DISTINCT FROM (NEW."history") OR OLD."other_dates" IS DISTINCT FROM (NEW."other_dates") OR OLD."cross_reference" IS DISTINCT FROM (NEW."cross_reference") OR OLD."correction" IS DISTINCT FROM (NEW."correction") OR OLD."citation_count" IS DISTINCT FROM (NEW."citation_count") OR OLD."precedential_status" IS DISTINCT FROM (NEW."precedential_status") OR OLD."date_blocked" IS DISTINCT FROM (NEW."date_blocked") OR OLD."blocked" IS DISTINCT FROM (NEW."blocked") OR OLD."filepath_json_harvard" IS DISTINCT FROM (NEW."filepath_json_harvard") OR OLD."arguments" IS DISTINCT FROM (NEW."arguments") OR OLD."headmatter" IS DISTINCT FROM (NEW."headmatter"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_6a181();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_6a181 ON "search_opinioncluster" IS 'a186ab65e2b0b6da774524ca6948808bf68a4f93';

--
-- Create trigger update_or_delete_snapshot_delete on model opinioncluster
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_58fe8()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterevent" ("arguments", "attorneys", "blocked", "case_name", "case_name_full", "case_name_short", "citation_count", "correction", "cross_reference", "date_blocked", "date_created", "date_filed", "date_filed_is_approximate", "date_modified", "disposition", "docket_id", "filepath_json_harvard", "headmatter", "headnotes", "history", "id", "judges", "nature_of_suit", "other_dates", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "posture", "precedential_status", "procedural_history", "scdb_decision_direction", "scdb_id", "scdb_votes_majority", "scdb_votes_minority", "slug", "source", "summary", "syllabus") VALUES (OLD."arguments", OLD."attorneys", OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short", OLD."citation_count", OLD."correction", OLD."cross_reference", OLD."date_blocked", OLD."date_created", OLD."date_filed", OLD."date_filed_is_approximate", OLD."date_modified", OLD."disposition", OLD."docket_id", OLD."filepath_json_harvard", OLD."headmatter", OLD."headnotes", OLD."history", OLD."id", OLD."judges", OLD."nature_of_suit", OLD."other_dates", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."posture", OLD."precedential_status", OLD."procedural_history", OLD."scdb_decision_direction", OLD."scdb_id", OLD."scdb_votes_majority", OLD."scdb_votes_minority", OLD."slug", OLD."source", OLD."summary", OLD."syllabus"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_58fe8 ON "search_opinioncluster";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_delete_58fe8
                AFTER DELETE ON "search_opinioncluster"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_58fe8();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_58fe8 ON "search_opinioncluster" IS 'efad05406fc64c608bbade46146fd2dbfd61692f';

COMMIT;
