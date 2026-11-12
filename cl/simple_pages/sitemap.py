"""Sitemap of simple, help, search, and user pages."""

from django.contrib import sitemaps
from django.urls import reverse


def make_url_dict(
    view_name: str,
    changefreq: str = "yearly",
    priority: float = 0.5,
) -> dict[str, float | str]:
    """Make a sitemap item for a view."""
    return {
        "view_name": view_name,
        "changefreq": changefreq,
        "priority": priority,
    }


class SimpleSitemap(sitemaps.Sitemap):
    """Sitemap of a fixed list of simple pages."""

    def items(self) -> list[dict[str, str | float]]:
        """List the pages in the sitemap."""
        return [
            # Simple pages
            make_url_dict(
                "citation_homepage", priority=0.6, changefreq="never"
            ),
            make_url_dict("contact", priority=0.5),
            # Help pages
            make_url_dict("help_home", priority=0.5, changefreq="monthly"),
            # Search
            make_url_dict("advanced_o", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_r", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_oa", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_p", priority=0.7, changefreq="weekly"),
            # Users
            make_url_dict("sign-in", priority=0.6, changefreq="never"),
            make_url_dict("register", priority=0.6, changefreq="never"),
            make_url_dict("password_reset", priority=0.4, changefreq="never"),
        ]

    def changefreq(self, obj: dict[str, str | float]) -> str | float:
        """Get the page's change frequency."""
        return obj["changefreq"]

    def priority(self, obj: dict[str, str | float]) -> str | float:
        """Get the page's priority as a string."""
        return str(obj["priority"])

    def location(  # type: ignore[override]
        self,
        obj: dict[str, str | float],
    ) -> str:
        """Get the URL of the view named by the item's ``view_name``."""
        return reverse(str(obj["view_name"]))
