#!/bin/bash
set -e

echo "Installing utilities"

# Make sure the sudo package is installed
apt install -y sudo

# Set up Sentry
curl -sL https://sentry.io/get-cli/ | bash
eval "$(sentry-cli bash-hook)"

# Set up AWS tools and gnupg (needed for apt-key add, below)
apt install -y awscli gnupg

# Install latest version of pg_dump (else we get an error about version mismatch
echo "deb http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list
curl --silent 'https://www.postgresql.org/media/keys/ACCC4CF8.asc' |  apt-key add -
apt-get update
apt-get install -y postgresql-client

# We only need to set PGPASSWORD once
export PGPASSWORD=$DB_PASSWORD

# search_court
court_fields='(
	       id, pacer_court_id, pacer_has_rss_feed, pacer_rss_entry_types, date_last_pacer_contact,
	       fjc_court_id, date_modified, in_use, has_opinion_scraper,
	       has_oral_argument_scraper, position, citation_string, short_name, full_name,
	       url, start_date, end_date, jurisdiction, notes, parent_court_id
	       )'
court_csv_filename="courts-$(date -I).csv"

# search_courthouse
courthouse_fields='(id, court_seat, building_name, address1, address2, city, county,
state, zip_code, country_code, court_id)'
courthouse_csv_filename="courthouses-$(date -I).csv"

# Through table for courts m2m field: appeals_to
# search_court_appeals_to
court_appeals_to_fields='(id, from_court_id, to_court_id)'
court_appeals_to_csv_filename="court-appeals-to-$(date -I).csv"

# search_docket
docket_fields='(id, date_created, date_modified, source, appeal_from_str,
	       assigned_to_str, referred_to_str, panel_str, date_last_index, date_cert_granted,
	       date_cert_denied, date_argued, date_reargued,
	       date_reargument_denied, date_filed, date_terminated,
	       date_last_filing, case_name_short, case_name, case_name_full, slug,
	       docket_number, docket_number_core, pacer_case_id, cause,
	       nature_of_suit, jury_demand, jurisdiction_type,
	       appellate_fee_status, appellate_case_type_information, mdl_status,
	       filepath_local, filepath_ia, filepath_ia_json, ia_upload_failure_count, ia_needs_upload,
	       ia_date_first_change, view_count, date_blocked, blocked, appeal_from_id, assigned_to_id,
	       court_id, idb_data_id, originating_court_information_id, referred_to_id
	       )'
dockets_csv_filename="dockets-$(date -I).csv"

# search_originatingcourtinformation
originatingcourtinformation_fields='(
	       id, date_created, date_modified, docket_number, assigned_to_str,
	       ordering_judge_str, court_reporter, date_disposed, date_filed, date_judgment,
	       date_judgment_eod, date_filed_noa, date_received_coa, assigned_to_id,
	       ordering_judge_id
	       )'
originatingcourtinformation_csv_filename="originating-court-information-$(date -I).csv"

# recap_fjcintegrateddatabase
fjcintegrateddatabase_fields='(
	       id, date_created, date_modified, dataset_source, office,
	       docket_number, origin, date_filed, jurisdiction, nature_of_suit,
	       title, section, subsection, diversity_of_residence, class_action,
	       monetary_demand, county_of_residence, arbitration_at_filing,
	       arbitration_at_termination, multidistrict_litigation_docket_number,
	       plaintiff, defendant, date_transfer, transfer_office,
	       transfer_docket_number, transfer_origin, date_terminated,
	       termination_class_action_status, procedural_progress, disposition,
	       nature_of_judgement, amount_received, judgment, pro_se,
	       year_of_tape, nature_of_offense, version, circuit_id, district_id
	   )'
fjcintegrateddatabase_csv_filename="fjc-integrated-database-$(date -I).csv"

# search_opinioncluster
opinioncluster_fields='(
	       id, date_created, date_modified, judges, date_filed,
	       date_filed_is_approximate, slug, case_name_short, case_name,
	       case_name_full, scdb_id, scdb_decision_direction, scdb_votes_majority,
	       scdb_votes_minority, source, procedural_history, attorneys,
	       nature_of_suit, posture, syllabus, headnotes, summary, disposition,
	       history, other_dates, cross_reference, correction, citation_count,
	       precedential_status, date_blocked, blocked, filepath_json_harvard, docket_id,
	       arguments, headmatter
	   )'
opinioncluster_csv_filename="opinion-clusters-$(date -I).csv"

# search_opinion
opinion_fields='(
	       id, date_created, date_modified, author_str, per_curiam, joined_by_str,
	       type, sha1, page_count, download_url, local_path, plain_text, html,
	       html_lawbox, html_columbia, html_anon_2020, xml_harvard,
	       html_with_citations, extracted_by_ocr, author_id, cluster_id
	   )'
opinions_csv_filename="opinions-$(date -I).csv"

# search_opinionscited
opinionscited_fields='(
	       id, depth, cited_opinion_id, citing_opinion_id
	   )'
opinionscited_csv_filename="citation-map-$(date -I).csv"

# search_citation
citation_fields='(
	       id, volume, reporter, page, type, cluster_id
	   )'
citations_csv_filename="citations-$(date -I).csv"

# search_parenthetical
parentheticals_fields='(
	       id, text, score, described_opinion_id, describing_opinion_id, group_id
	   )'
parentheticals_csv_filename="parentheticals-$(date -I).csv"

# audio_audio
oralarguments_fields='(
	       id, date_created, date_modified, source, case_name_short,
	       case_name, case_name_full, judges, sha1, download_url, local_path_mp3,
	       local_path_original_file, filepath_ia, ia_upload_failure_count, duration,
	       processing_complete, date_blocked, blocked, stt_status, stt_transcript,
	       stt_source, docket_id
	   )'
oralarguments_csv_filename="oral-arguments-$(date -I).csv"

# people_db_person
people_db_person_fields='(
	       id, date_created, date_modified, date_completed, fjc_id, slug, name_first,
	       name_middle, name_last, name_suffix, date_dob, date_granularity_dob,
	       date_dod, date_granularity_dod, dob_city, dob_state, dob_country,
	       dod_city, dod_state, dod_country, gender, religion, ftm_total_received,
	       ftm_eid, has_photo, is_alias_of_id
	   )'
people_db_person_csv_filename="people-db-people-$(date -I).csv"

# people_db_school
people_db_school_fields='(
	       id, date_created, date_modified, name, ein, is_alias_of_id
	   )'
people_db_school_csv_filename="people-db-schools-$(date -I).csv"

# people_db_position
people_db_position_fields='(
	       id, date_created, date_modified, position_type, job_title,
	       sector, organization_name, location_city, location_state,
	       date_nominated, date_elected, date_recess_appointment,
	       date_referred_to_judicial_committee, date_judicial_committee_action,
	       judicial_committee_action, date_hearing, date_confirmation, date_start,
	       date_granularity_start, date_termination, termination_reason,
	       date_granularity_termination, date_retirement, nomination_process, vote_type,
	       voice_vote, votes_yes, votes_no, votes_yes_percent, votes_no_percent, how_selected,
	       has_inferred_values, appointer_id, court_id, person_id, predecessor_id, school_id,
	       supervisor_id
	   )'
people_db_position_csv_filename="people-db-positions-$(date -I).csv"

# people_db_retentionevent
people_db_retentionevent_fields='(
	       id, date_created, date_modified, retention_type, date_retention,
	       votes_yes, votes_no, votes_yes_percent, votes_no_percent, unopposed,
	       won, position_id
	   )'
people_db_retentionevent_csv_filename="people-db-retention-events-$(date -I).csv"

# people_db_education
people_db_education_fields='(
	       id, date_created, date_modified, degree_level, degree_detail,
	       degree_year, person_id, school_id
	   )'
people_db_education_csv_filename="people-db-educations-$(date -I).csv"

# people_db_politicalaffiliation
politicalaffiliation_fields='(
	       id, date_created, date_modified, political_party, source,
	       date_start, date_granularity_start, date_end,
	       date_granularity_end, person_id
	   )'
politicalaffiliation_csv_filename="people-db-political-affiliations-$(date -I).csv"

# people_db_race
people_db_race_fields='(id, race)'
people_db_race_csv_filename="people_db_race-$(date -I).csv"

# people_db_person_race
people_db_person_race_fields='(
	       id, person_id, race_id
	   )'
people_db_person_race_csv_filename="people-db-races-$(date -I).csv"

# disclosures_financialdisclosure
financialdisclosure_fields='(
	       id, date_created, date_modified, year, download_filepath, filepath, thumbnail,
	       thumbnail_status, page_count, sha1, report_type, is_amended, addendum_content_raw,
	       addendum_redacted, has_been_extracted, person_id
	   )'
financialdisclosure_csv_filename="financial-disclosures-$(date -I).csv"

# disclosures_investment
investment_fields='(
	       id, date_created, date_modified, page_number, description, redacted,
	       income_during_reporting_period_code, income_during_reporting_period_type,
	       gross_value_code, gross_value_method,
	       transaction_during_reporting_period, transaction_date_raw,
	       transaction_date, transaction_value_code, transaction_gain_code,
	       transaction_partner, has_inferred_values, financial_disclosure_id
	   )'
investment_csv_filename="financial-disclosure-investments-$(date -I).csv"

# disclosures_position
disclosures_position_fields='(
	       id, date_created, date_modified, position, organization_name,
	       redacted, financial_disclosure_id
	   )'
disclosures_position_csv_filename="financial-disclosures-positions-$(date -I).csv"

# disclosures_agreement
disclosures_agreement_fields='(
	       id, date_created, date_modified, date_raw, parties_and_terms,
	       redacted, financial_disclosure_id
	   )'
disclosures_agreement_csv_filename="financial-disclosures-agreements-$(date -I).csv"

# disclosures_noninvestmentincome
noninvestmentincome_fields='(
	       id, date_created, date_modified, date_raw, source_type,
	       income_amount, redacted, financial_disclosure_id
	   )'
noninvestmentincome_csv_filename="financial-disclosures-non-investment-income-$(date -I).csv"

# disclosures_spouseincome
spouseincome_fields='(
	       id, date_created, date_modified, source_type, date_raw, redacted,
	       financial_disclosure_id
	   )'
spouseincome_csv_filename="financial-disclosures-spousal-income-$(date -I).csv"

# disclosures_reimbursement
disclosures_reimbursement_fields='(
	       id, date_created, date_modified, source, date_raw, location,
	       purpose, items_paid_or_provided, redacted, financial_disclosure_id
	   )'
disclosures_reimbursement_csv_filename="financial-disclosures-reimbursements-$(date -I).csv"

# disclosures_gift
disclosures_gift_fields='(
	       id, date_created, date_modified, source, description, value,
	       redacted, financial_disclosure_id
	   )'
disclosures_gift_csv_filename="financial-disclosures-gifts-$(date -I).csv"

# disclosures_debt
disclosures_debt_fields='(
	       id, date_created, date_modified, creditor_name, description,
	       value_code, redacted, financial_disclosure_id
	   )'
disclosures_debt_csv_filename="financial-disclosures-debts-$(date -I).csv"


people_db_attorneyorganization_fields='(
	       id, date_created, date_modified, lookup_key, name, address1, address2, city, state, zip_code
	   )'
people_db_attorneyorganization_csv_filename="people_db_attorneyorganization-$(date -I).csv"


people_db_attorney_fields='(
	       id, date_created, date_modified, name, contact_raw, phone, fax, email
	   )'
people_db_attorney_csv_filename="people_db_attorney-$(date -I).csv"


people_db_party_fields='(
	       id, date_created, date_modified, name, extra_info
	   )'
people_db_party_csv_filename="people_db_party-$(date -I).csv"


docket_fields='(
	       id, date_created, date_modified, date_cert_granted, date_cert_denied, date_argued,
		   date_reargued, date_reargument_denied, case_name_short, case_name, case_name_full, slug,
		   docket_number, blocked, court_id, assigned_to_id, cause, date_filed, date_list_filing,
		   date_terminated, filepath_ia, filepath_local, jurisdiction_type, jury_demand,
		   nature_of_suit, pacer_case_id, referred_to_id, source, assigned_to_str, view_count,
		   date_last_index, appeal_from_str, appellate_case_type_information,
		   appellate_fee_status, panel_str, originating_court_information_id, mdl_status,
		   filepath_ia_json, ia_date_first_change, ia_needs_upload, ia_upload_failure_count,
		   docket_number_core, idb_data_id
	   )'
dockets_csv_filename="search_docket-$(date -I).csv"



people_db_partytype_fields='(
	       id, name, docket_id, party_id, date_terminated, extra_info,
		   highest_offense_level_opening, highest_offense_level_terminated
	   )'
people_db_partytype_csv_filename="people_db_partytype-$(date -I).csv"


fjcintegrateddatabase_fields='(
	       id, dataset_source, date_created, date_modified, office, docket_number, origin, date_filed,
		   jurisdiction, nature_of_suit, title, section, subsection, diversity_of_residence, class_action,
		   monetary_demand, county_of_residence, arbitrarion_at_filing, arbitration_at_termination, 
		   multidistrict_litigation_docket_number, plaintiff, defendant, date_transfer, transfer_office,
		   transfer_docket_number, transfer_oprigin, date_terminated, termination_class_action_status,
		   procedural_progress, disposition, nature_of_judgement, amount_recieved, judgment, pro_se,
		   year_of_tape, circuit_id, district_id, nature_of_offense, version
	   )'
fjcintegrateddatabase_csv_filename="recap_fjcintegrateddatabase-$(date -I).csv"


people_db_criminalcount_fields='(
	       id, date_created, date_modified, creditor_name, description,
	       value_code, redacted, financial_disclosure_id
	   )'
people_db_criminalcount_csv_filename="people_db_criminalcount-$(date -I).csv"


people_db_criminalcomplaint_fields='(
	       id, name, disposition, status, party_type_id
	   )'
people_db_criminalcomplaint_csv_filename="people_db_criminalcomplaint-$(date -I).csv"


people_db_role_fields='(
	       id, role, date_action, attorney_id, docket_id, party_id, role_raw
	   )'
people_db_role_csv_filename="people_db_role-$(date -I).csv"


people_db_attorneyorganizationassociation_fields='(
	       id, attorney_id, attorney_organization_id, docket_id
	   )'
people_db_attorneyorganizationassociation_csv_filename="people_db_attorneyorganizationassociation-$(date -I).csv"


search_docketentry_fields='(
	       id, date_created_date_modified, date_filed, entry_number, description, docket_id,
		   pacer_sequence_number, recap_sequence_number
	   )'
search_docketentry_csv_filename="search_docketentry-$(date -I).csv"


search_opinioncluster_panel_fields='(
	       id, opinioncluster_id, person_id
	   )'
search_opinioncluster_panel_csv_filename="search_opinioncluster_panel-$(date -I).csv"


search_opinioncluster_non_participating_judges_fields='(
	       id, opinioncluster_id, person_id
	   )'
search_opinioncluster_non_participating_judges_csv_filename="search_opinioncluster_non_participating_judges-$(date -I).csv"

# If you add or remove a table, you need to update this number
NUM_TABLES=42

# Every new table added to bulk script should be added as an associative array
# This ordering is important. Tables with foreign key constraints must be loaded in order.
declare -a t_1=("people_db_person" "$people_db_person_fields" "$people_db_person_csv_filename")
declare -a t_2=("people_db_race" "$people_db_race_fields" "$people_db_race_csv_filename")
declare -a t_3=("people_db_school" "$people_db_school_fields" "$people_db_school_csv_filename")
declare -a t_4=("search_court" "$court_fields" "$court_csv_filename")
declare -a t_5=("people_db_position" "$people_db_position_fields" "$people_db_position_csv_filename")
declare -a t_6=("recap_fjcintegrateddatabase" "$fjcintegrateddatabase_fields" "$fjcintegrateddatabase_csv_filename")
declare -a t_7=("search_originatingcourtinformation" "$originatingcourtinformation_fields" "$originatingcourtinformation_csv_filename")

declare -a t_8=("people_db_attorneyorganization" "$people_db_attorneyorganization_fields" "$people_db_attorneyorganization_csv_filename")
declare -a t_9=("people_db_attorney" "$people_db_attorney_fields" "$people_db_attorney_csv_filename")
declare -a t_10=("people_db_party" "$people_db_party_fields" "$people_db_party_csv_filename")
declare -a t_11=("search_docket" "$docket_fields" "$dockets_csv_filename")
declare -a t_12=("search_opinioncluster" "$opinioncluster_fields" "$opinioncluster_csv_filename")
declare -a t_13=("people_db_partytype" "$people_db_partytype_fields" "$people_db_partytype_csv_filename")
declare -a t_14=("recap_fjcintegrateddatabase" "$fjcintegrateddatabase_fields" "$fjcintegrateddatabase_csv_filename")
declare -a t_15=("people_db_criminalcount" "$people_db_criminalcount_fields" "$people_db_criminalcount_csv_filename")
declare -a t_16=("people_db_criminalcomplaint" "$people_db_criminalcomplaint_fields" "$people_db_criminalcomplaint_csv_filename")
declare -a t_17=("people_db_role" "$people_db_role_fields" "$people_db_role_csv_filename")
declare -a t_18=("people_db_attorneyorganizationassociation" "$people_db_attorneyorganizationassociation_fields" "$people_db_attorneyorganizationassociation_csv_filename")
declare -a t_19=("search_docketentry" "$search_docketentry_fields" "$search_docketentry_csv_filename")
declare -a t_20=("search_opinioncluster_panel" "$search_opinioncluster_panel_fields" "$search_opinioncluster_panel_csv_filename")
declare -a t_21=("search_opinioncluster_non_participating_judges" "$search_opinioncluster_non_participating_judges_fields" "$search_opinioncluster_non_participating_judges_csv_filename")

declare -a t_22=("search_opinion" "$opinion_fields" "$opinions_csv_filename")
declare -a t_23=("search_opinion_joined_by" "$search_opinion_joined_by_fields" "$search_opinion_joined_by_csv_filename")
declare -a t_24=("search_courthouse" "$courthouse_fields" "$courthouse_csv_filename")
declare -a t_25=("search_court_appeals_to" "$court_appeals_to_fields" "$court_appeals_to_csv_filename")
declare -a t_26=("search_opinionscited" "$opinionscited_fields" "$opinionscited_csv_filename")
declare -a t_27=("search_citation" "$citation_fields" "$citations_csv_filename")
declare -a t_28=("search_parenthetical" "$parentheticals_fields" "$parentheticals_csv_filename")
declare -a t_29=("audio_audio" "$oralarguments_fields" "$oralarguments_csv_filename")
declare -a t_30=("people_db_retentionevent" "$people_db_retentionevent_fields" "$people_db_retentionevent_csv_filename")
declare -a t_31=("people_db_education" "$people_db_education_fields" "$people_db_education_csv_filename")
declare -a t_32=("people_db_politicalaffiliation" "$politicalaffiliation_fields" "$politicalaffiliation_csv_filename")
declare -a t_33=("people_db_person_race" "$people_db_person_race_fields" "$people_db_person_race_csv_filename")
declare -a t_34=("disclosures_financialdisclosure" "$financialdisclosure_fields" "$financialdisclosure_csv_filename")
declare -a t_35=("disclosures_investment" "$investment_fields" "$investment_csv_filename")
declare -a t_36=("disclosures_position" "$disclosures_position_fields" "$disclosures_position_csv_filename")
declare -a t_37=("disclosures_agreement" "$disclosures_agreement_fields" "$disclosures_agreement_csv_filename")
declare -a t_38=("disclosures_noninvestmentincome" "$noninvestmentincome_fields" "$noninvestmentincome_csv_filename")
declare -a t_39=("disclosures_spouseincome" "$spouseincome_fields" "$spouseincome_csv_filename")
declare -a t_40=("disclosures_reimbursement" "$disclosures_reimbursement_fields" "$disclosures_reimbursement_csv_filename")
declare -a t_41=("disclosures_gift" "$disclosures_gift_fields" "$disclosures_gift_csv_filename")
declare -a t_42=("disclosures_debt" "$disclosures_debt_fields" "$disclosures_debt_csv_filename")

# Create a new array with the data of each associative array
declare -a listOfLists
for (( i=1; i<=$NUM_TABLES; i++ )); do
    declare -n table_array="t_$i"
    listOfLists+=("(${table_array[*]@Q})")
done

# Stream to S3
for group in "${listOfLists[@]}"; do
declare -a lst="$group"
echo "Streaming ${lst[0]} to S3"
psql \
	--command \
	  "set statement_timeout to 0;
	   COPY ${lst[0]} ${lst[1]} TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER, QUOTE '`', FORCE_QUOTE *)" \
	--quiet \
	--host "$DB_HOST" \
	--username "$DB_USER" \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/"${lst[2]}".bz2 --acl public-read
done

echo "Exporting schema to S3"
schema_filename="schema-$(date -I).sql"
pg_dump \
    --host "$DB_HOST" \
    --username "$DB_USER" \
    --create \
    --schema-only \
    --table 'search_*' \
    --table 'people_db_*' \
    --table 'audio_*' \
	--table 'recap_*' \
	--table 'disclosures_*' \
    --no-privileges \
    --no-publications \
    --no-subscriptions courtlistener | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/"$schema_filename" --acl public-read

echo "Generating and streaming load bulk data script to S3"
BULK_SCRIPT_FILENAME="load-bulk-data-$(date -I).sh"
# Create a temp file to store the script
OUT="$(mktemp /tmp/temp_load_bulk_load_data.XXXXXXXXXX)" || { echo "Failed to create temp file"; exit 1; }
# Start creating the script to load bulk data
cat > "$OUT" <<- EOF
#!/bin/bash
set -e
# You must place all uncompressed bulk files in the same directory and set
# environment variable BULK_DIR, BULK_DB_HOST, BULK_DB_USER, BULK_DB_PASSWORD
# NOTES:
# 1. If you have your postgresql instance on a docker service, you need to mount
# the directory where the bulk files are, otherwise you will get this error:
# ERROR:  could not open file No such file or directory
# 2. You may need to grant execute permissions to this file

if [[ -z \${BULK_DIR} ]];
then
echo "Variable having name 'BULK_DIR' is not set. BULK_DIR is where all the unzipped files are."
exit
fi

if [[ -z \${BULK_DB_HOST} ]];
then
echo "Variable having name 'BULK_DB_HOST' is not set."
exit
fi

if [[ -z \${BULK_DB_USER} ]];
then
echo "Variable having name 'BULK_DB_USER' is not set."
exit
fi

if [[ -z \${BULK_DB_PASSWORD} ]];
then
echo "Variable having name 'BULK_DB_PASSWORD' is not set."
exit
fi

# Default from schema is 'courtlistener'
export BULK_DB_NAME=courtlistener
export PGPASSWORD=\$BULK_DB_PASSWORD

echo "Loading schema to database: $schema_filename"
psql -f "\$BULK_DIR"/$schema_filename --host "\$BULK_DB_HOST" --username "\$BULK_DB_USER"

EOF

# Start adding the code to the script to load the tables
for group in "${listOfLists[@]}"; do
declare -a lst="$group"
cat >> "$OUT" <<- EOF
echo "Loading ${lst[2]} to database"
psql --command \
"COPY public.${lst[0]} ${lst[1]} FROM '\$BULK_DIR/${lst[2]}' WITH (FORMAT csv, ENCODING utf8, QUOTE '`', HEADER)" \
--host "\$BULK_DB_HOST" \
--username "\$BULK_DB_USER" \
--dbname "\$BULK_DB_NAME"

EOF
done

# Upload generated file to S3
aws s3 cp "$OUT" s3://com-courtlistener-storage/bulk-data/"$BULK_SCRIPT_FILENAME" --acl public-read

# Remove the temp file when script ends to execute
trap "rm -f $OUT" EXIT

echo "Done."
