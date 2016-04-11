import os

from django.core.management import BaseCommand
from django.utils.formats import date_format
from django.utils.text import slugify
from judge_pics import judge_root

from cl.people_db.models import Person, GRANULARITY_DAY


class Command(BaseCommand):
    help = ('Run through the judges and see which have pictures in the '
            'judge-pics project.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data."
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options

        # Run the requested method.
        self.map_judges_to_photos()

    def map_judges_to_photos(self):
        """Identify which of the judges in the DB have photos.

        We iterate over the entire collection of judges, identifying which have
        photos. We could instead iterate over the photos, but that increases
        the risk of duplicate issues.
        """
        # Create a dict of judge paths, mapping paths to empty lists.
        judge_paths = os.listdir(os.path.join(judge_root, '128'))
        judge_map = {}
        for path in judge_paths:
            judge_map[path] = []

        # Iterate over the people, attempting to look them up in the list
        people = Person.objects.filter(is_alias_of=None)
        for person in people:
            slug_name = slugify("%s %s" % (person.name_last,
                                           person.name_first)) + ".jpeg"
            if person.date_granularity_dob == GRANULARITY_DAY:
                slug_name_dob = slug_name.rsplit('.')[0] + date_format(
                        person.date_dob, "-Y-m-d") + ".jpeg"
            else:
                slug_name_dob = None
            for name in [slug_name, slug_name_dob]:
                if name in judge_map:
                    # If there's a hit, add the path to the dict of judge paths.
                    judge_map[name].append(person)
                    break

        # After iterating, set all people to not have photos.
        if not self.debug:
            people.update(has_photo=False)

        found = 0
        missed = 0
        multi = 0
        for path, people in judge_map.items():
            if len(people) == 0:
                print "WARNING: Did not find a judge for %s" % path
                missed += 1
            if len(people) == 1:
                person = people[0]
                print "INFO: Updating judge %s" % person
                found += 1
                if not self.debug:
                    person.has_photo = True
                    person.save()
            if len(people) > 1:
                print "WARNING: Found more than one match for %s\nFound:" % path
                for person in people:
                    print "    %s - %s" % (person, person.date_dob)
                multi += 1

        print "\n\n%s Matches\n%s Missed\n%s Multiple results" % (found, missed,
                                                              multi)
