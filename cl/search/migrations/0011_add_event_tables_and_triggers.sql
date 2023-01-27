BEGIN;
--
-- Create model Claim
--
CREATE TABLE "search_claim"
(
    "id"                          serial                   NOT NULL PRIMARY KEY,
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
-- Create model Court
--
CREATE TABLE "search_court"
(
    "id"                        varchar(15)              NOT NULL PRIMARY KEY,
    "pacer_court_id"            smallint                 NULL CHECK ("pacer_court_id" >= 0),
    "pacer_has_rss_feed"        boolean                  NULL,
    "pacer_rss_entry_types"     text                     NOT NULL,
    "date_last_pacer_contact"   timestamp with time zone NULL,
    "fjc_court_id"              varchar(3)               NOT NULL,
    "date_modified"             timestamp with time zone NOT NULL,
    "in_use"                    boolean                  NOT NULL,
    "has_opinion_scraper"       boolean                  NOT NULL,
    "has_oral_argument_scraper" boolean                  NOT NULL,
    "position"                  double precision         NOT NULL UNIQUE,
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
-- Create model Docket
--
CREATE TABLE "search_docket"
(
    "id"                              serial                   NOT NULL PRIMARY KEY,
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
    "view_count"                      integer                  NOT NULL,
    "date_blocked"                    date                     NULL,
    "blocked"                         boolean                  NOT NULL,
    "appeal_from_id"                  varchar(15)              NULL,
    "assigned_to_id"                  integer                  NULL,
    "court_id"                        varchar(15)              NOT NULL,
    "idb_data_id"                     integer                  NULL UNIQUE
);
--
-- Create model DocketEntry
--
CREATE TABLE "search_docketentry"
(
    "id"                    serial                   NOT NULL PRIMARY KEY,
    "date_created"          timestamp with time zone NOT NULL,
    "date_modified"         timestamp with time zone NOT NULL,
    "date_filed"            date                     NULL,
    "entry_number"          bigint                   NULL,
    "recap_sequence_number" varchar(50)              NOT NULL,
    "pacer_sequence_number" integer                  NULL,
    "description"           text                     NOT NULL,
    "docket_id"             integer                  NOT NULL
);
--
-- Create model Opinion
--
CREATE TABLE "search_opinion"
(
    "id"                  serial                   NOT NULL PRIMARY KEY,
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
    "extracted_by_ocr"    boolean                  NOT NULL,
    "author_id"           integer                  NULL
);
--
-- Create model Tag
--
CREATE TABLE "search_tag"
(
    "id"            serial                   NOT NULL PRIMARY KEY,
    "date_created"  timestamp with time zone NOT NULL,
    "date_modified" timestamp with time zone NOT NULL,
    "name"          varchar(50)              NOT NULL UNIQUE
);
--
-- Create model RECAPDocument
--
CREATE TABLE "search_recapdocument"
(
    "id"                      serial                   NOT NULL PRIMARY KEY,
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
    "description"             text                     NOT NULL,
    "docket_entry_id"         integer                  NOT NULL
);
CREATE TABLE "search_recapdocument_tags"
(
    "id"               serial  NOT NULL PRIMARY KEY,
    "recapdocument_id" integer NOT NULL,
    "tag_id"           integer NOT NULL
);
--
-- Create model OriginatingCourtInformation
--
CREATE TABLE "search_originatingcourtinformation"
(
    "id"                 serial                   NOT NULL PRIMARY KEY,
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
    "date_received_coa"  date                     NULL,
    "assigned_to_id"     integer                  NULL,
    "ordering_judge_id"  integer                  NULL
);
--
-- Create model OpinionsCited
--
CREATE TABLE "search_opinionscited"
(
    "id"                serial  NOT NULL PRIMARY KEY,
    "depth"             integer NOT NULL,
    "cited_opinion_id"  integer NOT NULL,
    "citing_opinion_id" integer NOT NULL
);
--
-- Create model OpinionCluster
--
CREATE TABLE "search_opinioncluster"
(
    "id"                        serial                   NOT NULL PRIMARY KEY,
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
    "filepath_json_harvard"     varchar(1000)            NOT NULL,
    "docket_id"                 integer                  NOT NULL
);
CREATE TABLE "search_opinioncluster_non_participating_judges"
(
    "id"                serial  NOT NULL PRIMARY KEY,
    "opinioncluster_id" integer NOT NULL,
    "person_id"         integer NOT NULL
);
CREATE TABLE "search_opinioncluster_panel"
(
    "id"                serial  NOT NULL PRIMARY KEY,
    "opinioncluster_id" integer NOT NULL,
    "person_id"         integer NOT NULL
);
--
-- Add field cluster to opinion
--
ALTER TABLE "search_opinion"
    ADD COLUMN "cluster_id" integer NOT NULL
        CONSTRAINT "search_opinion_cluster_id_09bd537a_fk_search_opinioncluster_id" REFERENCES "search_opinioncluster" ("id") DEFERRABLE INITIALLY DEFERRED;
SET CONSTRAINTS "search_opinion_cluster_id_09bd537a_fk_search_opinioncluster_id" IMMEDIATE;
--
-- Add field joined_by to opinion
--
CREATE TABLE "search_opinion_joined_by"
(
    "id"         serial  NOT NULL PRIMARY KEY,
    "opinion_id" integer NOT NULL,
    "person_id"  integer NOT NULL
);
--
-- Add field opinions_cited to opinion
--
--
-- Add field tags to docketentry
--
CREATE TABLE "search_docketentry_tags"
(
    "id"             serial  NOT NULL PRIMARY KEY,
    "docketentry_id" integer NOT NULL,
    "tag_id"         integer NOT NULL
);
--
-- Add field originating_court_information to docket
--
ALTER TABLE "search_docket"
    ADD COLUMN "originating_court_information_id" integer NULL UNIQUE
        CONSTRAINT "search_docket_originating_court_in_6f8d0fbd_fk_search_or" REFERENCES "search_originatingcourtinformation" ("id") DEFERRABLE INITIALLY DEFERRED;
SET CONSTRAINTS "search_docket_originating_court_in_6f8d0fbd_fk_search_or" IMMEDIATE;
--
-- Add field panel to docket
--
CREATE TABLE "search_docket_panel"
(
    "id"        serial  NOT NULL PRIMARY KEY,
    "docket_id" integer NOT NULL,
    "person_id" integer NOT NULL
);
--
-- Add field parties to docket
--
--
-- Add field referred_to to docket
--
ALTER TABLE "search_docket"
    ADD COLUMN "referred_to_id" integer NULL
        CONSTRAINT "search_docket_referred_to_id_cf6332e0_fk_people_db_person_id" REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
SET CONSTRAINTS "search_docket_referred_to_id_cf6332e0_fk_people_db_person_id" IMMEDIATE;
--
-- Add field tags to docket
--
CREATE TABLE "search_docket_tags"
(
    "id"        serial  NOT NULL PRIMARY KEY,
    "docket_id" integer NOT NULL,
    "tag_id"    integer NOT NULL
);
--
-- Create model ClaimHistory
--
CREATE TABLE "search_claimhistory"
(
    "id"                      serial                   NOT NULL PRIMARY KEY,
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
    "pacer_case_id"           varchar(100)             NOT NULL,
    "claim_id"                integer                  NOT NULL
);
--
-- Add field docket to claim
--
ALTER TABLE "search_claim"
    ADD COLUMN "docket_id" integer NOT NULL
        CONSTRAINT "search_claim_docket_id_b37171a9_fk_search_docket_id" REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
SET CONSTRAINTS "search_claim_docket_id_b37171a9_fk_search_docket_id" IMMEDIATE;
--
-- Add field tags to claim
--
CREATE TABLE "search_claim_tags"
(
    "id"       serial  NOT NULL PRIMARY KEY,
    "claim_id" integer NOT NULL,
    "tag_id"   integer NOT NULL
);
--
-- Create model Citation
--
CREATE TABLE "search_citation"
(
    "id"         serial   NOT NULL PRIMARY KEY,
    "volume"     smallint NOT NULL,
    "reporter"   text     NOT NULL,
    "page"       text     NOT NULL,
    "type"       smallint NOT NULL,
    "cluster_id" integer  NOT NULL
);
--
-- Create model BankruptcyInformation
--
CREATE TABLE "search_bankruptcyinformation"
(
    "id"                       serial                   NOT NULL PRIMARY KEY,
    "date_created"             timestamp with time zone NOT NULL,
    "date_modified"            timestamp with time zone NOT NULL,
    "date_converted"           timestamp with time zone NULL,
    "date_last_to_file_claims" timestamp with time zone NULL,
    "date_last_to_file_govt"   timestamp with time zone NULL,
    "date_debtor_dismissed"    timestamp with time zone NULL,
    "chapter"                  varchar(10)              NOT NULL,
    "trustee_str"              text                     NOT NULL,
    "docket_id"                integer                  NOT NULL UNIQUE
);
--
-- Create index search_recapdocument_filepath_local_7dc6b0e53ccf753_uniq on field(s) filepath_local of model recapdocument
--
CREATE INDEX "search_recapdocument_filepath_local_7dc6b0e53ccf753_uniq" ON "search_recapdocument" ("filepath_local");
--
-- Alter unique_together for recapdocument (1 constraint(s))
--
ALTER TABLE "search_recapdocument"
    ADD CONSTRAINT "search_recapdocument_docket_entry_id_document_3a7bbbba_uniq" UNIQUE ("docket_entry_id",
                                                                                         "document_number",
                                                                                         "attachment_number");
--
-- Alter index_together for recapdocument (1 constraint(s))
--
CREATE INDEX "search_recapdocument_document_type_document_n_f531242f_idx" ON "search_recapdocument" ("document_type",
                                                                                                     "document_number",
                                                                                                     "attachment_number");
--
-- Alter unique_together for opinionscited (1 constraint(s))
--
ALTER TABLE "search_opinionscited"
    ADD CONSTRAINT "search_opinionscited_citing_opinion_id_cited__ece0ff2a_uniq" UNIQUE ("citing_opinion_id", "cited_opinion_id");
--
-- Alter index_together for docketentry (1 constraint(s))
--
CREATE INDEX "search_docketentry_recap_sequence_number_en_da10a2c8_idx" ON "search_docketentry" ("recap_sequence_number", "entry_number");
--
-- Create index search_dock_court_i_a043ae_idx on field(s) court_id, id of model docket
--
CREATE INDEX "search_dock_court_i_a043ae_idx" ON "search_docket" ("court_id", "id");
--
-- Alter unique_together for docket (1 constraint(s))
--
ALTER TABLE "search_docket"
    ADD CONSTRAINT "search_docket_docket_number_pacer_case_a3184727_uniq" UNIQUE ("docket_number", "pacer_case_id", "court_id");
--
-- Alter index_together for docket (1 constraint(s))
--
CREATE INDEX "search_docket_ia_upload_failure_count__1da403a6_idx" ON "search_docket" ("ia_upload_failure_count",
                                                                                       "ia_needs_upload",
                                                                                       "ia_date_first_change");
--
-- Alter unique_together for citation (1 constraint(s))
--
ALTER TABLE "search_citation"
    ADD CONSTRAINT "search_citation_cluster_id_volume_reporter_page_1987e27b_uniq" UNIQUE ("cluster_id", "volume", "reporter", "page");
--
-- Alter index_together for citation (2 constraint(s))
--
CREATE INDEX "search_citation_volume_reporter_page_2606b024_idx" ON "search_citation" ("volume", "reporter", "page");
CREATE INDEX "search_citation_volume_reporter_a3a77c16_idx" ON "search_citation" ("volume", "reporter");
CREATE INDEX "search_claim_date_created_8c2e998c" ON "search_claim" ("date_created");
CREATE INDEX "search_claim_date_modified_f38130a2" ON "search_claim" ("date_modified");
CREATE INDEX "search_claim_claim_number_263236b3" ON "search_claim" ("claim_number");
CREATE INDEX "search_claim_claim_number_263236b3_like" ON "search_claim" ("claim_number" varchar_pattern_ops);
CREATE INDEX "search_court_id_61737e1f_like" ON "search_court" ("id" varchar_pattern_ops);
CREATE INDEX "search_court_date_modified_593d1692" ON "search_court" ("date_modified");
ALTER TABLE "search_docket"
    ADD CONSTRAINT "search_docket_appeal_from_id_e8bffa28_fk_search_court_id" FOREIGN KEY ("appeal_from_id") REFERENCES "search_court" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docket"
    ADD CONSTRAINT "search_docket_assigned_to_id_167c3921_fk_people_db_person_id" FOREIGN KEY ("assigned_to_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docket"
    ADD CONSTRAINT "search_docket_court_id_2bc55eb7_fk_search_court_id" FOREIGN KEY ("court_id") REFERENCES "search_court" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docket"
    ADD CONSTRAINT "search_docket_idb_data_id_eff93778_fk_recap_fjc" FOREIGN KEY ("idb_data_id") REFERENCES "recap_fjcintegrateddatabase" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_docket_date_created_27b493ee" ON "search_docket" ("date_created");
CREATE INDEX "search_docket_date_modified_4a377f1d" ON "search_docket" ("date_modified");
CREATE INDEX "search_docket_date_cert_granted_3778fc78" ON "search_docket" ("date_cert_granted");
CREATE INDEX "search_docket_date_cert_denied_b2518866" ON "search_docket" ("date_cert_denied");
CREATE INDEX "search_docket_date_argued_57937f24" ON "search_docket" ("date_argued");
CREATE INDEX "search_docket_date_reargued_fb8ef0ca" ON "search_docket" ("date_reargued");
CREATE INDEX "search_docket_date_reargument_denied_7b248c40" ON "search_docket" ("date_reargument_denied");
CREATE INDEX "search_docket_docket_number_b2afb9d6" ON "search_docket" ("docket_number");
CREATE INDEX "search_docket_docket_number_b2afb9d6_like" ON "search_docket" ("docket_number" text_pattern_ops);
CREATE INDEX "search_docket_docket_number_core_9278e62b" ON "search_docket" ("docket_number_core");
CREATE INDEX "search_docket_docket_number_core_9278e62b_like" ON "search_docket" ("docket_number_core" varchar_pattern_ops);
CREATE INDEX "search_docket_pacer_case_id_f40edfdc" ON "search_docket" ("pacer_case_id");
CREATE INDEX "search_docket_pacer_case_id_f40edfdc_like" ON "search_docket" ("pacer_case_id" varchar_pattern_ops);
CREATE INDEX "search_docket_ia_date_first_change_0052482f" ON "search_docket" ("ia_date_first_change");
CREATE INDEX "search_docket_date_blocked_32120f9d" ON "search_docket" ("date_blocked");
CREATE INDEX "search_docket_appeal_from_id_e8bffa28" ON "search_docket" ("appeal_from_id");
CREATE INDEX "search_docket_appeal_from_id_e8bffa28_like" ON "search_docket" ("appeal_from_id" varchar_pattern_ops);
CREATE INDEX "search_docket_assigned_to_id_167c3921" ON "search_docket" ("assigned_to_id");
CREATE INDEX "search_docket_court_id_2bc55eb7" ON "search_docket" ("court_id");
CREATE INDEX "search_docket_court_id_2bc55eb7_like" ON "search_docket" ("court_id" varchar_pattern_ops);
ALTER TABLE "search_docketentry"
    ADD CONSTRAINT "search_docketentry_docket_id_1b1cfd82_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_docketentry_date_created_178219dc" ON "search_docketentry" ("date_created");
CREATE INDEX "search_docketentry_date_modified_3f6cd940" ON "search_docketentry" ("date_modified");
CREATE INDEX "search_docketentry_docket_id_1b1cfd82" ON "search_docketentry" ("docket_id");
ALTER TABLE "search_opinion"
    ADD CONSTRAINT "search_opinion_author_id_69e3caa8_fk_people_db_person_id" FOREIGN KEY ("author_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinion_date_created_76a4ddf9" ON "search_opinion" ("date_created");
CREATE INDEX "search_opinion_date_modified_524fb7ff" ON "search_opinion" ("date_modified");
CREATE INDEX "search_opinion_sha1_62196033" ON "search_opinion" ("sha1");
CREATE INDEX "search_opinion_sha1_62196033_like" ON "search_opinion" ("sha1" varchar_pattern_ops);
CREATE INDEX "search_opinion_download_url_8428ad91" ON "search_opinion" ("download_url");
CREATE INDEX "search_opinion_download_url_8428ad91_like" ON "search_opinion" ("download_url" varchar_pattern_ops);
CREATE INDEX "search_opinion_local_path_8c124953" ON "search_opinion" ("local_path");
CREATE INDEX "search_opinion_local_path_8c124953_like" ON "search_opinion" ("local_path" varchar_pattern_ops);
CREATE INDEX "search_opinion_extracted_by_ocr_122ced11" ON "search_opinion" ("extracted_by_ocr");
CREATE INDEX "search_opinion_author_id_69e3caa8" ON "search_opinion" ("author_id");
CREATE INDEX "search_tag_date_created_2f7686f6" ON "search_tag" ("date_created");
CREATE INDEX "search_tag_date_modified_7cca5217" ON "search_tag" ("date_modified");
CREATE INDEX "search_tag_name_593bfca8_like" ON "search_tag" ("name" varchar_pattern_ops);
ALTER TABLE "search_recapdocument"
    ADD CONSTRAINT "search_recapdocument_docket_entry_id_75b4ffaa_fk_search_do" FOREIGN KEY ("docket_entry_id") REFERENCES "search_docketentry" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_recapdocument_date_created_370bf4c4" ON "search_recapdocument" ("date_created");
CREATE INDEX "search_recapdocument_date_modified_1859a140" ON "search_recapdocument" ("date_modified");
CREATE INDEX "search_recapdocument_document_number_9f9ef00c" ON "search_recapdocument" ("document_number");
CREATE INDEX "search_recapdocument_document_number_9f9ef00c_like" ON "search_recapdocument" ("document_number" varchar_pattern_ops);
CREATE INDEX "search_recapdocument_is_free_on_pacer_fa7086fc" ON "search_recapdocument" ("is_free_on_pacer");
CREATE INDEX "search_recapdocument_docket_entry_id_75b4ffaa" ON "search_recapdocument" ("docket_entry_id");
ALTER TABLE "search_recapdocument_tags"
    ADD CONSTRAINT "search_recapdocument_tags_recapdocument_id_tag_id_7ede4f9a_uniq" UNIQUE ("recapdocument_id", "tag_id");
ALTER TABLE "search_recapdocument_tags"
    ADD CONSTRAINT "search_recapdocument_recapdocument_id_015bbc3b_fk_search_re" FOREIGN KEY ("recapdocument_id") REFERENCES "search_recapdocument" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_recapdocument_tags"
    ADD CONSTRAINT "search_recapdocument_tags_tag_id_979de8eb_fk_search_tag_id" FOREIGN KEY ("tag_id") REFERENCES "search_tag" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_recapdocument_tags_recapdocument_id_015bbc3b" ON "search_recapdocument_tags" ("recapdocument_id");
CREATE INDEX "search_recapdocument_tags_tag_id_979de8eb" ON "search_recapdocument_tags" ("tag_id");
ALTER TABLE "search_originatingcourtinformation"
    ADD CONSTRAINT "search_originatingco_assigned_to_id_80fa4306_fk_people_db" FOREIGN KEY ("assigned_to_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_originatingcourtinformation"
    ADD CONSTRAINT "search_originatingco_ordering_judge_id_33089265_fk_people_db" FOREIGN KEY ("ordering_judge_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_originatingcourtinformation_date_created_bba63222" ON "search_originatingcourtinformation" ("date_created");
CREATE INDEX "search_originatingcourtinformation_date_modified_dc93df7f" ON "search_originatingcourtinformation" ("date_modified");
CREATE INDEX "search_originatingcourtinformation_assigned_to_id_80fa4306" ON "search_originatingcourtinformation" ("assigned_to_id");
CREATE INDEX "search_originatingcourtinformation_ordering_judge_id_33089265" ON "search_originatingcourtinformation" ("ordering_judge_id");
ALTER TABLE "search_opinionscited"
    ADD CONSTRAINT "search_opinionscited_cited_opinion_id_7e2e0ebe_fk_search_op" FOREIGN KEY ("cited_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_opinionscited"
    ADD CONSTRAINT "search_opinionscited_citing_opinion_id_232c9279_fk_search_op" FOREIGN KEY ("citing_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinionscited_depth_46bacaef" ON "search_opinionscited" ("depth");
CREATE INDEX "search_opinionscited_cited_opinion_id_7e2e0ebe" ON "search_opinionscited" ("cited_opinion_id");
CREATE INDEX "search_opinionscited_citing_opinion_id_232c9279" ON "search_opinionscited" ("citing_opinion_id");
ALTER TABLE "search_opinioncluster"
    ADD CONSTRAINT "search_opinioncluster_docket_id_9f294661_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinioncluster_date_created_d7f23b11" ON "search_opinioncluster" ("date_created");
CREATE INDEX "search_opinioncluster_date_modified_50202208" ON "search_opinioncluster" ("date_modified");
CREATE INDEX "search_opinioncluster_date_filed_2b868d4e" ON "search_opinioncluster" ("date_filed");
CREATE INDEX "search_opinioncluster_scdb_id_b253d0c1" ON "search_opinioncluster" ("scdb_id");
CREATE INDEX "search_opinioncluster_scdb_id_b253d0c1_like" ON "search_opinioncluster" ("scdb_id" varchar_pattern_ops);
CREATE INDEX "search_opinioncluster_citation_count_1cba641a" ON "search_opinioncluster" ("citation_count");
CREATE INDEX "search_opinioncluster_precedential_status_5e76e77d" ON "search_opinioncluster" ("precedential_status");
CREATE INDEX "search_opinioncluster_precedential_status_5e76e77d_like" ON "search_opinioncluster" ("precedential_status" varchar_pattern_ops);
CREATE INDEX "search_opinioncluster_date_blocked_6b067122" ON "search_opinioncluster" ("date_blocked");
CREATE INDEX "search_opinioncluster_blocked_a24109d7" ON "search_opinioncluster" ("blocked");
CREATE INDEX "search_opinioncluster_filepath_json_harvard_4b8057d0" ON "search_opinioncluster" ("filepath_json_harvard");
CREATE INDEX "search_opinioncluster_filepath_json_harvard_4b8057d0_like" ON "search_opinioncluster" ("filepath_json_harvard" varchar_pattern_ops);
CREATE INDEX "search_opinioncluster_docket_id_9f294661" ON "search_opinioncluster" ("docket_id");
ALTER TABLE "search_opinioncluster_non_participating_judges"
    ADD CONSTRAINT "search_opinioncluster_no_opinioncluster_id_person_af3516e2_uniq" UNIQUE ("opinioncluster_id", "person_id");
ALTER TABLE "search_opinioncluster_non_participating_judges"
    ADD CONSTRAINT "search_opinioncluste_opinioncluster_id_a4aa0f49_fk_search_op" FOREIGN KEY ("opinioncluster_id") REFERENCES "search_opinioncluster" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_opinioncluster_non_participating_judges"
    ADD CONSTRAINT "search_opinioncluste_person_id_7b9957f6_fk_people_db" FOREIGN KEY ("person_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinioncluster_non__opinioncluster_id_a4aa0f49" ON "search_opinioncluster_non_participating_judges" ("opinioncluster_id");
CREATE INDEX "search_opinioncluster_non__person_id_7b9957f6" ON "search_opinioncluster_non_participating_judges" ("person_id");
ALTER TABLE "search_opinioncluster_panel"
    ADD CONSTRAINT "search_opinioncluster_pa_opinioncluster_id_person_e77a1e9d_uniq" UNIQUE ("opinioncluster_id", "person_id");
ALTER TABLE "search_opinioncluster_panel"
    ADD CONSTRAINT "search_opinioncluste_opinioncluster_id_b0a8bd25_fk_search_op" FOREIGN KEY ("opinioncluster_id") REFERENCES "search_opinioncluster" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_opinioncluster_panel"
    ADD CONSTRAINT "search_opinioncluste_person_id_3030c7a7_fk_people_db" FOREIGN KEY ("person_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinioncluster_panel_opinioncluster_id_b0a8bd25" ON "search_opinioncluster_panel" ("opinioncluster_id");
CREATE INDEX "search_opinioncluster_panel_person_id_3030c7a7" ON "search_opinioncluster_panel" ("person_id");
CREATE INDEX "search_opinion_cluster_id_09bd537a" ON "search_opinion" ("cluster_id");
ALTER TABLE "search_opinion_joined_by"
    ADD CONSTRAINT "search_opinion_joined_by_opinion_id_person_id_4ec29de1_uniq" UNIQUE ("opinion_id", "person_id");
ALTER TABLE "search_opinion_joined_by"
    ADD CONSTRAINT "search_opinion_joine_opinion_id_4c5b0f4d_fk_search_op" FOREIGN KEY ("opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_opinion_joined_by"
    ADD CONSTRAINT "search_opinion_joine_person_id_0a318600_fk_people_db" FOREIGN KEY ("person_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinion_joined_by_opinion_id_4c5b0f4d" ON "search_opinion_joined_by" ("opinion_id");
CREATE INDEX "search_opinion_joined_by_person_id_0a318600" ON "search_opinion_joined_by" ("person_id");
ALTER TABLE "search_docketentry_tags"
    ADD CONSTRAINT "search_docketentry_tags_docketentry_id_tag_id_20f48773_uniq" UNIQUE ("docketentry_id", "tag_id");
ALTER TABLE "search_docketentry_tags"
    ADD CONSTRAINT "search_docketentry_t_docketentry_id_1c1ec392_fk_search_do" FOREIGN KEY ("docketentry_id") REFERENCES "search_docketentry" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docketentry_tags"
    ADD CONSTRAINT "search_docketentry_tags_tag_id_6e1780db_fk_search_tag_id" FOREIGN KEY ("tag_id") REFERENCES "search_tag" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_docketentry_tags_docketentry_id_1c1ec392" ON "search_docketentry_tags" ("docketentry_id");
CREATE INDEX "search_docketentry_tags_tag_id_6e1780db" ON "search_docketentry_tags" ("tag_id");
ALTER TABLE "search_docket_panel"
    ADD CONSTRAINT "search_docket_panel_docket_id_person_id_90a9d8a2_uniq" UNIQUE ("docket_id", "person_id");
ALTER TABLE "search_docket_panel"
    ADD CONSTRAINT "search_docket_panel_docket_id_d3e42a51_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docket_panel"
    ADD CONSTRAINT "search_docket_panel_person_id_866a42fc_fk_people_db_person_id" FOREIGN KEY ("person_id") REFERENCES "people_db_person" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_docket_panel_docket_id_d3e42a51" ON "search_docket_panel" ("docket_id");
CREATE INDEX "search_docket_panel_person_id_866a42fc" ON "search_docket_panel" ("person_id");
CREATE INDEX "search_docket_referred_to_id_cf6332e0" ON "search_docket" ("referred_to_id");
ALTER TABLE "search_docket_tags"
    ADD CONSTRAINT "search_docket_tags_docket_id_tag_id_8675bd10_uniq" UNIQUE ("docket_id", "tag_id");
ALTER TABLE "search_docket_tags"
    ADD CONSTRAINT "search_docket_tags_docket_id_38bcf847_fk_search_docket_id" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_docket_tags"
    ADD CONSTRAINT "search_docket_tags_tag_id_751c8e09_fk_search_tag_id" FOREIGN KEY ("tag_id") REFERENCES "search_tag" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_docket_tags_docket_id_38bcf847" ON "search_docket_tags" ("docket_id");
CREATE INDEX "search_docket_tags_tag_id_751c8e09" ON "search_docket_tags" ("tag_id");
ALTER TABLE "search_claimhistory"
    ADD CONSTRAINT "search_claimhistory_claim_id_e130e572_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_claimhistory_date_created_586d545e" ON "search_claimhistory" ("date_created");
CREATE INDEX "search_claimhistory_date_modified_5f6ec339" ON "search_claimhistory" ("date_modified");
CREATE INDEX "search_claimhistory_document_number_6316c155" ON "search_claimhistory" ("document_number");
CREATE INDEX "search_claimhistory_document_number_6316c155_like" ON "search_claimhistory" ("document_number" varchar_pattern_ops);
CREATE INDEX "search_claimhistory_is_free_on_pacer_81332a2c" ON "search_claimhistory" ("is_free_on_pacer");
CREATE INDEX "search_claimhistory_claim_id_e130e572" ON "search_claimhistory" ("claim_id");
CREATE INDEX "search_claim_docket_id_b37171a9" ON "search_claim" ("docket_id");
ALTER TABLE "search_claim_tags"
    ADD CONSTRAINT "search_claim_tags_claim_id_tag_id_2f236693_uniq" UNIQUE ("claim_id", "tag_id");
ALTER TABLE "search_claim_tags"
    ADD CONSTRAINT "search_claim_tags_claim_id_2cf554b5_fk_search_claim_id" FOREIGN KEY ("claim_id") REFERENCES "search_claim" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_claim_tags"
    ADD CONSTRAINT "search_claim_tags_tag_id_73b6bd4d_fk_search_tag_id" FOREIGN KEY ("tag_id") REFERENCES "search_tag" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_claim_tags_claim_id_2cf554b5" ON "search_claim_tags" ("claim_id");
CREATE INDEX "search_claim_tags_tag_id_73b6bd4d" ON "search_claim_tags" ("tag_id");
ALTER TABLE "search_citation"
    ADD CONSTRAINT "search_citation_cluster_id_a075f179_fk_search_opinioncluster_id" FOREIGN KEY ("cluster_id") REFERENCES "search_opinioncluster" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_citation_reporter_792f5533" ON "search_citation" ("reporter");
CREATE INDEX "search_citation_reporter_792f5533_like" ON "search_citation" ("reporter" text_pattern_ops);
CREATE INDEX "search_citation_cluster_id_a075f179" ON "search_citation" ("cluster_id");
ALTER TABLE "search_bankruptcyinformation"
    ADD CONSTRAINT "search_bankruptcyinf_docket_id_91fa3275_fk_search_do" FOREIGN KEY ("docket_id") REFERENCES "search_docket" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_bankruptcyinformation_date_created_60f180b0" ON "search_bankruptcyinformation" ("date_created");
CREATE INDEX "search_bankruptcyinformation_date_modified_c1b76dd9" ON "search_bankruptcyinformation" ("date_modified");
COMMIT;
