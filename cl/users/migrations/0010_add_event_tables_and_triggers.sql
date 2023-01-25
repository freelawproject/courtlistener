BEGIN;
--
-- Create model UserProfileBarMembershipEvent
--
CREATE TABLE "users_userprofilebarmembershipevent"
(
    "pgh_id"         serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at" timestamp with time zone NOT NULL,
    "pgh_label"      text                     NOT NULL,
    "id"             integer                  NOT NULL
);
--
-- Create model UserProfileEvent
--
CREATE TABLE "users_userprofileevent"
(
    "pgh_id"                  serial                   NOT NULL PRIMARY KEY,
    "pgh_created_at"          timestamp with time zone NOT NULL,
    "pgh_label"               text                     NOT NULL,
    "id"                      integer                  NOT NULL,
    "stub_account"            boolean                  NOT NULL,
    "employer"                varchar(100)             NULL,
    "address1"                varchar(100)             NULL,
    "address2"                varchar(100)             NULL,
    "city"                    varchar(50)              NULL,
    "state"                   varchar(2)               NULL,
    "zip_code"                varchar(10)              NULL,
    "avatar"                  varchar(100)             NOT NULL,
    "wants_newsletter"        boolean                  NOT NULL,
    "unlimited_docket_alerts" boolean                  NOT NULL,
    "plaintext_preferred"     boolean                  NOT NULL,
    "activation_key"          varchar(40)              NOT NULL,
    "key_expires"             timestamp with time zone NULL,
    "email_confirmed"         boolean                  NOT NULL,
    "notes"                   text                     NOT NULL,
    "is_tester"               boolean                  NOT NULL,
    "recap_email"             varchar(254)             NOT NULL,
    "auto_subscribe"          boolean                  NOT NULL
);
--
-- Create proxy model UserProfileBarMembership
--
--
-- Create trigger snapshot_insert on model userprofile
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_31610()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2",
                                          "auto_subscribe", "avatar", "city",
                                          "email_confirmed", "employer", "id",
                                          "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "plaintext_preferred", "recap_email", "state",
                                          "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe",
            NEW."avatar", NEW."city", NEW."email_confirmed", NEW."employer", NEW."id",
            NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email",
            NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts",
            NEW."user_id", NEW."wants_newsletter", NEW."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_31610 ON "users_userprofile";
CREATE TRIGGER pgtrigger_snapshot_insert_31610
    AFTER INSERT
    ON "users_userprofile"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_31610();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_31610 ON "users_userprofile" IS 'aa341719534a80b6c9f390387615a65236106919';
;
--
-- Create trigger snapshot_update on model userprofile
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_74231()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "users_userprofileevent" ("activation_key", "address1", "address2",
                                          "auto_subscribe", "avatar", "city",
                                          "email_confirmed", "employer", "id",
                                          "is_tester", "key_expires", "notes",
                                          "pgh_context_id", "pgh_created_at",
                                          "pgh_label", "pgh_obj_id",
                                          "plaintext_preferred", "recap_email", "state",
                                          "stub_account", "unlimited_docket_alerts",
                                          "user_id", "wants_newsletter", "zip_code")
    VALUES (NEW."activation_key", NEW."address1", NEW."address2", NEW."auto_subscribe",
            NEW."avatar", NEW."city", NEW."email_confirmed", NEW."employer", NEW."id",
            NEW."is_tester", NEW."key_expires", NEW."notes", _pgh_attach_context(),
            NOW(), 'snapshot', NEW."id", NEW."plaintext_preferred", NEW."recap_email",
            NEW."state", NEW."stub_account", NEW."unlimited_docket_alerts",
            NEW."user_id", NEW."wants_newsletter", NEW."zip_code");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_74231 ON "users_userprofile";
CREATE TRIGGER pgtrigger_snapshot_update_74231
    AFTER UPDATE
    ON "users_userprofile"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_74231();

COMMENT ON TRIGGER pgtrigger_snapshot_update_74231 ON "users_userprofile" IS '5a100c4fbaec17c304654aaeca224fdd740ead43';
;
--
-- Add field pgh_context to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field pgh_obj to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "pgh_obj_id" integer NOT NULL;
--
-- Add field user to userprofileevent
--
ALTER TABLE "users_userprofileevent"
    ADD COLUMN "user_id" integer NOT NULL;
--
-- Add field barmembership to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "barmembership_id" integer NOT NULL;
--
-- Add field pgh_context to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "pgh_context_id" uuid NULL;
--
-- Add field userprofile to userprofilebarmembershipevent
--
ALTER TABLE "users_userprofilebarmembershipevent"
    ADD COLUMN "userprofile_id" integer NOT NULL;
--
-- Create trigger snapshot_insert on model userprofilebarmembership
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_insert_de1c8()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (NEW."barmembership_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_insert_de1c8 ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_snapshot_insert_de1c8
    AFTER INSERT
    ON "users_userprofile_barmembership"


    FOR EACH ROW
EXECUTE PROCEDURE pgtrigger_snapshot_insert_de1c8();

COMMENT ON TRIGGER pgtrigger_snapshot_insert_de1c8 ON "users_userprofile_barmembership" IS '2af83be1b83550629a688c44113e1c0430d8ef8e';
;
--
-- Create trigger snapshot_update on model userprofilebarmembership
--

CREATE OR REPLACE FUNCTION "public"._pgtrigger_should_ignore(
    trigger_name NAME
)
    RETURNS BOOLEAN AS
$$
DECLARE
    _pgtrigger_ignore TEXT[];
    _result           BOOLEAN;
BEGIN
    BEGIN
        SELECT INTO _pgtrigger_ignore CURRENT_SETTING('pgtrigger.ignore');
    EXCEPTION
        WHEN OTHERS THEN
    END;
    IF _pgtrigger_ignore IS NOT NULL THEN
        SELECT trigger_name = ANY (_pgtrigger_ignore)
        INTO _result;
        RETURN _result;
    ELSE
        RETURN FALSE;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pgtrigger_snapshot_update_cb3f2()
    RETURNS TRIGGER AS
$$

BEGIN
    IF ("public"._pgtrigger_should_ignore(TG_NAME) IS TRUE) THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    INSERT INTO "users_userprofilebarmembershipevent" ("barmembership_id", "id",
                                                       "pgh_context_id",
                                                       "pgh_created_at", "pgh_label",
                                                       "userprofile_id")
    VALUES (NEW."barmembership_id", NEW."id", _pgh_attach_context(), NOW(), 'snapshot',
            NEW."userprofile_id");
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pgtrigger_snapshot_update_cb3f2 ON "users_userprofile_barmembership";
CREATE TRIGGER pgtrigger_snapshot_update_cb3f2
    AFTER UPDATE
    ON "users_userprofile_barmembership"


    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE PROCEDURE pgtrigger_snapshot_update_cb3f2();

COMMENT ON TRIGGER pgtrigger_snapshot_update_cb3f2 ON "users_userprofile_barmembership" IS 'dfa53db455704cc58ca39636c262a174fe876878';
;
CREATE INDEX "users_userprofileevent_pgh_context_id_b240d6a7" ON "users_userprofileevent" ("pgh_context_id");
CREATE INDEX "users_userprofileevent_pgh_obj_id_d6261087" ON "users_userprofileevent" ("pgh_obj_id");
CREATE INDEX "users_userprofileevent_user_id_52cc3748" ON "users_userprofileevent" ("user_id");
CREATE INDEX "users_userprofilebarmembershipevent_barmembership_id_90427e0c" ON "users_userprofilebarmembershipevent" ("barmembership_id");
CREATE INDEX "users_userprofilebarmembershipevent_pgh_context_id_fee0358d" ON "users_userprofilebarmembershipevent" ("pgh_context_id");
CREATE INDEX "users_userprofilebarmembershipevent_userprofile_id_b75055e4" ON "users_userprofilebarmembershipevent" ("userprofile_id");
COMMIT;
