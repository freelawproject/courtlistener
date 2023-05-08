BEGIN;
--
-- Remove trigger update_or_delete_snapshot_update from model abarating
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_5d5cb ON "people_db_abarating";
--
-- Remove trigger update_or_delete_snapshot_update from model education
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_4e1c4 ON "people_db_education";
--
-- Remove trigger update_or_delete_snapshot_update from model person
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0f619 ON "people_db_person";
--
-- Remove trigger update_or_delete_snapshot_update from model politicalaffiliation
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_54863 ON "people_db_politicalaffiliation";
--
-- Remove trigger update_or_delete_snapshot_update from model position
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0586a ON "people_db_position";
--
-- Remove trigger update_or_delete_snapshot_update from model retentionevent
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ef1b8 ON "people_db_retentionevent";
--
-- Remove trigger update_or_delete_snapshot_update from model school
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_471f3 ON "people_db_school";
--
-- Remove trigger update_or_delete_snapshot_update from model source
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_88fe4 ON "people_db_source";
--
-- Create trigger update_or_delete_snapshot_update on model abarating
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_5d5cb()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_abaratingevent" ("date_created", "date_modified", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "rating", "year_rated") VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."rating", OLD."year_rated"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_5d5cb ON "people_db_abarating";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_5d5cb
                AFTER UPDATE ON "people_db_abarating"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."person_id" IS DISTINCT FROM (NEW."person_id") OR OLD."year_rated" IS DISTINCT FROM (NEW."year_rated") OR OLD."rating" IS DISTINCT FROM (NEW."rating"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_5d5cb();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_5d5cb ON "people_db_abarating" IS '13f74349ae81148bf7b34818895d2e9894c93b7e';
        
--
-- Create trigger update_or_delete_snapshot_update on model education
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_4e1c4()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_educationevent" ("date_created", "date_modified", "degree_detail", "degree_level", "degree_year", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "school_id") VALUES (OLD."date_created", OLD."date_modified", OLD."degree_detail", OLD."degree_level", OLD."degree_year", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."school_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_4e1c4 ON "people_db_education";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_4e1c4
                AFTER UPDATE ON "people_db_education"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."person_id" IS DISTINCT FROM (NEW."person_id") OR OLD."school_id" IS DISTINCT FROM (NEW."school_id") OR OLD."degree_level" IS DISTINCT FROM (NEW."degree_level") OR OLD."degree_detail" IS DISTINCT FROM (NEW."degree_detail") OR OLD."degree_year" IS DISTINCT FROM (NEW."degree_year"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_4e1c4();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_4e1c4 ON "people_db_education" IS 'c0837209f26fcd9f74a4b0032277e97122c8a369';
        
--
-- Create trigger update_or_delete_snapshot_update on model person
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_0f619()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_personevent" ("date_completed", "date_created", "date_dob", "date_dod", "date_granularity_dob", "date_granularity_dod", "date_modified", "dob_city", "dob_country", "dob_state", "dod_city", "dod_country", "dod_state", "fjc_id", "ftm_eid", "ftm_total_received", "gender", "has_photo", "id", "is_alias_of_id", "name_first", "name_last", "name_middle", "name_suffix", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "religion", "slug") VALUES (OLD."date_completed", OLD."date_created", OLD."date_dob", OLD."date_dod", OLD."date_granularity_dob", OLD."date_granularity_dod", OLD."date_modified", OLD."dob_city", OLD."dob_country", OLD."dob_state", OLD."dod_city", OLD."dod_country", OLD."dod_state", OLD."fjc_id", OLD."ftm_eid", OLD."ftm_total_received", OLD."gender", OLD."has_photo", OLD."id", OLD."is_alias_of_id", OLD."name_first", OLD."name_last", OLD."name_middle", OLD."name_suffix", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."religion", OLD."slug"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0f619 ON "people_db_person";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_0f619
                AFTER UPDATE ON "people_db_person"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."is_alias_of_id" IS DISTINCT FROM (NEW."is_alias_of_id") OR OLD."date_completed" IS DISTINCT FROM (NEW."date_completed") OR OLD."fjc_id" IS DISTINCT FROM (NEW."fjc_id") OR OLD."slug" IS DISTINCT FROM (NEW."slug") OR OLD."name_first" IS DISTINCT FROM (NEW."name_first") OR OLD."name_middle" IS DISTINCT FROM (NEW."name_middle") OR OLD."name_last" IS DISTINCT FROM (NEW."name_last") OR OLD."name_suffix" IS DISTINCT FROM (NEW."name_suffix") OR OLD."date_dob" IS DISTINCT FROM (NEW."date_dob") OR OLD."date_granularity_dob" IS DISTINCT FROM (NEW."date_granularity_dob") OR OLD."date_dod" IS DISTINCT FROM (NEW."date_dod") OR OLD."date_granularity_dod" IS DISTINCT FROM (NEW."date_granularity_dod") OR OLD."dob_city" IS DISTINCT FROM (NEW."dob_city") OR OLD."dob_state" IS DISTINCT FROM (NEW."dob_state") OR OLD."dob_country" IS DISTINCT FROM (NEW."dob_country") OR OLD."dod_city" IS DISTINCT FROM (NEW."dod_city") OR OLD."dod_state" IS DISTINCT FROM (NEW."dod_state") OR OLD."dod_country" IS DISTINCT FROM (NEW."dod_country") OR OLD."gender" IS DISTINCT FROM (NEW."gender") OR OLD."religion" IS DISTINCT FROM (NEW."religion") OR OLD."ftm_total_received" IS DISTINCT FROM (NEW."ftm_total_received") OR OLD."ftm_eid" IS DISTINCT FROM (NEW."ftm_eid") OR OLD."has_photo" IS DISTINCT FROM (NEW."has_photo"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_0f619();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_0f619 ON "people_db_person" IS '08ac51839dafb5c0605bd71dcf96c6a08ec56db5';
        
--
-- Create trigger update_or_delete_snapshot_update on model politicalaffiliation
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_54863()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_politicalaffiliationevent" ("date_created", "date_end", "date_granularity_end", "date_granularity_start", "date_modified", "date_start", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "political_party", "source") VALUES (OLD."date_created", OLD."date_end", OLD."date_granularity_end", OLD."date_granularity_start", OLD."date_modified", OLD."date_start", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."political_party", OLD."source"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_54863 ON "people_db_politicalaffiliation";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_54863
                AFTER UPDATE ON "people_db_politicalaffiliation"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."person_id" IS DISTINCT FROM (NEW."person_id") OR OLD."political_party" IS DISTINCT FROM (NEW."political_party") OR OLD."source" IS DISTINCT FROM (NEW."source") OR OLD."date_start" IS DISTINCT FROM (NEW."date_start") OR OLD."date_granularity_start" IS DISTINCT FROM (NEW."date_granularity_start") OR OLD."date_end" IS DISTINCT FROM (NEW."date_end") OR OLD."date_granularity_end" IS DISTINCT FROM (NEW."date_granularity_end"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_54863();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_54863 ON "people_db_politicalaffiliation" IS '0690cb3e0c0915ec679829351fc663db56d56b81';
        
--
-- Create trigger update_or_delete_snapshot_update on model position
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_0586a()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_positionevent" ("appointer_id", "court_id", "date_confirmation", "date_created", "date_elected", "date_granularity_start", "date_granularity_termination", "date_hearing", "date_judicial_committee_action", "date_modified", "date_nominated", "date_recess_appointment", "date_referred_to_judicial_committee", "date_retirement", "date_start", "date_termination", "has_inferred_values", "how_selected", "id", "job_title", "judicial_committee_action", "location_city", "location_state", "nomination_process", "organization_name", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "position_type", "predecessor_id", "school_id", "sector", "supervisor_id", "termination_reason", "voice_vote", "vote_type", "votes_no", "votes_no_percent", "votes_yes", "votes_yes_percent") VALUES (OLD."appointer_id", OLD."court_id", OLD."date_confirmation", OLD."date_created", OLD."date_elected", OLD."date_granularity_start", OLD."date_granularity_termination", OLD."date_hearing", OLD."date_judicial_committee_action", OLD."date_modified", OLD."date_nominated", OLD."date_recess_appointment", OLD."date_referred_to_judicial_committee", OLD."date_retirement", OLD."date_start", OLD."date_termination", OLD."has_inferred_values", OLD."how_selected", OLD."id", OLD."job_title", OLD."judicial_committee_action", OLD."location_city", OLD."location_state", OLD."nomination_process", OLD."organization_name", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."position_type", OLD."predecessor_id", OLD."school_id", OLD."sector", OLD."supervisor_id", OLD."termination_reason", OLD."voice_vote", OLD."vote_type", OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_0586a ON "people_db_position";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_0586a
                AFTER UPDATE ON "people_db_position"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."position_type" IS DISTINCT FROM (NEW."position_type") OR OLD."job_title" IS DISTINCT FROM (NEW."job_title") OR OLD."sector" IS DISTINCT FROM (NEW."sector") OR OLD."person_id" IS DISTINCT FROM (NEW."person_id") OR OLD."court_id" IS DISTINCT FROM (NEW."court_id") OR OLD."school_id" IS DISTINCT FROM (NEW."school_id") OR OLD."organization_name" IS DISTINCT FROM (NEW."organization_name") OR OLD."location_city" IS DISTINCT FROM (NEW."location_city") OR OLD."location_state" IS DISTINCT FROM (NEW."location_state") OR OLD."appointer_id" IS DISTINCT FROM (NEW."appointer_id") OR OLD."supervisor_id" IS DISTINCT FROM (NEW."supervisor_id") OR OLD."predecessor_id" IS DISTINCT FROM (NEW."predecessor_id") OR OLD."date_nominated" IS DISTINCT FROM (NEW."date_nominated") OR OLD."date_elected" IS DISTINCT FROM (NEW."date_elected") OR OLD."date_recess_appointment" IS DISTINCT FROM (NEW."date_recess_appointment") OR OLD."date_referred_to_judicial_committee" IS DISTINCT FROM (NEW."date_referred_to_judicial_committee") OR OLD."date_judicial_committee_action" IS DISTINCT FROM (NEW."date_judicial_committee_action") OR OLD."judicial_committee_action" IS DISTINCT FROM (NEW."judicial_committee_action") OR OLD."date_hearing" IS DISTINCT FROM (NEW."date_hearing") OR OLD."date_confirmation" IS DISTINCT FROM (NEW."date_confirmation") OR OLD."date_start" IS DISTINCT FROM (NEW."date_start") OR OLD."date_granularity_start" IS DISTINCT FROM (NEW."date_granularity_start") OR OLD."date_termination" IS DISTINCT FROM (NEW."date_termination") OR OLD."termination_reason" IS DISTINCT FROM (NEW."termination_reason") OR OLD."date_granularity_termination" IS DISTINCT FROM (NEW."date_granularity_termination") OR OLD."date_retirement" IS DISTINCT FROM (NEW."date_retirement") OR OLD."nomination_process" IS DISTINCT FROM (NEW."nomination_process") OR OLD."vote_type" IS DISTINCT FROM (NEW."vote_type") OR OLD."voice_vote" IS DISTINCT FROM (NEW."voice_vote") OR OLD."votes_yes" IS DISTINCT FROM (NEW."votes_yes") OR OLD."votes_no" IS DISTINCT FROM (NEW."votes_no") OR OLD."votes_yes_percent" IS DISTINCT FROM (NEW."votes_yes_percent") OR OLD."votes_no_percent" IS DISTINCT FROM (NEW."votes_no_percent") OR OLD."how_selected" IS DISTINCT FROM (NEW."how_selected") OR OLD."has_inferred_values" IS DISTINCT FROM (NEW."has_inferred_values"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_0586a();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_0586a ON "people_db_position" IS '0a03fa6888352997aeba8315cf01e6fa6735ba95';
        
--
-- Create trigger update_or_delete_snapshot_update on model retentionevent
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_ef1b8()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_retentioneventevent" ("date_created", "date_modified", "date_retention", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "position_id", "retention_type", "unopposed", "votes_no", "votes_no_percent", "votes_yes", "votes_yes_percent", "won") VALUES (OLD."date_created", OLD."date_modified", OLD."date_retention", OLD."id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."position_id", OLD."retention_type", OLD."unopposed", OLD."votes_no", OLD."votes_no_percent", OLD."votes_yes", OLD."votes_yes_percent", OLD."won"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_ef1b8 ON "people_db_retentionevent";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_ef1b8
                AFTER UPDATE ON "people_db_retentionevent"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."position_id" IS DISTINCT FROM (NEW."position_id") OR OLD."retention_type" IS DISTINCT FROM (NEW."retention_type") OR OLD."date_retention" IS DISTINCT FROM (NEW."date_retention") OR OLD."votes_yes" IS DISTINCT FROM (NEW."votes_yes") OR OLD."votes_no" IS DISTINCT FROM (NEW."votes_no") OR OLD."votes_yes_percent" IS DISTINCT FROM (NEW."votes_yes_percent") OR OLD."votes_no_percent" IS DISTINCT FROM (NEW."votes_no_percent") OR OLD."unopposed" IS DISTINCT FROM (NEW."unopposed") OR OLD."won" IS DISTINCT FROM (NEW."won"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_ef1b8();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_ef1b8 ON "people_db_retentionevent" IS '52253b9ece6ddd4e044b41b5f840d2e46791fb7a';
        
--
-- Create trigger update_or_delete_snapshot_update on model school
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_471f3()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_schoolevent" ("date_created", "date_modified", "ein", "id", "is_alias_of_id", "name", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id") VALUES (OLD."date_created", OLD."date_modified", OLD."ein", OLD."id", OLD."is_alias_of_id", OLD."name", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_471f3 ON "people_db_school";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_471f3
                AFTER UPDATE ON "people_db_school"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."is_alias_of_id" IS DISTINCT FROM (NEW."is_alias_of_id") OR OLD."name" IS DISTINCT FROM (NEW."name") OR OLD."ein" IS DISTINCT FROM (NEW."ein"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_471f3();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_471f3 ON "people_db_school" IS 'fcb9b90cd9230495908dec047c6d260c1ead3dd5';
        
--
-- Create trigger update_or_delete_snapshot_update on model source
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

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_88fe4()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "people_db_sourceevent" ("date_accessed", "date_created", "date_modified", "id", "notes", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "url") VALUES (OLD."date_accessed", OLD."date_created", OLD."date_modified", OLD."id", OLD."notes", OLD."person_id", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."url"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_88fe4 ON "people_db_source";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_88fe4
                AFTER UPDATE ON "people_db_source"
                
                
                FOR EACH ROW WHEN (OLD."id" IS DISTINCT FROM (NEW."id") OR OLD."date_created" IS DISTINCT FROM (NEW."date_created") OR OLD."person_id" IS DISTINCT FROM (NEW."person_id") OR OLD."url" IS DISTINCT FROM (NEW."url") OR OLD."date_accessed" IS DISTINCT FROM (NEW."date_accessed") OR OLD."notes" IS DISTINCT FROM (NEW."notes"))
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_88fe4();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_88fe4 ON "people_db_source" IS '7d04b1b7898b11902defc3b43ccbcff539cf174c';
        
COMMIT;
