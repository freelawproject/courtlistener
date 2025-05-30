from django.contrib import sitemaps
from django.urls import reverse


def make_url_dict(
    view_name: str,
    changefreq: str = "yearly",
    priority: float = 0.5,
) -> dict[str, float | str]:
    return {
        "view_name": view_name,
        "changefreq": changefreq,
        "priority": priority,
    }


class SimpleSitemap(sitemaps.Sitemap):
    def items(self) -> list[dict[str, str | float]]:
        return [
            # API
            make_url_dict("api_index", priority=0.7),
            make_url_dict("rest_docs", priority=0.6),
            make_url_dict("alert_api_help", priority=0.5),
            make_url_dict("financial_disclosures_api_help", priority=0.5),
            make_url_dict("case_law_api_help", priority=0.5),
            make_url_dict("citation_api_help", priority=0.5),
            make_url_dict("pacer_api_help", priority=0.5),
            make_url_dict("recap_api_help", priority=0.5),
            make_url_dict("judge_api_help", priority=0.5),
            make_url_dict("oral_argument_api_help", priority=0.5),
            make_url_dict("visualization_api_help", priority=0.5),
            make_url_dict("webhooks_docs", priority=0.5),
            make_url_dict("webhooks_getting_started", priority=0.5),
            make_url_dict("search_api_help", priority=0.5),
            make_url_dict("citation_lookup_api", priority=0.5),
            make_url_dict("bulk_data_index", priority=0.6),
            make_url_dict("replication_docs", priority=0.6),
            # Simple pages
            make_url_dict("faq", priority=0.6),
            make_url_dict(
                "citation_homepage", priority=0.6, changefreq="never"
            ),
            make_url_dict("coverage", priority=0.4),
            make_url_dict(
                "coverage_opinions", priority=0.4, changefreq="daily"
            ),
            make_url_dict("coverage_fds", priority=0.4),
            make_url_dict("coverage_recap", priority=0.4),
            make_url_dict("feeds_info", priority=0.4, changefreq="never"),
            make_url_dict("podcasts", priority=0.6, changefreq="never"),
            make_url_dict("contribute", priority=0.6, changefreq="never"),
            make_url_dict("contact", priority=0.5),
            make_url_dict("terms", priority=0.1),
            # Help pages
            make_url_dict("help_home", priority=0.5, changefreq="monthly"),
            make_url_dict("markdown_help", priority=0.4, changefreq="never"),
            make_url_dict("alert_help", priority=0.4, changefreq="monthly"),
            make_url_dict("delete_help", priority=0.3, changefreq="monthly"),
            make_url_dict("advanced_search", priority=0.5),
            make_url_dict(
                "recap_email_help", priority=0.5, changefreq="monthly"
            ),
            # Search
            make_url_dict("advanced_o", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_r", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_oa", priority=0.7, changefreq="weekly"),
            make_url_dict("advanced_p", priority=0.7, changefreq="weekly"),
            # Users
            make_url_dict("sign-in", priority=0.6, changefreq="never"),
            make_url_dict("register", priority=0.6, changefreq="never"),
            make_url_dict("password_reset", priority=0.4, changefreq="never"),
            # Visualizations
            make_url_dict("mapper_homepage", priority=0.7),
            make_url_dict("new_visualization", priority=0.4),
            make_url_dict("viz_gallery", priority=0.6, changefreq="hourly"),
        ]

    def changefreq(self, obj: dict[str, str | float]) -> str | float:
        return obj["changefreq"]

    def priority(self, obj: dict[str, str | float]) -> str | float:
        return str(obj["priority"])

    def location(  # type: ignore[override]
        self,
        obj: dict[str, str | float],
    ) -> str:
        return reverse(str(obj["view_name"]))
