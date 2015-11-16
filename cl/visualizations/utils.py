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
