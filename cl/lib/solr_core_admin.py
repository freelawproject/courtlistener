import io
import json
from typing import Dict, List, Union, cast

import lxml
import requests
from django.conf import settings
from lxml.etree import _ElementTree
from scorched.exc import SolrError


def swap_solr_core(
    current_core: str,
    desired_core: str,
    url: str = settings.SOLR_HOST,
) -> None:
    """Swap cores, keeping on on deck for easy reversion.

    @current_core is the core you are currently using which will be swapped OUT.
    @desired_core is the core you intend to make live which will be swapped IN.
    """
    params = {
        "wt": "json",
        "action": "SWAP",
        "core": current_core,
        "other": desired_core,
    }
    r = requests.get(f"{url}/solr/admin/cores", params=params, timeout=30)
    if r.status_code != 200:
        print(
            "Problem swapping cores. Got status_code of %s. "
            "Check the Solr logs for details." % r.status_code
        )


def get_solr_core_status(
    core: str = "all",
    url: str = settings.SOLR_HOST,
) -> _ElementTree:
    """Get the status for the solr core as an XML document."""
    if core == "all":
        core_query = ""
    else:
        core_query = f"&core={core}"
    r = requests.get(
        f"{url}/solr/admin/cores?action=STATUS{core_query}",
        timeout=10,
    )
    if r.status_code != 200:
        print(
            "Problem getting the core status. Got status_code of %s. "
            "Check the Solr logs for details." % r.status_code
        )

    try:
        solr_config = lxml.etree.parse(io.BytesIO(r.content))
    except lxml.etree.XMLSyntaxError as e:
        raise SolrError(f"Invalid XML in schema:\n{e.args[0]}")

    return solr_config


def get_term_frequency(
    count: int = 500,
    result_type: str = "dict",
    field: str = "text",
    url: str = settings.SOLR_HOST,
) -> Union[Dict[str, int], List[str]]:
    """Get the term frequency in the index.

    result_type can be json, list or dict.
    """
    params = {
        "fl": field,
        "numTerms": str(count),
        "wt": "json",
    }
    r = requests.get(f"{url}/solr/admin/luke", params=params, timeout=10)
    content_as_json = json.loads(r.content)
    if result_type == "list":
        if len(content_as_json["fields"]) == 0:
            return []
        else:
            top_terms = []
            for result in content_as_json["fields"]["text"]["topTerms"]:
                # Top terms is a list of alternating terms and counts. Their
                # types are different, so we'll use that.
                if isinstance(result, str):
                    top_terms.append(result)
            return top_terms
    elif result_type == "dict":
        if len(content_as_json["fields"]) == 0:
            return {}
        else:
            top_terms_dict = {}
            for result in content_as_json["fields"]["text"]["topTerms"]:
                # We set aside the term until we reach its count, then we add
                # them as a k,v pair
                if isinstance(result, str):
                    key = result
                else:
                    top_terms_dict[key] = result
            return top_terms_dict
    else:
        raise ValueError("Unknown output type!")


def get_data_dir(core: str, url: str = settings.SOLR_HOST):
    """
    Interrogate Solr to get the location of its data directory.

    Useful when writing the external_pagerank file or when reading it.
    """
    status_doc = get_solr_core_status(url=url)
    result = cast(
        List[_ElementTree],
        status_doc.xpath(f'//*[@name="{core}"]//*[@name="dataDir"]/text()'),
    )
    return str(result[0])
