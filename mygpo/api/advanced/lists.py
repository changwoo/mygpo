#
# This file is part of my.gpodder.org.
#
# my.gpodder.org is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# my.gpodder.org is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with my.gpodder.org. If not, see <http://www.gnu.org/licenses/>.
#

from functools import partial

from django.http import HttpResponse, HttpResponseBadRequest, \
     HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.contrib.sites.models import RequestSite
from django.template.defaultfilters import slugify

from mygpo.api.advanced.directory import podcast_data
from mygpo.api.httpresponse import JsonResponse
from mygpo.share.models import PodcastList
from mygpo.api.basic_auth import require_valid_user, check_username
from mygpo.api import models
from mygpo.core.models import Podcast
from mygpo.decorators import allowed_methods, repeat_on_conflict
from mygpo import migrate
from mygpo.api.simple import parse_subscription, format_podcast_list, \
     check_format
from mygpo.share.views import list_decorator



@csrf_exempt
@require_valid_user
@check_username
@check_format
@allowed_methods(['POST'])
def create(request, username, format):
    """ Creates a new podcast list and links to it in the Location header """

    title = request.GET.get('title', None)

    if not title:
        return HttpResponseBadRequest('Title missing')

    slug = slugify(title)

    if not slug:
        return HttpResponseBadRequest('Invalid title')

    user = migrate.get_or_migrate_user(request.user)

    plist = PodcastList.for_user_slug(user._id, slug)

    if plist:
        return HttpResponse('List already exists', status=409)

    urls = parse_subscription(request.raw_post_data, format)
    podcasts = [Podcast.for_url(url, create=True) for url in urls]
    podcast_ids = map(Podcast.get_id, podcasts)

    plist = PodcastList()
    plist.title = title
    plist.slug = slug
    plist.user = user._id
    plist.podcasts = podcast_ids
    plist.save()

    response = HttpResponse(status=201)
    list_url = reverse('api-get-list', args=[user.username, slug, format])
    response['Location'] = list_url

    return response



def _get_list_data(l, username, domain):
    return dict(
            title= l.title,
            name = l.slug,
            web  = 'http://%s%s' % (domain,
                reverse('list-show', args=[username, l.slug])),
        )


@csrf_exempt
@allowed_methods(['GET'])
def get_lists(request, username):
    """ Returns a list of all podcast lists by the given user """

    user = get_object_or_404(User, username=username)
    user = migrate.get_or_migrate_user(user)

    lists = PodcastList.for_user(user._id)

    site = RequestSite(request)

    get_data = partial(_get_list_data, username=user.username,
                domain=site.domain)
    lists_data = map(get_data, lists)

    return JsonResponse(lists_data)


@csrf_exempt
@check_format
@allowed_methods(['GET', 'PUT', 'DELETE'])
def podcast_list(request, *args, **kwargs):

    handlers = dict(
            GET = get_list,
            PUT = update_list,
            DELETE = delete_list,
        )

    return handlers[request.method](request, *args, **kwargs)


@list_decorator(must_own=False)
def get_list(request, plist, owner, format):
    """ Returns the contents of the podcast list """

    try:
        scale = int(request.GET.get('scale_logo', 64))
    except (TypeError, ValueError):
        return HttpResponseBadRequest('scale_logo has to be a numeric value')

    podcasts = Podcast.get_multi(plist.podcasts)

    domain = RequestSite(request).domain
    p_data = lambda p: podcast_data(p, domain, scale)
    title = '{title} by {username}'.format(title=plist.title,
            username=owner.username)

    return format_podcast_list(podcasts, format, title, json_map=p_data,
            jsonp_padding=request.GET.get('jsonp', ''),
            xml_template='podcasts.xml', request=request)


@require_valid_user
@list_decorator(must_own=True)
def update_list(request, plist, owner, format):
    """ Replaces the podcasts in the list and returns 204 No Content """

    user = migrate.get_or_migrate_user(request.user)
    is_own = owner == user

    if not is_own:
        return HttpResponseForbidden()

    urls = parse_subscription(request.raw_post_data, format)
    podcasts = [Podcast.for_url(url, create=True) for url in urls]
    podcast_ids = map(Podcast.get_id, podcasts)

    @repeat_on_conflict(['podcast_ids'])
    def _update(plist, podcast_ids):
        plist.podcasts = podcast_ids
        plist.save()

    _update(plist=plist, podcast_ids=podcast_ids)

    return HttpResponse(status=204)


@require_valid_user
@list_decorator(must_own=True)
def delete_list(request, plist, owner, format):
    """ Delete the podcast list and returns 204 No Content """

    user = migrate.get_or_migrate_user(request.user)
    is_own = owner == user

    if not is_own:
        return HttpResponseForbidden()

    @repeat_on_conflict(['plist'])
    def _delete(plist):
        plist.delete()

    _delete(plist=plist)

    return HttpResponse(status=204)
