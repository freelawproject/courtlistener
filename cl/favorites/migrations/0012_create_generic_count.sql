BEGIN;
--
-- Create model GenericCount
--
CREATE TABLE "favorites_genericcount" ("label" varchar(255) NOT NULL PRIMARY KEY, "value" bigint NOT NULL);
CREATE INDEX "favorites_genericcount_label_3fc2756b_like" ON "favorites_genericcount" ("label" varchar_pattern_ops);
COMMIT;
