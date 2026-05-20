from django.db import migrations


def add_fladistctapp6(apps, schema_editor):
    Court = apps.get_model("search", "Court")
    Courthouse = apps.get_model("search", "Courthouse")

    fladistctapp6 = Court.objects.create(
        id="fladistctapp6",
        jurisdiction="SA",
        short_name="Florida Sixth District Court of Appeal",
        full_name="Florida Sixth District Court of Appeal",
        citation_string="Fla. Dist. Ct. App. 6th Dist.",
        position=355.015,
        url="https://6dca.flcourts.gov",
        start_date="2023-01-01",
        end_date=None,
        in_use=True,
        has_opinion_scraper=False,
        has_oral_argument_scraper=False,
        notes="Created as part of Florida state court scraping project.",
    )

    parent = Court.objects.get(pk="fladistctapp")
    fladistctapp6.appeals_to.add(parent)

    Courthouse.objects.create(
        court=fladistctapp6,
        court_seat=True,
        building_name="Florida Sixth District Court of Appeal",
        address1="1997 E Edgewood Drive",
        city="Lakeland",
        state="FL",
        zip_code="33803",
        country_code="US",
    )


def reverse_add_fladistctapp6(apps, schema_editor):
    Court = apps.get_model("search", "Court")
    Court.objects.filter(pk="fladistctapp6").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("search", "0058_texasdocument_processing_error"),
    ]

    operations = [
        migrations.RunPython(
            add_fladistctapp6,
            reverse_add_fladistctapp6,
        ),
    ]
