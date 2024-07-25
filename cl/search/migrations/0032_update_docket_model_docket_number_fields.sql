BEGIN;
--
-- Remove trigger update_or_delete_snapshot_delete from model docket
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_7294f ON "search_docket";
--
-- Remove trigger update_or_delete_snapshot_update from model docket
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_7e039 ON "search_docket";
--
-- Add field case_type to docket
--
ALTER TABLE "search_docket" ADD COLUMN "case_type" varchar(5) DEFAULT '' NOT NULL;
ALTER TABLE "search_docket" ALTER COLUMN "case_type" DROP DEFAULT;
--
-- Add field defendant_number to docket
--
ALTER TABLE "search_docket" ADD COLUMN "defendant_number" smallint NULL;
--
-- Add field judge_initials to docket
--
ALTER TABLE "search_docket" ADD COLUMN "judge_initials" varchar(4) DEFAULT '' NOT NULL;
ALTER TABLE "search_docket" ALTER COLUMN "judge_initials" DROP DEFAULT;
--
-- Add field office_code to docket
--
ALTER TABLE "search_docket" ADD COLUMN "office_code" varchar(1) DEFAULT '' NOT NULL;
ALTER TABLE "search_docket" ALTER COLUMN "office_code" DROP DEFAULT;
--
-- Add field parent_docket to docket
--
ALTER TABLE "search_docket" ADD COLUMN "parent_docket_id" integer NULL CONSTRAINT "search_docket_parent_docket_id_1a514426_fk_search_docket_id" REFERENCES "search_docket"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_docket_parent_docket_id_1a514426_fk_search_docket_id" IMMEDIATE;
--
-- Add field case_type to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "case_type" varchar(5) DEFAULT '' NOT NULL;
ALTER TABLE "search_docketevent" ALTER COLUMN "case_type" DROP DEFAULT;
--
-- Add field defendant_number to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "defendant_number" smallint NULL;
--
-- Add field judge_initials to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "judge_initials" varchar(4) DEFAULT '' NOT NULL;
ALTER TABLE "search_docketevent" ALTER COLUMN "judge_initials" DROP DEFAULT;
--
-- Add field office_code to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "office_code" varchar(1) DEFAULT '' NOT NULL;
ALTER TABLE "search_docketevent" ALTER COLUMN "office_code" DROP DEFAULT;
--
-- Add field parent_docket to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "parent_docket_id" integer NULL;
--
-- Create trigger update_or_delete_snapshot_update on model docket
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_7e039()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str", "appellate_case_type_information", "appellate_fee_status", "assigned_to_id", "assigned_to_str", "blocked", "case_name", "case_name_full", "case_name_short", "case_type", "cause", "court_id", "date_argued", "date_blocked", "date_cert_denied", "date_cert_granted", "date_created", "date_filed", "date_last_filing", "date_last_index", "date_modified", "date_reargued", "date_reargument_denied", "date_terminated", "defendant_number", "docket_number", "docket_number_core", "filepath_ia", "filepath_ia_json", "filepath_local", "ia_date_first_change", "ia_needs_upload", "ia_upload_failure_count", "id", "idb_data_id", "judge_initials", "jurisdiction_type", "jury_demand", "mdl_status", "nature_of_suit", "office_code", "originating_court_information_id", "pacer_case_id", "panel_str", "parent_docket_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "referred_to_id", "referred_to_str", "slug", "source") VALUES (OLD."appeal_from_id", OLD."appeal_from_str", OLD."appellate_case_type_information", OLD."appellate_fee_status", OLD."assigned_to_id", OLD."assigned_to_str", OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short", OLD."case_type", OLD."cause", OLD."court_id", OLD."date_argued", OLD."date_blocked", OLD."date_cert_denied", OLD."date_cert_granted", OLD."date_created", OLD."date_filed", OLD."date_last_filing", OLD."date_last_index", OLD."date_modified", OLD."date_reargued", OLD."date_reargument_denied", OLD."date_terminated", OLD."defendant_number", OLD."docket_number", OLD."docket_number_core", OLD."filepath_ia", OLD."filepath_ia_json", OLD."filepath_local", OLD."ia_date_first_change", OLD."ia_needs_upload", OLD."ia_upload_failure_count", OLD."id", OLD."idb_data_id", OLD."judge_initials", OLD."jurisdiction_type", OLD."jury_demand", OLD."mdl_status", OLD."nature_of_suit", OLD."office_code", OLD."originating_court_information_id", OLD."pacer_case_id", OLD."panel_str", OLD."parent_docket_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."referred_to_id", OLD."referred_to_str", OLD."slug", OLD."source"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_7e039 ON "search_docket";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_7e039
                AFTER UPDATE ON "search_docket"


                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."source" IS DISTINCT FROM (NEW."source") OR OLD."court_id" IS DISTINCT FROM (NEW."court_id") OR OLD."appeal_from_id" IS DISTINCT FROM (NEW."appeal_from_id") OR OLD."parent_docket_id" IS DISTINCT FROM (NEW."parent_docket_id") OR OLD."appeal_from_str" IS DISTINCT FROM (NEW."appeal_from_str") OR OLD."originating_court_information_id" IS DISTINCT FROM (NEW."originating_court_information_id") OR OLD."idb_data_id" IS DISTINCT FROM (NEW."idb_data_id") OR OLD."assigned_to_id" IS DISTINCT FROM (NEW."assigned_to_id") OR OLD."assigned_to_str" IS DISTINCT FROM (NEW."assigned_to_str") OR OLD."referred_to_id" IS DISTINCT FROM (NEW."referred_to_id") OR OLD."referred_to_str" IS DISTINCT FROM (NEW."referred_to_str") OR OLD."panel_str" IS DISTINCT FROM (NEW."panel_str") OR OLD."date_last_index" IS DISTINCT FROM (NEW."date_last_index") OR OLD."date_cert_granted" IS DISTINCT FROM (NEW."date_cert_granted") OR OLD."date_cert_denied" IS DISTINCT FROM (NEW."date_cert_denied") OR OLD."date_argued" IS DISTINCT FROM (NEW."date_argued") OR OLD."date_reargued" IS DISTINCT FROM (NEW."date_reargued") OR OLD."date_reargument_denied" IS DISTINCT FROM (NEW."date_reargument_denied") OR OLD."date_filed" IS DISTINCT FROM (NEW."date_filed") OR OLD."date_terminated" IS DISTINCT FROM (NEW."date_terminated") OR OLD."date_last_filing" IS DISTINCT FROM (NEW."date_last_filing") OR OLD."case_name_short" IS DISTINCT FROM (NEW."case_name_short") OR OLD."case_name" IS DISTINCT FROM (NEW."case_name") OR OLD."case_name_full" IS DISTINCT FROM (NEW."case_name_full") OR OLD."slug" IS DISTINCT FROM (NEW."slug") OR OLD."docket_number" IS DISTINCT FROM (NEW."docket_number") OR OLD."docket_number_core" IS DISTINCT FROM (NEW."docket_number_core") OR OLD."office_code" IS DISTINCT FROM (NEW."office_code") OR OLD."case_type" IS DISTINCT FROM (NEW."case_type") OR OLD."judge_initials" IS DISTINCT FROM (NEW."judge_initials") OR OLD."defendant_number" IS DISTINCT FROM (NEW."defendant_number") OR OLD."pacer_case_id" IS DISTINCT FROM (NEW."pacer_case_id") OR OLD."cause" IS DISTINCT FROM (NEW."cause") OR OLD."nature_of_suit" IS DISTINCT FROM (NEW."nature_of_suit") OR OLD."jury_demand" IS DISTINCT FROM (NEW."jury_demand") OR OLD."jurisdiction_type" IS DISTINCT FROM (NEW."jurisdiction_type") OR OLD."appellate_fee_status" IS DISTINCT FROM (NEW."appellate_fee_status") OR OLD."appellate_case_type_information" IS DISTINCT FROM (NEW."appellate_case_type_information") OR OLD."mdl_status" IS DISTINCT FROM (NEW."mdl_status") OR OLD."filepath_local" IS DISTINCT FROM (NEW."filepath_local") OR OLD."filepath_ia" IS DISTINCT FROM (NEW."filepath_ia") OR OLD."filepath_ia_json" IS DISTINCT FROM (NEW."filepath_ia_json") OR OLD."ia_upload_failure_count" IS DISTINCT FROM (NEW."ia_upload_failure_count") OR OLD."ia_needs_upload" IS DISTINCT FROM (NEW."ia_needs_upload") OR OLD."ia_date_first_change" IS DISTINCT FROM (NEW."ia_date_first_change") OR OLD."date_blocked" IS DISTINCT FROM (NEW."date_blocked") OR OLD."blocked" IS DISTINCT FROM (NEW."blocked"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_7e039();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_7e039 ON "search_docket" IS '8154023f4bc7281606f9e0be331261fc3cc71241';

--
-- Create trigger update_or_delete_snapshot_delete on model docket
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_7294f()
            RETURNS TRIGGER AS $$

                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str", "appellate_case_type_information", "appellate_fee_status", "assigned_to_id", "assigned_to_str", "blocked", "case_name", "case_name_full", "case_name_short", "case_type", "cause", "court_id", "date_argued", "date_blocked", "date_cert_denied", "date_cert_granted", "date_created", "date_filed", "date_last_filing", "date_last_index", "date_modified", "date_reargued", "date_reargument_denied", "date_terminated", "defendant_number", "docket_number", "docket_number_core", "filepath_ia", "filepath_ia_json", "filepath_local", "ia_date_first_change", "ia_needs_upload", "ia_upload_failure_count", "id", "idb_data_id", "judge_initials", "jurisdiction_type", "jury_demand", "mdl_status", "nature_of_suit", "office_code", "originating_court_information_id", "pacer_case_id", "panel_str", "parent_docket_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "referred_to_id", "referred_to_str", "slug", "source") VALUES (OLD."appeal_from_id", OLD."appeal_from_str", OLD."appellate_case_type_information", OLD."appellate_fee_status", OLD."assigned_to_id", OLD."assigned_to_str", OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short", OLD."case_type", OLD."cause", OLD."court_id", OLD."date_argued", OLD."date_blocked", OLD."date_cert_denied", OLD."date_cert_granted", OLD."date_created", OLD."date_filed", OLD."date_last_filing", OLD."date_last_index", OLD."date_modified", OLD."date_reargued", OLD."date_reargument_denied", OLD."date_terminated", OLD."defendant_number", OLD."docket_number", OLD."docket_number_core", OLD."filepath_ia", OLD."filepath_ia_json", OLD."filepath_local", OLD."ia_date_first_change", OLD."ia_needs_upload", OLD."ia_upload_failure_count", OLD."id", OLD."idb_data_id", OLD."judge_initials", OLD."jurisdiction_type", OLD."jury_demand", OLD."mdl_status", OLD."nature_of_suit", OLD."office_code", OLD."originating_court_information_id", OLD."pacer_case_id", OLD."panel_str", OLD."parent_docket_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."referred_to_id", OLD."referred_to_str", OLD."slug", OLD."source"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_7294f ON "search_docket";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_delete_7294f
                AFTER DELETE ON "search_docket"


                FOR EACH ROW
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_7294f();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_7294f ON "search_docket" IS '5b02a9c2cedd3b32a8c455a966bf31b02576d67f';

CREATE INDEX "search_docket_case_type_f76fd404" ON "search_docket" ("case_type");
CREATE INDEX "search_docket_case_type_f76fd404_like" ON "search_docket" ("case_type" varchar_pattern_ops);
CREATE INDEX "search_docket_defendant_number_04074363" ON "search_docket" ("defendant_number");
CREATE INDEX "search_docket_judge_initials_2513584d" ON "search_docket" ("judge_initials");
CREATE INDEX "search_docket_judge_initials_2513584d_like" ON "search_docket" ("judge_initials" varchar_pattern_ops);
CREATE INDEX "search_docket_office_code_51016743" ON "search_docket" ("office_code");
CREATE INDEX "search_docket_office_code_51016743_like" ON "search_docket" ("office_code" varchar_pattern_ops);
CREATE INDEX "search_docket_parent_docket_id_1a514426" ON "search_docket" ("parent_docket_id");
CREATE INDEX "search_docketevent_parent_docket_id_c7c9c9ad" ON "search_docketevent" ("parent_docket_id");
COMMIT;