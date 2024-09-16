import time
from typing import Dict

from django.conf import settings
from django.contrib import messages

from cl.lib.types import EmailType
from cl.stats.utils import tally_stat
from cl.visualizations.exceptions import TooManyNodes
from cl.visualizations.models import JSONVersion


async def build_visualization(viz):
    """Use the start and end points to generate a visualization

    :param viz: A Visualization object to work on
    :return: A tuple of (status<str>, viz)
    """
    build_kwargs = {
        "parent_authority": viz.cluster_end,
        "visited_nodes": {},
        "good_nodes": {},
        "max_hops": 3,
    }
    t1 = time.time()
    try:
        g = await viz.build_nx_digraph(**build_kwargs)
    except TooManyNodes:
        try:
            # Try with fewer hops.
            build_kwargs["max_hops"] = 2
            g = await viz.build_nx_digraph(**build_kwargs)
        except TooManyNodes:
            # Still too many hops. Abort.
            await tally_stat("visualization.too_many_nodes_failure")
            return "too_many_nodes", viz

    if len(g.edges()) == 0:
        await tally_stat("visualization.too_few_nodes_failure")
        return "too_few_nodes", viz

    t2 = time.time()
    viz.generation_time = t2 - t1

    await viz.asave()
    await viz.add_clusters(g)
    j = await viz.to_json(g)
    jv = JSONVersion(map=viz, json_data=j)
    await jv.asave()
    return "success", viz


emails: Dict[str, EmailType] = {
    "referer_detected": {
        "subject": "Somebody seems to have embedded a viz somewhere.",
        "body": "Hey admins,\n\n"
        "It looks like somebody embedded a SCOTUSMap on a blog or "
        "something. Somebody needs to check this out and possibly "
        "approve it. It appears to be at:\n\n"
        " - %s\n\n"
        "With a page title of:\n\n"
        " - %s\n\n"
        "And can be reviewed at:\n\n"
        " - https://www.courtlistener.com%s\n\n"
        "If nobody approves it, it'll never show up on the site.\n\n"
        "Godspeed, fair admin.\n"
        "The CourtListener bots",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    }
}

message_dict = {
    "too_many_nodes": {
        "level": messages.WARNING,
        "message": "<strong>That network has too many cases.</strong> We "
        "were unable to create your network because the "
        "finished product would contain too  many cases. "
        "We've found that in practice, such networks are "
        "difficult to read and take far too long for our "
        "servers to create. Try building a smaller network by "
        "selecting different cases.",
    },
    "too_few_nodes": {
        "level": messages.WARNING,
        "message": "<strong>That network has no citations between the "
        "cases.</strong> With no connections between the cases, we "
        "can't build a network. Try selecting different cases that "
        "you're sure cite each other.",
    },
    "fewer_hops_delivered": {
        "level": messages.SUCCESS,
        "message": "We were unable to build your network with three "
        "degrees of separation because it grew too large. "
        "The network below was built with two degrees of "
        "separation.",
    },
}
