-- Generated with sqlmigrate for pghistory migrations 0001-0005
--
-- These were missed when adding this feature, so I'm adding them here.
-- They've been applied manually.
--

--
-- pghistory 0001
--
BEGIN;
--
-- Create model Context
--
CREATE TABLE "pghistory_context"
(
    "id"         uuid                     NOT NULL PRIMARY KEY,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "metadata"   jsonb                    NOT NULL
);
COMMIT;


--
-- pghistory 0002 (noop)
--
BEGIN;
--
-- Create model AggregateEvent
--
COMMIT;


--
-- pghistory 0003 (noop)
--
BEGIN;
--
-- Alter field metadata on context
--
COMMIT;


--
-- pghistory 0004
--
BEGIN;
--
-- MIGRATION NOW PERFORMS OPERATION THAT CANNOT BE WRITTEN AS SQL:
-- Raw Python operation
--
COMMIT;


--
-- pghistory 0005
--
BEGIN;
--
-- Create model Events
--
--
-- Create proxy model MiddlewareEvents
--
COMMIT;
