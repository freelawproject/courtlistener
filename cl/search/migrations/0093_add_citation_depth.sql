--
-- Add field depth to opinionscited
--

-- Create the column without a default value
ALTER TABLE "search_opinionscited" ADD COLUMN "depth" integer;

-- Set the value to the default
UPDATE "search_opinionscited" set "depth" = 1;

-- Make it not nullable (this is safe because our Python code will be always setting the value to the default
ALTER TABLE "search_opinionscited" ALTER COLUMN "depth" SET NOT NULL;

-- Add the index, but do it concurrently. Note that concurrent ones can't be in a transaction.
CREATE INDEX CONCURRENTLY "search_opinionscited_depth_46bacaef" ON "search_opinionscited" ("depth");
