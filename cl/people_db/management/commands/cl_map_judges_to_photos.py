import os

from django.utils.text import slugify
from django.utils.timezone import now
from judge_pics import judge_root

from cl.custom_filters.templatetags.extras import granular_date
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import Person


class Command(VerboseCommand):
    help = (
        "Run through the judges and see which have pictures in the "
        "judge-pics project."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.debug = options["debug"]
        self.options = options

        # Run the requested method.
        self.map_judges_to_photos()

    @staticmethod
    def make_slugs(person):
        slug_name = (
            f"{slugify(f'{person.name_last} {person.name_first}')}.jpeg"
        )

        slug_name_dob = "{slug}-{date}.jpeg".format(
            slug=slug_name.rsplit(".")[0],
            date=granular_date(person, "date_dob", iso=True).lower(),
        )
        return slug_name, slug_name_dob

    def map_judges_to_photos(self):
        """Identify which of the judges in the DB have photos.

        We iterate over the entire collection of judges, identifying which have
        photos. We could instead iterate over the photos, but that increases
        the risk of duplicate issues.
        """
        # Create a dict of judge paths, mapping paths to empty lists.
        judge_paths = os.listdir(os.path.join(judge_root, "orig"))
        judge_map = {}
        for path in judge_paths:
            judge_map[path] = []

        # Iterate over the people, attempting to look them up in the list
        people = Person.objects.filter(is_alias_of=None)
        for person in people:
            for name in self.make_slugs(person):
                if name in judge_map:
                    # If there's a hit, add the path to the dict of judge paths.
                    judge_map[name].append(person)
                    break

        # After iterating, set all people to not have photos.
        if not self.debug:
            people.update(date_modified=now(), has_photo=False)

        found = 0
        missed = 0
        multi = 0
        for path, people in judge_map.items():
            if len(people) == 0:
                logger.warning(f"Did not find a judge for {path}")
                missed += 1
            if len(people) == 1:
                person = people[0]
                found += 1
                if not self.debug:
                    logger.info(f"Updating judge {person}")
                    person.has_photo = True
                    person.save()
            if len(people) > 1:
                logger.warning(f"Found more than one match for {path}:")
                for person in people:
                    logger.warning(
                        "Found: %s - %s"
                        % (person, granular_date(person, "date_dob", iso=True))
                    )
                multi += 1

        logger.info(
            f"\n\n{found} Matches\n{missed} Missed\n{multi} Multiple results"
        )
