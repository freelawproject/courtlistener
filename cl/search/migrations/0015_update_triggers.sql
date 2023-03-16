BEGIN;
--
-- Remove trigger snapshot_insert from model bankruptcyinformation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cfb47 ON "search_bankruptcyinformation";
--
-- Remove trigger snapshot_update from model bankruptcyinformation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_3cb5e ON "search_bankruptcyinformation";
--
-- Remove trigger snapshot_insert from model citation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_596d3 ON "search_citation";
--
-- Remove trigger snapshot_update from model citation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_31b3d ON "search_citation";
--
-- Remove trigger snapshot_insert from model claim
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b04cb ON "search_claim";
--
-- Remove trigger snapshot_update from model claim
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_63c7f ON "search_claim";
--
-- Remove trigger snapshot_insert from model claimhistory
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6ef1e ON "search_claimhistory";
--
-- Remove trigger snapshot_update from model claimhistory
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6d7e5 ON "search_claimhistory";
--
-- Remove trigger snapshot_insert from model claimtags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_5fb47 ON "search_claim_tags";
--
-- Remove trigger snapshot_update from model claimtags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_0f6a3 ON "search_claim_tags";
--
-- Remove trigger snapshot_insert from model court
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_82101 ON "search_court";
--
-- Remove trigger snapshot_update from model court
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc9e2 ON "search_court";
--
-- Remove trigger snapshot_insert from model docket
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_fe9ff ON "search_docket";
--
-- Remove trigger snapshot_update from model docket
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1e722 ON "search_docket";
--
-- Remove trigger snapshot_insert from model docketentry
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_2de73 ON "search_docketentry";
--
-- Remove trigger snapshot_update from model docketentry
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d8176 ON "search_docketentry";
--
-- Remove trigger snapshot_insert from model docketentrytags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_feff2 ON "search_docketentry_tags";
--
-- Remove trigger snapshot_update from model docketentrytags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1a242 ON "search_docketentry_tags";
--
-- Remove trigger snapshot_insert from model docketpanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_23fa7 ON "search_docket_panel";
--
-- Remove trigger snapshot_update from model docketpanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_e0bd2 ON "search_docket_panel";
--
-- Remove trigger snapshot_insert from model dockettags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b723b ON "search_docket_tags";
--
-- Remove trigger snapshot_update from model dockettags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_59839 ON "search_docket_tags";
--
-- Remove trigger snapshot_insert from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6ae1e ON "search_opinion";
--
-- Remove trigger snapshot_update from model opinion
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cdf06 ON "search_opinion";
--
-- Remove trigger snapshot_insert from model opinioncluster
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b55e2 ON "search_opinioncluster";
--
-- Remove trigger snapshot_update from model opinioncluster
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_f129e ON "search_opinioncluster";
--
-- Remove trigger snapshot_insert from model opinionclusternonparticipatingjudges
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0000e ON "search_opinioncluster_non_participating_judges";
--
-- Remove trigger snapshot_update from model opinionclusternonparticipatingjudges
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f2d1 ON "search_opinioncluster_non_participating_judges";
--
-- Remove trigger snapshot_insert from model opinionclusterpanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3e719 ON "search_opinioncluster_panel";
--
-- Remove trigger snapshot_update from model opinionclusterpanel
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2a689 ON "search_opinioncluster_panel";
--
-- Remove trigger snapshot_insert from model opinionjoinedby
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_541c3 ON "search_opinion_joined_by";
--
-- Remove trigger snapshot_update from model opinionjoinedby
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_23a70 ON "search_opinion_joined_by";
--
-- Remove trigger snapshot_insert from model originatingcourtinformation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_73cad ON "search_originatingcourtinformation";
--
-- Remove trigger snapshot_update from model originatingcourtinformation
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_b65c9 ON "search_originatingcourtinformation";
--
-- Remove trigger snapshot_insert from model recapdocument
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_570b5 ON "search_recapdocument";
--
-- Remove trigger snapshot_update from model recapdocument
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6713a ON "search_recapdocument";
--
-- Remove trigger snapshot_insert from model recapdocumenttags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_fd858 ON "search_recapdocument_tags";
--
-- Remove trigger snapshot_update from model recapdocumenttags
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_52362 ON "search_recapdocument_tags";
--
-- Remove trigger snapshot_insert from model tag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3bd86 ON "search_tag";
--
-- Remove trigger snapshot_update from model tag
--
DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_a85e0 ON "search_tag";
--
-- Create trigger custom_snapshot_update on model bankruptcyinformation
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_2d975()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_bankruptcyinformationevent" ("chapter", "date_converted", "date_created",
                                                     "date_debtor_dismissed", "date_last_to_file_claims",
                                                     "date_last_to_file_govt", "date_modified", "docket_id", "id",
                                                     "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                                     "trustee_str")
    VALUES (OLD."chapter", OLD."date_converted", OLD."date_created", OLD."date_debtor_dismissed",
            OLD."date_last_to_file_claims", OLD."date_last_to_file_govt", OLD."date_modified", OLD."docket_id",
            OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."trustee_str");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_2d975 ON "search_bankruptcyinformation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_2d975
    AFTER UPDATE
    ON "search_bankruptcyinformation"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."docket_id" IS DISTINCT FROM NEW."docket_id" OR
          OLD."date_converted" IS DISTINCT FROM NEW."date_converted" OR
          OLD."date_last_to_file_claims" IS DISTINCT FROM NEW."date_last_to_file_claims" OR
          OLD."date_last_to_file_govt" IS DISTINCT FROM NEW."date_last_to_file_govt" OR
          OLD."date_debtor_dismissed" IS DISTINCT FROM NEW."date_debtor_dismissed" OR
          OLD."chapter" IS DISTINCT FROM NEW."chapter" OR OLD."trustee_str" IS DISTINCT FROM NEW."trustee_str")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2d975();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2d975 ON "search_bankruptcyinformation" IS '657ccc4d7a2ae92a64c5dbd649e6db6a2605a540';
;
--
-- Create trigger custom_snapshot_update on model citation
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_5c8dd()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_citationevent" ("cluster_id", "id", "page", "pgh_context_id", "pgh_created_at", "pgh_label",
                                        "pgh_obj_id", "reporter", "type", "volume")
    VALUES (OLD."cluster_id", OLD."id", OLD."page", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."reporter", OLD."type", OLD."volume");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_5c8dd ON "search_citation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_5c8dd
    AFTER UPDATE
    ON "search_citation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_5c8dd();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_5c8dd ON "search_citation" IS 'cfffec0c5e5e03f909ad2dc19ff6d83e2f3bb34e';
;
--
-- Create trigger custom_snapshot_update on model claim
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_76873()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_claimevent" ("amount_claimed", "claim_number", "creditor_details", "creditor_id",
                                     "date_claim_modified", "date_created", "date_last_amendment_entered",
                                     "date_last_amendment_filed", "date_modified", "date_original_entered",
                                     "date_original_filed", "description", "docket_id", "entered_by", "filed_by", "id",
                                     "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "priority_claimed",
                                     "remarks", "secured_claimed", "status", "unsecured_claimed")
    VALUES (OLD."amount_claimed", OLD."claim_number", OLD."creditor_details", OLD."creditor_id",
            OLD."date_claim_modified", OLD."date_created", OLD."date_last_amendment_entered",
            OLD."date_last_amendment_filed", OLD."date_modified", OLD."date_original_entered",
            OLD."date_original_filed", OLD."description", OLD."docket_id", OLD."entered_by", OLD."filed_by", OLD."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."priority_claimed", OLD."remarks",
            OLD."secured_claimed", OLD."status", OLD."unsecured_claimed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_76873 ON "search_claim";
CREATE TRIGGER pgtrigger_custom_snapshot_update_76873
    AFTER UPDATE
    ON "search_claim"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."docket_id" IS DISTINCT FROM NEW."docket_id" OR
          OLD."date_claim_modified" IS DISTINCT FROM NEW."date_claim_modified" OR
          OLD."date_original_entered" IS DISTINCT FROM NEW."date_original_entered" OR
          OLD."date_original_filed" IS DISTINCT FROM NEW."date_original_filed" OR
          OLD."date_last_amendment_entered" IS DISTINCT FROM NEW."date_last_amendment_entered" OR
          OLD."date_last_amendment_filed" IS DISTINCT FROM NEW."date_last_amendment_filed" OR
          OLD."claim_number" IS DISTINCT FROM NEW."claim_number" OR
          OLD."creditor_details" IS DISTINCT FROM NEW."creditor_details" OR
          OLD."creditor_id" IS DISTINCT FROM NEW."creditor_id" OR OLD."status" IS DISTINCT FROM NEW."status" OR
          OLD."entered_by" IS DISTINCT FROM NEW."entered_by" OR OLD."filed_by" IS DISTINCT FROM NEW."filed_by" OR
          OLD."amount_claimed" IS DISTINCT FROM NEW."amount_claimed" OR
          OLD."unsecured_claimed" IS DISTINCT FROM NEW."unsecured_claimed" OR
          OLD."secured_claimed" IS DISTINCT FROM NEW."secured_claimed" OR
          OLD."priority_claimed" IS DISTINCT FROM NEW."priority_claimed" OR
          OLD."description" IS DISTINCT FROM NEW."description" OR OLD."remarks" IS DISTINCT FROM NEW."remarks")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_76873();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_76873 ON "search_claim" IS 'd2379afbfc0afd045ad6e8a227358cd8327bb0e1';
;
--
-- Create trigger custom_snapshot_update on model claimhistory
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_aa65e()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_claimhistoryevent" ("attachment_number", "claim_doc_id", "claim_document_type", "claim_id",
                                            "date_created", "date_filed", "date_modified", "date_upload", "description",
                                            "document_number", "file_size", "filepath_ia", "filepath_local",
                                            "ia_upload_failure_count", "id", "is_available", "is_free_on_pacer",
                                            "is_sealed", "ocr_status", "pacer_case_id", "pacer_dm_id", "pacer_doc_id",
                                            "page_count", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id",
                                            "plain_text", "sha1", "thumbnail", "thumbnail_status")
    VALUES (OLD."attachment_number", OLD."claim_doc_id", OLD."claim_document_type", OLD."claim_id", OLD."date_created",
            OLD."date_filed", OLD."date_modified", OLD."date_upload", OLD."description", OLD."document_number",
            OLD."file_size", OLD."filepath_ia", OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id",
            OLD."is_available", OLD."is_free_on_pacer", OLD."is_sealed", OLD."ocr_status", OLD."pacer_case_id",
            OLD."pacer_dm_id", OLD."pacer_doc_id", OLD."page_count", _pgh_attach_context(), NOW(), 'custom_snapshot',
            OLD."id", OLD."plain_text", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_aa65e ON "search_claimhistory";
CREATE TRIGGER pgtrigger_custom_snapshot_update_aa65e
    AFTER UPDATE
    ON "search_claimhistory"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."sha1" IS DISTINCT FROM NEW."sha1" OR OLD."page_count" IS DISTINCT FROM NEW."page_count" OR
          OLD."file_size" IS DISTINCT FROM NEW."file_size" OR
          OLD."filepath_local" IS DISTINCT FROM NEW."filepath_local" OR
          OLD."filepath_ia" IS DISTINCT FROM NEW."filepath_ia" OR
          OLD."ia_upload_failure_count" IS DISTINCT FROM NEW."ia_upload_failure_count" OR
          OLD."thumbnail" IS DISTINCT FROM NEW."thumbnail" OR
          OLD."thumbnail_status" IS DISTINCT FROM NEW."thumbnail_status" OR
          OLD."plain_text" IS DISTINCT FROM NEW."plain_text" OR OLD."ocr_status" IS DISTINCT FROM NEW."ocr_status" OR
          OLD."date_upload" IS DISTINCT FROM NEW."date_upload" OR
          OLD."document_number" IS DISTINCT FROM NEW."document_number" OR
          OLD."attachment_number" IS DISTINCT FROM NEW."attachment_number" OR
          OLD."pacer_doc_id" IS DISTINCT FROM NEW."pacer_doc_id" OR
          OLD."is_available" IS DISTINCT FROM NEW."is_available" OR
          OLD."is_free_on_pacer" IS DISTINCT FROM NEW."is_free_on_pacer" OR
          OLD."is_sealed" IS DISTINCT FROM NEW."is_sealed" OR OLD."claim_id" IS DISTINCT FROM NEW."claim_id" OR
          OLD."date_filed" IS DISTINCT FROM NEW."date_filed" OR
          OLD."claim_document_type" IS DISTINCT FROM NEW."claim_document_type" OR
          OLD."description" IS DISTINCT FROM NEW."description" OR
          OLD."claim_doc_id" IS DISTINCT FROM NEW."claim_doc_id" OR
          OLD."pacer_dm_id" IS DISTINCT FROM NEW."pacer_dm_id" OR
          OLD."pacer_case_id" IS DISTINCT FROM NEW."pacer_case_id")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_aa65e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_aa65e ON "search_claimhistory" IS '6c6f7374cce2a90fefeb37b4aade9fda40b5022c';
;
--
-- Create trigger custom_snapshot_update on model claimtags
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_de007()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_claimtagsevent" ("claim_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "tag_id")
    VALUES (OLD."claim_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_de007 ON "search_claim_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_update_de007
    AFTER UPDATE
    ON "search_claim_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_de007();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_de007 ON "search_claim_tags" IS 'b0ffc2d5d494db8c1e8c8a9a181b0a1fde529e48';
;
--
-- Create trigger custom_snapshot_update on model court
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_94f74()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_courtevent" ("citation_string", "date_last_pacer_contact", "date_modified", "end_date",
                                     "fjc_court_id", "full_name", "has_opinion_scraper", "has_oral_argument_scraper",
                                     "id", "in_use", "jurisdiction", "notes", "pacer_court_id", "pacer_has_rss_feed",
                                     "pacer_rss_entry_types", "pgh_context_id", "pgh_created_at", "pgh_label",
                                     "pgh_obj_id", "position", "short_name", "start_date", "url")
    VALUES (OLD."citation_string", OLD."date_last_pacer_contact", OLD."date_modified", OLD."end_date",
            OLD."fjc_court_id", OLD."full_name", OLD."has_opinion_scraper", OLD."has_oral_argument_scraper", OLD."id",
            OLD."in_use", OLD."jurisdiction", OLD."notes", OLD."pacer_court_id", OLD."pacer_has_rss_feed",
            OLD."pacer_rss_entry_types", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."position",
            OLD."short_name", OLD."start_date", OLD."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_94f74 ON "search_court";
CREATE TRIGGER pgtrigger_custom_snapshot_update_94f74
    AFTER UPDATE
    ON "search_court"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."pacer_court_id" IS DISTINCT FROM NEW."pacer_court_id" OR
          OLD."pacer_has_rss_feed" IS DISTINCT FROM NEW."pacer_has_rss_feed" OR
          OLD."pacer_rss_entry_types" IS DISTINCT FROM NEW."pacer_rss_entry_types" OR
          OLD."date_last_pacer_contact" IS DISTINCT FROM NEW."date_last_pacer_contact" OR
          OLD."fjc_court_id" IS DISTINCT FROM NEW."fjc_court_id" OR OLD."in_use" IS DISTINCT FROM NEW."in_use" OR
          OLD."has_opinion_scraper" IS DISTINCT FROM NEW."has_opinion_scraper" OR
          OLD."has_oral_argument_scraper" IS DISTINCT FROM NEW."has_oral_argument_scraper" OR
          OLD."position" IS DISTINCT FROM NEW."position" OR
          OLD."citation_string" IS DISTINCT FROM NEW."citation_string" OR
          OLD."short_name" IS DISTINCT FROM NEW."short_name" OR OLD."full_name" IS DISTINCT FROM NEW."full_name" OR
          OLD."url" IS DISTINCT FROM NEW."url" OR OLD."start_date" IS DISTINCT FROM NEW."start_date" OR
          OLD."end_date" IS DISTINCT FROM NEW."end_date" OR OLD."jurisdiction" IS DISTINCT FROM NEW."jurisdiction" OR
          OLD."notes" IS DISTINCT FROM NEW."notes")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_94f74();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_94f74 ON "search_court" IS 'eef2fbd964fa3090df69e7919a8672ac6742e5e2';
;
--
-- Create trigger custom_snapshot_update on model docket
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_a5c9a()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str", "appellate_case_type_information",
                                      "appellate_fee_status", "assigned_to_id", "assigned_to_str", "blocked",
                                      "case_name", "case_name_full", "case_name_short", "cause", "court_id",
                                      "date_argued", "date_blocked", "date_cert_denied", "date_cert_granted",
                                      "date_created", "date_filed", "date_last_filing", "date_last_index",
                                      "date_modified", "date_reargued", "date_reargument_denied", "date_terminated",
                                      "docket_number", "docket_number_core", "filepath_ia", "filepath_ia_json",
                                      "filepath_local", "ia_date_first_change", "ia_needs_upload",
                                      "ia_upload_failure_count", "id", "idb_data_id", "jurisdiction_type",
                                      "jury_demand", "mdl_status", "nature_of_suit", "originating_court_information_id",
                                      "pacer_case_id", "panel_str", "pgh_context_id", "pgh_created_at", "pgh_label",
                                      "pgh_obj_id", "referred_to_id", "referred_to_str", "slug", "source")
    VALUES (OLD."appeal_from_id", OLD."appeal_from_str", OLD."appellate_case_type_information",
            OLD."appellate_fee_status", OLD."assigned_to_id", OLD."assigned_to_str", OLD."blocked", OLD."case_name",
            OLD."case_name_full", OLD."case_name_short", OLD."cause", OLD."court_id", OLD."date_argued",
            OLD."date_blocked", OLD."date_cert_denied", OLD."date_cert_granted", OLD."date_created", OLD."date_filed",
            OLD."date_last_filing", OLD."date_last_index", OLD."date_modified", OLD."date_reargued",
            OLD."date_reargument_denied", OLD."date_terminated", OLD."docket_number", OLD."docket_number_core",
            OLD."filepath_ia", OLD."filepath_ia_json", OLD."filepath_local", OLD."ia_date_first_change",
            OLD."ia_needs_upload", OLD."ia_upload_failure_count", OLD."id", OLD."idb_data_id", OLD."jurisdiction_type",
            OLD."jury_demand", OLD."mdl_status", OLD."nature_of_suit", OLD."originating_court_information_id",
            OLD."pacer_case_id", OLD."panel_str", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."referred_to_id", OLD."referred_to_str", OLD."slug", OLD."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_a5c9a ON "search_docket";
CREATE TRIGGER pgtrigger_custom_snapshot_update_a5c9a
    AFTER UPDATE
    ON "search_docket"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."source" IS DISTINCT FROM NEW."source" OR OLD."court_id" IS DISTINCT FROM NEW."court_id" OR
          OLD."appeal_from_id" IS DISTINCT FROM NEW."appeal_from_id" OR
          OLD."appeal_from_str" IS DISTINCT FROM NEW."appeal_from_str" OR
          OLD."originating_court_information_id" IS DISTINCT FROM NEW."originating_court_information_id" OR
          OLD."idb_data_id" IS DISTINCT FROM NEW."idb_data_id" OR
          OLD."assigned_to_id" IS DISTINCT FROM NEW."assigned_to_id" OR
          OLD."assigned_to_str" IS DISTINCT FROM NEW."assigned_to_str" OR
          OLD."referred_to_id" IS DISTINCT FROM NEW."referred_to_id" OR
          OLD."referred_to_str" IS DISTINCT FROM NEW."referred_to_str" OR
          OLD."panel_str" IS DISTINCT FROM NEW."panel_str" OR
          OLD."date_last_index" IS DISTINCT FROM NEW."date_last_index" OR
          OLD."date_cert_granted" IS DISTINCT FROM NEW."date_cert_granted" OR
          OLD."date_cert_denied" IS DISTINCT FROM NEW."date_cert_denied" OR
          OLD."date_argued" IS DISTINCT FROM NEW."date_argued" OR
          OLD."date_reargued" IS DISTINCT FROM NEW."date_reargued" OR
          OLD."date_reargument_denied" IS DISTINCT FROM NEW."date_reargument_denied" OR
          OLD."date_filed" IS DISTINCT FROM NEW."date_filed" OR
          OLD."date_terminated" IS DISTINCT FROM NEW."date_terminated" OR
          OLD."date_last_filing" IS DISTINCT FROM NEW."date_last_filing" OR
          OLD."case_name_short" IS DISTINCT FROM NEW."case_name_short" OR
          OLD."case_name" IS DISTINCT FROM NEW."case_name" OR
          OLD."case_name_full" IS DISTINCT FROM NEW."case_name_full" OR OLD."slug" IS DISTINCT FROM NEW."slug" OR
          OLD."docket_number" IS DISTINCT FROM NEW."docket_number" OR
          OLD."docket_number_core" IS DISTINCT FROM NEW."docket_number_core" OR
          OLD."pacer_case_id" IS DISTINCT FROM NEW."pacer_case_id" OR OLD."cause" IS DISTINCT FROM NEW."cause" OR
          OLD."nature_of_suit" IS DISTINCT FROM NEW."nature_of_suit" OR
          OLD."jury_demand" IS DISTINCT FROM NEW."jury_demand" OR
          OLD."jurisdiction_type" IS DISTINCT FROM NEW."jurisdiction_type" OR
          OLD."appellate_fee_status" IS DISTINCT FROM NEW."appellate_fee_status" OR
          OLD."appellate_case_type_information" IS DISTINCT FROM NEW."appellate_case_type_information" OR
          OLD."mdl_status" IS DISTINCT FROM NEW."mdl_status" OR
          OLD."filepath_local" IS DISTINCT FROM NEW."filepath_local" OR
          OLD."filepath_ia" IS DISTINCT FROM NEW."filepath_ia" OR
          OLD."filepath_ia_json" IS DISTINCT FROM NEW."filepath_ia_json" OR
          OLD."ia_upload_failure_count" IS DISTINCT FROM NEW."ia_upload_failure_count" OR
          OLD."ia_needs_upload" IS DISTINCT FROM NEW."ia_needs_upload" OR
          OLD."ia_date_first_change" IS DISTINCT FROM NEW."ia_date_first_change" OR
          OLD."date_blocked" IS DISTINCT FROM NEW."date_blocked" OR OLD."blocked" IS DISTINCT FROM NEW."blocked")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_a5c9a();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_a5c9a ON "search_docket" IS 'c2aae13b60683fab35ecc126d707c7b08cd0d69a';
;
--
-- Create trigger custom_snapshot_update on model docketentry
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_1fcaa()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_docketentryevent" ("date_created", "date_filed", "date_modified", "description", "docket_id",
                                           "entry_number", "id", "pacer_sequence_number", "pgh_context_id",
                                           "pgh_created_at", "pgh_label", "pgh_obj_id", "recap_sequence_number",
                                           "time_filed")
    VALUES (OLD."date_created", OLD."date_filed", OLD."date_modified", OLD."description", OLD."docket_id",
            OLD."entry_number", OLD."id", OLD."pacer_sequence_number", _pgh_attach_context(), NOW(), 'custom_snapshot',
            OLD."id", OLD."recap_sequence_number", OLD."time_filed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_1fcaa ON "search_docketentry";
CREATE TRIGGER pgtrigger_custom_snapshot_update_1fcaa
    AFTER UPDATE
    ON "search_docketentry"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."docket_id" IS DISTINCT FROM NEW."docket_id" OR OLD."date_filed" IS DISTINCT FROM NEW."date_filed" OR
          OLD."time_filed" IS DISTINCT FROM NEW."time_filed" OR
          OLD."entry_number" IS DISTINCT FROM NEW."entry_number" OR
          OLD."recap_sequence_number" IS DISTINCT FROM NEW."recap_sequence_number" OR
          OLD."pacer_sequence_number" IS DISTINCT FROM NEW."pacer_sequence_number" OR
          OLD."description" IS DISTINCT FROM NEW."description")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_1fcaa();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_1fcaa ON "search_docketentry" IS 'f3875da23fceafcc4abe78f2358d754fff09bd7f';
;
--
-- Create trigger custom_snapshot_update on model docketentrytags
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_63669()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_docketentrytagsevent" ("docketentry_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                               "tag_id")
    VALUES (OLD."docketentry_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_63669 ON "search_docketentry_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_update_63669
    AFTER UPDATE
    ON "search_docketentry_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_63669();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_63669 ON "search_docketentry_tags" IS 'ecdcc45eed67cbbb684d972cc2558702ad0403eb';
;
--
-- Create trigger custom_snapshot_update on model docketpanel
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_6b46c()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_docketpanelevent" ("docket_id", "id", "person_id", "pgh_context_id", "pgh_created_at",
                                           "pgh_label")
    VALUES (OLD."docket_id", OLD."id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_6b46c ON "search_docket_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_update_6b46c
    AFTER UPDATE
    ON "search_docket_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_6b46c();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_6b46c ON "search_docket_panel" IS '8e665c08631ef348ce02db66c55944b6d8f07be1';
;
--
-- Create trigger custom_snapshot_update on model dockettags
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_1e09e()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_dockettagsevent" ("docket_id", "id", "pgh_context_id", "pgh_created_at", "pgh_label", "tag_id")
    VALUES (OLD."docket_id", OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_1e09e ON "search_docket_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_update_1e09e
    AFTER UPDATE
    ON "search_docket_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_1e09e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_1e09e ON "search_docket_tags" IS '560eb2ddfa3fc28e6559091655f13dac8b138097';
;
--
-- Create trigger custom_snapshot_update on model opinion
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_e1164()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id", "date_created", "date_modified",
                                       "download_url", "extracted_by_ocr", "html", "html_anon_2020", "html_columbia",
                                       "html_lawbox", "html_with_citations", "id", "joined_by_str", "local_path",
                                       "page_count", "per_curiam", "pgh_context_id", "pgh_created_at", "pgh_label",
                                       "pgh_obj_id", "plain_text", "sha1", "type", "xml_harvard")
    VALUES (OLD."author_id", OLD."author_str", OLD."cluster_id", OLD."date_created", OLD."date_modified",
            OLD."download_url", OLD."extracted_by_ocr", OLD."html", OLD."html_anon_2020", OLD."html_columbia",
            OLD."html_lawbox", OLD."html_with_citations", OLD."id", OLD."joined_by_str", OLD."local_path",
            OLD."page_count", OLD."per_curiam", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id",
            OLD."plain_text", OLD."sha1", OLD."type", OLD."xml_harvard");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_e1164 ON "search_opinion";
CREATE TRIGGER pgtrigger_custom_snapshot_update_e1164
    AFTER UPDATE
    ON "search_opinion"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."cluster_id" IS DISTINCT FROM NEW."cluster_id" OR OLD."author_id" IS DISTINCT FROM NEW."author_id" OR
          OLD."author_str" IS DISTINCT FROM NEW."author_str" OR OLD."per_curiam" IS DISTINCT FROM NEW."per_curiam" OR
          OLD."joined_by_str" IS DISTINCT FROM NEW."joined_by_str" OR OLD."type" IS DISTINCT FROM NEW."type" OR
          OLD."sha1" IS DISTINCT FROM NEW."sha1" OR OLD."page_count" IS DISTINCT FROM NEW."page_count" OR
          OLD."download_url" IS DISTINCT FROM NEW."download_url" OR
          OLD."local_path" IS DISTINCT FROM NEW."local_path" OR OLD."plain_text" IS DISTINCT FROM NEW."plain_text" OR
          OLD."html" IS DISTINCT FROM NEW."html" OR OLD."html_lawbox" IS DISTINCT FROM NEW."html_lawbox" OR
          OLD."html_columbia" IS DISTINCT FROM NEW."html_columbia" OR
          OLD."html_anon_2020" IS DISTINCT FROM NEW."html_anon_2020" OR
          OLD."xml_harvard" IS DISTINCT FROM NEW."xml_harvard" OR
          OLD."html_with_citations" IS DISTINCT FROM NEW."html_with_citations" OR
          OLD."extracted_by_ocr" IS DISTINCT FROM NEW."extracted_by_ocr")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_e1164();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_e1164 ON "search_opinion" IS 'bf51d30cc89eddb1db6454f7124da5b56168fc5d';
;
--
-- Create trigger custom_snapshot_update on model opinioncluster
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_927eb()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_opinionclusterevent" ("attorneys", "blocked", "case_name", "case_name_full", "case_name_short",
                                              "citation_count", "correction", "cross_reference", "date_blocked",
                                              "date_created", "date_filed", "date_filed_is_approximate",
                                              "date_modified", "disposition", "docket_id", "filepath_json_harvard",
                                              "headnotes", "history", "id", "judges", "nature_of_suit", "other_dates",
                                              "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "posture",
                                              "precedential_status", "procedural_history", "scdb_decision_direction",
                                              "scdb_id", "scdb_votes_majority", "scdb_votes_minority", "slug", "source",
                                              "summary", "syllabus")
    VALUES (OLD."attorneys", OLD."blocked", OLD."case_name", OLD."case_name_full", OLD."case_name_short",
            OLD."citation_count", OLD."correction", OLD."cross_reference", OLD."date_blocked", OLD."date_created",
            OLD."date_filed", OLD."date_filed_is_approximate", OLD."date_modified", OLD."disposition", OLD."docket_id",
            OLD."filepath_json_harvard", OLD."headnotes", OLD."history", OLD."id", OLD."judges", OLD."nature_of_suit",
            OLD."other_dates", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id", OLD."posture",
            OLD."precedential_status", OLD."procedural_history", OLD."scdb_decision_direction", OLD."scdb_id",
            OLD."scdb_votes_majority", OLD."scdb_votes_minority", OLD."slug", OLD."source", OLD."summary",
            OLD."syllabus");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_927eb ON "search_opinioncluster";
CREATE TRIGGER pgtrigger_custom_snapshot_update_927eb
    AFTER UPDATE
    ON "search_opinioncluster"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."docket_id" IS DISTINCT FROM NEW."docket_id" OR OLD."judges" IS DISTINCT FROM NEW."judges" OR
          OLD."date_filed" IS DISTINCT FROM NEW."date_filed" OR
          OLD."date_filed_is_approximate" IS DISTINCT FROM NEW."date_filed_is_approximate" OR
          OLD."slug" IS DISTINCT FROM NEW."slug" OR OLD."case_name_short" IS DISTINCT FROM NEW."case_name_short" OR
          OLD."case_name" IS DISTINCT FROM NEW."case_name" OR
          OLD."case_name_full" IS DISTINCT FROM NEW."case_name_full" OR OLD."scdb_id" IS DISTINCT FROM NEW."scdb_id" OR
          OLD."scdb_decision_direction" IS DISTINCT FROM NEW."scdb_decision_direction" OR
          OLD."scdb_votes_majority" IS DISTINCT FROM NEW."scdb_votes_majority" OR
          OLD."scdb_votes_minority" IS DISTINCT FROM NEW."scdb_votes_minority" OR
          OLD."source" IS DISTINCT FROM NEW."source" OR
          OLD."procedural_history" IS DISTINCT FROM NEW."procedural_history" OR
          OLD."attorneys" IS DISTINCT FROM NEW."attorneys" OR
          OLD."nature_of_suit" IS DISTINCT FROM NEW."nature_of_suit" OR OLD."posture" IS DISTINCT FROM NEW."posture" OR
          OLD."syllabus" IS DISTINCT FROM NEW."syllabus" OR OLD."headnotes" IS DISTINCT FROM NEW."headnotes" OR
          OLD."summary" IS DISTINCT FROM NEW."summary" OR OLD."disposition" IS DISTINCT FROM NEW."disposition" OR
          OLD."history" IS DISTINCT FROM NEW."history" OR OLD."other_dates" IS DISTINCT FROM NEW."other_dates" OR
          OLD."cross_reference" IS DISTINCT FROM NEW."cross_reference" OR
          OLD."correction" IS DISTINCT FROM NEW."correction" OR
          OLD."citation_count" IS DISTINCT FROM NEW."citation_count" OR
          OLD."precedential_status" IS DISTINCT FROM NEW."precedential_status" OR
          OLD."date_blocked" IS DISTINCT FROM NEW."date_blocked" OR OLD."blocked" IS DISTINCT FROM NEW."blocked" OR
          OLD."filepath_json_harvard" IS DISTINCT FROM NEW."filepath_json_harvard")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_927eb();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_927eb ON "search_opinioncluster" IS '53022c83e1da2739f43d7957ab4882c119960216';
;
--
-- Create trigger custom_snapshot_update on model opinionclusternonparticipatingjudges
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_ffb31()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_opinionclusternonparticipatingjudgesevent" ("id", "opinioncluster_id", "person_id",
                                                                    "pgh_context_id", "pgh_created_at", "pgh_label")
    VALUES (OLD."id", OLD."opinioncluster_id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_ffb31 ON "search_opinioncluster_non_participating_judges";
CREATE TRIGGER pgtrigger_custom_snapshot_update_ffb31
    AFTER UPDATE
    ON "search_opinioncluster_non_participating_judges"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_ffb31();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_ffb31 ON "search_opinioncluster_non_participating_judges" IS 'de6310eda964650917c4c813b12ae475958cff7b';
;
--
-- Create trigger custom_snapshot_update on model opinionclusterpanel
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_69622()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_opinionclusterpanelevent" ("id", "opinioncluster_id", "person_id", "pgh_context_id",
                                                   "pgh_created_at", "pgh_label")
    VALUES (OLD."id", OLD."opinioncluster_id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_69622 ON "search_opinioncluster_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_update_69622
    AFTER UPDATE
    ON "search_opinioncluster_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_69622();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_69622 ON "search_opinioncluster_panel" IS '22119c25de05266160154612a848d0387c587178';
;
--
-- Create trigger custom_snapshot_update on model opinionjoinedby
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_5a491()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_opinionjoinedbyevent" ("id", "opinion_id", "person_id", "pgh_context_id", "pgh_created_at",
                                               "pgh_label")
    VALUES (OLD."id", OLD."opinion_id", OLD."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_5a491 ON "search_opinion_joined_by";
CREATE TRIGGER pgtrigger_custom_snapshot_update_5a491
    AFTER UPDATE
    ON "search_opinion_joined_by"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_5a491();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_5a491 ON "search_opinion_joined_by" IS 'b41c8725925745435501525f1daae59ebe18cd52';
;
--
-- Create trigger custom_snapshot_update on model originatingcourtinformation
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_0891b()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_originatingcourtinformationevent" ("assigned_to_id", "assigned_to_str", "court_reporter",
                                                           "date_created", "date_disposed", "date_filed",
                                                           "date_filed_noa", "date_judgment", "date_judgment_eod",
                                                           "date_modified", "date_received_coa", "docket_number", "id",
                                                           "ordering_judge_id", "ordering_judge_str", "pgh_context_id",
                                                           "pgh_created_at", "pgh_label", "pgh_obj_id")
    VALUES (OLD."assigned_to_id", OLD."assigned_to_str", OLD."court_reporter", OLD."date_created", OLD."date_disposed",
            OLD."date_filed", OLD."date_filed_noa", OLD."date_judgment", OLD."date_judgment_eod", OLD."date_modified",
            OLD."date_received_coa", OLD."docket_number", OLD."id", OLD."ordering_judge_id", OLD."ordering_judge_str",
            _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_0891b ON "search_originatingcourtinformation";
CREATE TRIGGER pgtrigger_custom_snapshot_update_0891b
    AFTER UPDATE
    ON "search_originatingcourtinformation"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."docket_number" IS DISTINCT FROM NEW."docket_number" OR
          OLD."assigned_to_id" IS DISTINCT FROM NEW."assigned_to_id" OR
          OLD."assigned_to_str" IS DISTINCT FROM NEW."assigned_to_str" OR
          OLD."ordering_judge_id" IS DISTINCT FROM NEW."ordering_judge_id" OR
          OLD."ordering_judge_str" IS DISTINCT FROM NEW."ordering_judge_str" OR
          OLD."court_reporter" IS DISTINCT FROM NEW."court_reporter" OR
          OLD."date_disposed" IS DISTINCT FROM NEW."date_disposed" OR
          OLD."date_filed" IS DISTINCT FROM NEW."date_filed" OR
          OLD."date_judgment" IS DISTINCT FROM NEW."date_judgment" OR
          OLD."date_judgment_eod" IS DISTINCT FROM NEW."date_judgment_eod" OR
          OLD."date_filed_noa" IS DISTINCT FROM NEW."date_filed_noa" OR
          OLD."date_received_coa" IS DISTINCT FROM NEW."date_received_coa")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_0891b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_0891b ON "search_originatingcourtinformation" IS 'd86ec452da5e4f76fb0ade2fa7ac2f247d0f3368';
;
--
-- Create trigger custom_snapshot_update on model recapdocument
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_e466a()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_recapdocumentevent" ("attachment_number", "date_created", "date_modified", "date_upload",
                                             "description", "docket_entry_id", "document_number", "document_type",
                                             "file_size", "filepath_ia", "filepath_local", "ia_upload_failure_count",
                                             "id", "is_available", "is_free_on_pacer", "is_sealed", "ocr_status",
                                             "pacer_doc_id", "page_count", "pgh_context_id", "pgh_created_at",
                                             "pgh_label", "pgh_obj_id", "plain_text", "sha1", "thumbnail",
                                             "thumbnail_status")
    VALUES (OLD."attachment_number", OLD."date_created", OLD."date_modified", OLD."date_upload", OLD."description",
            OLD."docket_entry_id", OLD."document_number", OLD."document_type", OLD."file_size", OLD."filepath_ia",
            OLD."filepath_local", OLD."ia_upload_failure_count", OLD."id", OLD."is_available", OLD."is_free_on_pacer",
            OLD."is_sealed", OLD."ocr_status", OLD."pacer_doc_id", OLD."page_count", _pgh_attach_context(), NOW(),
            'custom_snapshot', OLD."id", OLD."plain_text", OLD."sha1", OLD."thumbnail", OLD."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_e466a ON "search_recapdocument";
CREATE TRIGGER pgtrigger_custom_snapshot_update_e466a
    AFTER UPDATE
    ON "search_recapdocument"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."sha1" IS DISTINCT FROM NEW."sha1" OR OLD."page_count" IS DISTINCT FROM NEW."page_count" OR
          OLD."file_size" IS DISTINCT FROM NEW."file_size" OR
          OLD."filepath_local" IS DISTINCT FROM NEW."filepath_local" OR
          OLD."filepath_ia" IS DISTINCT FROM NEW."filepath_ia" OR
          OLD."ia_upload_failure_count" IS DISTINCT FROM NEW."ia_upload_failure_count" OR
          OLD."thumbnail" IS DISTINCT FROM NEW."thumbnail" OR
          OLD."thumbnail_status" IS DISTINCT FROM NEW."thumbnail_status" OR
          OLD."plain_text" IS DISTINCT FROM NEW."plain_text" OR OLD."ocr_status" IS DISTINCT FROM NEW."ocr_status" OR
          OLD."date_upload" IS DISTINCT FROM NEW."date_upload" OR
          OLD."document_number" IS DISTINCT FROM NEW."document_number" OR
          OLD."attachment_number" IS DISTINCT FROM NEW."attachment_number" OR
          OLD."pacer_doc_id" IS DISTINCT FROM NEW."pacer_doc_id" OR
          OLD."is_available" IS DISTINCT FROM NEW."is_available" OR
          OLD."is_free_on_pacer" IS DISTINCT FROM NEW."is_free_on_pacer" OR
          OLD."is_sealed" IS DISTINCT FROM NEW."is_sealed" OR
          OLD."docket_entry_id" IS DISTINCT FROM NEW."docket_entry_id" OR
          OLD."document_type" IS DISTINCT FROM NEW."document_type" OR
          OLD."description" IS DISTINCT FROM NEW."description")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_e466a();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_e466a ON "search_recapdocument" IS '593e64987262f6541e6cd050bd7e0056b5515079';
;
--
-- Create trigger custom_snapshot_update on model recapdocumenttags
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_1e77f()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_recapdocumenttagsevent" ("id", "pgh_context_id", "pgh_created_at", "pgh_label",
                                                 "recapdocument_id", "tag_id")
    VALUES (OLD."id", _pgh_attach_context(), NOW(), 'custom_snapshot', OLD."recapdocument_id", OLD."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_1e77f ON "search_recapdocument_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_update_1e77f
    AFTER UPDATE
    ON "search_recapdocument_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_1e77f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_1e77f ON "search_recapdocument_tags" IS '0afc1523ccb5b27cba767724fc3e50d37d766b0e';
;
--
-- Create trigger custom_snapshot_update on model tag
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_update_2bc42()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "search_tagevent" ("date_created", "date_modified", "id", "name", "pgh_context_id", "pgh_created_at",
                                   "pgh_label", "pgh_obj_id")
    VALUES (OLD."date_created", OLD."date_modified", OLD."id", OLD."name", _pgh_attach_context(), NOW(),
            'custom_snapshot', OLD."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_update_2bc42 ON "search_tag";
CREATE TRIGGER pgtrigger_custom_snapshot_update_2bc42
    AFTER UPDATE
    ON "search_tag"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."name" IS DISTINCT FROM NEW."name")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2bc42();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2bc42 ON "search_tag" IS '6418d70c317a8acdfb154f1c8c35a145e3d08676';
;
COMMIT;
