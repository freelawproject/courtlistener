BEGIN;
--
-- Alter field date_created on bankruptcyinformation
--
ALTER TABLE "search_bankruptcyinformation" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:07.956785+00:00'::timestamptz;
ALTER TABLE "search_bankruptcyinformation" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on bankruptcyinformation
--
ALTER TABLE "search_bankruptcyinformation" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:07.993726+00:00'::timestamptz;
ALTER TABLE "search_bankruptcyinformation" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on claim
--
ALTER TABLE "search_claim" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.032587+00:00'::timestamptz;
ALTER TABLE "search_claim" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on claim
--
ALTER TABLE "search_claim" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:08.068089+00:00'::timestamptz;
ALTER TABLE "search_claim" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on claimhistory
--
ALTER TABLE "search_claimhistory" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.083260+00:00'::timestamptz;
ALTER TABLE "search_claimhistory" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on claimhistory
--
ALTER TABLE "search_claimhistory" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:08.099977+00:00'::timestamptz;
ALTER TABLE "search_claimhistory" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on docket
--
ALTER TABLE "search_docket" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.141440+00:00'::timestamptz;
ALTER TABLE "search_docket" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_created on docketentry
--
ALTER TABLE "search_docketentry" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.179710+00:00'::timestamptz;
ALTER TABLE "search_docketentry" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on docketentry
--
ALTER TABLE "search_docketentry" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:08.214727+00:00'::timestamptz;
ALTER TABLE "search_docketentry" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on opinion
--
ALTER TABLE "search_opinion" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.248067+00:00'::timestamptz;
ALTER TABLE "search_opinion" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_created on opinioncluster
--
ALTER TABLE "search_opinioncluster" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.279495+00:00'::timestamptz;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_created on originatingcourtinformation
--
ALTER TABLE "search_originatingcourtinformation" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.306086+00:00'::timestamptz;
ALTER TABLE "search_originatingcourtinformation" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on originatingcourtinformation
--
ALTER TABLE "search_originatingcourtinformation" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:08.331585+00:00'::timestamptz;
ALTER TABLE "search_originatingcourtinformation" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on recapdocument
--
ALTER TABLE "search_recapdocument" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.349511+00:00'::timestamptz;
ALTER TABLE "search_recapdocument" ALTER COLUMN "date_created" DROP DEFAULT;
--
-- Alter field date_modified on recapdocument
--
ALTER TABLE "search_recapdocument" ALTER COLUMN "date_modified" SET DEFAULT '2020-12-23T15:08:08.368904+00:00'::timestamptz;
ALTER TABLE "search_recapdocument" ALTER COLUMN "date_modified" DROP DEFAULT;
--
-- Alter field date_created on tag
--
ALTER TABLE "search_tag" ALTER COLUMN "date_created" SET DEFAULT '2020-12-23T15:08:08.384568+00:00'::timestamptz;
ALTER TABLE "search_tag" ALTER COLUMN "date_created" DROP DEFAULT;
COMMIT;
