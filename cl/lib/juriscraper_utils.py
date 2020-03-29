import pkgutil
import juriscraper
import importlib


def get_scraper_object_by_name(court_id):
    """Identify and instantiate a Site() object given the name of a court

    :param court_id: The ID of a site; must correspond with the name of a
    module without the underscore suffix.
    :type court_id: str
    :return: An instantiated Site() object from the module requested
    :rtype: juriscraper.AbstractSite.Site
    """
    for _, full_module_path, _ in pkgutil.walk_packages(
        juriscraper.__path__, juriscraper.__name__ + "."
    ):
        # Get the module name from the full path and trim
        # any suffixes like _p, _u
        module_name = full_module_path.rsplit(".", 1)[1].rsplit("_", 1)[0]
        if module_name == court_id:
            return importlib.import_module(full_module_path).Site()
