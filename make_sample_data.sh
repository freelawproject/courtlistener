#!/bin/bash
# This file loops through a few sample sizes and generates sample data in the /sata/sample-data directory

# Get the password
echo -n "What is the database password for the postgres user: "
read -s db_pw
echo

for size in 50 500 5000 50000
do
    echo "Generating sample of $size random records"
    PGPASSWORD="$db_pw" /usr/bin/psql -U postgres -v count=$size -d courtlistener -a -f /sata/sample-data/make_sample_data.sql > /dev/null
    sudo chown www-data /tmp/citation_data.sql
    sudo chown www-data /tmp/document_data.sql
    sudo mv /tmp/citation_data.sql /sata/sample-data/citation_data_$size.sql
    sudo mv /tmp/document_data.sql /sata/sample-data/document_data_$size.sql
done
