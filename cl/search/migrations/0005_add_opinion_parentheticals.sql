BEGIN;
--
-- Create model Parenthetical
--
CREATE TABLE "search_parenthetical" ("id" serial NOT NULL PRIMARY KEY, "text" text NOT NULL, "score" double precision NOT NULL, "described_opinion_id" integer NOT NULL, "describing_opinion_id" integer NOT NULL);
ALTER TABLE "search_parenthetical" ADD CONSTRAINT "search_parenthetical_described_opinion_id_ddd408db_fk_search_op" FOREIGN KEY ("described_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "search_parenthetical" ADD CONSTRAINT "search_parenthetical_describing_opinion_i_07864494_fk_search_op" FOREIGN KEY ("describing_opinion_id") REFERENCES "search_opinion" ("id") DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "search_parenthetical_score_cab0b2a1" ON "search_parenthetical" ("score");
CREATE INDEX "search_parenthetical_described_opinion_id_ddd408db" ON "search_parenthetical" ("described_opinion_id");
CREATE INDEX "search_parenthetical_describing_opinion_id_07864494" ON "search_parenthetical" ("describing_opinion_id");
COMMIT;
