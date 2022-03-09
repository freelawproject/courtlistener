BEGIN;
--
-- Create model ParentheticalGroup
--
CREATE TABLE "search_parentheticalgroup" ("id" serial NOT NULL PRIMARY KEY, "score" double precision NOT NULL, "size" integer NOT NULL, "opinion_id" integer NOT NULL, "representative_id" integer NOT NULL);
--
-- Add field group to parenthetical
--
ALTER TABLE "search_parenthetical" ADD COLUMN "group_id" integer NULL CONSTRAINT "search_parenthetical_group_id_00a7def3_fk_search_pa" REFERENCES "search_parentheticalgroup"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_parenthetical_group_id_00a7def3_fk_search_pa" IMMEDIATE;
--
-- Create index search_pare_score_16f118_idx on field(s) score of model parentheticalgroup
--
CREATE INDEX "search_pare_score_16f118_idx" ON "search_parentheticalgroup" ("score");
ALTER TABLE "search_parentheticalgroup" ADD CONSTRAINT "search_parenthetical_opinion_id_fd6bb935_fk_search_op" FOREIGN KEY ("opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_parentheticalgroup" ADD CONSTRAINT "search_parenthetical_representative_id_00e5a857_fk_search_pa" FOREIGN KEY ("representative_id") REFERENCES "search_parenthetical" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_parentheticalgroup_opinion_id_fd6bb935" ON "search_parentheticalgroup" ("opinion_id");
CREATE INDEX "search_parentheticalgroup_representative_id_00e5a857" ON "search_parentheticalgroup" ("representative_id");
CREATE INDEX "search_parenthetical_group_id_00a7def3" ON "search_parenthetical" ("group_id");
COMMIT;
