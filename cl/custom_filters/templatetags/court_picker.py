from django import template
from django.conf import settings
from django.template.defaultfilters import stringfilter
import numpy
from courts_db import find_court_by_id

register = template.Library()



state_circuits = {
   "Maine": 1,
   "Massachusetts": 1,
   "New Hampshire": 1,
   "Puerto Rico": 1,
   "Rhode Island": 1,
   "Connecticut": 2,
   "New York": 2,
   "Vermont": 2,
   "Delaware": 3,
   "New Jersey": 3,
   "Pennsylvania": 3,
   "Maryland": 4,
   "North Carolina": 4,
   "South Carolina": 4,
   "Virginia": 4,
   "West Virginia": 4,
   "Louisiana": 5,
   "Mississippi": 5,
   "Texas": 5,
   "Kentucky": 6,
   "Michigan": 6,
   "Ohio": 6,
   "Tennessee": 6,
   "Illinois": 7,
   "Chicago": 7,
   "Indiana": 7,
   "Wisconsin": 7,
   "Arkansas": 8,
   "Iowa": 8,
   "Minnesota": 8,
   "Missouri": 8,
   "Nebraska": 8,
   "North Dakota": 8,
   "South Dakota": 8,
   "Alaska": 9,
   "Arizona": 9,
   "California": 9,
   "Hawaii": 9,
   "Idaho": 9,
   "Montana": 9,
   "Nevada": 9,
   "Oregon": 9,
   "Washington": 9,
   "Colorado": 10,
   "Kansas": 10,
   "New Mexico": 10,
   "Oklahoma": 10,
   "Utah": 10,
   "Wyoming": 10,
   "Alabama": 11,
   "Florida": 11,
   "Georgia": 11,
   "District of Columbia": "D.C.",
   "Washington D.C.": "D.C."
}


@register.filter
@stringfilter
def clean_fed(courtstring):
    c = courtstring.replace("Court of Appeals for the ", "")
    c = c.replace("Supreme Court of the United States", "U.S. Supreme Court ")
    return c

@register.filter
@stringfilter
def x_clean(courtstring):
    c = courtstring.replace("U.S. Circuit Court for the District", "D.")
    c = c.replace("U.S. Circuit Court District", "D.")
    return c

@register.filter
@stringfilter
def replace(value, arg):
    """Removes all values of arg from the given string"""
    return value.replace(arg.split("|")[0], arg.split("|")[1])

@register.filter
def split_columns(state_dict, count):
    return numpy.array_split(sorted(state_dict), count)

@register.filter(name='split')
def split(value, key):
  """
    Returns the value turned into a list.
  """
  return value.split(key)


@register.filter
@stringfilter
def clean_crt(courtstring):
    if "Bankruptcy" in courtstring:
        return courtstring.replace("United States Bankruptcy Court, ", "USBC ")
    courtstring = courtstring.replace("U.S. Circuit Court for the District of", "C.C.")
    courtstring = courtstring.replace("Court of Appeals for the ", "")
    return courtstring


@register.filter
def parse_courts(courts, tab):
    court_list = []

    state_dict = {}
    dist_dict = {}
    bank_dict = {}
    federal_dict = {}

    for court in courts:
        if tab == "special":
            if court.jurisdiction == "FS":
                court_list.append(court.__dict__)

        if tab == "federal":
            if court.jurisdiction == "F":
                court_query = find_court_by_id(court.id)
                if court_query:
                    if court.full_name == "Court of Appeals for the Federal Circuit":
                        c = court.__dict__
                        c['order'] = 100 + 14
                        federal_dict[str(102)] = [c]
                        continue
                    if court.full_name == "Supreme Court of the United States":
                        c = court.__dict__
                        c['order'] = 100
                        federal_dict[str(100)] = [c]
                        continue
                    circuit = state_circuits[court_query[0]['location'].title()]
                    if circuit == "D.C.":
                        circuit = 0
                    c = court.__dict__
                    c['order'] = 103 + circuit
                    k = 103 + circuit
                    if str(k) in federal_dict.keys():
                        l = federal_dict[str(k)]
                        l.append(c)
                        federal_dict[str(k)] = l
                    else:
                        federal_dict[str(k)] = [c]

                        # federal_dict["Federal"] = [c]

        if tab == "district":
            if court.jurisdiction == "FD":
                c = find_court_by_id(court.id)
                if c:
                    if c[0]['location'] in dist_dict.keys():
                        l = dist_dict[c[0]['location']]
                        l.append(court.__dict__)
                        dist_dict[c[0]['location']] = l
                    else:
                        dist_dict[c[0]['location']] = [court.__dict__]

        if tab == "state":
            if court.jurisdiction[0] == "S":
                c = find_court_by_id(court.id)
                if c:
                    loc = c[0]['location']
                    if loc == "Washington D.C.":
                        loc = "D.C."
                    if loc == "Dakota Territory":
                        loc = "North Dakota"
                    if loc in state_dict.keys():
                        l = state_dict[loc]
                        l.append(court.__dict__)
                        state_dict[loc] = l
                    else:
                        state_dict[loc] = [court.__dict__]

        if tab == "military":
            if court.jurisdiction[0] == "M":
                court_list.append(court.full_name)
            if court.jurisdiction == "FS":
                cf = court.full_name.lower()
                if "army" in cf or "armed" in cf or "vet" in cf:
                    court_list.append(court.full_name)

        if tab == "tribal":
            if court.jurisdiction[0] == "T" and court.jurisdiction != 'T':
                court_list.append(court.full_name)

        if tab == "bankruptcy":
            if court.jurisdiction == "FB":
                c = find_court_by_id(court.id)
                if c:
                    if c[0]['location'] in bank_dict.keys():
                        l = bank_dict[c[0]['location']]
                        l.append(court.__dict__)
                        bank_dict[c[0]['location']] = l
                    else:
                        bank_dict[c[0]['location']] = [court.__dict__]

    if tab == "district":
        return dist_dict

    if tab == "state":
        return state_dict

    if tab == "special":
        return court_list

    if tab == "federal":
        result = sorted(federal_dict.iteritems(),
                        key=lambda (k, v): (k, v))
        return result

    if tab == "bankruptcy":
        return bank_dict



    return court_list


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
