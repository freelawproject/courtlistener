BEGIN;
--
-- Create model BankruptcyInformationEvent
--
CREATE TABLE "search_bankruptcyinformationevent"
(
    "pgh_id"                   serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"           timestamp with time zone NOT NULL,
    "pgh_label"                text                     NOT NULL,
    "id"                       integer                  NOT NULL,
    "date_created"             timestamp with time zone NOT NULL,
    "date_modified"            timestamp with time zone NOT NULL,
    "date_converted"           timestamp with time zone NULL,
    "date_last_to_file_claims" timestamp with time zone NULL,
    "date_last_to_file_govt"   timestamp with time zone NULL,
    "date_debtor_dismissed"    timestamp with time zone NULL,
    "chapter"                  varchar(10)              NOT NULL,
    "trustee_str"              text                     NOT NULL
);
--
-- Create model CitationEvent
--
CREATE TABLE "search_citationevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "volume"         smallint                 NOT NULL,
    "reporter"       text                     NOT NULL,
    "page"           text                     NOT NULL,
    "type"           smallint                 NOT NULL
);
--
-- Create model ClaimEvent
--
CREATE TABLE "search_claimevent"
(
    "pgh_id"                      serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"              timestamp with time zone NOT NULL,
    "pgh_label"                   text                     NOT NULL,
    "id"                          integer                  NOT NULL,
    "date_created"                timestamp with time zone NOT NULL,
    "date_modified"               timestamp with time zone NOT NULL,
    "date_claim_modified"         timestamp with time zone NULL,
    "date_original_entered"       timestamp with time zone NULL,
    "date_original_filed"         timestamp with time zone NULL,
    "date_last_amendment_entered" timestamp with time zone NULL,
    "date_last_amendment_filed"   timestamp with time zone NULL,
    "claim_number"                varchar(10)              NOT NULL,
    "creditor_details"            text                     NOT NULL,
    "creditor_id"                 varchar(50)              NOT NULL,
    "status"                      varchar(1000)            NOT NULL,
    "entered_by"                  varchar(1000)            NOT NULL,
    "filed_by"                    varchar(1000)            NOT NULL,
    "amount_claimed"              varchar(100)             NOT NULL,
    "unsecured_claimed"           varchar(100)             NOT NULL,
    "secured_claimed"             varchar(100)             NOT NULL,
    "priority_claimed"            varchar(100)             NOT NULL,
    "description"                 text                     NOT NULL,
    "remarks"                     text                     NOT NULL
);
--
-- Create model ClaimHistoryEvent
--
CREATE TABLE "search_claimhistoryevent"
(
    "pgh_id"                  serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"          timestamp with time zone NOT NULL,
    "pgh_label"               text                     NOT NULL,
    "id"                      integer                  NOT NULL,
    "date_created"            timestamp with time zone NOT NULL,
    "date_modified"           timestamp with time zone NOT NULL,
    "sha1"                    varchar(40)              NOT NULL,
    "page_count"              integer                  NULL,
    "file_size"               integer                  NULL,
    "filepath_local"          varchar(1000)            NOT NULL,
    "filepath_ia"             varchar(1000)            NOT NULL,
    "ia_upload_failure_count" smallint                 NULL,
    "thumbnail"               varchar(100)             NULL,
    "thumbnail_status"        smallint                 NOT NULL,
    "plain_text"              text                     NOT NULL,
    "ocr_status"              smallint                 NULL,
    "date_upload"             timestamp with time zone NULL,
    "document_number"         varchar(32)              NOT NULL,
    "attachment_number"       smallint                 NULL,
    "pacer_doc_id"            varchar(32)              NOT NULL,
    "is_available"            boolean                  NULL,
    "is_free_on_pacer"        boolean                  NULL,
    "is_sealed"               boolean                  NULL,
    "date_filed"              date                     NULL,
    "claim_document_type"     integer                  NOT NULL,
    "description"             text                     NOT NULL,
    "claim_doc_id"            varchar(32)              NOT NULL,
    "pacer_dm_id"             integer                  NULL,
    "pacer_case_id"           varchar(100)             NOT NULL
);
--
-- Create model ClaimTagsEvent
--
CREATE TABLE "search_claimtagsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model CourtEvent
--
CREATE TABLE "search_courtevent"
(
    "pgh_id"                    serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"            timestamp with time zone NOT NULL,
    "pgh_label"                 text                     NOT NULL,
    "id"                        varchar(15)              NOT NULL,
    "pacer_court_id"            smallint                 NULL CHECK ("pacer_court_id" >= 0),
    "pacer_has_rss_feed"        boolean                  NULL,
    "pacer_rss_entry_types"     text                     NOT NULL,
    "date_last_pacer_contact"   timestamp with time zone NULL,
    "fjc_court_id"              varchar(3)               NOT NULL,
    "date_modified"             timestamp with time zone NOT NULL,
    "in_use"                    boolean                  NOT NULL,
    "has_opinion_scraper"       boolean                  NOT NULL,
    "has_oral_argument_scraper" boolean                  NOT NULL,
    "position"                  double precision         NOT NULL,
    "citation_string"           varchar(100)             NOT NULL,
    "short_name"                varchar(100)             NOT NULL,
    "full_name"                 varchar(200)             NOT NULL,
    "url"                       varchar(500)             NOT NULL,
    "start_date"                date                     NULL,
    "end_date"                  date                     NULL,
    "jurisdiction"              varchar(3)               NOT NULL,
    "notes"                     text                     NOT NULL
);
--
-- Create model DocketEntryEvent
--
CREATE TABLE "search_docketentryevent"
(
    "pgh_id"                serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"        timestamp with time zone NOT NULL,
    "pgh_label"             text                     NOT NULL,
    "id"                    integer                  NOT NULL,
    "date_created"          timestamp with time zone NOT NULL,
    "date_modified"         timestamp with time zone NOT NULL,
    "date_filed"            date                     NULL,
    "entry_number"          bigint                   NULL,
    "recap_sequence_number" varchar(50)              NOT NULL,
    "pacer_sequence_number" integer                  NULL,
    "description"           text                     NOT NULL
);
--
-- Create model DocketEntryTagsEvent
--
CREATE TABLE "search_docketentrytagsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model DocketEvent
--
CREATE TABLE "search_docketevent"
(
    "pgh_id"                          serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"                  timestamp with time zone NOT NULL,
    "pgh_label"                       text                     NOT NULL,
    "id"                              integer                  NOT NULL,
    "date_created"                    timestamp with time zone NOT NULL,
    "date_modified"                   timestamp with time zone NOT NULL,
    "source"                          smallint                 NOT NULL,
    "appeal_from_str"                 text                     NOT NULL,
    "assigned_to_str"                 text                     NOT NULL,
    "referred_to_str"                 text                     NOT NULL,
    "panel_str"                       text                     NOT NULL,
    "date_last_index"                 timestamp with time zone NULL,
    "date_cert_granted"               date                     NULL,
    "date_cert_denied"                date                     NULL,
    "date_argued"                     date                     NULL,
    "date_reargued"                   date                     NULL,
    "date_reargument_denied"          date                     NULL,
    "date_filed"                      date                     NULL,
    "date_terminated"                 date                     NULL,
    "date_last_filing"                date                     NULL,
    "case_name_short"                 text                     NOT NULL,
    "case_name"                       text                     NOT NULL,
    "case_name_full"                  text                     NOT NULL,
    "slug"                            varchar(75)              NOT NULL,
    "docket_number"                   text                     NULL,
    "docket_number_core"              varchar(20)              NOT NULL,
    "pacer_case_id"                   varchar(100)             NULL,
    "cause"                           varchar(2000)            NOT NULL,
    "nature_of_suit"                  varchar(1000)            NOT NULL,
    "jury_demand"                     varchar(500)             NOT NULL,
    "jurisdiction_type"               varchar(100)             NOT NULL,
    "appellate_fee_status"            text                     NOT NULL,
    "appellate_case_type_information" text                     NOT NULL,
    "mdl_status"                      varchar(100)             NOT NULL,
    "filepath_local"                  varchar(1000)            NOT NULL,
    "filepath_ia"                     varchar(1000)            NOT NULL,
    "filepath_ia_json"                varchar(1000)            NOT NULL,
    "ia_upload_failure_count"         smallint                 NULL,
    "ia_needs_upload"                 boolean                  NULL,
    "ia_date_first_change"            timestamp with time zone NULL,
    "date_blocked"                    date                     NULL,
    "blocked"                         boolean                  NOT NULL
);
--
-- Create model DocketPanelEvent
--
CREATE TABLE "search_docketpanelevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model DocketTagsEvent
--
CREATE TABLE "search_dockettagsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model OpinionClusterEvent
--
CREATE TABLE "search_opinionclusterevent"
(
    "pgh_id"                    serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"            timestamp with time zone NOT NULL,
    "pgh_label"                 text                     NOT NULL,
    "id"                        integer                  NOT NULL,
    "date_created"              timestamp with time zone NOT NULL,
    "date_modified"             timestamp with time zone NOT NULL,
    "judges"                    text                     NOT NULL,
    "date_filed"                date                     NOT NULL,
    "date_filed_is_approximate" boolean                  NOT NULL,
    "slug"                      varchar(75)              NULL,
    "case_name_short"           text                     NOT NULL,
    "case_name"                 text                     NOT NULL,
    "case_name_full"            text                     NOT NULL,
    "scdb_id"                   varchar(10)              NOT NULL,
    "scdb_decision_direction"   integer                  NULL,
    "scdb_votes_majority"       integer                  NULL,
    "scdb_votes_minority"       integer                  NULL,
    "source"                    varchar(10)              NOT NULL,
    "procedural_history"        text                     NOT NULL,
    "attorneys"                 text                     NOT NULL,
    "nature_of_suit"            text                     NOT NULL,
    "posture"                   text                     NOT NULL,
    "syllabus"                  text                     NOT NULL,
    "headnotes"                 text                     NOT NULL,
    "summary"                   text                     NOT NULL,
    "disposition"               text                     NOT NULL,
    "history"                   text                     NOT NULL,
    "other_dates"               text                     NOT NULL,
    "cross_reference"           text                     NOT NULL,
    "correction"                text                     NOT NULL,
    "citation_count"            integer                  NOT NULL,
    "precedential_status"       varchar(50)              NOT NULL,
    "date_blocked"              date                     NULL,
    "blocked"                   boolean                  NOT NULL,
    "filepath_json_harvard"     varchar(1000)            NOT NULL
);
--
-- Create model OpinionClusterNonParticipatingJudgesEvent
--
CREATE TABLE "search_opinionclusternonparticipatingjudgesevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model OpinionClusterPanelEvent
--
CREATE TABLE "search_opinionclusterpanelevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model OpinionEvent
--
CREATE TABLE "search_opinionevent"
(
    "pgh_id"              serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"      timestamp with time zone NOT NULL,
    "pgh_label"           text                     NOT NULL,
    "id"                  integer                  NOT NULL,
    "date_created"        timestamp with time zone NOT NULL,
    "date_modified"       timestamp with time zone NOT NULL,
    "author_str"          text                     NOT NULL,
    "per_curiam"          boolean                  NOT NULL,
    "joined_by_str"       text                     NOT NULL,
    "type"                varchar(20)              NOT NULL,
    "sha1"                varchar(40)              NOT NULL,
    "page_count"          integer                  NULL,
    "download_url"        varchar(500)             NULL,
    "local_path"          varchar(100)             NOT NULL,
    "plain_text"          text                     NOT NULL,
    "html"                text                     NOT NULL,
    "html_lawbox"         text                     NOT NULL,
    "html_columbia"       text                     NOT NULL,
    "html_anon_2020"      text                     NOT NULL,
    "xml_harvard"         text                     NOT NULL,
    "html_with_citations" text                     NOT NULL,
    "extracted_by_ocr"    boolean                  NOT NULL
);
--
-- Create model OpinionJoinedByEvent
--
CREATE TABLE "search_opinionjoinedbyevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model OriginatingCourtInformationEvent
--
CREATE TABLE "search_originatingcourtinformationevent"
(
    "pgh_id"             serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"     timestamp with time zone NOT NULL,
    "pgh_label"          text                     NOT NULL,
    "id"                 integer                  NOT NULL,
    "date_created"       timestamp with time zone NOT NULL,
    "date_modified"      timestamp with time zone NOT NULL,
    "docket_number"      text                     NOT NULL,
    "assigned_to_str"    text                     NOT NULL,
    "ordering_judge_str" text                     NOT NULL,
    "court_reporter"     text                     NOT NULL,
    "date_disposed"      date                     NULL,
    "date_filed"         date                     NULL,
    "date_judgment"      date                     NULL,
    "date_judgment_eod"  date                     NULL,
    "date_filed_noa"     date                     NULL,
    "date_received_coa"  date                     NULL
);
--
-- Create model RECAPDocumentEvent
--
CREATE TABLE "search_recapdocumentevent"
(
    "pgh_id"                  serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"          timestamp with time zone NOT NULL,
    "pgh_label"               text                     NOT NULL,
    "id"                      integer                  NOT NULL,
    "date_created"            timestamp with time zone NOT NULL,
    "date_modified"           timestamp with time zone NOT NULL,
    "sha1"                    varchar(40)              NOT NULL,
    "page_count"              integer                  NULL,
    "file_size"               integer                  NULL,
    "filepath_local"          varchar(1000)            NOT NULL,
    "filepath_ia"             varchar(1000)            NOT NULL,
    "ia_upload_failure_count" smallint                 NULL,
    "thumbnail"               varchar(100)             NULL,
    "thumbnail_status"        smallint                 NOT NULL,
    "plain_text"              text                     NOT NULL,
    "ocr_status"              smallint                 NULL,
    "date_upload"             timestamp with time zone NULL,
    "document_number"         varchar(32)              NOT NULL,
    "attachment_number"       smallint                 NULL,
    "pacer_doc_id"            varchar(32)              NOT NULL,
    "is_available"            boolean                  NULL,
    "is_free_on_pacer"        boolean                  NULL,
    "is_sealed"               boolean                  NULL,
    "document_type"           integer                  NOT NULL,
    "description"             text                     NOT NULL
);
--
-- Create model RECAPDocumentTagsEvent
--
CREATE TABLE "search_recapdocumenttagsevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model TagEvent
--
CREATE TABLE "search_tagevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL,
    "date_created"   timestamp with time zone NOT NULL,
    "date_modified"  timestamp with time zone NOT NULL,
    "name"           varchar(50)              NOT NULL
);
--
-- Create proxy model ClaimTags
--
--
-- Create proxy model DocketEntryTags
--
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
-- Create proxy model RECAPDocumentTags
--
--
-- Create trigger snapshot_insert on model bankruptcyinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_cfb47()
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
    INSERT INTO "search_bankruptcyinformationevent" ("chapter",
                                                     "date_converted",
                                                     "date_created",
                                                     "date_debtor_dismissed",
                                                     "date_last_to_file_claims",
                                                     "date_last_to_file_govt",
                                                     "date_modified",
                                                     "docket_id", "id",
                                                     "pgh_context_id",
                                                     "pgh_created_at",
                                                     "pgh_label", "pgh_obj_id",
                                                     "trustee_str")
    VALUES (NEW."chapter", NEW."date_converted", NEW."date_created",
            NEW."date_debtor_dismissed", NEW."date_last_to_file_claims",
            NEW."date_last_to_file_govt", NEW."date_modified", NEW."docket_id",
            NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."trustee_str");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_cfb47 ON "search_bankruptcyinformation";
CREATE TRIGGER pgtrigger_snapshot_insert_cfb47
    AFTER INSERT
    ON "search_bankruptcyinformation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_cfb47();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_cfb47 ON "search_bankruptcyinformation" IS 'b6e2e031746df26ee4f45a445c3502ffe4668055';
;
--
-- Create trigger snapshot_update on model bankruptcyinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_3cb5e()
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
    INSERT INTO "search_bankruptcyinformationevent" ("chapter",
                                                     "date_converted",
                                                     "date_created",
                                                     "date_debtor_dismissed",
                                                     "date_last_to_file_claims",
                                                     "date_last_to_file_govt",
                                                     "date_modified",
                                                     "docket_id", "id",
                                                     "pgh_context_id",
                                                     "pgh_created_at",
                                                     "pgh_label", "pgh_obj_id",
                                                     "trustee_str")
    VALUES (NEW."chapter", NEW."date_converted", NEW."date_created",
            NEW."date_debtor_dismissed", NEW."date_last_to_file_claims",
            NEW."date_last_to_file_govt", NEW."date_modified", NEW."docket_id",
            NEW."id", _pgh_attach_context(), NOW(), 'snapshot', NEW."id",
            NEW."trustee_str");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_3cb5e ON "search_bankruptcyinformation";
CREATE TRIGGER pgtrigger_snapshot_update_3cb5e
    AFTER UPDATE
    ON "search_bankruptcyinformation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_3cb5e();

COMMENT ON TRIGGER pgtrigger_snapshot_update_3cb5e ON "search_bankruptcyinformation" IS '071539ff19cdfd63d50b59e68abc413770f240b0';
;
--
-- Create trigger snapshot_insert on model citation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_596d3()
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
    INSERT INTO "search_citationevent" ("cluster_id", "id", "page",
                                        "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "reporter",
                                        "type", "volume")
    VALUES (NEW."cluster_id", NEW."id", NEW."page", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."reporter", NEW."type",
            NEW."volume");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_596d3 ON "search_citation";
CREATE TRIGGER pgtrigger_snapshot_insert_596d3
    AFTER INSERT
    ON "search_citation"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_31b3d()
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
    INSERT INTO "search_citationevent" ("cluster_id", "id", "page",
                                        "pgh_context_id", "pgh_created_at",
                                        "pgh_label", "pgh_obj_id", "reporter",
                                        "type", "volume")
    VALUES (NEW."cluster_id", NEW."id", NEW."page", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."reporter", NEW."type",
            NEW."volume");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_31b3d ON "search_citation";
CREATE TRIGGER pgtrigger_snapshot_update_31b3d
    AFTER UPDATE
    ON "search_citation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_31b3d();

COMMENT ON TRIGGER pgtrigger_snapshot_update_31b3d ON "search_citation" IS 'b2b27f069bb64eddfd351add29fc2dbe8243da86';
;
--
-- Create trigger snapshot_insert on model claim
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b04cb()
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
    INSERT INTO "search_claimevent" ("amount_claimed", "claim_number",
                                     "creditor_details", "creditor_id",
                                     "date_claim_modified", "date_created",
                                     "date_last_amendment_entered",
                                     "date_last_amendment_filed",
                                     "date_modified", "date_original_entered",
                                     "date_original_filed", "description",
                                     "docket_id", "entered_by", "filed_by",
                                     "id", "pgh_context_id", "pgh_created_at",
                                     "pgh_label", "pgh_obj_id",
                                     "priority_claimed", "remarks",
                                     "secured_claimed", "status",
                                     "unsecured_claimed")
    VALUES (NEW."amount_claimed", NEW."claim_number", NEW."creditor_details",
            NEW."creditor_id", NEW."date_claim_modified", NEW."date_created",
            NEW."date_last_amendment_entered", NEW."date_last_amendment_filed",
            NEW."date_modified", NEW."date_original_entered",
            NEW."date_original_filed", NEW."description", NEW."docket_id",
            NEW."entered_by", NEW."filed_by", NEW."id", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."priority_claimed", NEW."remarks",
            NEW."secured_claimed", NEW."status", NEW."unsecured_claimed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b04cb ON "search_claim";
CREATE TRIGGER pgtrigger_snapshot_insert_b04cb
    AFTER INSERT
    ON "search_claim"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_b04cb();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_b04cb ON "search_claim" IS '264fac80b9f9d17711a20ba680b4b742553484bf';
;
--
-- Create trigger snapshot_update on model claim
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_63c7f()
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
    INSERT INTO "search_claimevent" ("amount_claimed", "claim_number",
                                     "creditor_details", "creditor_id",
                                     "date_claim_modified", "date_created",
                                     "date_last_amendment_entered",
                                     "date_last_amendment_filed",
                                     "date_modified", "date_original_entered",
                                     "date_original_filed", "description",
                                     "docket_id", "entered_by", "filed_by",
                                     "id", "pgh_context_id", "pgh_created_at",
                                     "pgh_label", "pgh_obj_id",
                                     "priority_claimed", "remarks",
                                     "secured_claimed", "status",
                                     "unsecured_claimed")
    VALUES (NEW."amount_claimed", NEW."claim_number", NEW."creditor_details",
            NEW."creditor_id", NEW."date_claim_modified", NEW."date_created",
            NEW."date_last_amendment_entered", NEW."date_last_amendment_filed",
            NEW."date_modified", NEW."date_original_entered",
            NEW."date_original_filed", NEW."description", NEW."docket_id",
            NEW."entered_by", NEW."filed_by", NEW."id", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."priority_claimed", NEW."remarks",
            NEW."secured_claimed", NEW."status", NEW."unsecured_claimed");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_63c7f ON "search_claim";
CREATE TRIGGER pgtrigger_snapshot_update_63c7f
    AFTER UPDATE
    ON "search_claim"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_63c7f();

COMMENT ON TRIGGER pgtrigger_snapshot_update_63c7f ON "search_claim" IS '933de5877707e3e75e97e2554018455373ab9a91';
;
--
-- Create trigger snapshot_insert on model claimhistory
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_6ef1e()
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
    INSERT INTO "search_claimhistoryevent" ("attachment_number",
                                            "claim_doc_id",
                                            "claim_document_type", "claim_id",
                                            "date_created", "date_filed",
                                            "date_modified", "date_upload",
                                            "description", "document_number",
                                            "file_size", "filepath_ia",
                                            "filepath_local",
                                            "ia_upload_failure_count", "id",
                                            "is_available", "is_free_on_pacer",
                                            "is_sealed", "ocr_status",
                                            "pacer_case_id", "pacer_dm_id",
                                            "pacer_doc_id", "page_count",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id",
                                            "plain_text", "sha1", "thumbnail",
                                            "thumbnail_status")
    VALUES (NEW."attachment_number", NEW."claim_doc_id",
            NEW."claim_document_type", NEW."claim_id", NEW."date_created",
            NEW."date_filed", NEW."date_modified", NEW."date_upload",
            NEW."description", NEW."document_number", NEW."file_size",
            NEW."filepath_ia", NEW."filepath_local",
            NEW."ia_upload_failure_count", NEW."id", NEW."is_available",
            NEW."is_free_on_pacer", NEW."is_sealed", NEW."ocr_status",
            NEW."pacer_case_id", NEW."pacer_dm_id", NEW."pacer_doc_id",
            NEW."page_count", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."plain_text", NEW."sha1", NEW."thumbnail",
            NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6ef1e ON "search_claimhistory";
CREATE TRIGGER pgtrigger_snapshot_insert_6ef1e
    AFTER INSERT
    ON "search_claimhistory"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_6ef1e();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_6ef1e ON "search_claimhistory" IS '44f3f940c8f4861700eedfc1961edd6a0812f510';
;
--
-- Create trigger snapshot_update on model claimhistory
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6d7e5()
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
    INSERT INTO "search_claimhistoryevent" ("attachment_number",
                                            "claim_doc_id",
                                            "claim_document_type", "claim_id",
                                            "date_created", "date_filed",
                                            "date_modified", "date_upload",
                                            "description", "document_number",
                                            "file_size", "filepath_ia",
                                            "filepath_local",
                                            "ia_upload_failure_count", "id",
                                            "is_available", "is_free_on_pacer",
                                            "is_sealed", "ocr_status",
                                            "pacer_case_id", "pacer_dm_id",
                                            "pacer_doc_id", "page_count",
                                            "pgh_context_id", "pgh_created_at",
                                            "pgh_label", "pgh_obj_id",
                                            "plain_text", "sha1", "thumbnail",
                                            "thumbnail_status")
    VALUES (NEW."attachment_number", NEW."claim_doc_id",
            NEW."claim_document_type", NEW."claim_id", NEW."date_created",
            NEW."date_filed", NEW."date_modified", NEW."date_upload",
            NEW."description", NEW."document_number", NEW."file_size",
            NEW."filepath_ia", NEW."filepath_local",
            NEW."ia_upload_failure_count", NEW."id", NEW."is_available",
            NEW."is_free_on_pacer", NEW."is_sealed", NEW."ocr_status",
            NEW."pacer_case_id", NEW."pacer_dm_id", NEW."pacer_doc_id",
            NEW."page_count", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."plain_text", NEW."sha1", NEW."thumbnail",
            NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6d7e5 ON "search_claimhistory";
CREATE TRIGGER pgtrigger_snapshot_update_6d7e5
    AFTER UPDATE
    ON "search_claimhistory"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_6d7e5();

COMMENT ON TRIGGER pgtrigger_snapshot_update_6d7e5 ON "search_claimhistory" IS '6f572cce9d396475ebd78635a092e4d3f9290c9d';
;
--
-- Create trigger snapshot_insert on model court
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_82101()
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
    INSERT INTO "search_courtevent" ("citation_string",
                                     "date_last_pacer_contact",
                                     "date_modified", "end_date",
                                     "fjc_court_id", "full_name",
                                     "has_opinion_scraper",
                                     "has_oral_argument_scraper", "id",
                                     "in_use", "jurisdiction", "notes",
                                     "pacer_court_id", "pacer_has_rss_feed",
                                     "pacer_rss_entry_types", "pgh_context_id",
                                     "pgh_created_at", "pgh_label",
                                     "pgh_obj_id", "position", "short_name",
                                     "start_date", "url")
    VALUES (NEW."citation_string", NEW."date_last_pacer_contact",
            NEW."date_modified", NEW."end_date", NEW."fjc_court_id",
            NEW."full_name", NEW."has_opinion_scraper",
            NEW."has_oral_argument_scraper", NEW."id", NEW."in_use",
            NEW."jurisdiction", NEW."notes", NEW."pacer_court_id",
            NEW."pacer_has_rss_feed", NEW."pacer_rss_entry_types",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position",
            NEW."short_name", NEW."start_date", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_82101 ON "search_court";
CREATE TRIGGER pgtrigger_snapshot_insert_82101
    AFTER INSERT
    ON "search_court"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cc9e2()
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
    INSERT INTO "search_courtevent" ("citation_string",
                                     "date_last_pacer_contact",
                                     "date_modified", "end_date",
                                     "fjc_court_id", "full_name",
                                     "has_opinion_scraper",
                                     "has_oral_argument_scraper", "id",
                                     "in_use", "jurisdiction", "notes",
                                     "pacer_court_id", "pacer_has_rss_feed",
                                     "pacer_rss_entry_types", "pgh_context_id",
                                     "pgh_created_at", "pgh_label",
                                     "pgh_obj_id", "position", "short_name",
                                     "start_date", "url")
    VALUES (NEW."citation_string", NEW."date_last_pacer_contact",
            NEW."date_modified", NEW."end_date", NEW."fjc_court_id",
            NEW."full_name", NEW."has_opinion_scraper",
            NEW."has_oral_argument_scraper", NEW."id", NEW."in_use",
            NEW."jurisdiction", NEW."notes", NEW."pacer_court_id",
            NEW."pacer_has_rss_feed", NEW."pacer_rss_entry_types",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id", NEW."position",
            NEW."short_name", NEW."start_date", NEW."url");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cc9e2 ON "search_court";
CREATE TRIGGER pgtrigger_snapshot_update_cc9e2
    AFTER UPDATE
    ON "search_court"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cc9e2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cc9e2 ON "search_court" IS '51eac3389569bbe20caaf3d42566643bf6b7c091';
;
--
-- Create trigger snapshot_insert on model docket
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_fe9ff()
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
    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str",
                                      "appellate_case_type_information",
                                      "appellate_fee_status", "assigned_to_id",
                                      "assigned_to_str", "blocked",
                                      "case_name", "case_name_full",
                                      "case_name_short", "cause", "court_id",
                                      "date_argued", "date_blocked",
                                      "date_cert_denied", "date_cert_granted",
                                      "date_created", "date_filed",
                                      "date_last_filing", "date_last_index",
                                      "date_modified", "date_reargued",
                                      "date_reargument_denied",
                                      "date_terminated", "docket_number",
                                      "docket_number_core", "filepath_ia",
                                      "filepath_ia_json", "filepath_local",
                                      "ia_date_first_change",
                                      "ia_needs_upload",
                                      "ia_upload_failure_count", "id",
                                      "idb_data_id", "jurisdiction_type",
                                      "jury_demand", "mdl_status",
                                      "nature_of_suit",
                                      "originating_court_information_id",
                                      "pacer_case_id", "panel_str",
                                      "pgh_context_id", "pgh_created_at",
                                      "pgh_label", "pgh_obj_id",
                                      "referred_to_id", "referred_to_str",
                                      "slug", "source")
    VALUES (NEW."appeal_from_id", NEW."appeal_from_str",
            NEW."appellate_case_type_information", NEW."appellate_fee_status",
            NEW."assigned_to_id", NEW."assigned_to_str", NEW."blocked",
            NEW."case_name", NEW."case_name_full", NEW."case_name_short",
            NEW."cause", NEW."court_id", NEW."date_argued", NEW."date_blocked",
            NEW."date_cert_denied", NEW."date_cert_granted",
            NEW."date_created", NEW."date_filed", NEW."date_last_filing",
            NEW."date_last_index", NEW."date_modified", NEW."date_reargued",
            NEW."date_reargument_denied", NEW."date_terminated",
            NEW."docket_number", NEW."docket_number_core", NEW."filepath_ia",
            NEW."filepath_ia_json", NEW."filepath_local",
            NEW."ia_date_first_change", NEW."ia_needs_upload",
            NEW."ia_upload_failure_count", NEW."id", NEW."idb_data_id",
            NEW."jurisdiction_type", NEW."jury_demand", NEW."mdl_status",
            NEW."nature_of_suit", NEW."originating_court_information_id",
            NEW."pacer_case_id", NEW."panel_str", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."referred_to_id", NEW."referred_to_str",
            NEW."slug", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_fe9ff ON "search_docket";
CREATE TRIGGER pgtrigger_snapshot_insert_fe9ff
    AFTER INSERT
    ON "search_docket"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_fe9ff();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_fe9ff ON "search_docket" IS '04c887cce02fd7c82d51b97966b5267ae1fcf55b';
;
--
-- Create trigger snapshot_update on model docket
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_1e722()
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
    INSERT INTO "search_docketevent" ("appeal_from_id", "appeal_from_str",
                                      "appellate_case_type_information",
                                      "appellate_fee_status", "assigned_to_id",
                                      "assigned_to_str", "blocked",
                                      "case_name", "case_name_full",
                                      "case_name_short", "cause", "court_id",
                                      "date_argued", "date_blocked",
                                      "date_cert_denied", "date_cert_granted",
                                      "date_created", "date_filed",
                                      "date_last_filing", "date_last_index",
                                      "date_modified", "date_reargued",
                                      "date_reargument_denied",
                                      "date_terminated", "docket_number",
                                      "docket_number_core", "filepath_ia",
                                      "filepath_ia_json", "filepath_local",
                                      "ia_date_first_change",
                                      "ia_needs_upload",
                                      "ia_upload_failure_count", "id",
                                      "idb_data_id", "jurisdiction_type",
                                      "jury_demand", "mdl_status",
                                      "nature_of_suit",
                                      "originating_court_information_id",
                                      "pacer_case_id", "panel_str",
                                      "pgh_context_id", "pgh_created_at",
                                      "pgh_label", "pgh_obj_id",
                                      "referred_to_id", "referred_to_str",
                                      "slug", "source")
    VALUES (NEW."appeal_from_id", NEW."appeal_from_str",
            NEW."appellate_case_type_information", NEW."appellate_fee_status",
            NEW."assigned_to_id", NEW."assigned_to_str", NEW."blocked",
            NEW."case_name", NEW."case_name_full", NEW."case_name_short",
            NEW."cause", NEW."court_id", NEW."date_argued", NEW."date_blocked",
            NEW."date_cert_denied", NEW."date_cert_granted",
            NEW."date_created", NEW."date_filed", NEW."date_last_filing",
            NEW."date_last_index", NEW."date_modified", NEW."date_reargued",
            NEW."date_reargument_denied", NEW."date_terminated",
            NEW."docket_number", NEW."docket_number_core", NEW."filepath_ia",
            NEW."filepath_ia_json", NEW."filepath_local",
            NEW."ia_date_first_change", NEW."ia_needs_upload",
            NEW."ia_upload_failure_count", NEW."id", NEW."idb_data_id",
            NEW."jurisdiction_type", NEW."jury_demand", NEW."mdl_status",
            NEW."nature_of_suit", NEW."originating_court_information_id",
            NEW."pacer_case_id", NEW."panel_str", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."referred_to_id", NEW."referred_to_str",
            NEW."slug", NEW."source");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1e722 ON "search_docket";
CREATE TRIGGER pgtrigger_snapshot_update_1e722
    AFTER UPDATE
    ON "search_docket"


    FOR EACH ROW
    WHEN (OLD."id" IS DISTINCT FROM NEW."id" OR
          OLD."date_created" IS DISTINCT FROM NEW."date_created" OR
          OLD."date_modified" IS DISTINCT FROM NEW."date_modified" OR
          OLD."source" IS DISTINCT FROM NEW."source" OR
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
          OLD."case_name_full" IS DISTINCT FROM NEW."case_name_full" OR
          OLD."slug" IS DISTINCT FROM NEW."slug" OR
          OLD."docket_number" IS DISTINCT FROM NEW."docket_number" OR
          OLD."docket_number_core" IS DISTINCT FROM NEW."docket_number_core" OR
          OLD."pacer_case_id" IS DISTINCT FROM NEW."pacer_case_id" OR
          OLD."cause" IS DISTINCT FROM NEW."cause" OR
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
          OLD."date_blocked" IS DISTINCT FROM NEW."date_blocked" OR
          OLD."blocked" IS DISTINCT FROM NEW."blocked")
EXECUTE PROCEDURE pgtrigger_snapshot_update_1e722();

COMMENT ON TRIGGER pgtrigger_snapshot_update_1e722 ON "search_docket" IS '9eebb23babc3541b7751f2c9b01d901ca412a29e';
;
--
-- Create trigger snapshot_insert on model docketentry
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_2de73()
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
    INSERT INTO "search_docketentryevent" ("date_created", "date_filed",
                                           "date_modified", "description",
                                           "docket_id", "entry_number", "id",
                                           "pacer_sequence_number",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id",
                                           "recap_sequence_number")
    VALUES (NEW."date_created", NEW."date_filed", NEW."date_modified",
            NEW."description", NEW."docket_id", NEW."entry_number", NEW."id",
            NEW."pacer_sequence_number", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."recap_sequence_number");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_2de73 ON "search_docketentry";
CREATE TRIGGER pgtrigger_snapshot_insert_2de73
    AFTER INSERT
    ON "search_docketentry"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_2de73();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_2de73 ON "search_docketentry" IS '450e40b2bc6926900cd248d20213469983610eab';
;
--
-- Create trigger snapshot_update on model docketentry
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_d8176()
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
    INSERT INTO "search_docketentryevent" ("date_created", "date_filed",
                                           "date_modified", "description",
                                           "docket_id", "entry_number", "id",
                                           "pacer_sequence_number",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label", "pgh_obj_id",
                                           "recap_sequence_number")
    VALUES (NEW."date_created", NEW."date_filed", NEW."date_modified",
            NEW."description", NEW."docket_id", NEW."entry_number", NEW."id",
            NEW."pacer_sequence_number", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."recap_sequence_number");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_d8176 ON "search_docketentry";
CREATE TRIGGER pgtrigger_snapshot_update_d8176
    AFTER UPDATE
    ON "search_docketentry"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_d8176();

COMMENT ON TRIGGER pgtrigger_snapshot_update_d8176 ON "search_docketentry" IS 'df36b55d492329989de598df687d1aefe2ca0568';
;
--
-- Create trigger snapshot_insert on model opinion
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_6ae1e()
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
    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id",
                                       "date_created", "date_modified",
                                       "download_url", "extracted_by_ocr",
                                       "html", "html_anon_2020",
                                       "html_columbia", "html_lawbox",
                                       "html_with_citations", "id",
                                       "joined_by_str", "local_path",
                                       "page_count", "per_curiam",
                                       "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id", "plain_text",
                                       "sha1", "type", "xml_harvard")
    VALUES (NEW."author_id", NEW."author_str", NEW."cluster_id",
            NEW."date_created", NEW."date_modified", NEW."download_url",
            NEW."extracted_by_ocr", NEW."html", NEW."html_anon_2020",
            NEW."html_columbia", NEW."html_lawbox", NEW."html_with_citations",
            NEW."id", NEW."joined_by_str", NEW."local_path", NEW."page_count",
            NEW."per_curiam", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."plain_text", NEW."sha1", NEW."type",
            NEW."xml_harvard");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_6ae1e ON "search_opinion";
CREATE TRIGGER pgtrigger_snapshot_insert_6ae1e
    AFTER INSERT
    ON "search_opinion"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cdf06()
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
    INSERT INTO "search_opinionevent" ("author_id", "author_str", "cluster_id",
                                       "date_created", "date_modified",
                                       "download_url", "extracted_by_ocr",
                                       "html", "html_anon_2020",
                                       "html_columbia", "html_lawbox",
                                       "html_with_citations", "id",
                                       "joined_by_str", "local_path",
                                       "page_count", "per_curiam",
                                       "pgh_context_id", "pgh_created_at",
                                       "pgh_label", "pgh_obj_id", "plain_text",
                                       "sha1", "type", "xml_harvard")
    VALUES (NEW."author_id", NEW."author_str", NEW."cluster_id",
            NEW."date_created", NEW."date_modified", NEW."download_url",
            NEW."extracted_by_ocr", NEW."html", NEW."html_anon_2020",
            NEW."html_columbia", NEW."html_lawbox", NEW."html_with_citations",
            NEW."id", NEW."joined_by_str", NEW."local_path", NEW."page_count",
            NEW."per_curiam", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."id", NEW."plain_text", NEW."sha1", NEW."type",
            NEW."xml_harvard");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cdf06 ON "search_opinion";
CREATE TRIGGER pgtrigger_snapshot_update_cdf06
    AFTER UPDATE
    ON "search_opinion"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cdf06();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cdf06 ON "search_opinion" IS '31abe6319b984ddbc8ee374a72c87b915099904c';
;
--
-- Create trigger snapshot_insert on model opinioncluster
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b55e2()
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
    INSERT INTO "search_opinionclusterevent" ("attorneys", "blocked",
                                              "case_name", "case_name_full",
                                              "case_name_short",
                                              "citation_count", "correction",
                                              "cross_reference",
                                              "date_blocked", "date_created",
                                              "date_filed",
                                              "date_filed_is_approximate",
                                              "date_modified", "disposition",
                                              "docket_id",
                                              "filepath_json_harvard",
                                              "headnotes", "history", "id",
                                              "judges", "nature_of_suit",
                                              "other_dates", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "pgh_obj_id", "posture",
                                              "precedential_status",
                                              "procedural_history",
                                              "scdb_decision_direction",
                                              "scdb_id", "scdb_votes_majority",
                                              "scdb_votes_minority", "slug",
                                              "source", "summary", "syllabus")
    VALUES (NEW."attorneys", NEW."blocked", NEW."case_name",
            NEW."case_name_full", NEW."case_name_short", NEW."citation_count",
            NEW."correction", NEW."cross_reference", NEW."date_blocked",
            NEW."date_created", NEW."date_filed",
            NEW."date_filed_is_approximate", NEW."date_modified",
            NEW."disposition", NEW."docket_id", NEW."filepath_json_harvard",
            NEW."headnotes", NEW."history", NEW."id", NEW."judges",
            NEW."nature_of_suit", NEW."other_dates", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."posture",
            NEW."precedential_status", NEW."procedural_history",
            NEW."scdb_decision_direction", NEW."scdb_id",
            NEW."scdb_votes_majority", NEW."scdb_votes_minority", NEW."slug",
            NEW."source", NEW."summary", NEW."syllabus");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b55e2 ON "search_opinioncluster";
CREATE TRIGGER pgtrigger_snapshot_insert_b55e2
    AFTER INSERT
    ON "search_opinioncluster"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_f129e()
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
    INSERT INTO "search_opinionclusterevent" ("attorneys", "blocked",
                                              "case_name", "case_name_full",
                                              "case_name_short",
                                              "citation_count", "correction",
                                              "cross_reference",
                                              "date_blocked", "date_created",
                                              "date_filed",
                                              "date_filed_is_approximate",
                                              "date_modified", "disposition",
                                              "docket_id",
                                              "filepath_json_harvard",
                                              "headnotes", "history", "id",
                                              "judges", "nature_of_suit",
                                              "other_dates", "pgh_context_id",
                                              "pgh_created_at", "pgh_label",
                                              "pgh_obj_id", "posture",
                                              "precedential_status",
                                              "procedural_history",
                                              "scdb_decision_direction",
                                              "scdb_id", "scdb_votes_majority",
                                              "scdb_votes_minority", "slug",
                                              "source", "summary", "syllabus")
    VALUES (NEW."attorneys", NEW."blocked", NEW."case_name",
            NEW."case_name_full", NEW."case_name_short", NEW."citation_count",
            NEW."correction", NEW."cross_reference", NEW."date_blocked",
            NEW."date_created", NEW."date_filed",
            NEW."date_filed_is_approximate", NEW."date_modified",
            NEW."disposition", NEW."docket_id", NEW."filepath_json_harvard",
            NEW."headnotes", NEW."history", NEW."id", NEW."judges",
            NEW."nature_of_suit", NEW."other_dates", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."posture",
            NEW."precedential_status", NEW."procedural_history",
            NEW."scdb_decision_direction", NEW."scdb_id",
            NEW."scdb_votes_majority", NEW."scdb_votes_minority", NEW."slug",
            NEW."source", NEW."summary", NEW."syllabus");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_f129e ON "search_opinioncluster";
CREATE TRIGGER pgtrigger_snapshot_update_f129e
    AFTER UPDATE
    ON "search_opinioncluster"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_f129e();

COMMENT ON TRIGGER pgtrigger_snapshot_update_f129e ON "search_opinioncluster" IS 'aab40c6b0b890403f82c3934397e16526f1f9753';
;
--
-- Create trigger snapshot_insert on model originatingcourtinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_73cad()
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
    INSERT INTO "search_originatingcourtinformationevent" ("assigned_to_id",
                                                           "assigned_to_str",
                                                           "court_reporter",
                                                           "date_created",
                                                           "date_disposed",
                                                           "date_filed",
                                                           "date_filed_noa",
                                                           "date_judgment",
                                                           "date_judgment_eod",
                                                           "date_modified",
                                                           "date_received_coa",
                                                           "docket_number",
                                                           "id",
                                                           "ordering_judge_id",
                                                           "ordering_judge_str",
                                                           "pgh_context_id",
                                                           "pgh_created_at",
                                                           "pgh_label",
                                                           "pgh_obj_id")
    VALUES (NEW."assigned_to_id", NEW."assigned_to_str", NEW."court_reporter",
            NEW."date_created", NEW."date_disposed", NEW."date_filed",
            NEW."date_filed_noa", NEW."date_judgment", NEW."date_judgment_eod",
            NEW."date_modified", NEW."date_received_coa", NEW."docket_number",
            NEW."id", NEW."ordering_judge_id", NEW."ordering_judge_str",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_73cad ON "search_originatingcourtinformation";
CREATE TRIGGER pgtrigger_snapshot_insert_73cad
    AFTER INSERT
    ON "search_originatingcourtinformation"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_73cad();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_73cad ON "search_originatingcourtinformation" IS '2b8f1370dbf171b3adb82c231835f68ed15883ea';
;
--
-- Create trigger snapshot_update on model originatingcourtinformation
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_b65c9()
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
    INSERT INTO "search_originatingcourtinformationevent" ("assigned_to_id",
                                                           "assigned_to_str",
                                                           "court_reporter",
                                                           "date_created",
                                                           "date_disposed",
                                                           "date_filed",
                                                           "date_filed_noa",
                                                           "date_judgment",
                                                           "date_judgment_eod",
                                                           "date_modified",
                                                           "date_received_coa",
                                                           "docket_number",
                                                           "id",
                                                           "ordering_judge_id",
                                                           "ordering_judge_str",
                                                           "pgh_context_id",
                                                           "pgh_created_at",
                                                           "pgh_label",
                                                           "pgh_obj_id")
    VALUES (NEW."assigned_to_id", NEW."assigned_to_str", NEW."court_reporter",
            NEW."date_created", NEW."date_disposed", NEW."date_filed",
            NEW."date_filed_noa", NEW."date_judgment", NEW."date_judgment_eod",
            NEW."date_modified", NEW."date_received_coa", NEW."docket_number",
            NEW."id", NEW."ordering_judge_id", NEW."ordering_judge_str",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_b65c9 ON "search_originatingcourtinformation";
CREATE TRIGGER pgtrigger_snapshot_update_b65c9
    AFTER UPDATE
    ON "search_originatingcourtinformation"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_b65c9();

COMMENT ON TRIGGER pgtrigger_snapshot_update_b65c9 ON "search_originatingcourtinformation" IS '57463c4b707eb2d496fac1dc2722952ec2a5cf73';
;
--
-- Create trigger snapshot_insert on model recapdocument
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_570b5()
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
    INSERT INTO "search_recapdocumentevent" ("attachment_number",
                                             "date_created", "date_modified",
                                             "date_upload", "description",
                                             "docket_entry_id",
                                             "document_number",
                                             "document_type", "file_size",
                                             "filepath_ia", "filepath_local",
                                             "ia_upload_failure_count", "id",
                                             "is_available",
                                             "is_free_on_pacer", "is_sealed",
                                             "ocr_status", "pacer_doc_id",
                                             "page_count", "pgh_context_id",
                                             "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "plain_text",
                                             "sha1", "thumbnail",
                                             "thumbnail_status")
    VALUES (NEW."attachment_number", NEW."date_created", NEW."date_modified",
            NEW."date_upload", NEW."description", NEW."docket_entry_id",
            NEW."document_number", NEW."document_type", NEW."file_size",
            NEW."filepath_ia", NEW."filepath_local",
            NEW."ia_upload_failure_count", NEW."id", NEW."is_available",
            NEW."is_free_on_pacer", NEW."is_sealed", NEW."ocr_status",
            NEW."pacer_doc_id", NEW."page_count", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."plain_text", NEW."sha1",
            NEW."thumbnail", NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_570b5 ON "search_recapdocument";
CREATE TRIGGER pgtrigger_snapshot_insert_570b5
    AFTER INSERT
    ON "search_recapdocument"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_570b5();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_570b5 ON "search_recapdocument" IS 'a9d69669ad636fb0d8f07fa062220e9ae34a0bb2';
;
--
-- Create trigger snapshot_update on model recapdocument
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_6713a()
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
    INSERT INTO "search_recapdocumentevent" ("attachment_number",
                                             "date_created", "date_modified",
                                             "date_upload", "description",
                                             "docket_entry_id",
                                             "document_number",
                                             "document_type", "file_size",
                                             "filepath_ia", "filepath_local",
                                             "ia_upload_failure_count", "id",
                                             "is_available",
                                             "is_free_on_pacer", "is_sealed",
                                             "ocr_status", "pacer_doc_id",
                                             "page_count", "pgh_context_id",
                                             "pgh_created_at", "pgh_label",
                                             "pgh_obj_id", "plain_text",
                                             "sha1", "thumbnail",
                                             "thumbnail_status")
    VALUES (NEW."attachment_number", NEW."date_created", NEW."date_modified",
            NEW."date_upload", NEW."description", NEW."docket_entry_id",
            NEW."document_number", NEW."document_type", NEW."file_size",
            NEW."filepath_ia", NEW."filepath_local",
            NEW."ia_upload_failure_count", NEW."id", NEW."is_available",
            NEW."is_free_on_pacer", NEW."is_sealed", NEW."ocr_status",
            NEW."pacer_doc_id", NEW."page_count", _pgh_attach_context(), NOW(),
            'snapshot', NEW."id", NEW."plain_text", NEW."sha1",
            NEW."thumbnail", NEW."thumbnail_status");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_6713a ON "search_recapdocument";
CREATE TRIGGER pgtrigger_snapshot_update_6713a
    AFTER UPDATE
    ON "search_recapdocument"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_6713a();

COMMENT ON TRIGGER pgtrigger_snapshot_update_6713a ON "search_recapdocument" IS 'e7beed06fa16a7b2610d0979ff0dba8d9867f41b';
;
--
-- Create trigger snapshot_insert on model tag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_3bd86()
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
    INSERT INTO "search_tagevent" ("date_created", "date_modified", "id",
                                   "name", "pgh_context_id", "pgh_created_at",
                                   "pgh_label", "pgh_obj_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."name",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3bd86 ON "search_tag";
CREATE TRIGGER pgtrigger_snapshot_insert_3bd86
    AFTER INSERT
    ON "search_tag"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_3bd86();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_3bd86 ON "search_tag" IS '889376f85e05cb06779dd07163f260c88886eb06';
;
--
-- Create trigger snapshot_update on model tag
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_a85e0()
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
    INSERT INTO "search_tagevent" ("date_created", "date_modified", "id",
                                   "name", "pgh_context_id", "pgh_created_at",
                                   "pgh_label", "pgh_obj_id")
    VALUES (NEW."date_created", NEW."date_modified", NEW."id", NEW."name",
            _pgh_attach_context(), NOW(), 'snapshot', NEW."id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_a85e0 ON "search_tag";
CREATE TRIGGER pgtrigger_snapshot_update_a85e0
    AFTER UPDATE
    ON "search_tag"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_a85e0();

COMMENT ON TRIGGER pgtrigger_snapshot_update_a85e0 ON "search_tag" IS '8e5aee2dfb7d31ff1e18b3e528e77697a292ecdc';
;
--
-- Add field pgh_context to tagevent
--
ALTER TABLE "search_tagevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to tagevent
--
ALTER TABLE "search_tagevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field pgh_context to recapdocumenttagsevent
--
ALTER TABLE "search_recapdocumenttagsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field recapdocument to recapdocumenttagsevent
--
ALTER TABLE "search_recapdocumenttagsevent"
    ADD COLUMN "recapdocument_id" integer NOT NULL;
--
-- Add field tag to recapdocumenttagsevent
--
ALTER TABLE "search_recapdocumenttagsevent"
    ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field docket_entry to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent"
    ADD COLUMN "docket_entry_id" integer NOT NULL;
--
-- Add field pgh_context to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to recapdocumentevent
--
ALTER TABLE "search_recapdocumentevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field assigned_to to originatingcourtinformationevent
--
ALTER TABLE "search_originatingcourtinformationevent"
    ADD COLUMN "assigned_to_id" integer NULL;
--
-- Add field ordering_judge to originatingcourtinformationevent
--
ALTER TABLE "search_originatingcourtinformationevent"
    ADD COLUMN "ordering_judge_id" integer NULL;
--
-- Add field pgh_context to originatingcourtinformationevent
--
ALTER TABLE "search_originatingcourtinformationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to originatingcourtinformationevent
--
ALTER TABLE "search_originatingcourtinformationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field opinion to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent"
    ADD COLUMN "opinion_id" integer NOT NULL;
--
-- Add field person to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionjoinedbyevent
--
ALTER TABLE "search_opinionjoinedbyevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field author to opinionevent
--
ALTER TABLE "search_opinionevent"
    ADD COLUMN "author_id" integer NULL;
--
-- Add field cluster to opinionevent
--
ALTER TABLE "search_opinionevent"
    ADD COLUMN "cluster_id" integer NOT NULL;
--
-- Add field pgh_context to opinionevent
--
ALTER TABLE "search_opinionevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to opinionevent
--
ALTER TABLE "search_opinionevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field opinioncluster to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent"
    ADD COLUMN "opinioncluster_id" integer NOT NULL;
--
-- Add field person to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusterpanelevent
--
ALTER TABLE "search_opinionclusterpanelevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field opinioncluster to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent"
    ADD COLUMN "opinioncluster_id" integer NOT NULL;
--
-- Add field person to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusternonparticipatingjudgesevent
--
ALTER TABLE "search_opinionclusternonparticipatingjudgesevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field docket to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to opinionclusterevent
--
ALTER TABLE "search_opinionclusterevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field docket to dockettagsevent
--
ALTER TABLE "search_dockettagsevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to dockettagsevent
--
ALTER TABLE "search_dockettagsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field tag to dockettagsevent
--
ALTER TABLE "search_dockettagsevent"
    ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field docket to docketpanelevent
--
ALTER TABLE "search_docketpanelevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field person to docketpanelevent
--
ALTER TABLE "search_docketpanelevent"
    ADD COLUMN "person_id" integer NOT NULL;
--
-- Add field pgh_context to docketpanelevent
--
ALTER TABLE "search_docketpanelevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field appeal_from to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "appeal_from_id" varchar(15) NULL;
--
-- Add field assigned_to to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "assigned_to_id" integer NULL;
--
-- Add field court to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "court_id" varchar(15) NOT NULL;
--
-- Add field idb_data to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "idb_data_id" integer NULL;
--
-- Add field originating_court_information to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "originating_court_information_id" integer NULL;
--
-- Add field pgh_context to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field referred_to to docketevent
--
ALTER TABLE "search_docketevent"
    ADD COLUMN "referred_to_id" integer NULL;
--
-- Add field docketentry to docketentrytagsevent
--
ALTER TABLE "search_docketentrytagsevent"
    ADD COLUMN "docketentry_id" integer NOT NULL;
--
-- Add field pgh_context to docketentrytagsevent
--
ALTER TABLE "search_docketentrytagsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field tag to docketentrytagsevent
--
ALTER TABLE "search_docketentrytagsevent"
    ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field docket to docketentryevent
--
ALTER TABLE "search_docketentryevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to docketentryevent
--
ALTER TABLE "search_docketentryevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to docketentryevent
--
ALTER TABLE "search_docketentryevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field pgh_context to courtevent
--
ALTER TABLE "search_courtevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to courtevent
--
ALTER TABLE "search_courtevent"
    ADD COLUMN "pgh_obj_id" varchar(15) NOT NULL;
--
-- Add field claim to claimtagsevent
--
ALTER TABLE "search_claimtagsevent"
    ADD COLUMN "claim_id" integer NOT NULL;
--
-- Add field pgh_context to claimtagsevent
--
ALTER TABLE "search_claimtagsevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field tag to claimtagsevent
--
ALTER TABLE "search_claimtagsevent"
    ADD COLUMN "tag_id" integer NOT NULL;
--
-- Add field claim to claimhistoryevent
--
ALTER TABLE "search_claimhistoryevent"
    ADD COLUMN "claim_id" integer NOT NULL;
--
-- Add field pgh_context to claimhistoryevent
--
ALTER TABLE "search_claimhistoryevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to claimhistoryevent
--
ALTER TABLE "search_claimhistoryevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field docket to claimevent
--
ALTER TABLE "search_claimevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to claimevent
--
ALTER TABLE "search_claimevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to claimevent
--
ALTER TABLE "search_claimevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field cluster to citationevent
--
ALTER TABLE "search_citationevent"
    ADD COLUMN "cluster_id" integer NOT NULL;
--
-- Add field pgh_context to citationevent
--
ALTER TABLE "search_citationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to citationevent
--
ALTER TABLE "search_citationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field docket to bankruptcyinformationevent
--
ALTER TABLE "search_bankruptcyinformationevent"
    ADD COLUMN "docket_id" integer NOT NULL;
--
-- Add field pgh_context to bankruptcyinformationevent
--
ALTER TABLE "search_bankruptcyinformationevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to bankruptcyinformationevent
--
ALTER TABLE "search_bankruptcyinformationevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Create trigger snapshot_insert on model claimtags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_5fb47()
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
    INSERT INTO "search_claimtagsevent" ("claim_id", "id", "pgh_context_id",
                                         "pgh_created_at", "pgh_label",
                                         "tag_id")
    VALUES (NEW."claim_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_5fb47 ON "search_claim_tags";
CREATE TRIGGER pgtrigger_snapshot_insert_5fb47
    AFTER INSERT
    ON "search_claim_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_5fb47();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_5fb47 ON "search_claim_tags" IS '7d6de7400655f2b9c6d0d6f95c8523e448cc99f1';
;
--
-- Create trigger snapshot_update on model claimtags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_0f6a3()
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
    INSERT INTO "search_claimtagsevent" ("claim_id", "id", "pgh_context_id",
                                         "pgh_created_at", "pgh_label",
                                         "tag_id")
    VALUES (NEW."claim_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_0f6a3 ON "search_claim_tags";
CREATE TRIGGER pgtrigger_snapshot_update_0f6a3
    AFTER UPDATE
    ON "search_claim_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_0f6a3();

COMMENT ON TRIGGER pgtrigger_snapshot_update_0f6a3 ON "search_claim_tags" IS 'a237915dffa2fbba56a37be93864df8c3da24897';
;
--
-- Create trigger snapshot_insert on model docketentrytags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_feff2()
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
    INSERT INTO "search_docketentrytagsevent" ("docketentry_id", "id",
                                               "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "tag_id")
    VALUES (NEW."docketentry_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_feff2 ON "search_docketentry_tags";
CREATE TRIGGER pgtrigger_snapshot_insert_feff2
    AFTER INSERT
    ON "search_docketentry_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_feff2();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_feff2 ON "search_docketentry_tags" IS 'd627501475c1f07602cdd7c4a8d4d7d4ab0fc047';
;
--
-- Create trigger snapshot_update on model docketentrytags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_1a242()
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
    INSERT INTO "search_docketentrytagsevent" ("docketentry_id", "id",
                                               "pgh_context_id",
                                               "pgh_created_at", "pgh_label",
                                               "tag_id")
    VALUES (NEW."docketentry_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_1a242 ON "search_docketentry_tags";
CREATE TRIGGER pgtrigger_snapshot_update_1a242
    AFTER UPDATE
    ON "search_docketentry_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_1a242();

COMMENT ON TRIGGER pgtrigger_snapshot_update_1a242 ON "search_docketentry_tags" IS '0423a62b841573f0f3870b98a5dac81c90423a08';
;
--
-- Create trigger snapshot_insert on model docketpanel
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_23fa7()
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
    INSERT INTO "search_docketpanelevent" ("docket_id", "id", "person_id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label")
    VALUES (NEW."docket_id", NEW."id", NEW."person_id", _pgh_attach_context(),
            NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_23fa7 ON "search_docket_panel";
CREATE TRIGGER pgtrigger_snapshot_insert_23fa7
    AFTER INSERT
    ON "search_docket_panel"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_e0bd2()
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
    INSERT INTO "search_docketpanelevent" ("docket_id", "id", "person_id",
                                           "pgh_context_id", "pgh_created_at",
                                           "pgh_label")
    VALUES (NEW."docket_id", NEW."id", NEW."person_id", _pgh_attach_context(),
            NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_e0bd2 ON "search_docket_panel";
CREATE TRIGGER pgtrigger_snapshot_update_e0bd2
    AFTER UPDATE
    ON "search_docket_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_e0bd2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_e0bd2 ON "search_docket_panel" IS 'cabe688dcbfa55a212287ebe5d52037924bead84';
;
--
-- Create trigger snapshot_insert on model dockettags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_b723b()
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
    INSERT INTO "search_dockettagsevent" ("docket_id", "id", "pgh_context_id",
                                          "pgh_created_at", "pgh_label",
                                          "tag_id")
    VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_b723b ON "search_docket_tags";
CREATE TRIGGER pgtrigger_snapshot_insert_b723b
    AFTER INSERT
    ON "search_docket_tags"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_59839()
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
    INSERT INTO "search_dockettagsevent" ("docket_id", "id", "pgh_context_id",
                                          "pgh_created_at", "pgh_label",
                                          "tag_id")
    VALUES (NEW."docket_id", NEW."id", _pgh_attach_context(), NOW(),
            'snapshot', NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_59839 ON "search_docket_tags";
CREATE TRIGGER pgtrigger_snapshot_update_59839
    AFTER UPDATE
    ON "search_docket_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_59839();

COMMENT ON TRIGGER pgtrigger_snapshot_update_59839 ON "search_docket_tags" IS 'b25d863b87575dfdfb93a36dd16afc3d3ac115e9';
;
--
-- Create trigger snapshot_insert on model opinionclusternonparticipatingjudges
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_0000e()
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
    INSERT INTO "search_opinionclusternonparticipatingjudgesevent" ("id",
                                                                    "opinioncluster_id",
                                                                    "person_id",
                                                                    "pgh_context_id",
                                                                    "pgh_created_at",
                                                                    "pgh_label")
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_0000e ON "search_opinioncluster_non_participating_judges";
CREATE TRIGGER pgtrigger_snapshot_insert_0000e
    AFTER INSERT
    ON "search_opinioncluster_non_participating_judges"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_8f2d1()
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
    INSERT INTO "search_opinionclusternonparticipatingjudgesevent" ("id",
                                                                    "opinioncluster_id",
                                                                    "person_id",
                                                                    "pgh_context_id",
                                                                    "pgh_created_at",
                                                                    "pgh_label")
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_8f2d1 ON "search_opinioncluster_non_participating_judges";
CREATE TRIGGER pgtrigger_snapshot_update_8f2d1
    AFTER UPDATE
    ON "search_opinioncluster_non_participating_judges"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_8f2d1();

COMMENT ON TRIGGER pgtrigger_snapshot_update_8f2d1 ON "search_opinioncluster_non_participating_judges" IS '22f3de5e60619ba7e4b1c57941a63fd0183abd28';
;
--
-- Create trigger snapshot_insert on model opinionclusterpanel
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_3e719()
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
    INSERT INTO "search_opinionclusterpanelevent" ("id", "opinioncluster_id",
                                                   "person_id",
                                                   "pgh_context_id",
                                                   "pgh_created_at",
                                                   "pgh_label")
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_3e719 ON "search_opinioncluster_panel";
CREATE TRIGGER pgtrigger_snapshot_insert_3e719
    AFTER INSERT
    ON "search_opinioncluster_panel"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_2a689()
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
    INSERT INTO "search_opinionclusterpanelevent" ("id", "opinioncluster_id",
                                                   "person_id",
                                                   "pgh_context_id",
                                                   "pgh_created_at",
                                                   "pgh_label")
    VALUES (NEW."id", NEW."opinioncluster_id", NEW."person_id",
            _pgh_attach_context(), NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_2a689 ON "search_opinioncluster_panel";
CREATE TRIGGER pgtrigger_snapshot_update_2a689
    AFTER UPDATE
    ON "search_opinioncluster_panel"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_2a689();

COMMENT ON TRIGGER pgtrigger_snapshot_update_2a689 ON "search_opinioncluster_panel" IS '2d92289ef7590f116a68817146315937e25b2715';
;
--
-- Create trigger snapshot_insert on model opinionjoinedby
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_541c3()
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
    INSERT INTO "search_opinionjoinedbyevent" ("id", "opinion_id", "person_id",
                                               "pgh_context_id",
                                               "pgh_created_at", "pgh_label")
    VALUES (NEW."id", NEW."opinion_id", NEW."person_id", _pgh_attach_context(),
            NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_541c3 ON "search_opinion_joined_by";
CREATE TRIGGER pgtrigger_snapshot_insert_541c3
    AFTER INSERT
    ON "search_opinion_joined_by"


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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_23a70()
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
    INSERT INTO "search_opinionjoinedbyevent" ("id", "opinion_id", "person_id",
                                               "pgh_context_id",
                                               "pgh_created_at", "pgh_label")
    VALUES (NEW."id", NEW."opinion_id", NEW."person_id", _pgh_attach_context(),
            NOW(), 'snapshot');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_23a70 ON "search_opinion_joined_by";
CREATE TRIGGER pgtrigger_snapshot_update_23a70
    AFTER UPDATE
    ON "search_opinion_joined_by"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_23a70();

COMMENT ON TRIGGER pgtrigger_snapshot_update_23a70 ON "search_opinion_joined_by" IS '694b606ec9b855311a850bf376434611982b334c';
;
--
-- Create trigger snapshot_insert on model recapdocumenttags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_fd858()
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
    INSERT INTO "search_recapdocumenttagsevent" ("id", "pgh_context_id",
                                                 "pgh_created_at", "pgh_label",
                                                 "recapdocument_id", "tag_id")
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."recapdocument_id", NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_fd858 ON "search_recapdocument_tags";
CREATE TRIGGER pgtrigger_snapshot_insert_fd858
    AFTER INSERT
    ON "search_recapdocument_tags"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_fd858();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_fd858 ON "search_recapdocument_tags" IS 'd97d525ad21b7af6ebdb7166a54cbfedcbf01612';
;
--
-- Create trigger snapshot_update on model recapdocumenttags
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

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_52362()
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
    INSERT INTO "search_recapdocumenttagsevent" ("id", "pgh_context_id",
                                                 "pgh_created_at", "pgh_label",
                                                 "recapdocument_id", "tag_id")
    VALUES (NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."recapdocument_id", NEW."tag_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_52362 ON "search_recapdocument_tags";
CREATE TRIGGER pgtrigger_snapshot_update_52362
    AFTER UPDATE
    ON "search_recapdocument_tags"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_52362();

COMMENT ON TRIGGER pgtrigger_snapshot_update_52362 ON "search_recapdocument_tags" IS '1dd6766c3c40e5efdb228a1f92a7d64ddee0a107';
;
CREATE INDEX "search_tagevent_pgh_context_id_03f699de" ON "search_tagevent" ("pgh_context_id");
CREATE INDEX "search_tagevent_pgh_obj_id_af8c9817" ON "search_tagevent" ("pgh_obj_id");
CREATE INDEX "search_recapdocumenttagsevent_pgh_context_id_ff9be284" ON "search_recapdocumenttagsevent" ("pgh_context_id");
CREATE INDEX "search_recapdocumenttagsevent_recapdocument_id_c6f0a858" ON "search_recapdocumenttagsevent" ("recapdocument_id");
CREATE INDEX "search_recapdocumenttagsevent_tag_id_9fa96f02" ON "search_recapdocumenttagsevent" ("tag_id");
CREATE INDEX "search_recapdocumentevent_docket_entry_id_055ee57b" ON "search_recapdocumentevent" ("docket_entry_id");
CREATE INDEX "search_recapdocumentevent_pgh_context_id_37bf47c3" ON "search_recapdocumentevent" ("pgh_context_id");
CREATE INDEX "search_recapdocumentevent_pgh_obj_id_aa9c8d6e" ON "search_recapdocumentevent" ("pgh_obj_id");
CREATE INDEX "search_originatingcourtinformationevent_assigned_to_id_fcce9094" ON "search_originatingcourtinformationevent" ("assigned_to_id");
CREATE INDEX "search_originatingcourtinf_ordering_judge_id_5aa931cb" ON "search_originatingcourtinformationevent" ("ordering_judge_id");
CREATE INDEX "search_originatingcourtinformationevent_pgh_context_id_d8ffc4c8" ON "search_originatingcourtinformationevent" ("pgh_context_id");
CREATE INDEX "search_originatingcourtinformationevent_pgh_obj_id_32490a9c" ON "search_originatingcourtinformationevent" ("pgh_obj_id");
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
CREATE INDEX "search_docketentrytagsevent_docketentry_id_1aa64197" ON "search_docketentrytagsevent" ("docketentry_id");
CREATE INDEX "search_docketentrytagsevent_pgh_context_id_f91c4367" ON "search_docketentrytagsevent" ("pgh_context_id");
CREATE INDEX "search_docketentrytagsevent_tag_id_9d769fa5" ON "search_docketentrytagsevent" ("tag_id");
CREATE INDEX "search_docketentryevent_docket_id_469ad4c0" ON "search_docketentryevent" ("docket_id");
CREATE INDEX "search_docketentryevent_pgh_context_id_1bd9c36d" ON "search_docketentryevent" ("pgh_context_id");
CREATE INDEX "search_docketentryevent_pgh_obj_id_584ac554" ON "search_docketentryevent" ("pgh_obj_id");
CREATE INDEX "search_courtevent_pgh_context_id_7a93b57e" ON "search_courtevent" ("pgh_context_id");
CREATE INDEX "search_courtevent_pgh_obj_id_a86c8348" ON "search_courtevent" ("pgh_obj_id");
CREATE INDEX "search_courtevent_pgh_obj_id_a86c8348_like" ON "search_courtevent" ("pgh_obj_id" varchar_pattern_ops);
CREATE INDEX "search_claimtagsevent_claim_id_34146335" ON "search_claimtagsevent" ("claim_id");
CREATE INDEX "search_claimtagsevent_pgh_context_id_bb236d3a" ON "search_claimtagsevent" ("pgh_context_id");
CREATE INDEX "search_claimtagsevent_tag_id_fdeb7331" ON "search_claimtagsevent" ("tag_id");
CREATE INDEX "search_claimhistoryevent_claim_id_a256e51f" ON "search_claimhistoryevent" ("claim_id");
CREATE INDEX "search_claimhistoryevent_pgh_context_id_fbccd42a" ON "search_claimhistoryevent" ("pgh_context_id");
CREATE INDEX "search_claimhistoryevent_pgh_obj_id_51dc3876" ON "search_claimhistoryevent" ("pgh_obj_id");
CREATE INDEX "search_claimevent_docket_id_b016b91c" ON "search_claimevent" ("docket_id");
CREATE INDEX "search_claimevent_pgh_context_id_421c9863" ON "search_claimevent" ("pgh_context_id");
CREATE INDEX "search_claimevent_pgh_obj_id_eb8bb005" ON "search_claimevent" ("pgh_obj_id");
CREATE INDEX "search_citationevent_cluster_id_3cc4bdde" ON "search_citationevent" ("cluster_id");
CREATE INDEX "search_citationevent_pgh_context_id_a721796b" ON "search_citationevent" ("pgh_context_id");
CREATE INDEX "search_citationevent_pgh_obj_id_74bef0e4" ON "search_citationevent" ("pgh_obj_id");
CREATE INDEX "search_bankruptcyinformationevent_docket_id_e6ca7d29" ON "search_bankruptcyinformationevent" ("docket_id");
CREATE INDEX "search_bankruptcyinformationevent_pgh_context_id_5e7bd505" ON "search_bankruptcyinformationevent" ("pgh_context_id");
CREATE INDEX "search_bankruptcyinformationevent_pgh_obj_id_73c1db25" ON "search_bankruptcyinformationevent" ("pgh_obj_id");
COMMIT;

