BEGIN;
--
-- Create model CitationEvent
--
CREATE TABLE "search_citationevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL, "volume" smallint NOT NULL, "reporter" text NOT NULL, "page" text NOT NULL, "type" smallint NOT NULL);
--
-- Create model CourtEvent
--
CREATE TABLE "search_courtevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" varchar(15) NOT NULL, "pacer_court_id" smallint NULL CHECK ("pacer_court_id" >= 0), "pacer_has_rss_feed" boolean NULL, "pacer_rss_entry_types" text NOT NULL, "date_last_pacer_contact" timestamp with time zone NULL, "fjc_court_id" varchar(3) NOT NULL, "date_modified" timestamp with time zone NOT NULL, "in_use" boolean NOT NULL, "has_opinion_scraper" boolean NOT NULL, "has_oral_argument_scraper" boolean NOT NULL, "position" double precision NOT NULL, "citation_string" varchar(100) NOT NULL, "short_name" varchar(100) NOT NULL, "full_name" varchar(200) NOT NULL, "url" varchar(500) NOT NULL, "start_date" date NULL, "end_date" date NULL, "jurisdiction" varchar(3) NOT NULL, "notes" text NOT NULL);
--
-- Create model DocketEvent
--
CREATE TABLE "search_docketevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "source" smallint NOT NULL, "appeal_from_str" text NOT NULL, "assigned_to_str" text NOT NULL, "referred_to_str" text NOT NULL, "panel_str" text NOT NULL, "date_last_index" timestamp with time zone NULL, "date_cert_granted" date NULL, "date_cert_denied" date NULL, "date_argued" date NULL, "date_reargued" date NULL, "date_reargument_denied" date NULL, "date_filed" date NULL, "date_terminated" date NULL, "date_last_filing" date NULL, "case_name_short" text NOT NULL, "case_name" text NOT NULL, "case_name_full" text NOT NULL, "slug" varchar(75) NOT NULL, "docket_number" text NULL, "docket_number_core" varchar(20) NOT NULL, "pacer_case_id" varchar(100) NULL, "cause" varchar(2000) NOT NULL, "nature_of_suit" varchar(1000) NOT NULL, "jury_demand" varchar(500) NOT NULL, "jurisdiction_type" varchar(100) NOT NULL, "appellate_fee_status" text NOT NULL, "appellate_case_type_information" text NOT NULL, "mdl_status" varchar(100) NOT NULL, "filepath_local" varchar(1000) NOT NULL, "filepath_ia" varchar(1000) NOT NULL, "filepath_ia_json" varchar(1000) NOT NULL, "ia_upload_failure_count" smallint NULL, "ia_needs_upload" boolean NULL, "ia_date_first_change" timestamp with time zone NULL, "view_count" integer NOT NULL, "date_blocked" date NULL, "blocked" boolean NOT NULL);
--
-- Create model DocketPanelEvent
--
CREATE TABLE "search_docketpanelevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL);
--
-- Create model DocketTagsEvent
--
CREATE TABLE "search_dockettagsevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL);
--
-- Create model OpinionClusterEvent
--
CREATE TABLE "search_opinionclusterevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "judges" text NOT NULL, "date_filed" date NOT NULL, "date_filed_is_approximate" boolean NOT NULL, "slug" varchar(75) NULL, "case_name_short" text NOT NULL, "case_name" text NOT NULL, "case_name_full" text NOT NULL, "scdb_id" varchar(10) NOT NULL, "scdb_decision_direction" integer NULL, "scdb_votes_majority" integer NULL, "scdb_votes_minority" integer NULL, "source" varchar(10) NOT NULL, "procedural_history" text NOT NULL, "attorneys" text NOT NULL, "nature_of_suit" text NOT NULL, "posture" text NOT NULL, "syllabus" text NOT NULL, "headnotes" text NOT NULL, "summary" text NOT NULL, "disposition" text NOT NULL, "history" text NOT NULL, "other_dates" text NOT NULL, "cross_reference" text NOT NULL, "correction" text NOT NULL, "citation_count" integer NOT NULL, "precedential_status" varchar(50) NOT NULL, "date_blocked" date NULL, "blocked" boolean NOT NULL, "filepath_json_harvard" varchar(1000) NOT NULL);
--
-- Create model OpinionClusterNonParticipatingJudgesEvent
--
CREATE TABLE "search_opinionclusternonparticipatingjudgesevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL);
--
-- Create model OpinionClusterPanelEvent
--
CREATE TABLE "search_opinionclusterpanelevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL);
--
-- Create model OpinionEvent
--
CREATE TABLE "search_opinionevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "author_str" text NOT NULL, "per_curiam" boolean NOT NULL, "joined_by_str" text NOT NULL, "type" varchar(20) NOT NULL, "sha1" varchar(40) NOT NULL, "page_count" integer NULL, "download_url" varchar(500) NULL, "local_path" varchar(100) NOT NULL, "plain_text" text NOT NULL, "html" text NOT NULL, "html_lawbox" text NOT NULL, "html_columbia" text NOT NULL, "html_anon_2020" text NOT NULL, "xml_harvard" text NOT NULL, "html_with_citations" text NOT NULL, "extracted_by_ocr" boolean NOT NULL);
--
-- Create model OpinionJoinedByEvent
--
CREATE TABLE "search_opinionjoinedbyevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL);
--
-- Create model OpinionOpinionsCitedEvent
--
CREATE TABLE "search_opinionopinionscitedevent" ("pgh_id" serial NOT NULL PRIMARY KEY, "pgh_created_at" timestamp with time zone NOT NULL, "pgh_label" text NOT NULL, "id" integer NOT NULL, "depth" integer NOT NULL);
--
-- Create proxy model DocketPanel
--
--
-- Create proxy model DocketTags
--
--
-- Create proxy model OpinionClusterNonParticipatingJudges
--
--
-- Create proxy model OpinionClusterPanel
--
--
-- Create proxy model OpinionJoinedBy
--
--
-- Create proxy model OpinionOpinionsCited
--
--
-- Create trigger snapshot_insert on model citation
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_596d3()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_citationevent" ("cluster_id", "id", "page", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reporter", "type", "volume") VALUES (NEW."cluster_id", NEW."id", NEW."page", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."reporter", NEW."type", NEW."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_596d3 ON "search_citation";
            CREATE  TRIGGER pgtrigger_snapshot_insert_596d3
                AFTER INSERT ON "search_citation"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_596d3();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_596d3 ON "search_citation" IS '6754ba8bbf994aee87c5236c0cb63f6ac2dedba0';
        ;
--
-- Create trigger snapshot_update on model citation
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_31b3d()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_citationevent" ("cluster_id", "id", "page", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reporter", "type", "volume") VALUES (NEW."cluster_id", NEW."id", NEW."page", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."reporter", NEW."type", NEW."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_31b3d ON "search_citation";
            CREATE  TRIGGER pgtrigger_snapshot_update_31b3d
                AFTER UPDATE ON "search_citation"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_31b3d();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_31b3d ON "search_citation" IS 'b2b27f069bb64eddfd351add29fc2dbe8243da86';
        ;
--
-- Create trigger snapshot_insert on model court
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_82101()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_courtevent" ("citation_string", "date_last_pacer_contact", "date_modified", "end_date", "fjc_court_id", "full_name", "has_opinion_scraper", "has_oral_argument_scraper", "id", "in_use", "jurisdiction", "notes", "pacer_court_id", "pacer_has_rss_feed", "pacer_rss_entry_types", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "position", "short_name", "start_date", "url") VALUES (NEW."citation_string", NEW."date_last_pacer_contact", NEW."date_modified", NEW."end_date", NEW."fjc_court_id", NEW."full_name", NEW."has_opinion_scraper", NEW."has_oral_argument_scraper", NEW."id", NEW."in_use", NEW."jurisdiction", NEW."notes", NEW."pacer_court_id", NEW."pacer_has_rss_feed", NEW."pacer_rss_entry_types", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position", NEW."short_name", NEW."start_date", NEW."url"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_82101 ON "search_court";
            CREATE  TRIGGER pgtrigger_snapshot_insert_82101
                AFTER INSERT ON "search_court"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_82101();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_82101 ON "search_court" IS 'ed2bc4b44e37b73726ebde31bf3c78f4c3619d98';
        ;
--
-- Create trigger snapshot_update on model court
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cc9e2()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_courtevent" ("citation_string", "date_last_pacer_contact", "date_modified", "end_date", "fjc_court_id", "full_name", "has_opinion_scraper", "has_oral_argument_scraper", "id", "in_use", "jurisdiction", "notes", "pacer_court_id", "pacer_has_rss_feed", "pacer_rss_entry_types", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "position", "short_name", "start_date", "url") VALUES (NEW."citation_string", NEW."date_last_pacer_contact", NEW."date_modified", NEW."end_date", NEW."fjc_court_id", NEW."full_name", NEW."has_opinion_scraper", NEW."has_oral_argument_scraper", NEW."id", NEW."in_use", NEW."jurisdiction", NEW."notes", NEW."pacer_court_id", NEW."pacer_has_rss_feed", NEW."pacer_rss_entry_types", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position", NEW."short_name", NEW."start_date", NEW."url"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc9e2 ON "search_court";
            CREATE  TRIGGER pgtrigger_snapshot_update_cc9e2
                AFTER UPDATE ON "search_court"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_cc9e2();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_cc9e2 ON "search_court" IS '51eac3389569bbe20caaf3d42566643bf6b7c091';
        ;
--
-- Create trigger snapshot_insert on model docket
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_fe9ff()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str", "appellate_case_type_information", "appellate_fee_status", "assigned_to_id", "assigned_to_str", "blocked", "case_name", "case_name_full", "case_name_short", "cause", "court_id", "date_argued", "date_blocked", "date_cert_denied", "date_cert_granted", "date_created", "date_filed", "date_last_filing", "date_last_index", "date_modified", "date_reargued", "date_reargument_denied", "date_terminated", "docket_number", "docket_number_core", "filepath_ia", "filepath_ia_json", "filepath_local", "ia_date_first_change", "ia_needs_upload", "ia_upload_failure_count", "id", "idb_data_id", "jurisdiction_type", "jury_demand", "mdl_status", "nature_of_suit", "originating_court_information_id", "pacer_case_id", "panel_str", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "referred_to_id", "referred_to_str", "slug", "source", "view_count") VALUES (NEW."appeal_from_id", NEW."appeal_from_str", NEW."appellate_case_type_information", NEW."appellate_fee_status", NEW."assigned_to_id", NEW."assigned_to_str", NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short", NEW."cause", NEW."court_id", NEW."date_argued", NEW."date_blocked", NEW."date_cert_denied", NEW."date_cert_granted", NEW."date_created", NEW."date_filed", NEW."date_last_filing", NEW."date_last_index", NEW."date_modified", NEW."date_reargued", NEW."date_reargument_denied", NEW."date_terminated", NEW."docket_number", NEW."docket_number_core", NEW."filepath_ia", NEW."filepath_ia_json", NEW."filepath_local", NEW."ia_date_first_change", NEW."ia_needs_upload", NEW."ia_upload_failure_count", NEW."id", NEW."idb_data_id", NEW."jurisdiction_type", NEW."jury_demand", NEW."mdl_status", NEW."nature_of_suit", NEW."originating_court_information_id", NEW."pacer_case_id", NEW."panel_str", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."referred_to_id", NEW."referred_to_str", NEW."slug", NEW."source", NEW."view_count"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_fe9ff ON "search_docket";
            CREATE  TRIGGER pgtrigger_snapshot_insert_fe9ff
                AFTER INSERT ON "search_docket"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_fe9ff();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_fe9ff ON "search_docket" IS '8177d4bbd7e4bede9a2a5e821fa582d48728a9a3';
        ;
--
-- Create trigger snapshot_update on model docket
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_1e722()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str", "appellate_case_type_information", "appellate_fee_status", "assigned_to_id", "assigned_to_str", "blocked", "case_name", "case_name_full", "case_name_short", "cause", "court_id", "date_argued", "date_blocked", "date_cert_denied", "date_cert_granted", "date_created", "date_filed", "date_last_filing", "date_last_index", "date_modified", "date_reargued", "date_reargument_denied", "date_terminated", "docket_number", "docket_number_core", "filepath_ia", "filepath_ia_json", "filepath_local", "ia_date_first_change", "ia_needs_upload", "ia_upload_failure_count", "id", "idb_data_id", "jurisdiction_type", "jury_demand", "mdl_status", "nature_of_suit", "originating_court_information_id", "pacer_case_id", "panel_str", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "referred_to_id", "referred_to_str", "slug", "source", "view_count") VALUES (NEW."appeal_from_id", NEW."appeal_from_str", NEW."appellate_case_type_information", NEW."appellate_fee_status", NEW."assigned_to_id", NEW."assigned_to_str", NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short", NEW."cause", NEW."court_id", NEW."date_argued", NEW."date_blocked", NEW."date_cert_denied", NEW."date_cert_granted", NEW."date_created", NEW."date_filed", NEW."date_last_filing", NEW."date_last_index", NEW."date_modified", NEW."date_reargued", NEW."date_reargument_denied", NEW."date_terminated", NEW."docket_number", NEW."docket_number_core", NEW."filepath_ia", NEW."filepath_ia_json", NEW."filepath_local", NEW."ia_date_first_change", NEW."ia_needs_upload", NEW."ia_upload_failure_count", NEW."id", NEW."idb_data_id", NEW."jurisdiction_type", NEW."jury_demand", NEW."mdl_status", NEW."nature_of_suit", NEW."originating_court_information_id", NEW."pacer_case_id", NEW."panel_str", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."referred_to_id", NEW."referred_to_str", NEW."slug", NEW."source", NEW."view_count"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1e722 ON "search_docket";
            CREATE  TRIGGER pgtrigger_snapshot_update_1e722
                AFTER UPDATE ON "search_docket"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_1e722();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_1e722 ON "search_docket" IS '6e02e752adaf37d3f63141796444c9e12edcf00d';
        ;
--
-- Create trigger snapshot_insert on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_6ae1e()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "html_with_citations", "id", "joined_by_str", "local_path", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (NEW."author_id", NEW."author_str", NEW."cluster_id", NEW."date_created", NEW."date_modified", NEW."download_url", NEW."extracted_by_ocr", NEW."html", NEW."html_anon_2020", NEW."html_columbia", NEW."html_lawbox", NEW."html_with_citations", NEW."id", NEW."joined_by_str", NEW."local_path", NEW."page_count", NEW."per_curiam", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."plain_text", NEW."sha1", NEW."type", NEW."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6ae1e ON "search_opinion";
            CREATE  TRIGGER pgtrigger_snapshot_insert_6ae1e
                AFTER INSERT ON "search_opinion"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_6ae1e();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_6ae1e ON "search_opinion" IS 'c65912952e99b1fa6f54facaa7d46c04ea1fabed';
        ;
--
-- Create trigger snapshot_update on model opinion
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cdf06()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified", "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia", "html_lawbox", "html_with_citations", "id", "joined_by_str", "local_path", "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard") VALUES (NEW."author_id", NEW."author_str", NEW."cluster_id", NEW."date_created", NEW."date_modified", NEW."download_url", NEW."extracted_by_ocr", NEW."html", NEW."html_anon_2020", NEW."html_columbia", NEW."html_lawbox", NEW."html_with_citations", NEW."id", NEW."joined_by_str", NEW."local_path", NEW."page_count", NEW."per_curiam", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."plain_text", NEW."sha1", NEW."type", NEW."xml_harvard"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cdf06 ON "search_opinion";
            CREATE  TRIGGER pgtrigger_snapshot_update_cdf06
                AFTER UPDATE ON "search_opinion"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_cdf06();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_cdf06 ON "search_opinion" IS '31abe6319b984ddbc8ee374a72c87b915099904c';
        ;
--
-- Create trigger snapshot_insert on model opinioncluster
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b55e2()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterevent" ("attorneys", "blocked", "case_name", "case_name_full", "case_name_short", "citation_count", "correction", "cross_reference", "date_blocked", "date_created", "date_filed", "date_filed_is_approximate", "date_modified", "disposition", "docket_id", "filepath_json_harvard", "headnotes", "history", "id", "judges", "nature_of_suit", "other_dates", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "posture", "precedential_status", "procedural_history", "scdb_decision_direction", "scdb_id", "scdb_votes_majority", "scdb_votes_minority", "slug", "source", "summary", "syllabus") VALUES (NEW."attorneys", NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short", NEW."citation_count", NEW."correction", NEW."cross_reference", NEW."date_blocked", NEW."date_created", NEW."date_filed", NEW."date_filed_is_approximate", NEW."date_modified", NEW."disposition", NEW."docket_id", NEW."filepath_json_harvard", NEW."headnotes", NEW."history", NEW."id", NEW."judges", NEW."nature_of_suit", NEW."other_dates", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."posture", NEW."precedential_status", NEW."procedural_history", NEW."scdb_decision_direction", NEW."scdb_id", NEW."scdb_votes_majority", NEW."scdb_votes_minority", NEW."slug", NEW."source", NEW."summary", NEW."syllabus"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b55e2 ON "search_opinioncluster";
            CREATE  TRIGGER pgtrigger_snapshot_insert_b55e2
                AFTER INSERT ON "search_opinioncluster"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_b55e2();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_b55e2 ON "search_opinioncluster" IS '2cf587c27dec64b1d23bbacd51e65724a3b5b306';
        ;
--
-- Create trigger snapshot_update on model opinioncluster
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_f129e()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterevent" ("attorneys", "blocked", "case_name", "case_name_full", "case_name_short", "citation_count", "correction", "cross_reference", "date_blocked", "date_created", "date_filed", "date_filed_is_approximate", "date_modified", "disposition", "docket_id", "filepath_json_harvard", "headnotes", "history", "id", "judges", "nature_of_suit", "other_dates", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "posture", "precedential_status", "procedural_history", "scdb_decision_direction", "scdb_id", "scdb_votes_majority", "scdb_votes_minority", "slug", "source", "summary", "syllabus") VALUES (NEW."attorneys", NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short", NEW."citation_count", NEW."correction", NEW."cross_reference", NEW."date_blocked", NEW."date_created", NEW."date_filed", NEW."date_filed_is_approximate", NEW."date_modified", NEW."disposition", NEW."docket_id", NEW."filepath_json_harvard", NEW."headnotes", NEW."history", NEW."id", NEW."judges", NEW."nature_of_suit", NEW."other_dates", _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."posture", NEW."precedential_status", NEW."procedural_history", NEW."scdb_decision_direction", NEW."scdb_id", NEW."scdb_votes_majority", NEW."scdb_votes_minority", NEW."slug", NEW."source", NEW."summary", NEW."syllabus"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_f129e ON "search_opinioncluster";
            CREATE  TRIGGER pgtrigger_snapshot_update_f129e
                AFTER UPDATE ON "search_opinioncluster"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_f129e();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_f129e ON "search_opinioncluster" IS 'aab40c6b0b890403f82c3934397e16526f1f9753';
        ;
--
-- Add field cited_opinion to opinionopinionscitedevent
--
ALTER TABLE "search_opinionopinionscitedevent" ADD COLUMN "cited_opinion_id" integer NOT NULL;
--
-- Add field citing_opinion to opinionopinionscitedevent
--
ALTER TABLE "search_opinionopinionscitedevent" ADD COLUMN "citing_opinion_id" integer NOT NULL;
--
-- Add field pgh_context to opinionopinionscitedevent
--
ALTER TABLE "search_opinionopinionscitedevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field opinion to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent" ADD COLUMN "opinion_id" integer NOT NULL;
--
-- Add field person to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent" ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field author to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "author_id" integer NULL;
--
-- Add field cluster to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "cluster_id" integer NOT NULL;
--
-- Add field pgh_context to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to opinionevent
--
ALTER TABLE "search_opinionevent" ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field opinioncluster to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent" ADD COLUMN "opinioncluster_id" integer NOT NULL;
--
-- Add field person to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent" ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field opinioncluster to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent" ADD COLUMN "opinioncluster_id" integer NOT NULL;
--
-- Add field person to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent" ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field docket to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field docket to dockettagsevent
--
ALTER TABLE "search_dockettagsevent" ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to dockettagsevent
--
ALTER TABLE "search_dockettagsevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field tag to dockettagsevent
--
ALTER TABLE "search_dockettagsevent" ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field docket to docketpanelevent
--
ALTER TABLE "search_docketpanelevent" ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field person to docketpanelevent
--
ALTER TABLE "search_docketpanelevent" ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to docketpanelevent
--
ALTER TABLE "search_docketpanelevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field appeal_from to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "appeal_from_id" varchar(15) NULL;
--
-- Add field assigned_to to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "assigned_to_id" integer NULL;
--
-- Add field court to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "court_id" varchar(15) NOT NULL;
--
-- Add field idb_data to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "idb_data_id" integer NULL;
--
-- Add field originating_court_information to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "originating_court_information_id" integer NULL;
--
-- Add field pgh_context to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field referred_to to docketevent
--
ALTER TABLE "search_docketevent" ADD COLUMN "referred_to_id" integer NULL;
--
-- Add field pgh_context to courtevent
--
ALTER TABLE "search_courtevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to courtevent
--
ALTER TABLE "search_courtevent" ADD COLUMN "pgh_obj_id" varchar(15) NOT NULL;
--
-- Add field cluster to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "cluster_id" integer NOT NULL;
--
-- Add field pgh_context to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Create trigger snapshot_insert on model docketpanel
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_23fa7()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketpanelevent" ("docket_id", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."docket_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_23fa7 ON "search_docket_panel";
            CREATE  TRIGGER pgtrigger_snapshot_insert_23fa7
                AFTER INSERT ON "search_docket_panel"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_23fa7();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_23fa7 ON "search_docket_panel" IS '74d42fd24f3900652a09c52ff42225b822c3e4c4';
        ;
--
-- Create trigger snapshot_update on model docketpanel
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_e0bd2()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_docketpanelevent" ("docket_id", "id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."docket_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_e0bd2 ON "search_docket_panel";
            CREATE  TRIGGER pgtrigger_snapshot_update_e0bd2
                AFTER UPDATE ON "search_docket_panel"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_e0bd2();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_e0bd2 ON "search_docket_panel" IS 'cabe688dcbfa55a212287ebe5d52037924bead84';
        ;
--
-- Create trigger snapshot_insert on model dockettags
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b723b()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_dockettagsevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "tag_id") VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."tag_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b723b ON "search_docket_tags";
            CREATE  TRIGGER pgtrigger_snapshot_insert_b723b
                AFTER INSERT ON "search_docket_tags"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_b723b();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_b723b ON "search_docket_tags" IS '34cb6117e99c4cc416d306e94c46f4d38a27f14c';
        ;
--
-- Create trigger snapshot_update on model dockettags
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_59839()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_dockettagsevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "tag_id") VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."tag_id"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_59839 ON "search_docket_tags";
            CREATE  TRIGGER pgtrigger_snapshot_update_59839
                AFTER UPDATE ON "search_docket_tags"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_59839();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_59839 ON "search_docket_tags" IS 'b25d863b87575dfdfb93a36dd16afc3d3ac115e9';
        ;
--
-- Create trigger snapshot_insert on model opinionclusternonparticipatingjudges
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_0000e()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusternonparticipatingjudgesevent" ("id", "opinioncluster_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0000e ON "search_opinioncluster_non_participating_judges";
            CREATE  TRIGGER pgtrigger_snapshot_insert_0000e
                AFTER INSERT ON "search_opinioncluster_non_participating_judges"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_0000e();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_0000e ON "search_opinioncluster_non_participating_judges" IS 'c98991c93dda9f29eeab5e9126470e25f4ec7ea8';
        ;
--
-- Create trigger snapshot_update on model opinionclusternonparticipatingjudges
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8f2d1()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusternonparticipatingjudgesevent" ("id", "opinioncluster_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f2d1 ON "search_opinioncluster_non_participating_judges";
            CREATE  TRIGGER pgtrigger_snapshot_update_8f2d1
                AFTER UPDATE ON "search_opinioncluster_non_participating_judges"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_8f2d1();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_8f2d1 ON "search_opinioncluster_non_participating_judges" IS '22f3de5e60619ba7e4b1c57941a63fd0183abd28';
        ;
--
-- Create trigger snapshot_insert on model opinionclusterpanel
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_3e719()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterpanelevent" ("id", "opinioncluster_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3e719 ON "search_opinioncluster_panel";
            CREATE  TRIGGER pgtrigger_snapshot_insert_3e719
                AFTER INSERT ON "search_opinioncluster_panel"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_3e719();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_3e719 ON "search_opinioncluster_panel" IS '55685fc2e1efbfb7ba7a63a64ad0a14fcde37817';
        ;
--
-- Create trigger snapshot_update on model opinionclusterpanel
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_2a689()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionclusterpanelevent" ("id", "opinioncluster_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2a689 ON "search_opinioncluster_panel";
            CREATE  TRIGGER pgtrigger_snapshot_update_2a689
                AFTER UPDATE ON "search_opinioncluster_panel"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_2a689();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_2a689 ON "search_opinioncluster_panel" IS '2d92289ef7590f116a68817146315937e25b2715';
        ;
--
-- Create trigger snapshot_insert on model opinionjoinedby
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_541c3()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionjoinedbyevent" ("id", "opinion_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinion_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_541c3 ON "search_opinion_joined_by";
            CREATE  TRIGGER pgtrigger_snapshot_insert_541c3
                AFTER INSERT ON "search_opinion_joined_by"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_541c3();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_541c3 ON "search_opinion_joined_by" IS 'ab71a7d9bdeab2baa3568b2659edb83ba5653725';
        ;
--
-- Create trigger snapshot_update on model opinionjoinedby
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_23a70()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionjoinedbyevent" ("id", "opinion_id", "person_id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."id", NEW."opinion_id", NEW."person_id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_23a70 ON "search_opinion_joined_by";
            CREATE  TRIGGER pgtrigger_snapshot_update_23a70
                AFTER UPDATE ON "search_opinion_joined_by"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_23a70();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_23a70 ON "search_opinion_joined_by" IS '694b606ec9b855311a850bf376434611982b334c';
        ;
--
-- Create trigger snapshot_insert on model opinionopinionscited
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_89103()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionopinionscitedevent" ("cited_opinion_id", "citing_opinion_id", "depth", "id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."cited_opinion_id", NEW."citing_opinion_id", NEW."depth", NEW."id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_89103 ON "search_opinionscited";
            CREATE  TRIGGER pgtrigger_snapshot_insert_89103
                AFTER INSERT ON "search_opinionscited"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_snapshot_insert_89103();

            COMMENT ON TRIGGER pgtrigger_snapshot_insert_89103 ON "search_opinionscited" IS 'f91e95831640ad3589cb7d1dc1cc1a2983af00d9';
        ;
--
-- Create trigger snapshot_update on model opinionopinionscited
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

            CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6ec56()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_opinionopinionscitedevent" ("cited_opinion_id", "citing_opinion_id", "depth", "id", "pgh_context_id", "pgh_created_at", "pgh_label") VALUES (NEW."cited_opinion_id", NEW."citing_opinion_id", NEW."depth", NEW."id", _pgh_attach_context(), NOW(), 'snapshot'); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6ec56 ON "search_opinionscited";
            CREATE  TRIGGER pgtrigger_snapshot_update_6ec56
                AFTER UPDATE ON "search_opinionscited"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_snapshot_update_6ec56();

            COMMENT ON TRIGGER pgtrigger_snapshot_update_6ec56 ON "search_opinionscited" IS 'a9363eda8800fd5daa11ef4119ede0e8d576fd9f';
        ;
CREATE INDEX "search_opinionopinionscitedevent_cited_opinion_id_d147b66f" ON "search_opinionopinionscitedevent" ("cited_opinion_id");
CREATE INDEX "search_opinionopinionscitedevent_citing_opinion_id_5b43099b" ON "search_opinionopinionscitedevent" ("citing_opinion_id");
CREATE INDEX "search_opinionopinionscitedevent_pgh_context_id_f93ba49c" ON "search_opinionopinionscitedevent" ("pgh_context_id");
CREATE INDEX "search_opinionjoinedbyevent_opinion_id_9271b281" ON "search_opinionjoinedbyevent" ("opinion_id");
CREATE INDEX "search_opinionjoinedbyevent_person_id_dffa9dcb" ON "search_opinionjoinedbyevent" ("person_id");
CREATE INDEX "search_opinionjoinedbyevent_pgh_context_id_48acc9ad" ON "search_opinionjoinedbyevent" ("pgh_context_id");
CREATE INDEX "search_opinionevent_author_id_43b0c67a" ON "search_opinionevent" ("author_id");
CREATE INDEX "search_opinionevent_cluster_id_1205465b" ON "search_opinionevent" ("cluster_id");
CREATE INDEX "search_opinionevent_pgh_context_id_723082e0" ON "search_opinionevent" ("pgh_context_id");
CREATE INDEX "search_opinionevent_pgh_obj_id_63a2bc5f" ON "search_opinionevent" ("pgh_obj_id");
CREATE INDEX "search_opinionclusterpanelevent_opinioncluster_id_7128c9e4" ON "search_opinionclusterpanelevent" ("opinioncluster_id");
CREATE INDEX "search_opinionclusterpanelevent_person_id_b1c6a4a7" ON "search_opinionclusterpanelevent" ("person_id");
CREATE INDEX "search_opinionclusterpanelevent_pgh_context_id_8dcb8078" ON "search_opinionclusterpanelevent" ("pgh_context_id");
CREATE INDEX "search_opinionclusternonpa_opinioncluster_id_cc505710" ON "search_opinionclusternonparticipatingjudgesevent" ("opinioncluster_id");
CREATE INDEX "search_opinionclusternonpa_person_id_7bf4f773" ON "search_opinionclusternonparticipatingjudgesevent" ("person_id");
CREATE INDEX "search_opinionclusternonpa_pgh_context_id_aef74bea" ON "search_opinionclusternonparticipatingjudgesevent" ("pgh_context_id");
CREATE INDEX "search_opinionclusterevent_docket_id_165932da" ON "search_opinionclusterevent" ("docket_id");
CREATE INDEX "search_opinionclusterevent_pgh_context_id_273003da" ON "search_opinionclusterevent" ("pgh_context_id");
CREATE INDEX "search_opinionclusterevent_pgh_obj_id_f1ea380d" ON "search_opinionclusterevent" ("pgh_obj_id");
CREATE INDEX "search_dockettagsevent_docket_id_b1874f82" ON "search_dockettagsevent" ("docket_id");
CREATE INDEX "search_dockettagsevent_pgh_context_id_69b62450" ON "search_dockettagsevent" ("pgh_context_id");
CREATE INDEX "search_dockettagsevent_tag_id_728990f4" ON "search_dockettagsevent" ("tag_id");
CREATE INDEX "search_docketpanelevent_docket_id_1a9e206c" ON "search_docketpanelevent" ("docket_id");
CREATE INDEX "search_docketpanelevent_person_id_97094b3d" ON "search_docketpanelevent" ("person_id");
CREATE INDEX "search_docketpanelevent_pgh_context_id_03019aa7" ON "search_docketpanelevent" ("pgh_context_id");
CREATE INDEX "search_docketevent_appeal_from_id_388367c7" ON "search_docketevent" ("appeal_from_id");
CREATE INDEX "search_docketevent_appeal_from_id_388367c7_like" ON "search_docketevent" ("appeal_from_id" varchar_pattern_ops);
CREATE INDEX "search_docketevent_assigned_to_id_13bac477" ON "search_docketevent" ("assigned_to_id");
CREATE INDEX "search_docketevent_court_id_c6baeb82" ON "search_docketevent" ("court_id");
CREATE INDEX "search_docketevent_court_id_c6baeb82_like" ON "search_docketevent" ("court_id" varchar_pattern_ops);
CREATE INDEX "search_docketevent_idb_data_id_62179a0f" ON "search_docketevent" ("idb_data_id");
CREATE INDEX "search_docketevent_originating_court_information_id_47acc418" ON "search_docketevent" ("originating_court_information_id");
CREATE INDEX "search_docketevent_pgh_context_id_72300038" ON "search_docketevent" ("pgh_context_id");
CREATE INDEX "search_docketevent_pgh_obj_id_5d06013e" ON "search_docketevent" ("pgh_obj_id");
CREATE INDEX "search_docketevent_referred_to_id_ba58a272" ON "search_docketevent" ("referred_to_id");
CREATE INDEX "search_courtevent_pgh_context_id_7a93b57e" ON "search_courtevent" ("pgh_context_id");
CREATE INDEX "search_courtevent_pgh_obj_id_a86c8348" ON "search_courtevent" ("pgh_obj_id");
CREATE INDEX "search_courtevent_pgh_obj_id_a86c8348_like" ON "search_courtevent" ("pgh_obj_id" varchar_pattern_ops);
CREATE INDEX "search_citationevent_cluster_id_3cc4bdde" ON "search_citationevent" ("cluster_id");
CREATE INDEX "search_citationevent_pgh_context_id_a721796b" ON "search_citationevent" ("pgh_context_id");
CREATE INDEX "search_citationevent_pgh_obj_id_74bef0e4" ON "search_citationevent" ("pgh_obj_id");
COMMIT;
