from typing import Optional

from django.templatetags.static import static
from django.utils.text import slugify

from cl.custom_filters.templatetags.extras import granular_date
from cl.people_db.models import Person


def make_person_picture_path(person: Person) -> Optional[str]:
    """Make the path for a person's img tag."""

    img_path = None
    if person.has_photo:
        p = slugify(f"{person.name_last}-{person.name_first}".lower())
        if person.date_dob:
            img_path = static(
                "judge_pics/%s-%s.jpeg"
                % (p, granular_date(person, "date_dob", iso=True, default=""))
            )
        else:
            img_path = static(f"judge_pics/{p}.jpeg")

    return img_path


def make_title_str(person):
    """Make a nice title for somebody."""
    locations = ", ".join(
        {p.court.short_name for p in person.positions.all() if p.court}
    )
    title = person.name_full
    if locations:
        title = f"{title} ({locations})"
    return title
