import os
import lxml
import requests
import StringIO
import time
from alert import settings
from alert.lib.sunburnt import SolrError


def create_solr_core(core_name, data_dir='/tmp/solr/data'):
    """ Create a new core for use in testing."""
    if data_dir == '/tmp/solr/data':
        # If the user doesn't specify a data directory, we give them one with a unique location.
        # This way, it's very unlikely that anything will interfere with stuff it shouldn't.
        data_dir += '/tmp/solr/data-%s' % time.time()
    params = {
        'wt': 'json',
        'action': 'CREATE',
        'name': core_name,
        'dataDir': data_dir,
        'instanceDir': '/usr/local/solr/example/solr/collection1',
        'config': os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf', 'solrconfig.xml'),
        'schema': os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf', 'schema.xml'),
    }
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem creating core. Got status_code of %s. Check the Solr logs for details." % r.status_code


def delete_solr_core(core_name, delete_index=True):
    """ Delete a solr core by name."""
    params = {
        'wt': 'json',
        'action': 'UNLOAD',
        'core': core_name,
        'deleteIndex': str(delete_index).lower(),
    }
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem deleting core. Got status_code of %s. Check the Solr logs for details." % r.status_code


def swap_solr_core(current_core, desired_core):
    """Swap cores, keeping on on deck for easy reversion.

    @current_core is the core you are currently using, and which will be swapped OUT.
    @desired_core is the core you intend to make live, and which will be swapped IN.
    """
    params = {
        'wt': 'json',
        'action': 'SWAP',
        'core': current_core,
        'other': desired_core,
    }
    r = requests.get('http://localhost:8983/solr/admin/cores', params=params)
    if r.status_code != 200:
        print "Problem swapping cores. Got status_code of %s. Check the Solr logs for details." % r.status_code


def get_solr_core_status(core='all'):
    """Get the status for the solr core as an XML document."""
    if core == 'all':
        core_query = ''
    else:
        core_query = '&core=%s' % core
    r = requests.get('http://localhost:8983/solr/admin/cores?action=STATUS%s' % core_query)
    if r.status_code != 200:
        print "Problem getting the core status. Got status_code of %s. Check the Solr logs for details." % r.status_code

    try:
        solr_config = lxml.etree.parse(StringIO.StringIO(r.content))
    except lxml.etree.XMLSyntaxError, e:
        raise SolrError("Invalid XML in schema:\n%s" % e.args[0])

    return solr_config
