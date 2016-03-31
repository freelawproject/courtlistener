from django.utils.feedgenerator import Rss201rev2Feed

# For more details on the Podcast "Spec" see: https://www.apple.com/itunes/podcasts/specs.html

class iTunesPodcastsFeedGenerator(Rss201rev2Feed):
    def rss_attributes(self):
        return {u"version": self._version,
                u"xmlns:atom": u"http://www.w3.org/2005/Atom",
                u'xmlns:itunes': u'http://www.itunes.com/dtds/podcast-1.0.dtd'}

    def add_root_elements(self, handler):
        super(iTunesPodcastsFeedGenerator, self).add_root_elements(handler)
        handler.addQuickElement(u'itunes:subtitle', self.feed['subtitle'])
        handler.addQuickElement(u'itunes:author', self.feed['author_name'])
        handler.addQuickElement(u'itunes:summary', self.feed['description'])
        handler.addQuickElement(u'itunes:explicit',
                                self.feed['iTunes_explicit'])
        handler.startElement(u"itunes:owner", {})
        handler.addQuickElement(u'itunes:name', self.feed['iTunes_name'])
        handler.addQuickElement(u'itunes:email', self.feed['iTunes_email'])
        handler.endElement(u"itunes:owner")
        handler.addQuickElement(u'itunes:image', self.feed['iTunes_image_url'])

    def add_item_elements(self, handler, item):
        super(iTunesPodcastsFeedGenerator, self).add_item_elements(
            handler, item)
        handler.addQuickElement(u'itunes:duration', item['duration'])
        handler.addQuickElement(u'itunes:explicit', item['explicit'])
        handler.addQuickElement(u'itunes:author', item['author'])
