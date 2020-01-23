BEGIN;
--
-- Remove field federal_cite_one from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "federal_cite_one" CASCADE;
--
-- Remove field federal_cite_three from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "federal_cite_three" CASCADE;
--
-- Remove field federal_cite_two from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "federal_cite_two" CASCADE;
--
-- Remove field lexis_cite from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "lexis_cite" CASCADE;
--
-- Remove field neutral_cite from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "neutral_cite" CASCADE;
--
-- Remove field scotus_early_cite from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "scotus_early_cite" CASCADE;
--
-- Remove field specialty_cite_one from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "specialty_cite_one" CASCADE;
--
-- Remove field state_cite_one from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "state_cite_one" CASCADE;
--
-- Remove field state_cite_regional from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "state_cite_regional" CASCADE;
--
-- Remove field state_cite_three from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "state_cite_three" CASCADE;
--
-- Remove field state_cite_two from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "state_cite_two" CASCADE;
--
-- Remove field westlaw_cite from opinioncluster
--
ALTER TABLE "search_opinioncluster" DROP COLUMN "westlaw_cite" CASCADE;
COMMIT;
