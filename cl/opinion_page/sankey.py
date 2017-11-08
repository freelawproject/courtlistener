def find_matching_node(nodes, lookup, node_type):
    """Find a matching node that's already in the node array of parties,
    attorneys, and firms. Return it's location in the node array.
    :param nodes: The list of nodes, with each node being a dict.
    :param lookup: A dict indicating the key and value to lookup
    :param node_type: The type of node to lookup.
    :returns int or None: The location of the matched node or None, if none
    found.
    """
    assert len(lookup.keys()) == 1, "lookup param only supports dicts of len 1"
    lookup_key = lookup.keys()[0]
    lookup_value = lookup.values()[0]
    return next(
        (i for (i, node) in enumerate(nodes) if
         str(node[lookup_key]).lower() == str(lookup_value).lower() and
         node['type'] == node_type),
        None,
    )


def add_and_link_node(nodes, links, source_i, node):
    """Add a node if it doesn't already exist. Regardless of whether it exists,
    add a link to the node from the source_i field.

    :returns The location the node was inserted into the node list.
    """
    if node['type'] == 'party':
        # Just add it. No need to try to look it up. Parties shouldn't be
        # repeated in the source data. No need to do add links for parties
        # either.
        nodes.append(node)
        return len(nodes) - 1

    found_at = find_matching_node(nodes, {'id': node['id']}, node['type'])
    if found_at is None:
        nodes.append(node)
    item_location = found_at or len(nodes) - 1
    links.append({
        'source': source_i,
        'target': item_location,
        'value': 1,
    })
    return item_location


def make_sankey_json(party_types):
    """Make a json object for use with the sankey visualizations."""
    nodes = []
    links = []
    for pt in party_types:
        p = pt.party
        party_location = add_and_link_node(nodes, links, None, {
            'id': p.pk,
            'type': 'party',
            'name': p.name,
        })

        if len(p.attys_in_docket) == 0:
            name = 'Pro se / Unknown'
            _ = add_and_link_node(nodes, links, party_location, {
                'id': None,
                'type': 'attorney',
                'name': name,
            })
            continue  # Don't move on to attorneys/firms for this party.

        for a in p.attys_in_docket:
            atty_location = add_and_link_node(nodes, links, party_location, {
                'id': a.pk,
                'type': 'attorney',
                'name': a.name,
            })

            for f in a.firms_in_docket:
                add_and_link_node(nodes, links, atty_location, {
                    'id': f.pk,
                    'type': 'firm',
                    'name': f.name,
                })

    return {'nodes': nodes, 'links': links}
