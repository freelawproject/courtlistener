import parse_opinions
import populate_opinions

# have to do this while running as a standalone script?
import django
django.setup()

parsed = parse_opinions.parse_file('cl/corpus_importer/import_columbia/test_opinions/0a4c08bbcc64ef21.xml')
objects = populate_opinions.make_and_save(parsed)