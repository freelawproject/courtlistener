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
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

import f3_helpers

import argparse

def generate_training_data():
    '''Make a CSV that can be imported by the train_classifier method.
    
    Iterate over the documents in the corpus and check them for duplicates. 
    If they have a likely duplicate
    '''
    corpus = f3_helpers.Corpus('file:///var/www/court-listener/Resource.org/data/F3/')
    for volume in corpus:
        for case in volume:
            print case
            '''
            self.url = _get_url()
            self.sha1_hash = sha1_hash
            self.download_url = _get_download_url()
            self.body, self.body_text = _get_case_body()
            self.court = _get_court()
            self.case_date = _get_case_date(case_date)
            self.west_cite = _get_west_cite()
            self.docket_number = _get_docket_number()
            self.case_name, self.precedential_status = _get_case_name_and_status()
            self.status = 'R'
            '''


def train_classifier():
    '''Use the generated training data to make a logistic classifier.
    '''
    pass

def import_f3():
    '''Import F3 from resource.org using the logistic classifier.
    
    If training has not yet been run, abort.
    
    If duplicates are found, merge them and log the duplicate.
    
    If duplicates are not found, import the document.
    '''
    pass

def main():
    parser = argparse.ArgumentParser(description="Functions relating to importing "
                                                 "F3 via a logistic regression "
                                                 "classifier.")
    parser.add_argument('--gen_data',
                        action='store_true',
                        help="Generate training data as a CSV")
    parser.add_argument('--train',
                        action='store_true',
                        help="Use the generated training data to create a classifier")
    parser.add_argument('--import_f3',
                        action="store_true",
                        help=("Iterate over F3 from resource.org, and import"
                              " its contents. Use the logisitic classifier to"
                              " detect duplicates."))
    options = parser.parse_args()

    if not any([options.gen_data, options.train, options.import_f3]):
        parser.error('At least one argument is required.')

    if options.gen_data:
        generate_training_data()
    if options.train:
        train_classifier()
    if options.import_f3:
        import_f3()

    exit(0)


if __name__ == '__main__':
    main()
