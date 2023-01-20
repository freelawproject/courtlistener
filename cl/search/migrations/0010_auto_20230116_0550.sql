BEGIN;
--
-- Create model OpinionsCitedByRECAPDocument
--
CREATE TABLE "search_opinionscitedbyrecapdocument" ("id" serial NOT NULL PRIMARY KEY, "depth" integer NOT NULL, "cited_opinion_id" integer NOT NULL, "citing_document_id" integer NOT NULL);
--
-- Create index search_opin_depth_3307bd_idx on field(s) depth of model opinionscitedbyrecapdocument
--
CREATE INDEX "search_opin_depth_3307bd_idx" ON "search_opinionscitedbyrecapdocument" ("depth");
--
-- Alter unique_together for opinionscitedbyrecapdocument (1 constraint(s))
--
ALTER TABLE "search_opinionscitedbyrecapdocument" ADD CONSTRAINT "search_opinionscitedbyre_citing_document_id_cited_0c621cfd_uniq" UNIQUE ("citing_document_id", "cited_opinion_id");
ALTER TABLE "search_opinionscitedbyrecapdocument" ADD CONSTRAINT "search_opinionscited_cited_opinion_id_5f0347bb_fk_search_op" FOREIGN KEY ("cited_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_opinionscitedbyrecapdocument" ADD CONSTRAINT "search_opinionscited_citing_document_id_c64b751b_fk_search_re" FOREIGN KEY ("citing_document_id") REFERENCES "search_recapdocument" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_opinionscitedbyrecapdocument_cited_opinion_id_5f0347bb" ON "search_opinionscitedbyrecapdocument" ("cited_opinion_id");
CREATE INDEX "search_opinionscitedbyrecapdocument_citing_document_id_c64b751b" ON "search_opinionscitedbyrecapdocument" ("citing_document_id");
COMMIT;