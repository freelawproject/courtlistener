import StringIO
import json
import os
import time

import lxml
import requests

from cl import settings
from cl.lib.sunburnt import SolrError


def create_solr_core(
        core_name,
        data_dir='/tmp/solr/data',
        schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                            'schema.xml'),
        instance_dir='/usr/local/solr/example/solr/collection1',
        config=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                            'solrconfig.xml')):
    """ Create a new core for use in testing."""
    if data_dir == '/tmp/solr/data':
        # If the user doesn't specify a data directory, we give them one with
        # a unique location. This way, it's very unlikely that anything will
        # interfere with stuff it shouldn't.
        data_dir += '/tmp/solr/data-%s' % time.time()

    params = {
        'wt': 'json',
        'action': 'CREATE',
        'name': core_name,
        'dataDir': data_dir,
        'instanceDir': instance_dir,
        'config': config,
        'schema': schema,
        'persist': 'true',
    }
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem creating core. Got status_code of %s. Check the Solr " \
              "logs for details." % r.status_code


def create_default_cores():
    """Helper utility to create the default cores."""
    create_solr_core(
        core_name='collection1',
        data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr', 'data'),
        schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                            'schema.xml'),
        instance_dir='/usr/local/solr/example/solr/collection1',
    )
    create_solr_core(
        core_name='audio',
        data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr', 'data_audio'),
        schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                            'audio_schema.xml'),
        instance_dir='/usr/local/solr/example/solr/audio',
    )
    create_solr_core(
        core_name='dockets',
        data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr', 'data_dockets'),
        schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                            'dockets_schema.xml'),
        instance_dir='/usr/local/solr/example/solr/dockets',
    )


def delete_solr_core(core_name, delete_index=True, delete_data_dir=False):
    """ Delete a solr core by name."""
    params = {
        'wt': 'json',
        'action': 'UNLOAD',
        'core': core_name,
        'deleteIndex': str(delete_index).lower(),
        'deleteDataDir': str(delete_data_dir).lower(),
    }
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem deleting core. Got status_code of %s. Check the Solr " \
              "logs for details." % r.status_code


def swap_solr_core(current_core, desired_core):
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
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem swapping cores. Got status_code of %s. Check the Solr " \
              "logs for details." % r.status_code


def get_solr_core_status(core='all'):
    """Get the status for the solr core as an XML document."""
    if core == 'all':
        core_query = ''
    else:
        core_query = '&core=%s' % core
    r = requests.get(
        'http://localhost:8983/solr/admin/cores?action=STATUS%s' % core_query)
    if r.status_code != 200:
        print "Problem getting the core status. Got status_code of %s. Check " \
              "the Solr logs for details." % r.status_code

    try:
        solr_config = lxml.etree.parse(StringIO.StringIO(r.content))
    except lxml.etree.XMLSyntaxError, e:
        raise SolrError("Invalid XML in schema:\n%s" % e.args[0])

    return solr_config


def get_term_frequency(count=500, result_type='dict', field='text'):
    """Get the term frequency in the index.

    result_type can be json, list or dict.
    """
    params = {
        'fl': field,
        'numTerms': str(count),
        'wt': 'json',
    }
    r = requests.get('http://localhost:8983/solr/admin/luke', params=params)
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


def get_data_dir(core):
    """
    Interrogate Solr to get the location of its data directory.

    Useful when writing the external_pagerank file or when reading it.
    """
    status_doc = get_solr_core_status()
    return str(status_doc.xpath(
            '//*[@name="%s"]//*[@name="dataDir"]/text()' % core)[0])


def reload_pagerank_external_file_cache():
    """Hit the URL of reloadCache to reload ExternalFileField (necessary for
    Solr version prior to 4.1)
    """
    r = requests.get('http://localhost:8983/solr/reloadCache')
    if r.status_code != 200:
        print "Problem reloading cache. Got status_code of %s. Check the Solr " \
              "logs for details." % r.status_code
