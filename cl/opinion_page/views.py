from collections import defaultdict, OrderedDict
from itertools import groupby

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.urls import reverse
from django.db.models import F, Prefetch
from django.http import HttpResponseRedirect
from django.http.response import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from reporters_db import EDITIONS, NAMES_TO_EDITIONS, REPORTERS, \
    VARIATIONS_ONLY
from rest_framework.status import HTTP_404_NOT_FOUND, HTTP_300_MULTIPLE_CHOICES

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.lib import search_utils, sunburnt
from cl.lib.bot_detector import is_bot, is_og_bot
from cl.lib.model_helpers import suppress_autotime, choices_to_csv
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted
from cl.lib.string_utils import trunc
from cl.opinion_page.forms import CitationRedirectorForm, DocketEntryFilterForm
from cl.people_db.models import AttorneyOrganization, Role, CriminalCount
from cl.people_db.tasks import make_thumb_if_needed
from cl.recap.constants import COURT_TIMEZONES
from cl.search.models import Citation, Docket, OpinionCluster, RECAPDocument


def redirect_docket_recap(request, court, pacer_case_id):
    docket = get_object_or_404(Docket, pacer_case_id=pacer_case_id,
                               court=court)
    return HttpResponseRedirect(reverse('view_docket', args=[docket.pk,
                                                             docket.slug]))


def core_docket_data(request, pk):
    """Gather the core data for a docket, party, or IDB page."""
    docket = get_object_or_404(Docket, pk=pk)
    title = ', '.join([s for s in [
        trunc(best_case_name(docket), 100, ellipsis="..."),
        docket.docket_number,
    ] if s.strip()])

    try:
        fave = Favorite.objects.get(docket_id=docket.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'docket_id': docket.pk,
            'name': trunc(best_case_name(docket), 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    has_alert = False
    if request.user.is_authenticated:
        has_alert = DocketAlert.objects.filter(docket=docket,
                                               user=request.user).exists()

    return docket, {
        'docket': docket,
        'title': title,
        'favorite_form': favorite_form,
        'has_alert': has_alert,
        'timezone': COURT_TIMEZONES.get(docket.court_id, 'US/Eastern'),
        'private': docket.blocked,
    }


@ratelimit_if_not_whitelisted
def view_docket(request, pk, slug):
    docket, context = core_docket_data(request, pk)
    if not is_bot(request):
        with suppress_autotime(docket, ['date_modified']):
            cached_count = docket.view_count
            docket.view_count = F('view_count') + 1
            docket.save()
            docket.view_count = cached_count + 1

    de_list = docket.docket_entries.all().prefetch_related('recap_documents')
    form = DocketEntryFilterForm(request.GET)
    if form.is_valid():
        cd = form.cleaned_data
        if cd.get('entry_gte'):
            de_list = de_list.filter(entry_number__gte=cd['entry_gte'])
        if cd.get('entry_lte'):
            de_list = de_list.filter(entry_number__lte=cd['entry_lte'])
        if cd.get('filed_after'):
            de_list = de_list.filter(date_filed__gte=cd['filed_after'])
        if cd.get('filed_before'):
            de_list = de_list.filter(date_filed__lte=cd['filed_before'])
        if cd.get('order_by') == DocketEntryFilterForm.DESCENDING:
            de_list = de_list.order_by('-recap_sequence_number',
                                       '-entry_number')

    paginator = Paginator(de_list, 200, orphans=10)
    page = request.GET.get('page')
    try:
        docket_entries = paginator.page(page)
    except PageNotAnInteger:
        docket_entries = paginator.page(1)
    except EmptyPage:
        docket_entries = paginator.page(paginator.num_pages)

    context.update({
        'parties': docket.parties.exists(),  # Needed to show/hide parties tab.
        'docket_entries': docket_entries,
        'form': form,
        'get_string': search_utils.make_get_string(request),
    })
    return render(request, 'view_docket.html', context)


@ratelimit_if_not_whitelisted
def view_parties(request, docket_id, slug):
    """Show the parties and attorneys tab on the docket."""
    docket, context = core_docket_data(request, docket_id)

    # We work with this data at the level of party_types so that we can group
    # the parties by this field. From there, we do a whole mess of prefetching,
    # which reduces the number of queries needed for this down to four instead
    # of potentially thousands (good times!)
    party_types = (
        docket.party_types
            .select_related('party')
            .prefetch_related(
                Prefetch(
                    'party__roles',
                    queryset=Role.objects.filter(docket=docket).order_by(
                        'attorney_id', 'role', 'role_raw', 'date_action'
                    ).select_related(
                        'attorney'
                    ).prefetch_related(
                        Prefetch(
                            'attorney__organizations',
                            queryset=AttorneyOrganization.objects.filter(
                                attorney_organization_associations__docket=docket
                            ).distinct(),
                            to_attr='firms_in_docket',
                        )
                    )
                ),
                Prefetch(
                    'criminal_counts',
                    queryset=CriminalCount.objects.all().order_by('status')
                ),
                'criminal_complaints',
            ).order_by('name', 'party__name')
    )

    parties = []
    for party_type_name, party_types in groupby(party_types, lambda x: x.name):
        party_types = list(party_types)
        parties.append({
            'party_type_name': party_type_name,
            'party_type_objects': party_types
        })

    context.update({
        'parties': parties,
        'docket_entries': docket.docket_entries.exists(),
    })
    return render(request, 'docket_parties.html', context)


@ratelimit_if_not_whitelisted
def docket_idb_data(request, docket_id, slug):
    docket, context = core_docket_data(request, docket_id)
    context.update({
        'parties': docket.parties.exists(),  # Needed to show/hide parties tab.
        'docket_entries': docket.docket_entries.exists(),
        'origin_csv': choices_to_csv(docket.idb_data, 'origin'),
        'jurisdiction_csv': choices_to_csv(docket.idb_data, 'jurisdiction'),
        'arbitration_csv': choices_to_csv(docket.idb_data,
                                          'arbitration_at_filing'),
        'class_action_csv': choices_to_csv(docket.idb_data,
                                           'termination_class_action_status'),
        'procedural_progress_csv': choices_to_csv(docket.idb_data,
                                                  'procedural_progress'),
        'disposition_csv': choices_to_csv(docket.idb_data, 'disposition'),
        'nature_of_judgment_csv': choices_to_csv(docket.idb_data,
                                                 'nature_of_judgement'),
        'judgment_csv': choices_to_csv(docket.idb_data, 'judgment'),
        'pro_se_csv': choices_to_csv(docket.idb_data, 'pro_se'),
    })
    return render(request, 'docket_idb_data.html', context)


def make_rd_title(rd):
    de = rd.docket_entry
    d = de.docket
    return '{desc}#{doc_num}{att_num} in {case_name} ({court}{docket_number})'.format(
        desc='%s &ndash; ' % rd.description if rd.description else '',
        doc_num=rd.document_number,
        att_num=', Att. #%s' % rd.attachment_number if
                rd.document_type == RECAPDocument.ATTACHMENT else '',
        case_name=best_case_name(d),
        court=d.court.citation_string,
        docket_number=', %s' % d.docket_number if d.docket_number else '',
    )


@ratelimit_if_not_whitelisted
def view_recap_document(request, docket_id=None, doc_num=None,  att_num=None,
                        slug=''):
    """This view can either load an attachment or a regular document,
    depending on the URL pattern that is matched.
    """
    item = get_object_or_404(
        RECAPDocument,
        docket_entry__docket__id=docket_id,
        document_number=doc_num,
        attachment_number=att_num,
    )
    title = make_rd_title(item)
    if is_og_bot(request):
        make_thumb_if_needed(item)
        item.refresh_from_db()
    try:
        fave = Favorite.objects.get(recap_doc_id=item.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'recap_doc_id': item.pk,
            'name': trunc(title, 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    return render(request, 'recap_document.html', {
        'document': item,
        'title': title,
        'favorite_form': favorite_form,
        'private': True,  # Always True for RECAP docs.
    })


@never_cache
@ratelimit_if_not_whitelisted
def view_opinion(request, pk, _):
    """Using the cluster ID, return the cluster of opinions.

    We also test if the cluster ID is a favorite for the user, and send data
    if needed. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, cluster, title and favorite information
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = ', '.join([s for s in [
        trunc(best_case_name(cluster), 100, ellipsis="..."),
        cluster.citation_string,
    ] if s.strip()])
    has_downloads = False
    for sub_opinion in cluster.sub_opinions.all():
        if sub_opinion.local_path or sub_opinion.download_url:
            has_downloads = True
            break
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(cluster_id=cluster.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={
            'cluster_id': cluster.pk,
            'name': trunc(best_case_name(cluster), 100, ellipsis='...'),
        })
    else:
        favorite_form = FavoriteForm(instance=fave)

    if not is_bot(request):
        # Get the citing results from Solr for speed. Only do this for humans
        # to save on disk usage.
        conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        q = {
            'q': 'cites:({ids})'.format(
                ids=' OR '.join([str(pk) for pk in
                                 (cluster.sub_opinions
                                  .values_list('pk', flat=True))])
            ),
            'rows': 5,
            'start': 0,
            'sort': 'citeCount desc',
            'caller': 'view_opinion',
        }
        citing_clusters = conn.raw_query(**q).execute()

        # Get recommendations with MoreLikeThis query (cached)
        mlt_cache_key = 'opinion-mlt%s' % pk
        recommendations = cache.get(mlt_cache_key)

        if recommendations is None:
            mlt_query = conn.query(id=pk)\
                .mlt('text', count=5)\
                .field_limit(fields=['id', 'caseName', 'absolute_url'])
            recommendations = mlt_query.execute().more_like_this.docs

            cache.set(mlt_cache_key, recommendations, 60 * 60 * 24)
    else:
        citing_clusters = None
        recommendations = None

    return render(request, 'view_opinion.html', {
        'title': title,
        'cluster': cluster,
        'has_downloads': has_downloads,
        'favorite_form': favorite_form,
        'get_string': get_string,
        'private': cluster.blocked,
        'citing_clusters': citing_clusters,
        'top_authorities': cluster.authorities[:5],
        'recommendations': recommendations,
    })


@ratelimit_if_not_whitelisted
def view_authorities(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)

    return render(request, 'view_opinion_authorities.html', {
        'title': '%s, %s' % (
            trunc(best_case_name(cluster), 100),
            cluster.citation_string
        ),
        'cluster': cluster,
        'private': cluster.blocked or cluster.has_private_authority,
        'authorities': cluster.authorities.order_by('case_name'),
    })


@ratelimit_if_not_whitelisted
def cluster_visualizations(request, pk, slug):
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    return render(request, 'view_opinion_visualizations.html', {
        'title': '%s, %s' % (
            trunc(best_case_name(cluster), 100),
            cluster.citation_string
        ),
        'cluster': cluster,
        'private': cluster.blocked or cluster.has_private_authority,
    })


def throw_404(request, context):
    return render(request, 'volumes_for_reporter.html', context,
                  status=HTTP_404_NOT_FOUND)


def reporter_or_volume_handler(request, reporter, volume=None):
    """Show all the volumes for a given reporter abbreviation or all the cases
    for a reporter-volume dyad.

    Two things going on here:
    1. We don't know which reporter the user actually wants when they provide
       an ambiguous abbreviation. Just show them all.
    2. We want to also show off that we know all these reporter abbreviations.
    """
    root_reporter = EDITIONS.get(reporter)
    if not root_reporter:
        return throw_404(request, {
            'no_reporters': True,
            'reporter': reporter,
            'private': True,
        })

    volume_names = [r['name'] for r in REPORTERS[root_reporter]]
    variation_names = {}
    variation_abbrevs = VARIATIONS_ONLY.get(reporter, [])
    for abbrev in variation_abbrevs:
        for r in REPORTERS[abbrev]:
            if r['name'] not in volume_names:
                variation_names[r['name']] = abbrev

    if volume is None:
        # Show all the volumes for the case
        volumes_in_reporter = list(Citation.objects
                                   .filter(reporter=reporter)
                                   .order_by('reporter', 'volume')
                                   .values_list('volume', flat=True)
                                   .distinct())

        if not volumes_in_reporter:
            return throw_404(request, {
                'no_volumes': True,
                'reporter': reporter,
                'volume_names': volume_names,
                'private': True,
            })

        return render(
            request,
            'volumes_for_reporter.html',
            {
                'reporter': reporter,
                'volume_names': volume_names,
                'volumes': volumes_in_reporter,
                'variation_names': variation_names,
                'private': False,
            },
        )
    else:
        # Show all the cases for a volume-reporter dyad
        cases_in_volume = (OpinionCluster.objects
                           .filter(citations__reporter=reporter,
                                   citations__volume=volume)
                           .order_by('date_filed', 'citations__page'))

        if not cases_in_volume:
            return throw_404(request, {
                'no_cases': True,
                'reporter': reporter,
                'volume_names': volume_names,
                'volume': volume,
                'private': True,
            })

        paginator = Paginator(cases_in_volume, 250, orphans=5)
        page = request.GET.get('page')
        try:
            cases = paginator.page(page)
        except PageNotAnInteger:
            cases = paginator.page(1)
        except EmptyPage:
            cases = paginator.page(paginator.num_pages)

        return render(request, 'volumes_for_reporter.html', {
            'cases': cases,
            'reporter': reporter,
            'variation_names': variation_names,
            'volume': volume,
            'volume_names': volume_names,
            'private': True,
        })


def make_reporter_dict():
    """Make a dict of reporter names and abbreviations

    The format here is something like:

        {
            "Atlantic Reporter": ['A.', 'A.2d', 'A.3d'],
        }
    """
    reporters_in_db = list(Citation.objects
                           .order_by('reporter')
                           .values_list('reporter', flat=True)
                           .distinct())

    reporters = defaultdict(list)
    for name, abbrev_list in NAMES_TO_EDITIONS.items():
        for abbrev in abbrev_list:
            if abbrev in reporters_in_db:
                reporters[name].append(abbrev)
    reporters = OrderedDict(sorted(reporters.items(), key=lambda t: t[0]))
    return reporters


def citation_handler(request, reporter, volume, page):
    """Load the page when somebody looks up a complete citation"""

    citation_str = " ".join([volume, reporter, page])
    try:
        clusters = OpinionCluster.objects.filter(citation=citation_str)
    except ValueError:
        # Unable to parse the citation.
        cluster_count = 0
    else:
        cluster_count = clusters.count()

    # Show the correct page....
    if cluster_count == 0:
        # No results for an otherwise valid citation.
        return render(
            request,
            'citation_redirect_info_page.html',
            {
                'none_found': True,
                'citation_str': citation_str,
                'private': True,
            },
            status=HTTP_404_NOT_FOUND,
        )

    elif cluster_count == 1:
        # Total success. Redirect to correct location.
        return HttpResponseRedirect(
            clusters[0].get_absolute_url()
        )

    elif cluster_count > 1:
        # Multiple results. Show them.
        return HttpResponse(
            content=loader.render_to_string(
                'citation_redirect_info_page.html', {
                    'too_many': True,
                    'citation_str': citation_str,
                    'clusters': clusters,
                    'private': True,
                },
                request=request
            ),
            status=HTTP_300_MULTIPLE_CHOICES,
        )


def citation_redirector(request, reporter=None, volume=None, page=None):
    """Take a citation URL and use it to redirect the user to the canonical page
    for that citation.

    This uses the same infrastructure as the thing that identifies citations in
    the text of opinions.
    """
    if request.method == 'POST':
        form = CitationRedirectorForm(request.POST)
        if form.is_valid():
            # Redirect to the page with the right values
            cd = form.cleaned_data
            return HttpResponseRedirect(
                reverse('citation_redirector', kwargs=cd)
            )
        else:
            # Error in form, somehow.
            return render(request, 'citation_redirect_info_page.html', {
                'show_homepage': True,
                'form': form,
                'private': True
            })
    else:
        if all(_ is None for _ in (reporter, volume, page)):
            # No parameters. Show the standard page.
            form = CitationRedirectorForm()
            reporter_dict = make_reporter_dict()
            return render(request, 'citation_redirect_info_page.html', {
                'show_homepage': True,
                'reporter_dict': reporter_dict,
                'form': form,
                'private': False,
            })
        else:
            # We have a reporter (show volumes in it), a volume (show cases in
            # it), or a citation (show matching citation(s))
            if reporter and volume and page:
                return citation_handler(request, reporter, volume, page)
            elif reporter and volume and page is None:
                return reporter_or_volume_handler(request, reporter, volume)
            elif reporter and volume is None and page is None:
                return reporter_or_volume_handler(request, reporter)


@ensure_csrf_cookie
def block_item(request):
    """Block an item from search results using AJAX"""
    if request.is_ajax() and request.user.is_superuser:
        obj_type = request.POST['type']
        pk = request.POST['id']
        if obj_type == 'docket':
            # Block the docket
            d = get_object_or_404(Docket, pk=pk)
            d.blocked = True
            d.date_blocked = now()
            d.save()
        elif obj_type == 'cluster':
            # Block the cluster and the docket
            cluster = get_object_or_404(OpinionCluster, pk=pk)
            cluster.blocked = True
            cluster.date_blocked = now()
            cluster.save(index=False)
            cluster.docket.blocked = True
            cluster.docket.date_blocked = now()
            cluster.docket.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request",
        )
