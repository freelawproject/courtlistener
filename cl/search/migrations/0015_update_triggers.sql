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
-- Create trigger custom_snapshot_insert on model bankruptcyinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_0ce19()
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
    VALUES (NEW."chapter", NEW."date_converted", NEW."date_created", NEW."date_debtor_dismissed",
            NEW."date_last_to_file_claims", NEW."date_last_to_file_govt", NEW."date_modified", NEW."docket_id",
            NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."trustee_str");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_0ce19 ON "search_bankruptcyinformation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_0ce19
    AFTER INSERT
    ON "search_bankruptcyinformation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_0ce19();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_0ce19 ON "search_bankruptcyinformation" IS 'c467c3b2ca5838fa676f21c744bb4b8feb4afb39';
;
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2d975();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2d975 ON "search_bankruptcyinformation" IS '99f0b7b9558e69eed58c2bf61af7b94459078b9c';
;
--
-- Create trigger custom_snapshot_insert on model citation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_83000()
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
    VALUES (NEW."cluster_id", NEW."id", NEW."page", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."reporter", NEW."type", NEW."volume");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_83000 ON "search_citation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_83000
    AFTER INSERT
    ON "search_citation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_83000();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_83000 ON "search_citation" IS 'd1d83ce5524ab5dda81e13ac678a5a8e1593ea5c';
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
-- Create trigger custom_snapshot_insert on model claim
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_e8e87()
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
    VALUES (NEW."amount_claimed", NEW."claim_number", NEW."creditor_details", NEW."creditor_id",
            NEW."date_claim_modified", NEW."date_created", NEW."date_last_amendment_entered",
            NEW."date_last_amendment_filed", NEW."date_modified", NEW."date_original_entered",
            NEW."date_original_filed", NEW."description", NEW."docket_id", NEW."entered_by", NEW."filed_by", NEW."id",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."priority_claimed", NEW."remarks",
            NEW."secured_claimed", NEW."status", NEW."unsecured_claimed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_e8e87 ON "search_claim";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_e8e87
    AFTER INSERT
    ON "search_claim"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_e8e87();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_e8e87 ON "search_claim" IS '453e634b0355e80cb1b21a59a685954b5e702ec7';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_76873();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_76873 ON "search_claim" IS '00f9d3184af8a50cf4c5d6d26feb9c52ccf18f59';
;
--
-- Create trigger custom_snapshot_insert on model claimhistory
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_53e72()
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
    VALUES (NEW."attachment_number", NEW."claim_doc_id", NEW."claim_document_type", NEW."claim_id", NEW."date_created",
            NEW."date_filed", NEW."date_modified", NEW."date_upload", NEW."description", NEW."document_number",
            NEW."file_size", NEW."filepath_ia", NEW."filepath_local", NEW."ia_upload_failure_count", NEW."id",
            NEW."is_available", NEW."is_free_on_pacer", NEW."is_sealed", NEW."ocr_status", NEW."pacer_case_id",
            NEW."pacer_dm_id", NEW."pacer_doc_id", NEW."page_count", _pgh_attach_context(), NOW(), 'custom_snapshot',
            NEW."id", NEW."plain_text", NEW."sha1", NEW."thumbnail", NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_53e72 ON "search_claimhistory";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_53e72
    AFTER INSERT
    ON "search_claimhistory"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_53e72();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_53e72 ON "search_claimhistory" IS 'f189e46d1d76908a930296f0a7e246b93e4800c2';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_aa65e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_aa65e ON "search_claimhistory" IS '6e166458889009a05a4fcb89aab47bff611ebaaf';
;
--
-- Create trigger custom_snapshot_insert on model claimtags
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_e37f5()
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
    VALUES (NEW."claim_id", NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_e37f5 ON "search_claim_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_e37f5
    AFTER INSERT
    ON "search_claim_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_e37f5();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_e37f5 ON "search_claim_tags" IS '726b827f30385dadb1e30d67adf5b1432839b2e6';
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
-- Create trigger custom_snapshot_insert on model court
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_34307()
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
    VALUES (NEW."citation_string", NEW."date_last_pacer_contact", NEW."date_modified", NEW."end_date",
            NEW."fjc_court_id", NEW."full_name", NEW."has_opinion_scraper", NEW."has_oral_argument_scraper", NEW."id",
            NEW."in_use", NEW."jurisdiction", NEW."notes", NEW."pacer_court_id", NEW."pacer_has_rss_feed",
            NEW."pacer_rss_entry_types", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."position",
            NEW."short_name", NEW."start_date", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_34307 ON "search_court";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_34307
    AFTER INSERT
    ON "search_court"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_34307();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_34307 ON "search_court" IS 'a0f16e3881feb8305606df49ef13cb41baa0f3ce';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_94f74();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_94f74 ON "search_court" IS 'c36dc0f90219f1d2812f533878fc4e09e2851fe0';
;
--
-- Create trigger custom_snapshot_insert on model docket
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_69a95()
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
    VALUES (NEW."appeal_from_id", NEW."appeal_from_str", NEW."appellate_case_type_information",
            NEW."appellate_fee_status", NEW."assigned_to_id", NEW."assigned_to_str", NEW."blocked", NEW."case_name",
            NEW."case_name_full", NEW."case_name_short", NEW."cause", NEW."court_id", NEW."date_argued",
            NEW."date_blocked", NEW."date_cert_denied", NEW."date_cert_granted", NEW."date_created", NEW."date_filed",
            NEW."date_last_filing", NEW."date_last_index", NEW."date_modified", NEW."date_reargued",
            NEW."date_reargument_denied", NEW."date_terminated", NEW."docket_number", NEW."docket_number_core",
            NEW."filepath_ia", NEW."filepath_ia_json", NEW."filepath_local", NEW."ia_date_first_change",
            NEW."ia_needs_upload", NEW."ia_upload_failure_count", NEW."id", NEW."idb_data_id", NEW."jurisdiction_type",
            NEW."jury_demand", NEW."mdl_status", NEW."nature_of_suit", NEW."originating_court_information_id",
            NEW."pacer_case_id", NEW."panel_str", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."referred_to_id", NEW."referred_to_str", NEW."slug", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_69a95 ON "search_docket";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_69a95
    AFTER INSERT
    ON "search_docket"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_69a95();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_69a95 ON "search_docket" IS '03ed1cab242c9a84446f39e3845348a99b4e25ed';
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
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR OLD."source" IS DISTINCT FROM NEW."source" OR
          OLD."court_id" IS DISTINCT FROM NEW."court_id" OR
          OLD."appeal_from_id" IS DISTINCT FROM NEW."appeal_from_id" OR
          OLD."appeal_from_str" IS DISTINCT FROM NEW."appeal_from_str" OR
          OLD."originating_court_information_id" IS DISTINCT FROM NEW."originating_court_information_id" OR
          OLD."idb_data_id" IS DISTINCT FROM NEW."idb_data_id" OR
          OLD."assigned_to_id" IS DISTINCT FROM NEW."assigned_to_id" OR
          OLD."assigned_to_str" IS DISTINCT FROM NEW."assigned_to_str" OR
          OLD."referred_to_id" IS DISTINCT FROM NEW."referred_to_id" OR
          OLD."referred_to_str" IS DISTINCT FROM NEW."referred_to_str" OR
          OLD."panel_str" IS DISTINCT FROM NEW."panel_str" OR
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
          OLD."ia_needs_upload" IS DISTINCT FROM NEW."ia_needs_upload" OR OLD."blocked" IS DISTINCT FROM NEW."blocked")
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_a5c9a();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_a5c9a ON "search_docket" IS 'cdc31526f80b44739077d1f8f21fa84f77acd827';
;
--
-- Create trigger custom_snapshot_insert on model docketentry
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_9672f()
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
    VALUES (NEW."date_created", NEW."date_filed", NEW."date_modified", NEW."description", NEW."docket_id",
            NEW."entry_number", NEW."id", NEW."pacer_sequence_number", _pgh_attach_context(), NOW(), 'custom_snapshot',
            NEW."id", NEW."recap_sequence_number", NEW."time_filed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_9672f ON "search_docketentry";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_9672f
    AFTER INSERT
    ON "search_docketentry"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_9672f();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_9672f ON "search_docketentry" IS 'b0002f93c52c9c633cba71e68be977f919673ed7';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_1fcaa();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_1fcaa ON "search_docketentry" IS 'a35c7807b846621faba444e460f02a799eab1a6d';
;
--
-- Create trigger custom_snapshot_insert on model docketentrytags
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_d8ff9()
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
    VALUES (NEW."docketentry_id", NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_d8ff9 ON "search_docketentry_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_d8ff9
    AFTER INSERT
    ON "search_docketentry_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_d8ff9();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_d8ff9 ON "search_docketentry_tags" IS '16c3892511bc39c4c10f5a8efaf510d18d76f012';
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
-- Create trigger custom_snapshot_insert on model docketpanel
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_614fe()
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
    VALUES (NEW."docket_id", NEW."id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_614fe ON "search_docket_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_614fe
    AFTER INSERT
    ON "search_docket_panel"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_614fe();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_614fe ON "search_docket_panel" IS '411f304c25c41dc7a4355bd7c43a5dda6c4b897e';
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
-- Create trigger custom_snapshot_insert on model dockettags
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_1340e()
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
    VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_1340e ON "search_docket_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_1340e
    AFTER INSERT
    ON "search_docket_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_1340e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_1340e ON "search_docket_tags" IS '25b0082b8f46833b1cc94ba99bb847356860153a';
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
-- Create trigger custom_snapshot_insert on model opinion
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_18b5e()
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
    VALUES (NEW."author_id", NEW."author_str", NEW."cluster_id", NEW."date_created", NEW."date_modified",
            NEW."download_url", NEW."extracted_by_ocr", NEW."html", NEW."html_anon_2020", NEW."html_columbia",
            NEW."html_lawbox", NEW."html_with_citations", NEW."id", NEW."joined_by_str", NEW."local_path",
            NEW."page_count", NEW."per_curiam", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id",
            NEW."plain_text", NEW."sha1", NEW."type", NEW."xml_harvard");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_18b5e ON "search_opinion";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_18b5e
    AFTER INSERT
    ON "search_opinion"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_18b5e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_18b5e ON "search_opinion" IS 'b9f5a0ac11c71799ee19e5f0b3e5e89bb50a3ae2';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_e1164();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_e1164 ON "search_opinion" IS '08f7828872b60973dabfc047fec927901f1fb989';
;
--
-- Create trigger custom_snapshot_insert on model opinioncluster
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_0865b()
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
    VALUES (NEW."attorneys", NEW."blocked", NEW."case_name", NEW."case_name_full", NEW."case_name_short",
            NEW."citation_count", NEW."correction", NEW."cross_reference", NEW."date_blocked", NEW."date_created",
            NEW."date_filed", NEW."date_filed_is_approximate", NEW."date_modified", NEW."disposition", NEW."docket_id",
            NEW."filepath_json_harvard", NEW."headnotes", NEW."history", NEW."id", NEW."judges", NEW."nature_of_suit",
            NEW."other_dates", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id", NEW."posture",
            NEW."precedential_status", NEW."procedural_history", NEW."scdb_decision_direction", NEW."scdb_id",
            NEW."scdb_votes_majority", NEW."scdb_votes_minority", NEW."slug", NEW."source", NEW."summary",
            NEW."syllabus");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_0865b ON "search_opinioncluster";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_0865b
    AFTER INSERT
    ON "search_opinioncluster"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_0865b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_0865b ON "search_opinioncluster" IS '9da6e099de3aae7151a95aa01aa82d57243aec01';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_927eb();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_927eb ON "search_opinioncluster" IS 'fa303ebfe434c2b4c8d9c71ba726482935679f38';
;
--
-- Create trigger custom_snapshot_insert on model opinionclusternonparticipatingjudges
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_2f481()
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
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_2f481 ON "search_opinioncluster_non_participating_judges";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_2f481
    AFTER INSERT
    ON "search_opinioncluster_non_participating_judges"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_2f481();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_2f481 ON "search_opinioncluster_non_participating_judges" IS 'c08da0972b0dd849c5f12d831827081571bc2edc';
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
-- Create trigger custom_snapshot_insert on model opinionclusterpanel
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_f16ea()
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
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_f16ea ON "search_opinioncluster_panel";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_f16ea
    AFTER INSERT
    ON "search_opinioncluster_panel"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_f16ea();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_f16ea ON "search_opinioncluster_panel" IS '711b03d1219895fcad1ddfe3c511703ede211cd2';
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
-- Create trigger custom_snapshot_insert on model opinionjoinedby
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_86f0e()
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
    VALUES (NEW."id", NEW."opinion_id", NEW."person_id", _pgh_attach_context(), NOW(), 'custom_snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_86f0e ON "search_opinion_joined_by";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_86f0e
    AFTER INSERT
    ON "search_opinion_joined_by"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_86f0e();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_86f0e ON "search_opinion_joined_by" IS '26af638c8f2a2f9d3993b9c14d35aafc9e71371c';
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
-- Create trigger custom_snapshot_insert on model originatingcourtinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_91b5d()
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
    VALUES (NEW."assigned_to_id", NEW."assigned_to_str", NEW."court_reporter", NEW."date_created", NEW."date_disposed",
            NEW."date_filed", NEW."date_filed_noa", NEW."date_judgment", NEW."date_judgment_eod", NEW."date_modified",
            NEW."date_received_coa", NEW."docket_number", NEW."id", NEW."ordering_judge_id", NEW."ordering_judge_str",
            _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_91b5d ON "search_originatingcourtinformation";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_91b5d
    AFTER INSERT
    ON "search_originatingcourtinformation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_91b5d();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_91b5d ON "search_originatingcourtinformation" IS 'bf4c0d3d7ef7e8eed0b18f011c23eabb9cf338f0';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_0891b();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_0891b ON "search_originatingcourtinformation" IS 'ffa848cdd6911193896e18f6440b7dd7877d2041';
;
--
-- Create trigger custom_snapshot_insert on model recapdocument
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_de0a8()
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
    VALUES (NEW."attachment_number", NEW."date_created", NEW."date_modified", NEW."date_upload", NEW."description",
            NEW."docket_entry_id", NEW."document_number", NEW."document_type", NEW."file_size", NEW."filepath_ia",
            NEW."filepath_local", NEW."ia_upload_failure_count", NEW."id", NEW."is_available", NEW."is_free_on_pacer",
            NEW."is_sealed", NEW."ocr_status", NEW."pacer_doc_id", NEW."page_count", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id", NEW."plain_text", NEW."sha1", NEW."thumbnail", NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_de0a8 ON "search_recapdocument";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_de0a8
    AFTER INSERT
    ON "search_recapdocument"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_de0a8();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_de0a8 ON "search_recapdocument" IS 'ea18d6949452831cf4e5776f43c657e23e14bd0d';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_e466a();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_e466a ON "search_recapdocument" IS 'd20577b855a2764e65b5c8b73e0924dfeee235fe';
;
--
-- Create trigger custom_snapshot_insert on model recapdocumenttags
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_a2b8d()
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
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'custom_snapshot', NEW."recapdocument_id", NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_a2b8d ON "search_recapdocument_tags";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_a2b8d
    AFTER INSERT
    ON "search_recapdocument_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_a2b8d();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_a2b8d ON "search_recapdocument_tags" IS '10ba27a0fe288aaeb1d55d31ab61a9d06d31a0de';
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
-- Create trigger custom_snapshot_insert on model tag
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

CREATE OR REPLACE FUNCTION pgtrigger_custom_snapshot_insert_34bc4()
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
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."name", _pgh_attach_context(), NOW(),
            'custom_snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_custom_snapshot_insert_34bc4 ON "search_tag";
CREATE TRIGGER pgtrigger_custom_snapshot_insert_34bc4
    AFTER INSERT
    ON "search_tag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_custom_snapshot_insert_34bc4();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_insert_34bc4 ON "search_tag" IS '996a4f766a08ff91fa00aa4d6584b00ccd6c3f76';
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
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_custom_snapshot_update_2bc42();

COMMENT ON TRIGGER pgtrigger_custom_snapshot_update_2bc42 ON "search_tag" IS 'b79ab36201018b1a7756d824b0a5beba61ab165a';
;
COMMIT;
