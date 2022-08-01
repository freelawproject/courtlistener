#!/bin/bash
set -e

echo "Installing utilities"

# Set up Sentry
curl -sL https://sentry.io/get-cli/ | bash
eval "$(sentry-cli bash-hook)"

# Set up AWS tools and gnupg (needed for apt-key add, below)
apt install -y awscli gnupg

# Install latest version of pg_dump (else we get an error about version mismatch
echo "deb http://apt.postgresql.org/pub/repos/apt bullseye-pgdg main" > /etc/apt/sources.list.d/pgdg.list
curl --silent 'https://www.postgresql.org/media/keys/ACCC4CF8.asc' |  apt-key add -
apt-get update
apt-get install postgresql-client-14

# Stream to S3

echo "Streaming search_court to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_court (
	       id, pacer_court_id, pacer_has_rss_feed, fjc_court_id, date_modified,
	       in_use, has_opinion_scraper, has_oral_argument_scraper, position,
	       citation_string, short_name, full_name, url, start_date, end_date,
	       jurisdiction
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/courts-`date -I`.csv.bz2 --acl public-read

echo "Streaming search_docket to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_docket (
	       id, date_created, date_modified, source, appeal_from_str,
	       assigned_to_str, referred_to_str, panel_str, date_cert_granted,
	       date_cert_denied, date_argued, date_reargued, date_reargument_denied,
	       date_filed, date_terminated, date_last_filing, case_name_short,
	       case_name, case_name_full, slug, docket_number, docket_number_core,
	       pacer_case_id, cause, nature_of_suit, jury_demand, jurisdiction_type,
	       appellate_fee_status, appellate_case_type_information, mdl_status,
	       filepath_local, filepath_ia, filepath_ia_json, date_blocked, blocked,
	       appeal_from_id, assigned_to_id, court_id, idb_data_id,
	       originating_court_information_id, referred_to_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/dockets-`date -I`.csv.bz2 --acl public-read

echo "Streaming search_opinioncluster to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_opinioncluster (
	       id, date_created, date_modified, judges, date_filed,
	       date_filed_is_approximate, slug, case_name_short, case_name,
	       case_name_full, scdb_id, scdb_decision_direction, scdb_votes_majority,
	       scdb_votes_minority, source, procedural_history, attorneys,
	       nature_of_suit, posture, syllabus, headnotes, summary, disposition,
	       history, other_dates, cross_reference, correction, citation_count,
	       precedential_status, date_blocked, blcoked, docket_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/opinion-clusters-`date -I`.csv.bz2 --acl public-read

echo "Streaming search_opinion to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_opinion (
	       id, date_created, date_modified, author_str, per_curiam, joined_by_str,
	       type, sha1, page_count, download_url, local_path, plain_text, html,
	       html_lawbox, html_columbia, html_anon_2020, xml_harvard,
	       html_with_citations, extracted_by_ocr, author_id, cluster_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/opinions-`date -I`.csv.bz2 --acl public-read

echo "Streaming search_opinionscited to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_opinionscited (
	       id, depth, cited_opinion_id, citing_opinion_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST -\
	-username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/citation-map-`date -I`.csv.bz2 --acl public-read

echo "Streaming search_parenthetical to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY search_parenthetical (
	       id, text, score, described_opinion_id, describing_opinion_id, group_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/parentheticals-`date -I`.csv.bz2 --acl public-read

echo "Streaming audio_audio to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY audio_audio (
	       id, date_created, date_modified, source, case_name_short,
	       case_name, case_name_full, judges, sha1, download_url, local_path_mp3,
	       local_path_original_file, filepath_ia, duration, date_blocked,
	       blocked, docket_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/oral-arguments-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_person to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_person (
	       id, date_created, date_modified, fjc_id, slug, name_first,
	       name_middle, name_last, name_suffix, date_dob, date_granularity_dob,
	       date_dod, date_granularity_dod, dob_city, dob_state, dob_country,
	       dod_city, dod_state, dod_country, gender, religion, ftm_total_received,
	       ftn_eid, has_photo, is_alias_of_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-people-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_school to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_school (
	       id, date_created, date_modified, name, ein, is_alias_of_id,
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-schools-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_position to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_position (
	       id, date_created, date_modified, position_type, job_title,
	       sector, organization_name, location_city, location_state,
	       date_nominated, date_elected, date_recess_appointment,
	       date_referred_to_judicial_committee, date_judicial_committee_action,
	       date_hearing, date_confirmation, date_start, date_granularity_start,
	       date_termination, date_granularity_termination, date_retirement,
	       nomination_process, vote_type, voice_vote, votes_yes, votes_no,
	       votes_yes_percent, votes_no_percent, how_selected, has_inferred_values,
	       appointer_id, court_id, person_id, predecessor_id, school_id,
	       supervisor_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-positions-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_retentionevent to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_retentionevent (
	       id, date_created, date_modified, retention_type, date_retention,
	       votes_yes, votes_no, vote_yes_percent, votes_no_percent, unopposed, won
	       position_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-retention-events-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_education to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_education (
	       id, date_created, date_modified, degree_level, degree_detail,
	       degree_year, person_id, school_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-educations-`date -I`.csv.bz2 --acl public-read

echo "Streaming people_db_politicalaffiliation to S3"
PGPASSWORD=$DB_PASSWORD psql \
	--command \
	  'set statement_timeout to 0;
	   COPY people_db_politicalaffiliation (
	       id, date_created, date_modified, political_party, source,
	       date_start, date_granularity_start, date_end,
	       date_granularity_end, person_id
	   ) TO STDOUT WITH (FORMAT csv, ENCODING utf8, HEADER)' \
	--host $DB_HOST \
	--username $DB_USER \
	--dbname courtlistener | \
	bzip2 | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/people-db-political-affiliations-`date -I`.csv.bz2 --acl public-read

echo "Exporting schema to S3"
PGPASSWORD=$DB_PASSWORD pg_dump \
    --host $DB_HOST \
    --username $DB_USER \
    --create \
    --schema-only \
    --table 'search_*' \
    --table 'people_db_*' \
    --table 'audio_*' \
    --no-privileges \
    --no-publications \
    --no-subscriptions courtlistener | \
	aws s3 cp - s3://com-courtlistener-storage/bulk-data/schema-`date -I`.sql --acl public-read

echo "Done."
