from collections import OrderedDict

from cl.audio.sitemap import AudioSitemap
from cl.opinion_page.sitemap import DocketSitemap, OpinionSitemap
from cl.search.models import SEARCH_TYPES

# List the models that should use pregenerated sitemaps
pregenerated_sitemaps = OrderedDict(
    {
        SEARCH_TYPES.RECAP: DocketSitemap,
        SEARCH_TYPES.OPINION: OpinionSitemap,
        SEARCH_TYPES.ORAL_ARGUMENT: AudioSitemap,
    }
)

urlpatterns: list = []
