BEGIN;
ALTER TABLE "search_opinioncluster" ADD COLUMN "filepath_pdf_harvard" varchar(100) NULL;
ALTER TABLE "search_opinionclusterevent" ADD COLUMN "filepath_pdf_harvard" varchar(100) NULL;
COMMIT;