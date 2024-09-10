import json
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from cl.search.models import OpinionCluster
from tqdm import tqdm


class Command(BaseCommand):
    help = "Generate crosswalk between CAP and CL IDs"

    def handle(self, *args, **options):
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        )

        crosswalk = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=settings.R2_BUCKET_NAME, Prefix="a2d"
        ):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    response = s3.get_object(
                        Bucket=settings.R2_BUCKET_NAME, Key=obj["Key"]
                    )
                    cap_data = json.loads(
                        response["Body"].read().decode("utf-8")
                    )

                    # Match logic here (simplified for example)
                    cl_cluster = OpinionCluster.objects.filter(
                        case_name__icontains=cap_data["name"],
                        date_filed=cap_data["decision_date"],
                    ).first()

                    if cl_cluster:
                        crosswalk.append(
                            {
                                "cap_id": cap_data["id"],
                                "cl_id": cl_cluster.id,
                                "cap_path": obj["Key"],
                            }
                        )

        with open("cap_cl_crosswalk.json", "w") as f:
            json.dump(crosswalk, f)

        self.stdout.write(
            self.style.SUCCESS(
                f"Generated crosswalk with {len(crosswalk)} entries"
            )
        )
