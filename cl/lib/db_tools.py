from datetime import datetime, timezone

from django.db import connection

from cl.lib.command_utils import logger


def fetchall_as_dict(cursor):
    """Return all rows from a cursor as a dict.

    From: https://docs.djangoproject.com/en/3.0/topics/db/sql/#executing-custom-sql-directly

    :param cursor: The cursor that you wish to query
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def log_db_connection_info(model_name: str, instance_id: int) -> None:
    """Log connection information for the current database session.

    :param model_name: The name of the model being logged.
    :param instance_id: The ID of the model instance.
    :return: None
    """

    # Log connection settings and transaction details.
    try:
        db_settings = connection.settings_dict
        logger.info("Database Alias: %s", db_settings.get("NAME"))
        logger.info("Host: %s", db_settings.get("HOST"))
        logger.info("Port: %s", db_settings.get("PORT"))

        # Log the current database transaction state
        logger.info(
            "In atomic block: %s, instance: %s:%s",
            connection.in_atomic_block,
            model_name,
            instance_id,
        )
        logger.info(
            "Autocommit: %s, instance: %s:%s",
            connection.get_autocommit(),
            model_name,
            instance_id,
        )
        if hasattr(connection, "needs_rollback"):
            logger.info(
                "Connection needs rollback: %s,  instance: %s:%s",
                connection.needs_rollback,
                model_name,
                instance_id,
            )
    except Exception as e:
        logger.warning("Error retrieving DB transaction details: %s", e)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT pid, state, backend_start, xact_start
                    FROM pg_stat_activity
                    WHERE pid = pg_backend_pid();
                """
            )
            result = cursor.fetchone()
            if result:
                pid, state, backend_start, xact_start = result
            else:
                pid = state = backend_start = xact_start = None
    except Exception as e:
        logger.warning("Error retrieving connection details: %s", e)
        pid = state = backend_start = xact_start = None

    # Log the connection details and current UTC time
    current_time = datetime.now(timezone.utc)
    logger.info(
        "Connection details: PID=%s, state=%s, backend_start=%s, xact_start=%s logged_at=%s , instance: %s:%s",
        pid,
        state,
        backend_start,
        xact_start,
        current_time,
        model_name,
        instance_id,
    )
