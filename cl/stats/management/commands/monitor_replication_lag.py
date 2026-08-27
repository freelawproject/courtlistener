import boto3

from cl.lib.command_utils import VerboseCommand
from cl.stats.utils import get_replication_statuses

NAMESPACE = "CourtListener/Replication"
REGION = "us-west-2"


class Command(VerboseCommand):
    help = (
        "Publish per-slot Postgres replication lag to CloudWatch. A "
        "CloudWatch alarm on the MaxReplicationLagBytes metric fires the "
        "actual alert via SNS -> Chatbot -> Slack."
    )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        statuses = get_replication_statuses()
        per_slot_metrics = []
        max_lag = 0

        for server_name, rows in statuses.items():
            for row in rows:
                lag = row["lsn_distance"]
                if lag is None:
                    continue
                per_slot_metrics.append(
                    {
                        "MetricName": "ReplicationLagBytes",
                        "Dimensions": [
                            {"Name": "Server", "Value": server_name},
                            {"Name": "Slot", "Value": row["slot_name"]},
                        ],
                        "Value": float(lag),
                        "Unit": "Bytes",
                    }
                )
                max_lag = max(max_lag, lag)

        if not per_slot_metrics:
            return

        metric_data = per_slot_metrics + [
            {
                "MetricName": "MaxReplicationLagBytes",
                "Value": float(max_lag),
                "Unit": "Bytes",
            }
        ]

        cw = boto3.client("cloudwatch", region_name=REGION)
        cw.put_metric_data(Namespace=NAMESPACE, MetricData=metric_data)
