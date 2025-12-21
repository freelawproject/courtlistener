import time

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
            return "too_many_nodes", viz

    if len(g.edges()) == 0:
        return "too_few_nodes", viz

    t2 = time.time()
    viz.generation_time = t2 - t1

    await viz.asave()
    await viz.add_clusters(g)
    j = await viz.to_json(g)
    jv = JSONVersion(map=viz, json_data=j)
    await jv.asave()
    return "success", viz
