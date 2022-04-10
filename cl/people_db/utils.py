def make_title_str(person):
    """Make a nice title for somebody."""
    locations = ", ".join(
        {p.court.short_name for p in person.positions.all() if p.court}
    )
    title = person.name_full
    if locations:
        title = f"{title} ({locations})"
    return title
