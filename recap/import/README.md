
The import stage is divided to two parts.
    - Generate CSV files with docket names to be used as a reference to download.
    - Create celery tasks to download on parallel jobs.

Before doing anything, you will have to change the DB parameters in the recap_constants.py file.
Make sure the RECAP DB is accessible and has read permission.
By default it will point to your local MySQL DB.

You will also have to make sure Celery and a Message Broker is up and active.
Make sure the 'CELERY_MESSAGE_BROKER' in recap_constants.py points to your message broker.

For the first part, i.e generating csv reference files. Run...

    python recap_db_reference_creator.py

After the process completes. You will find CSV files in the 'recap_db_references/' folder.

To set up download tasks in celery. Run...

    python recap_docket_downloader_task_creator.py

To make sure every docket has been downloaded. You may run it again.

