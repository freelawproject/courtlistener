import StringIO
import json

import lxml
import requests
from django.conf import settings

from cl.lib.sunburnt import SolrError


def swap_solr_core(current_core, desired_core, url=settings.SOLR_HOST):
    """Swap cores, keeping on on deck for easy reversion.

    @current_core is the core you are currently using which will be swapped OUT.
    @desired_core is the core you intend to make live which will be swapped IN.
    """
    params = {
        'wt': 'json',
        'action': 'SWAP',
        'core': current_core,
        'other': desired_core,
    }
    r = requests.get('%s/solr/admin/cores' % url, params=params)
    if r.status_code != 200:
        print("Problem swapping cores. Got status_code of %s. "
              "Check the Solr logs for details." % r.status_code)


def get_solr_core_status(core='all', url=settings.SOLR_HOST):
    """Get the status for the solr core as an XML document."""
    if core == 'all':
        core_query = ''
    else:
        core_query = '&core=%s' % core
    r = requests.get('%s/solr/admin/cores?action=STATUS%s' % (url, core_query))
    if r.status_code != 200:
        print("Problem getting the core status. Got status_code of %s. "
              "Check the Solr logs for details." % r.status_code)

    try:
        solr_config = lxml.etree.parse(StringIO.StringIO(r.content))
    except lxml.etree.XMLSyntaxError as e:
        raise SolrError("Invalid XML in schema:\n%s" % e.args[0])

    return solr_config


def get_term_frequency(count=500, result_type='dict', field='text',
                       url=settings.SOLR_HOST):
    """Get the term frequency in the index.

    result_type can be json, list or dict.
    """
    params = {
        'fl': field,
        'numTerms': str(count),
        'wt': 'json',
    }
    r = requests.get('%s/solr/admin/luke' % url, params=params)
    content_as_json = json.loads(r.content)
    if result_type == 'list':
        if len(content_as_json['fields']) == 0:
            return []
        else:
            top_terms = []
            for result in content_as_json['fields']['text']['topTerms']:
                # Top terms is a list of alternating terms and counts. Their
                # types are different, so we'll use that.
                if isinstance(result, basestring):
                    top_terms.append(result)
            return top_terms
    elif result_type == 'dict':
        if len(content_as_json['fields']) == 0:
            return {}
        else:
            top_terms = {}
            for result in content_as_json['fields']['text']['topTerms']:
                # We set aside the term until we reach its count, then we add
                # them as a k,v pair
                if isinstance(result, basestring):
                    key = result
                else:
                    top_terms[key] = result
            return top_terms
    else:
        raise ValueError("Unknown output type!")


def get_data_dir(core, url=settings.SOLR_HOST):
    """
    Interrogate Solr to get the location of its data directory.

    Useful when writing the external_pagerank file or when reading it.
    """
    status_doc = get_solr_core_status(url=url)
    return str(status_doc.xpath(
            '//*[@name="%s"]//*[@name="dataDir"]/text()' % core)[0])


def reload_pagerank_external_file_cache(url=settings.SOLR_HOST):
    """Hit the URL of reloadCache to reload ExternalFileField (necessary for
    Solr version prior to 4.1)
    """
    r = requests.get('%s/solr/reloadCache' % url)
    if r.status_code != 200:
        raise Exception("Problem reloading pagerank cache. Got status_code of "
                        "%s. Check the Solr logs for details." % r.status_code)
