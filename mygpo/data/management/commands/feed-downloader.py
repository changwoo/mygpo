from itertools import islice, chain, imap as map
from django.core.management.base import BaseCommand
from mygpo.core.models import Podcast, PodcastGroup
from mygpo.directory.toplist import PodcastToplist
from mygpo.data import feeddownloader
from optparse import make_option
import datetime

UPDATE_LIMIT = datetime.datetime.now() - datetime.timedelta(days=15)

class Command(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option('--toplist', action='store_true', dest='toplist',
            default=False, help="Update all entries from the Toplist."),

        make_option('--update-new', action='store_true', dest='new',
            default=False, help="Update all podcasts with new Episodes"),

        make_option('--list-only', action='store_true', dest='list',
            default=False, help="Don't update anything, just list podcasts "),

        make_option('--max', action='store', dest='max', type='int',
            default=0, help="Set how many feeds should be updated at maximum"),

        make_option('--random', action='store_true', dest='random',
            default=False, help="Update random podcasts, best used with --max"),
        )


    def handle(self, *args, **options):

        queue = []

        if options.get('toplist'):
            queue = chain(queue, self.get_toplist())

        if options.get('new'):
            queue = chain(queue, self.self.get_podcast_with_new_episodes())

        if options.get('random'):
            queue = chain(queue, Podcast.random())


        get_podcast = lambda url: Podcast.for_url(url, create=True)
        args_podcasts = map(get_podcast, args)

        queue = chain(queue, args_podcasts)

        if not args and not options.get('toplist') and not options.get('new') \
                    and not options.get('random'):
           queue = chain(queue, Podcast.by_last_update())

        max_podcasts = options.get('max')
        if max_podcasts:
            queue = islice(queue, 0, max_podcasts)

        if options.get('list'):
            print '\n'.join([p.url for p in queue])

        else:
            print 'Updating podcasts...'
            feeddownloader.update_podcasts(queue)


    def get_podcast_with_new_episodes(self):
        db = newmodels.Podcast.get_db()
        res = db.view('maintenance/episodes_need_update',
                group_level = 1,
                reduce      = True,
            )

        for r in res:
            podcast_id = r['key']
            podcast = newmodels.Podcast.get(podcast_id)
            if podcast:
                yield podcast


    def get_toplist(self):
        toplist = PodcastToplist()
        for oldindex, obj in toplist[:100]:
            if isinstance(obj, Podcast):
                yield obj
            elif isinstance(obj, PodcastGroup):
                for p in obj.podcasts:
                    yield p

