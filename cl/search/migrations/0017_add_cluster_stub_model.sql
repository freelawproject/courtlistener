BEGIN;
--
-- Create model ClusterStub
--
CREATE TABLE "search_clusterstub" ("id" serial NOT NULL PRIMARY KEY, "date_created" timestamp with time zone NOT NULL, "date_modified" timestamp with time zone NOT NULL, "case_name" text NOT NULL, "case_name_full" text NOT NULL, "date_filed" date NULL, "date_decided" date NULL, "date_argued" date NULL, "date_revised" date NULL, "court_str" text NOT NULL, "docket_number" text NOT NULL, "raw_citations" text NOT NULL, "citations" jsonb NULL);
--
-- Remove trigger update_or_delete_snapshot_update from model citation
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_8f120 ON "search_citation";
--
-- Remove trigger update_or_delete_snapshot_delete from model citation
--
DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_9631d ON "search_citation";
--
-- Alter field cluster on citation
--
SET CONSTRAINTS "search_citation_cluster_id_a075f179_fk_search_opinioncluster_id" IMMEDIATE; ALTER TABLE "search_citation" DROP CONSTRAINT "search_citation_cluster_id_a075f179_fk_search_opinioncluster_id";
ALTER TABLE "search_citation" ALTER COLUMN "cluster_id" DROP NOT NULL;
ALTER TABLE "search_citation" ADD CONSTRAINT "search_citation_cluster_id_a075f179_fk_search_opinioncluster_id" FOREIGN KEY ("cluster_id") REFERENCES "search_opinioncluster" ("id") DEFERRABLE INITIALLY DEFERRED;
--
-- Alter field cluster on citationevent
--
ALTER TABLE "search_citationevent" ALTER COLUMN "cluster_id" DROP NOT NULL;
--
-- Create trigger update_or_delete_snapshot_update on model citation
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_update_8f120()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_citationevent" ("cluster_id", "cluster_stub_id", "id", "page", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reporter", "type", "volume") VALUES (OLD."cluster_id", OLD."cluster_stub_id", OLD."id", OLD."page", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."reporter", OLD."type", OLD."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_update_8f120 ON "search_citation";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_update_8f120
                AFTER UPDATE ON "search_citation"
                
                
                FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*)
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_update_8f120();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_update_8f120 ON "search_citation" IS 'a81041881c0deae3a0212fad2676c613d2e164fc';
        ;
--
-- Create trigger update_or_delete_snapshot_delete on model citation
--

            CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
                trigger_name NAME
            )
            RETURNS BOOLEAN AS $$
                DECLARE
                    _pgtrigger_ignore TEXT[];
                    _result BOOLEAN;
                BEGIN
                    BEGIN
                        SELECT INTO _pgtrigger_ignore
                            CURRENT_SETTING('pgtrigger.ignore');
                        EXCEPTION WHEN OTHERS THEN
                    END;
                    IF _pgtrigger_ignore IS NOT NULL THEN
                        SELECT trigger_name = ANY(_pgtrigger_ignore)
                        INTO _result;
                        RETURN _result;
                    ELSE
                        RETURN FALSE;
                    END IF;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE FUNCTION pgtrigger_update_or_delete_snapshot_delete_9631d()
            RETURNS TRIGGER AS $$
                
                BEGIN
                    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
                        IF (TG_OP = 'DELETE') THEN
                            RETURN OLD;
                        ELSE
                            RETURN NEW;
                        END IF;
                    END IF;
                    INSERT INTO "search_citationevent" ("cluster_id", "cluster_stub_id", "id", "page", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "reporter", "type", "volume") VALUES (OLD."cluster_id", OLD."cluster_stub_id", OLD."id", OLD."page", _pgh_attach_context(), NOW(), 'update_or_delete_snapshot', OLD."id", OLD."reporter", OLD."type", OLD."volume"); RETURN NULL;
                END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS pgtrigger_update_or_delete_snapshot_delete_9631d ON "search_citation";
            CREATE  TRIGGER pgtrigger_update_or_delete_snapshot_delete_9631d
                AFTER DELETE ON "search_citation"
                
                
                FOR EACH ROW 
                EXECUTE PROCEDURE pgtrigger_update_or_delete_snapshot_delete_9631d();

            COMMENT ON TRIGGER pgtrigger_update_or_delete_snapshot_delete_9631d ON "search_citation" IS '2f3ba1f8757d6bdfca6d9f54cd5c630ebc7d085d';
        ;
--
-- Add field court to clusterstub
--
ALTER TABLE "search_clusterstub" ADD COLUMN "court_id" varchar(15) NULL CONSTRAINT "search_clusterstub_court_id_46f62d96_fk_search_court_id" REFERENCES "search_court"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_clusterstub_court_id_46f62d96_fk_search_court_id" IMMEDIATE;
--
-- Add field cluster_stub to citation
--
ALTER TABLE "search_citation" ADD COLUMN "cluster_stub_id" integer NULL CONSTRAINT "search_citation_cluster_stub_id_166ec87c_fk_search_cl" REFERENCES "search_clusterstub"("id") DEFERRABLE INITIALLY DEFERRED; SET CONSTRAINTS "search_citation_cluster_stub_id_166ec87c_fk_search_cl" IMMEDIATE;
--
-- Add field cluster_stub to citationevent
--
ALTER TABLE "search_citationevent" ADD COLUMN "cluster_stub_id" integer NULL;
--
-- Alter unique_together for citation (2 constraint(s))
--
ALTER TABLE "search_citation" ADD CONSTRAINT "search_citation_cluster_stub_id_volume_r_d198435f_uniq" UNIQUE ("cluster_stub_id", "volume", "reporter", "page");
--
-- Create constraint not_both_null on model citation
--
ALTER TABLE "search_citation" ADD CONSTRAINT "not_both_null" CHECK (("cluster_id" IS NOT NULL OR "cluster_stub_id" IS NOT NULL));
CREATE INDEX "search_clusterstub_date_created_1f0e6740" ON "search_clusterstub" ("date_created");
CREATE INDEX "search_clusterstub_date_modified_847adf7d" ON "search_clusterstub" ("date_modified");
CREATE INDEX "search_clusterstub_court_id_46f62d96" ON "search_clusterstub" ("court_id");
CREATE INDEX "search_clusterstub_court_id_46f62d96_like" ON "search_clusterstub" ("court_id" varchar_pattern_ops);
CREATE INDEX "search_citation_cluster_stub_id_166ec87c" ON "search_citation" ("cluster_stub_id");
CREATE INDEX "search_citationevent_cluster_stub_id_ec6ea60b" ON "search_citationevent" ("cluster_stub_id");
COMMIT;
