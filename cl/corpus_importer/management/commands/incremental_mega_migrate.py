"""A script to migrate the old data from one database to another, transforming
it as necessary along the way.
"""
import logging
from collections import Counter
from datetime import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.db.models import Q
from django.utils.timezone import make_aware, utc, now
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.alerts.models import (
    Alert as AlertNew,
)
from cl.audio.models import (
    Audio as AudioNew,
)
from cl.corpus_importer.models_legacy import (
    Docket as DocketOld,
    Document as DocumentOld,
)
from cl.donate.models import (
    Donation as DonationNew,
)
from cl.favorites.models import (
    Favorite as FavoriteNew,
)
from cl.lib.argparse_types import valid_date_time
from cl.lib.model_helpers import disable_auto_now_fields
from cl.search.models import (
    Docket as DocketNew,
    Opinion as OpinionNew,
    OpinionsCited as OpinionsCitedNew,
    OpinionCluster as OpinionClusterNew,
    Court as CourtNew,
)
from cl.stats.models import Stat
from cl.users.models import (
    UserProfile as UserProfileNew
)

logger = logging.getLogger(__name__)

# Disable auto_now and auto_now_add fields so that they can be copied over from
# the old database.
disable_auto_now_fields(AlertNew, AudioNew, FavoriteNew, DocketNew, CourtNew,
                        OpinionClusterNew, OpinionNew)


class Command(BaseCommand):
    help = 'Migrate all data for all apps from one DB to another.'
    case_name_tweaker = CaseNameTweaker()
    the_beginning_of_time = make_aware(datetime(1750, 1, 1), utc)

    def add_arguments(self, parser):
        parser.add_argument(
            '--search',
            action='store_true',
            default=False,
            help="Do migrations for the models in the search app: opinions, "
                 "oral args, and dockets"
        )
        parser.add_argument(
            '--citations',
            action='store_true',
            default=False,
            help="Do migrations for citations between objects"
        )
        parser.add_argument(
            '--user-stuff',
            action='store_true',
            default=False,
            help="Do migrations for user-related stuff (bar memberships, "
                 "alerts, favorites, donations, etc.)"
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            default=False,
            help="Do migrations for stats"
        )
        parser.add_argument(
            '--start',
            type=valid_date_time,
            default=None,
            help="If provided, items modified on or after this date will be "
                 "migrated as best possible (some types will not be migrated "
                 "or will be migrated ignoring this parameter). (ISO-8601 "
                 "format)"
        )

    def handle(self, *args, **options):
        self.start = options['start']
        if options['search']:
            self.migrate_opinions_oral_args_and_dockets()
        if options['citations']:
            self.migrate_intra_object_citations()
        if options['user_stuff']:
            self.migrate_users(options['start'])
        if options['stats']:
            self.migrate_stats()

    @staticmethod
    def _none_to_blank(value):
        """Normalizes a field to be u'' instead of None. This is needed b/c the
        old models erroneously had null=True on a number of text fields. If they
        were set up properly according to Django conventions, they'd disallow
        null and have been set to blank instead.
        """
        if value is None:
            return u''
        else:
            return value

    def _get_case_names(self, case_name_orig):
        case_name_len = len(case_name_orig)
        max_case_name_len = 150
        if case_name_len > max_case_name_len:
            case_name = u''
            case_name_full = case_name_orig
        else:
            case_name = case_name_orig
            case_name_full = u''
        case_name_short = self.case_name_tweaker.make_case_name_short(
            case_name_orig)
        return case_name, case_name_full, case_name_short

    def _print_progress(self, progress, total, errors=None):
        """Print the progress of a migration subcomponent.

        If errors is provided it should be a dict of the form:

          errors = {
            'KeyError': 1982,
            'SomeOtherError': 42,
          }

        That is, error keys should be descriptive strings, and their values
        should be counts of how many times it happened.

        Note that using a collections.Counter object for this is very handy.
        """
        if not errors:
            errors = {}
        self.stdout.write("\r\tMigrated %s of %s (%d%%). Skipped %s: (%s)." % (
            progress,
            total,
            float(progress) / total * 100,
            sum(errors.values()),
            ', '.join(['%s: %s' % (k, v) for k, v in errors.items()]),
        ), ending='')
        self.stdout.flush()

    def migrate_opinions_oral_args_and_dockets(self):
        """Migrate the core objects across, diffing as you go.

        :param start_date: Items changed after this date will be processed.
        :return: None
        """
        self.stdout.write("Migrating dockets, audio files, and opinions...")
        # Find dockets modified after date or with sub-items modified after
        # date.
        q = Q(date_modified__gte=self.start)
        q |= Q(documents__date_modified__gte=self.start)
        q |= Q(audio_files__date_modified__gte=self.start)
        old_dockets = DocketOld.objects.using('old').filter(q)

        for old_docket in old_dockets:
            try:
                old_audio = old_docket.audio_files.all()[0]
            except IndexError:
                old_audio = None
            try:
                old_document = old_docket.documents.all()[0]
            except IndexError:
                old_document = None
            if old_document is None and old_audio is None:
                continue

            if old_document is not None:
                old_citation = old_document.citation
                old_docket.case_name, old_docket.case_name_full, old_docket.case_name_short = self._get_case_names(
                    old_citation.case_name)
            else:
                # Fall back on the docket if needed. Assumes they docket and
                # document case_names are always the same.
                old_docket.case_name, old_docket.case_name_full, old_docket.case_name_short = self._get_case_names(
                        old_docket.case_name)
            if old_audio is not None:
                old_audio.case_name, old_audio.case_name_full, old_audio.case_name_short = self._get_case_names(
                    old_audio.case_name)


            # Courts are in place thanks to initial data. Get the court.
            court = CourtNew.objects.get(pk=old_docket.court_id)

            # Do Dockets
            try:
                existing_docket = (DocketNew.objects
                                   .using('default')
                                   .get(pk=old_docket.pk))
            except DocketNew.DoesNotExist:
                existing_docket = None
            if existing_docket is not None:
                # Simply skip. All differences have been resolved by hand.
                new_docket = existing_docket
            else:
                # New docket, just create it.
                new_docket = DocketNew(
                    pk=old_docket.pk,
                    date_modified=old_docket.date_modified,
                    date_created=old_docket.date_modified,
                    court=court,
                    case_name=old_docket.case_name,
                    case_name_full=old_docket.case_name_full,
                    case_name_short=old_docket.case_name_short,
                    slug=self._none_to_blank(old_docket.slug),
                    docket_number=self._none_to_blank(
                        old_citation.docket_number),
                    date_blocked=old_docket.date_blocked,
                    blocked=old_docket.blocked,
                )
                if old_audio is not None:
                    new_docket.date_argued = old_audio.date_argued
                #new_docket.save(using='default')

            # Do Documents/Clusters
            if old_document is not None:
                try:
                    existing_oc = (OpinionClusterNew.objects
                                   .using('default')
                                   .get(pk=old_document.pk))
                except OpinionClusterNew.DoesNotExist:
                    existing_oc = None
                try:
                    existing_o = (OpinionNew.objects
                                  .using('default')
                                  .get(pk=old_document.pk))
                except OpinionNew.DoesNotExist:
                    existing_o = None
                if existing_oc is not None or existing_o is not None:
                    self.merge_citation_document_cluster(
                            old_document, old_citation, old_docket, existing_oc, existing_o)
                else:
                    # New item. Just add it.
                    pass

    def _print_attr(self, attr_name, old, new, yesno=False):
        old_val = getattr(old, attr_name, old)
        new_val = getattr(new, attr_name, new)

        if old_val and old_val != new_val:
            if yesno:
                self.stdout.write("  {attr_name} has changed.".format(
                    attr_name=attr_name
                ).decode('utf-8'))
            else:
                self.stdout.write("  {attr_name}:\n    '{old}'\n    '{new}'\n".format(
                    attr_name=attr_name,
                    old=old_val,
                    new=new_val,
                ).decode('utf-8'))

    def merge_citation_document_cluster(self, old_document, old_citation,
                                        old_docket, existing_oc, existing_o):
        """Merge the items."""
        self.stdout.write("Comparing pk: %s with citation %s to new cluster "
                          "and opinion." % (old_document.pk, old_citation.pk))
        if existing_oc.date_modified >= self.start and \
                        old_document.date_modified >= self.start:
            self._print_attr('date_filed', old_document, existing_oc)
            self._print_attr('case_name_short', old_docket, existing_oc)
            self._print_attr('case_name', old_docket, existing_oc)
            self._print_attr('case_name_full', old_docket, existing_oc)
            self._print_attr('federal_cite_one', old_citation, existing_oc)
            self._print_attr('federal_cite_two', old_citation, existing_oc)
            self._print_attr('federal_cite_three', old_citation, existing_oc)
            self._print_attr('state_cite_one', old_citation, existing_oc)
            self._print_attr('state_cite_two', old_citation, existing_oc)
            self._print_attr('state_cite_three', old_citation, existing_oc)
            self._print_attr('state_cite_regional', old_citation, existing_oc)
            self._print_attr('specialty_cite_one', old_citation, existing_oc)
            self._print_attr('scotus_early_cite', old_citation, existing_oc)
            self._print_attr('lexis_cite', old_citation, existing_oc)
            self._print_attr('westlaw_cite', old_citation, existing_oc)
            self._print_attr('neutral_cite', old_citation, existing_oc)
            self._print_attr('scdb_id', old_document.supreme_court_db_id, existing_oc)
            self._print_attr('nature_of_suit', old_document, existing_oc)
            self._print_attr('blocked', old_document, existing_oc)

        if existing_o.date_modified >= self.start and \
                old_document.date_modified >= self.start:
            self._print_attr('sha1', old_document, existing_o)
            self._print_attr('download_url', old_document, existing_o)
            self._print_attr('plain_text', old_document, existing_o, yesno=True)
            self._print_attr('html', old_document, existing_o, yesno=True)
            self._print_attr('html_lawbox', old_document, existing_o, yesno=True)
            self._print_attr('extracted_by_ocr', old_document, existing_o)


    def merge_dockets(self, old, old_citation, existing):
        """Merge the elements of the old Docket into the existing one."""
        self.stdout.write("Comparing dockets with id: %s\n" % existing.pk)
        if old.case_name_short and old.case_name_short != existing.case_name_short:
            self.stdout.write("  case_name_short:\n    %s\n    %s\n".decode('utf-8') % (
                old.case_name_short, existing.case_name_short,
            ))
        if old.case_name and old.case_name != existing.case_name:
            self.stdout.write("  case_name:\n    %s\n    %s\n".decode('utf-8') % (
                old.case_name, existing.case_name,
            ))
        if old.case_name_full and old.case_name_full != existing.case_name_full:
            self.stdout.write("  case_name_full:\n    %s\n    %s\n".decode('utf-8') % (
                old.case_name_full, existing.case_name_full,
            ))
        if old_citation.docket_number and old_citation.docket_number != existing.docket_number:
            self.stdout.write("  docket_number:\n    %s\n    %s\n".decode('utf-8') % (
                old_citation.docket_number, existing.docket_number
            ))
        if old.blocked and not existing.blocked:
            self.stdout.write("  Old is blocked but new is not.")

    def migrate_intra_object_citations(self):
        """This method migrates the citations from one database to the other so
        that we don't have to run the citation finding algorithm immediately
        after the migration. Recall that in the legacy schema, Documents have a
        One-2-Many relationship with Citations. This algo handles two kinds of
        citations. The first is the simple case (1 to 1):

                        +--> C2--D2
                       /
            D1--cites--
                       \
                        +--> C3--D3

        This is handled by making a new connection such that D1 cites D2 and D3:

            D1 --cites--> D2

                  and

            D1 --cites--> D3

        The next kind of citation handled is more difficult. In this case,
        multiple Documents share a single Citation (1 to N).

                                 +--D2
                                 |
                        +--> C1--+
                       /         |
            D1--cites--          +--D3
                       \
                        +--> C2--D4

        This is handled by making the original document cite to all the targets:

            D1--cites-->D2
            D1--cites-->D3
            D1--cites-->D4

        """
        self.stdout.write("Migrating citation references to new database...")
        self.stdout.write("\tBuilding lookup dict of Citation IDs to "
                          "Document IDs...")
        # Build lookup dict in memory to avoid DB hits in a moment
        citation_document_pairs = DocumentOld.objects.using(
            'old'
        ).values_list(
            'citation_id',
            'pk'
        )
        # This dict takes the form of:
        #   {
        #      citation_id: [
        #        document_id1,
        #        document_id2,
        #        ...
        #      ],
        #      ...
        #   }
        #
        # The basic idea is that for any citation object's ID, you can lookup a
        # list of the documents that have it associated with them.
        cite_to_doc_dict = {}
        for citation_id, document_pk in citation_document_pairs:
            if citation_id in cite_to_doc_dict:
                cite_to_doc_dict[citation_id].append(document_pk)
            else:
                cite_to_doc_dict[citation_id] = [document_pk]

        # Iterate over all existing citations and move them to the correct place
        self.stdout.write(
            "\tBuilding list of all citations from Documents to Citations..."
        )
        DocumentCitationsOld = DocumentOld.cases_cited.through
        all_citations = DocumentCitationsOld.objects.using('old')
        total_count = all_citations.count()
        citation_values = all_citations.values_list(
            'document_id',
            'citation_id'
        )
        progress = 0
        errors = Counter()
        starting_point = 14514268  # For use with failed scripts.
        self._print_progress(progress, total_count, errors)
        new_citations = []
        for document_id, citation_id in citation_values:
            if progress < starting_point:
                errors.update(['AlreadyDone'])
                progress += 1
                continue
            # Early abort if the Citation object has been deleted from the DB.
            try:
                cited_documents = cite_to_doc_dict[citation_id]
            except KeyError:
                errors.update(['KeyError:OrphanCitation'])
                continue
            for cited_document in cited_documents:
                new_citations.append(
                    OpinionsCitedNew(
                        citing_opinion_id=document_id,
                        cited_opinion_id=cited_document,
                    )
                )
                if len(new_citations) % 100 == 0:
                    try:
                        OpinionsCitedNew.objects.using(
                            'default'
                        ).bulk_create(
                            new_citations
                        )
                    except IntegrityError:
                        # Loop through each opinion and save it, marking the
                        # failures. Could do this in the first place, but it's
                        # slower.
                        for new_citation in new_citations:
                            try:
                                new_citation.save()
                            except IntegrityError:
                                errors.update(['IntegrityError:CiteFromOrToMissingOpinionID'])
                                continue
                    new_citations = []

            progress += 1
            self._print_progress(progress, total_count, errors)

        # One final push if there's anything left.
        if len(new_citations) > 0:
            OpinionsCitedNew.objects.using('default').bulk_create(new_citations)
        self.stdout.write(u'')  # Newline

    def migrate_users(self, start_date):
        self.stdout.write("Migrating users, profiles, alerts, favorites, and "
                          "donations to the new database...")
        old_users = User.objects.using('old').all()
        num_users = old_users.count()

        progress = 0
        self._print_progress(progress, num_users)
        for old_user in old_users:
            old_profile = old_user.profile_legacy
            old_alerts = old_profile.alert.all()
            old_favorites = old_profile.favorite.all()
            old_donations = old_profile.donation.all()

            new_user = User(
                pk=old_user.pk,
                username=old_user.username,
                first_name=old_user.first_name,
                last_name=old_user.last_name,
                email=old_user.email,
                is_staff=old_user.is_staff,
                is_active=old_user.is_active,
                is_superuser=old_user.is_superuser,
                date_joined=old_user.date_joined,
                last_login=old_user.last_login,
                password=old_user.password,
            )
            new_user.save(using='default')

            new_profile = UserProfileNew(
                pk=old_profile.pk,
                user=new_user,
                stub_account=old_profile.stub_account,
                employer=old_profile.employer,
                address1=old_profile.address1,
                address2=old_profile.address2,
                city=old_profile.city,
                state=old_profile.state,
                zip_code=old_profile.zip_code,
                avatar=old_profile.avatar,
                wants_newsletter=old_profile.wants_newsletter,
                plaintext_preferred=old_profile.plaintext_preferred,
                activation_key=old_profile.activation_key,
                key_expires=old_profile.key_expires,
                email_confirmed=old_profile.email_confirmed,
            )
            new_profile.save(using='default')
            new_profile.barmembership.add(
                *[membership.pk for membership in
                  old_profile.barmembership.all()]
            )

            for old_alert in old_alerts:
                new_alert = AlertNew(
                    pk=old_alert.pk,
                    user=new_user,
                    date_created=self.the_beginning_of_time,
                    date_modified=self.the_beginning_of_time,
                    name=old_alert.name,
                    query=old_alert.query,
                    rate=old_alert.rate,
                    always_send_email=old_alert.always_send_email,
                    date_last_hit=old_alert.date_last_hit,
                )
                new_alert.save(using='default')

            for old_favorite in old_favorites:
                opinion_fave_pk = getattr(old_favorite.doc_id, 'pk', None)
                audio_fave_pk = getattr(old_favorite.audio_id, 'pk', None)
                if opinion_fave_pk is not None:
                    cluster = OpinionClusterNew.objects.get(
                        pk=opinion_fave_pk)
                    audio = None
                else:
                    cluster = None
                    audio = AudioNew.objects.get(pk=audio_fave_pk)
                new_favorite = FavoriteNew(
                    pk=old_favorite.pk,
                    user=new_user,
                    cluster_id=cluster,
                    audio_id=audio,
                    date_created=old_favorite.date_modified or now(),
                    date_modified=old_favorite.date_modified or now(),
                    name=old_favorite.name,
                    notes=old_favorite.notes,
                )
                new_favorite.save(using='default')

            for old_donation in old_donations:
                new_donation = DonationNew(
                    pk=old_donation.pk,
                    donor=new_user,
                    date_modified=old_donation.date_modified,
                    date_created=old_donation.date_created,
                    clearing_date=old_donation.clearing_date,
                    send_annual_reminder=old_donation.send_annual_reminder,
                    amount=old_donation.amount,
                    payment_provider=old_donation.payment_provider,
                    payment_id=old_donation.payment_id,
                    transaction_id=old_donation.transaction_id,
                    status=old_donation.status,
                    referrer=old_donation.referrer,
                )
                new_donation.save(using='default')

            progress += 1
            self._print_progress(progress, num_users)
        self.stdout.write(u'')  # Do a newline...

    def migrate_stats(self):
        self.stdout.write("Migrating stats to the new database...")
        # Stats use the same model in new and old, with no db_table definitions.
        # Makes life oh-so-easy.
        old_stats = Stat.objects.using('old').all()
        stat_count = old_stats.count()

        progress = 0
        self._print_progress(progress, stat_count)
        for old_stat in old_stats:
            old_stat.save(using='default')
            progress += 1
            self._print_progress(progress, stat_count)
        self.stdout.write(u'')  # Do a newline...
