import time

import boto3
from django.conf import settings


def invalidate_cloudfront(paths: str | list[str]) -> str:
    """Delete an item from the CloudFront cache

    :param paths: An list of paths or a single path. Terminal asterisks are OK.
    Leading slashes are a must.
    :return The invalidation ID for the invalidation request.
    """
    # Normalize input
    if isinstance(paths, str):
        paths = list(paths)

    # Data checks
    for path in paths:
        assert "*" not in path.strip("*"), f"Got asterisk in middle of: {path}"
        assert path.startswith("/"), f"Path must start with a slash: {path}"

    # Send an invalidation
    cf = boto3.client("cloudfront")
    res = cf.create_invalidation(
        DistributionId=settings.CLOUDFRONT_DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {
                "Quantity": len(paths),
                "Items": paths,
            },
            "CallerReference": str(time.time()).replace(".", ""),
        },
    )
    invalidation_id = res["Invalidation"]["Id"]
    return invalidation_id
