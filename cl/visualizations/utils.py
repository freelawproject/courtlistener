from django.conf import settings
from django.contrib import messages


def reverse_endpoints_if_needed(start, end):
    """Make sure start date < end date, and flip if needed.

    The front end allows the user to put in the endpoints in whatever
    chronological order they prefer. This sorts them.
    """
    if start.date_filed < end.date_filed:
        return start, end
    else:
        return end, start


def within_max_hops(good_nodes, child_authority_id, hops_taken, max_hops):
    """Determine if a new route to a node that's already in the network is
    within the max_hops of the start_point.
    """
    shortest_path = good_nodes[child_authority_id]['shortest_path']
    if (shortest_path + hops_taken) > max_hops:
        return False
    return True


def graphs_intersect(good_nodes, main_graph, sub_graph):
    """Test if two graphs have common nodes.

    First check if it's in the main graph, then check if it's in good_nodes,
    indicating a second path to the start node.
    """
    return (any([(node in main_graph) for node in sub_graph.nodes()]) or
            any([(node in good_nodes) for node in sub_graph.nodes()]))


def set_shortest_path_to_end(good_nodes, node_id, target_id):
    """Determine if a path is to the end is shorter, and if so, update the
    current value.
    """
    is_shorter = False
    if node_id in good_nodes:
        current_length = good_nodes[node_id]['shortest_path']
        previous_length = good_nodes[target_id]['shortest_path'] + 1
        if current_length < previous_length:
            is_shorter = True
        good_nodes[node_id]['shortest_path'] = min(
            current_length,
            previous_length,
        )
    else:
        good_nodes[node_id] = {
            'shortest_path': good_nodes[target_id]['shortest_path'] + 1
        }
    return is_shorter


class TooManyNodes(Exception):
    class SetupException(Exception):
        def __init__(self, message):
            Exception.__init__(self, message)


emails = {
    'referer_detected': {
        'subject': "Somebody seems to have embedded a viz somewhere.",
        'body': "Hey admins,\n\n"
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
        'from': 'CourtListener <noreply@courtlistener.com>',
        'to': [a[1] for a in settings.ADMINS],
    }
}

message_dict = {
    'too_many_nodes': {
        'level': messages.WARNING,
        'message': '<strong>That network has too many nodes.</strong> We '
                   'were unable to create your visualization because the '
                   'finished product would contain too  many nodes. '
                   'We\'ve found that in practice, such networks are '
                   'difficult to read and take far too long for our '
                   'servers to create. Try building a smaller network by '
                   'selecting different cases.',
    },
    'fewer_hops_delivered': {
        'level': messages.SUCCESS,
        'message': "We were unable to build your network with three "
                   "degrees of separation because it grew too large. "
                   "The network below was built with two degrees of "
                   "separation.",
    }
}
