import importlib
import pkgutil
import re

import juriscraper


def walk_juriscraper():
    return pkgutil.walk_packages(
        juriscraper.__path__, f"{juriscraper.__name__}."
    )


def get_scraper_object_by_name(court_id: str, juriscraper_module: str = ""):
    """Identify and instantiate a Site() object given the name of a court

    :param court_id: The ID of a site; must correspond with the name of a
    module without the underscore suffix.
    :param juriscraper_module: full module name. Helps avoiding conflicts when
        there is more than 1 scraper for the same court id. For example,
        those on the united_states_backscrapers folders
    :return: An instantiated Site() object from the module requested
    :rtype: juriscraper.AbstractSite.Site
    """
    if juriscraper_module:
        if re.search(r"\.del$", juriscraper_module):
            # edge case where the module name is not the same as the court id
            juriscraper_module = juriscraper_module.replace(
                ".del", ".delaware"
            )

        return importlib.import_module(juriscraper_module).Site()

    for _, full_module_path, _ in walk_juriscraper():
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


def get_module_by_court_id(court_id: str, module_type: str):
    """Given a `court_id` return a juriscraper module path

    Some court_ids match multiple scraper files. These will force the user
    to use the full module path. For example, "lactapp_1" and "lactapp_5"
    match the same `court_id`, but scrape totally different sites, and
    their Site objects are expected to have different `extract_from_text`
    behavior

    :param court_id: court id to look for
    :param module_type: 'opinions' or 'oral_args'. Without this, some
        court_ids may match the 2 classes of scrapers

    :raises: ValueError if there is no match or there is more than 1 match
    :return: the full module path
    """
    if module_type not in ["opinions", "oral_args"]:
        raise ValueError(
            "module_type has to be one of ['opinions', 'oral_args']"
        )

    matches = []
    for _, module_string, _ in walk_juriscraper():
        if module_string.count(".") != 4 or module_type not in module_string:
            # Skip folder and lib modules. Skip type
            continue

        module_court_id = module_string.rsplit(".", 1)[1].rsplit("_", 1)[0]
        if module_court_id == court_id:
            matches.append(module_string)

    if len(matches) == 1:
        return matches[0]
    elif len(matches) == 0:
        raise ValueError(f"'{court_id}' doesn't match any juriscraper module")
    else:
        raise ValueError(
            f"'{court_id}' matches more than 1 juriscraper module."
            f"Use a full module path. Matches: '{matches}'"
        )
