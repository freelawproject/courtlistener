from django.utils.feedgenerator import Rss201rev2Feed


# For more details on the Podcast "Spec" see:
# https://help.apple.com/itc/podcasts_connect/#/itcb54353390
class iTunesPodcastsFeedGenerator(Rss201rev2Feed):
    def rss_attributes(self):
        return {
            "version": self._version,
            "xmlns:atom": "http://www.w3.org/2005/Atom",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        }

    def add_root_elements(self, handler):
        super().add_root_elements(handler)
        handler.addQuickElement("itunes:subtitle", self.feed["subtitle"])
        handler.addQuickElement("itunes:author", self.feed["author_name"])
        handler.addQuickElement("itunes:summary", self.feed["description"])
        handler.addQuickElement(
            "itunes:explicit", self.feed["iTunes_explicit"]
        )
        handler.startElement("itunes:owner", {})
        handler.addQuickElement("itunes:name", self.feed["iTunes_name"])
        handler.addQuickElement("itunes:email", self.feed["iTunes_email"])
        handler.endElement("itunes:owner")
        handler.addQuickElement(
            "itunes:image", None, {"href": self.feed["iTunes_image_url"]}
        )
        handler.addQuickElement(
            "itunes:category", None, {"text": "Government & Organizations"}
        )

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        handler.addQuickElement("itunes:duration", item["duration"])
        handler.addQuickElement("itunes:explicit", item["explicit"])
        handler.addQuickElement("itunes:author", item["author"])
