BEGIN;
--
-- Rename unnamed index for ('recap_document', 'status') on prayer to favorites_p_recap_d_00e8c5_idx
--
ALTER INDEX "favorites_prayer_recap_document_id_status_82e2dbbb_idx" RENAME TO "favorites_p_recap_d_00e8c5_idx";
--
-- Rename unnamed index for ('date_created', 'user', 'status') on prayer to favorites_p_date_cr_8bf054_idx
--
ALTER INDEX "favorites_prayer_date_created_user_id_status_880d7280_idx" RENAME TO "favorites_p_date_cr_8bf054_idx";
--
-- Rename unnamed index for ('recap_document', 'user') on prayer to favorites_p_recap_d_7c046c_idx
--
ALTER INDEX "favorites_prayer_recap_document_id_user_id_c5d30108_idx" RENAME TO "favorites_p_recap_d_7c046c_idx";
--
-- Rename unnamed index for ('user', 'name') on usertag to favorites_u_user_id_f6c9a6_idx
--
ALTER INDEX "favorites_usertag_user_id_name_54aef6fe_idx" RENAME TO "favorites_u_user_id_f6c9a6_idx";
COMMIT;
