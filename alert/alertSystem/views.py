# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from alert.alertSystem.models import *
from alert.userHandling.forms import *
from alert.userHandling.models import *
from alert.lib.encode_decode import ascii_to_num
from django.contrib.sites.models import Site
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404, get_list_or_404
from django.template import RequestContext
from django.template.defaultfilters import slugify
from django.utils import simplejson
from django.views.decorators.cache import cache_page
import string
import traceback


@cache_page(60*5)
def redirect_short_url(request, encoded_string):
    """Redirect a user to the CourtListener site from the crt.li site."""

    # strip any GET arguments from the string
    index = string.find(encoded_string, "&")
    if index != -1:
        # there's an ampersand. Strip the GET params.
        encoded_string = encoded_string[0:index]

    # Decode the string to find the object ID, and construct a link.
    num = ascii_to_num(encoded_string)

    # Get the document or throw a 404
    doc = get_object_or_404(Document, documentUUID = num)

    # Construct the URL
    slug = doc.citation.slug
    court = str(doc.court.courtUUID)
    current_site = Site.objects.get_current()
    URL = "http://" + current_site.domain + "/" + court + "/" + \
        encoded_string + "/" + slug + "/"
    return HttpResponsePermanentRedirect(URL)


@cache_page(60*5)
def viewCase(request, court, id, casename):
    '''
    Take a court, an ID, and a casename, and return the document. Casename
    isn't used, and can be anything.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite, so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    '''

    # Decode the id string back to an int
    id = ascii_to_num(id)

    # Look up the court, document, title and favorite information
    doc   = get_object_or_404(Document, documentUUID = id)
    ct    = get_object_or_404(Court, courtUUID = court)
    title = doc.citation.caseNameShort
    user  = request.user
    try:
        # Get the favorite, if possible
        fave = Favorite.objects.get(doc_id = doc.documentUUID, user = request.user)
        favorite_form = FavoriteForm(instance=fave)
    except ObjectDoesNotExist:
        favorite_form = FavoriteForm(initial = {'doc_id': doc.documentUUID})

    return render_to_response('display_cases.html', {'title': title,
        'doc': doc, 'court': ct, 'favorite_form': favorite_form},
        RequestContext(request))


@login_required
def save_or_update_favorite(request):
    '''Saves or updates a favorite.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a favorite in the database for a specific user. If the user
    already has the document favorited, it updates the favorite with the new
    information. If not, it creates a new favorite. Orphaned tags are deleted.
    '''
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        try:
            doc_id = request.POST['doc_id']
        except:
            return HttpResponse("Unknown doc_id")

        # Clean up the values returned from the tag field so they are a list
        # not a string. Needed b/c of the autocomplete widget returns a string
        # rather than a list.
        new_tags_data = []
        old_tags_data = []
        local_post_data = request.POST.copy()
        if len(local_post_data['tags']) > 0:
            # If we have more than zero tags, do some work here...
            local_post_data['tags'] = local_post_data['tags'].split(',')

            # For each value in the result, see if any of them are new. Set those
            # aside for later processing.
            for tag in local_post_data['tags']:
                # New tags look like NEWTAG_tagValue_END
                split_tag = tag.split('_')
                if split_tag[0] == 'NEWTAG' and split_tag[-1] == 'END':
                    # New tag. Add to a list of new tag values for later processing
                    new_tags_data.append("_".join(split_tag[1:-1]))
                else:
                    # Old tag, just append the ID
                    old_tags_data.append(tag)

            # Associate the new clean list with the one that we're going to process.
            local_post_data['tags'] = old_tags_data

        # Associate the user with the form
        local_post_data['user'] = request.user.id

        # Get the favorite, if it already exists for the user. Otherwise, create it.
        doc = Document.objects.get(documentUUID = doc_id)
        fave, created = Favorite.objects.get_or_create(user = request.user, doc_id = doc)
        form = FavoriteForm(local_post_data, instance = fave)

        if not created:
            # If it's an old favorite that is getting updated, we need to delete
            # any of its old tags that aren't part of the new favorite, if they
            # aren't associated with another favorite. This should keep orphans
            # out of the system.
            for tag in fave.tags.all():
                # for all of the tags in the old favorite in the DB...
                if tag.tag not in old_tags_data:
                    # if this tag is not still used in the updated favorite...
                    faves_using_tag = Favorite.objects.filter(tags = tag, user = request.user)
                    if len(faves_using_tag) == 1:
                        # Only the one fave is tagged with it. Delete it.
                        tag.delete()


        if form.is_valid():
            cd = form.cleaned_data

            # Add new tags to the system
            tags = list(cd['tags'])
            for tag in new_tags_data:
                try:
                    tag, created = Tag.objects.get_or_create(user = request.user, tag = tag)
                    tags.append(tag.id)
                except IntegrityError:
                    # The tag has already been created, possibly by double clicking
                    # the save button or on another tab.
                    pass

            # Then we update it
            fave.notes = cd['notes']
            fave.tags = tags
            fave.save()

        else:
            # invalid form...print errors...
            HttpResponse("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponse("Not an ajax request.")


@login_required
def delete_favorite(request):
    '''
    Deletes a favorite for a user using an ajax call and post data. If a tag
    will be orphaned after the deletion, the tag is deleted as well.
    '''
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        try:
            doc_id = request.POST['doc_id']
        except:
            return HttpResponse("Unknown doc_id")
        try:
            fave = Favorite.objects.get(user = request.user, doc_id = doc_id)
            for tag in fave.tags.all():
                # each of the tags associated with the favorite should be
                # deleted, if it will soon be an orphan
                try:
                    faves_using_tag = Favorite.objects.filter(tags = tag, user = request.user)
                    if len(faves_using_tag) == 1:
                        # Only the one fave is tagged with it. Delete it.
                        tag.delete()
                except:
                    # Failure for that tag
                    pass

            # Finally, delete the favorite
            fave.delete()
        except:
            # Couldn't find the document for some reason. Maybe they already
            # deleted it?
            pass

        return HttpResponse("It worked.")

    else:
        return HttpResponse("Not an ajax request.")



@login_required
def ajax_tags_typeahead(request):
    '''Returns the top ten typeahead results for a query.

    Given a query of some number of letters, returns the top ten tags containing
    those letters, alphabetically.

    Thus, if q == co, it might return "Constitutional Law".
    '''
    q = request.GET['q']
    tags = Tag.objects.filter(tag__icontains = q, user = request.user)\
        .order_by('tag')[:10]

    # Allow users to create a new tag, unless there is an exact match
    if tags.count() > 0:
        for tag in tags:
            if tag.tag == q:
                exact_tag_exists = True
                break
            else:
                exact_tag_exists = False
    else:
        exact_tag_exists = False

    tagsList = []
    keys = ['id', 'name']
    if not exact_tag_exists:
        # A tag of this value doesn't exist, allow the user to make it.
        tagsList.append(dict(zip(keys, ['NEWTAG_' + q + '_END', "Create: " + q])))

    # convert the tags to the right format
    for tag in tags:
        tagsList.append(dict(zip(keys, [str(tag.id), tag.tag])))

    return HttpResponse(simplejson.dumps(tagsList), mimetype = 'application/javascript')


@login_required
def view_opinions_by_tag(request, tagValues):
    '''Displays opinions tagged by a user with certain tags.

    Given a set of tags separated by pluses, pipes, and parentheses, unpack
    the set of tags and display the correct opinions. Currently only supports
    pluses (AND filters), and pipes (OR filters).

    See issue #167 for more details, and see this link for more implementation
    thoughts: http://stackoverflow.com/questions/108193/
    '''
    if '|' in tagValues:
        # it's an or query.
        tagList = tagValues.split('|')
        tags = Tag.objects.filter(tag__in = tagList, user = request.user)\
            .values_list('pk', flat=True)
        faves = Favorite.objects.filter(tags__in = list(tags), user = request.user).distinct()

    elif '+' in tagValues:
        # it's an and query - not very efficient.
        tagList = tagValues.split('+')
        tagObject = Tag.objects.get(tag = tagList[0], user = request.user)
        faves = Favorite.objects.filter(tags = tagObject, user = request.user)
        for tag in tagList[1:]:
            tagObject = Tag.objects.filter(tag = tag, user = request.user)
            faves = faves.filter(tags = tagObject, user = request.user).distinct()

    else:
        # it's a single tag
        tag = Tag.objects.get(tag = tagValues, user = request.user)
        faves = Favorite.objects.filter(tags = tag, user = request.user)

    # next, we paginate we will show ten results/page
    paginator = Paginator(faves, 10)

    # this will fail when the search fails, so try/except is needed.
    try:
        numResults = paginator.count
    except:
        numResults = 0

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # only allow queries up to page 1000.
    if page > 1000:
        return render_to_response('tag-results.html', {'over_limit': True,
            'tagValues': tagValues},
            RequestContext(request))

    # If page request is out of range, deliver last page of results.
    try:
        faves = paginator.page(page)
    except (EmptyPage, InvalidPage):
        faves = paginator.page(paginator.num_pages)
    except:
        faves = []

    return render_to_response('tag-results.html', {'faves': faves,
        'numResults': numResults, 'tagValues': tagValues},
        RequestContext(request))


@cache_page(60*15)
def viewDocumentListByCourt(request, court):
    '''
    Show documents for a court, ten at a time
    '''
    from django.core.paginator import Paginator, InvalidPage, EmptyPage
    if court == "all":
        # we get all records, sorted by dateFiled.
        docs = Document.objects.order_by("-dateFiled")
        ct = "All courts"
    else:
        ct = Court.objects.get(courtUUID = court)
        docs = Document.objects.filter(court = ct).order_by("-dateFiled")

    # we will show ten docs/page
    paginator = Paginator(docs, 10)

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # only allow queries up to page 100.
    if page > 100:
        return render_to_response('view_documents_by_court.html',
            {'over_limit': True}, RequestContext(request))

    # If page request is out of range, deliver last page of results.
    try:
        documents = paginator.page(page)
    except (EmptyPage, InvalidPage):
        documents = paginator.page(paginator.num_pages)

    return render_to_response('view_documents_by_court.html', {'title': ct,
        "documents": documents}, RequestContext(request))
