BEGIN;
--
-- Create table StateCourtDocument
--
CREATE TABLE "search_statecourtdocument" (
    "id" BIGSERIAL PRIMARY KEY,
    "document_number" varchar(32),
    "document_type" integer NOT NULL,
    "description" text,
    "source" varchar(64) NOT NULL DEFAULT 'acis',
    "source_url" text,
    "is_available" boolean DEFAULT false,
    "is_sealed" boolean,
    "docket_entry_id" bigint NOT NULL REFERENCES "dockets_docketentry" ("id") ON DELETE CASCADE,
    "date_created" timestamptz NOT NULL DEFAULT now(),
    "date_modified" timestamptz NOT NULL DEFAULT now()
);
--
-- Add indexes to StateCourtDocument
--
CREATE INDEX "search_statecourtdocument_document_number_idx" ON "search_statecourtdocument" ("document_number");
CREATE INDEX "search_statecourtdocument_document_type_idx" ON "search_statecourtdocument" ("document_type", "document_number", "source_url");
CREATE INDEX "search_statecourtdocument_filepath_local_idx" ON "search_statecourtdocument" ("filepath_local");
CREATE INDEX "search_statecourtdocument_source_url_idx" ON "search_statecourtdocument" ("source", "source_url");
--
-- Add unique constraint
--
ALTER TABLE "search_statecourtdocument" ADD CONSTRAINT "search_statecourtdocument_unique_entry" UNIQUE ("docket_entry_id", "document_number", "source_url");
--
-- Create table OpinionsCitedByStateCourtDocument
--
CREATE TABLE "search_opinionscitedbystatecourtdocument" (
    "id" BIGSERIAL PRIMARY KEY,
    "citing_document_id" bigint NOT NULL REFERENCES "search_statecourtdocument" ("id") ON DELETE CASCADE,
    "cited_opinion_id" bigint NOT NULL REFERENCES "opinions_opinion" ("id") ON DELETE CASCADE,
    "depth" integer NOT NULL DEFAULT 1,
    "date_created" timestamptz NOT NULL DEFAULT now(),
    "date_modified" timestamptz NOT NULL DEFAULT now()
);
--
-- Add unique constraint
--
ALTER TABLE "search_opinionscitedbystatecourtdocument" ADD CONSTRAINT "search_opinionscited_unique_pair" UNIQUE ("citing_document_id", "cited_opinion_id");
--
-- Add index on depth
--
CREATE INDEX "search_opinionscited_depth_idx" ON "search_opinionscitedbystatecourtdocument" ("depth");
--
-- Create table CaseIdentifier
--
CREATE TABLE "search_caseidentifier" (
    "id" BIGSERIAL PRIMARY KEY,
    "docket_id" bigint NOT NULL REFERENCES "dockets_docket" ("id") ON DELETE CASCADE,
    "id_type" varchar(64) NOT NULL,
    "identifier" varchar(128) NOT NULL,
    "note" varchar(255),
    "first_seen" timestamptz NOT NULL DEFAULT now()
);
--
-- Add unique constraint
--
ALTER TABLE "search_caseidentifier" ADD CONSTRAINT "search_caseidentifier_idtype_identifier_uniq" UNIQUE ("id_type", "identifier");
--
-- Add index on id_type + identifier
--
CREATE INDEX "search_caseidentifier_idtype_identifier_idx" ON "search_caseidentifier" ("id_type", "identifier");

COMMIT;
