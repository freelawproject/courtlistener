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
            try:
                return importlib.import_module(full_module_path).Site()
            except AttributeError:
                # This can happen when there's no Site() attribute, which can
                # happen when your court name intersects with the name of
                # something in Juriscraper. For example, a court named "test"
                # matches the juriscraper.lib.test_utils module after "_utils"
                # has been stripped off it. In any case, just ignore it when
                # this happens.
                continue
