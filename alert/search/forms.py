# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from haystack.forms import FacetedSearchForm

class ParallelFacetedSearchForm(FacetedSearchForm):
    '''Overrides the default form in order to provide check boxes and other 
    the other functionality that is necessary when parallel selections can be
    placed. 
    '''
    def __init__(self, *args, **kwargs):
        self.selected_facets = kwargs.pop("selected_facets", [])
        super(FacetedSearchForm, self).__init__(*args, **kwargs)

    def no_query_found(self):
        '''If there is no query, return everything'''
        return self.searchqueryset.all()

    def search(self):
        sqs = super(FacetedSearchForm, self).search().facet('status').facet('court')
        #sqs = super(FacetedSearchForm, self).search().facet('{!facet.mincount=1}court_exact').facet('status')
        #sqs = super(FacetedSearchForm, self).search().facet('{!ex=court_exact facet.mincount=1}court_exact').facet('{!ex=status_exact facet.mincount=1}status_exact')

        # We need to process each facet to ensure that the field name and the
        # value are quoted correctly and separately:
        for facet in self.selected_facets:
            if ":" not in facet:
                continue

            field, value = facet.split(":", 1)

            if value:
                # This works with the default functionality
                #sqs = sqs.narrow(u'%s:"%s"' % (field, sqs.query.clean(value)))
                # Creating the following query:
                # {facet=on&fl=*+score&start=0&q=(presiding+AND+NOT+(ninth))&facet.field=status_exact&facet.field=court_exact&wt=json&fq=django_ct:(search.document)&fq=court_exact:"3rd+Cir."}

                # This creates normal faceting as well
                value = sqs.query.clean(value)
                sqs = sqs.facet('{!ex="%s"}court' % (value))
                # {facet=on&fl=*+score&start=0&q=(presiding+AND+NOT+(ninth))&facet.field=status_exact&wt=json&fq=django_ct:(search.document)}

                sqs = sqs.narrow(u'{!tag="%s"}%s:"%s"' % (value, field, value))
                # Producing the following query:
                # {facet=on&fl=*+score&start=0&q=(presiding+AND+NOT+(ninth))&facet.field=status_exact&facet.field=court_exact&wt=json&fq=django_ct:(search.document)&fq={!tag%3D"2d+Cir."}court_exact:"2d+Cir."}


                #sqs = sqs.narrow(u'{!tag=%s}%s' % (field, sqs.query.clean(value)))
                #q=mainquery&fq=status:public&fq={!tag=dt}doctype:pdf&facet=on&facet.field={!ex=dt}doctype
                #{facet=on&fl=*+score&start=0&q=(presiding+AND+NOT+(ninth))&facet.field={!ex%3Dstatus_exact}status_exact&facet.field={!ex%3Dcourt_exact}court_exact&wt=json&fq=django_ct:(search.document)&fq={!tag%3Dcourt_exact}2d+Cir.}
        return sqs


        # ('{!ex=make_exact}make').facet('{!ex=body_exact}body')
        '''
            {facet=on
            &fl=*+score
            &start=0
            &q=(presiding+AND+NOT+(ninth))
            &facet.field={!ex%3Dstatus_exact}status_exact
            &facet.field={!ex%3Dcourt_exact}court_exact
            &wt=json
            &fq=django_ct:(search.document)
            &fq={!tag%3Dcourt_exact}"2d+Cir."}
            
            q=chevrolet
            &facet=true
            &facet.field=location
            &facet.field={!ex="2nd+Cir"}model
            &facet.mincount=1
            &fq={!tag="2nd+Cir"}model:"2nd+Cir"
            
        '''

    '''
    def search(self):
        sqs = super(ParallelFacetedSearchForm, self).search()
        if hasattr(self, 'data') and self.data.has_key(u'selected_facets'):
            for facet in self.data.getlist('selected_facets'):
                facet_name, facet_value = facet.split(':')
                narrow_query = u"{!tag=%s}%s" % (facet_name, facet)
                sqs = sqs.narrow(narrow_query)
        return sqs
    '''
