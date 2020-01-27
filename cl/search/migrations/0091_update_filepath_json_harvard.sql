
CREATE INDEX CONCURRENTLY "search_opinioncluster_filepath_json_harvard_4b8057d0" ON "search_opinioncluster" ("filepath_json_harvard");
CREATE INDEX CONCURRENTLY "search_opinioncluster_filepath_json_harvard_4b8057d0_like" ON "search_opinioncluster" ("filepath_json_harvard" varchar_pattern_ops);
