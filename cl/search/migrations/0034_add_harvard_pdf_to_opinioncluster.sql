BEGIN;
ALTER TABLE "search_opinioncluster" ADD COLUMN "filepath_pdf_harvard" varchar(100) DEFAULT '' NOT NULL;
ALTER TABLE "search_opinioncluster" ALTER COLUMN "filepath_pdf_harvard" DROP DEFAULT;
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "filepath_pdf_harvard" varchar(100) DEFAULT '' NOT NULL;
ALTER TABLE "search_opinionclusterevent" ALTER COLUMN "filepath_pdf_harvard" DROP DEFAULT;
COMMIT;