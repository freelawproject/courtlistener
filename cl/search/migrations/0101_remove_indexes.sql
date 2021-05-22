--
-- Alter field filepath_local on claimhistory
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_claimhistory_filepath_local_c52db4fc";
DROP INDEX CONCURRENTLY IF EXISTS "search_claimhistory_filepath_local_c52db4fc_like";
--
-- Alter field is_sealed on claimhistory
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_claimhistory_is_sealed_80556d76";
--
-- Alter field blocked on docket
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_61326117";
--
-- Alter field ia_needs_upload on docket
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_docket_f9b591e1";
--
-- Alter field pacer_sequence_number on docketentry
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_docketentry_eb19fcf7";
--
-- Alter field recap_sequence_number on docketentry
--
-- Fixed (2x)
DROP INDEX CONCURRENTLY IF EXISTS "search_docketentry_bff4d47b";
DROP INDEX CONCURRENTLY IF EXISTS "search_docketentry_recap_sequence_number_d700f0391e8213a_like";
--
-- Alter field document_type on recapdocument
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_recapdocument_86559dba";
--
-- Alter field filepath_local on recapdocument
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_recapdocument_filepath_local_7dc6b0e53ccf753_like";
--
-- Alter field is_sealed on recapdocument
--
-- Fixed
DROP INDEX CONCURRENTLY IF EXISTS "search_recapdocument_b4e48d82";
