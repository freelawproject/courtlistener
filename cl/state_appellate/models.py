from django.db import models


class Court(models.Model):
    """
    Represents a state appellate court.
    """

    court_name = models.CharField(max_length=255, unique=True)


class Entity(models.Model):
    """
    Base model for entities (Person or Organization).
    An entity can have an address.
    """

    address = models.ForeignKey(
        "Address",
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_set",
    )

    class Meta:
        abstract = True


class Person(Entity):
    """
    Represents a person like a judge or point of contact (POC), for example.
    """

    first_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255)


class Organization(Entity):
    """
    Represents an organization.
    """

    name = models.CharField(max_length=255)
    department = models.CharField(max_length=255, null=True)


class Address(models.Model):
    """
    Represents a physical address.
    """

    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)

    def __str__(self):
        return (
            f"{self.address_line1}, {self.city}, {self.state} {self.zip_code}"
        )


class TrialCourt(models.Model):
    """
    Represents a trial court from which cases are appealed.
    """

    name = models.CharField(max_length=255)
    county = models.CharField(max_length=255)
    case_number = models.CharField(max_length=100)
    judge = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
    )
    judgement_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "case_number"],
                name="unique_trial_court_case",
            )
        ]


class Opinion(models.Model):
    """
    Represents a Court of Appeal opinion document.
    """

    pdf_file = models.FileField(upload_to="opinions/pdf/%Y/%m/", null=True)
    pdf_uri = models.URLField(
        max_length=500,
        null=True,
        help_text="External PDF URL if hosted elsewhere",
    )

    docx_file = models.FileField(upload_to="opinions/docx/%Y/%m/", null=True)
    docx_uri = models.URLField(
        max_length=500,
        null=True,
        help_text="External DOCX URL if hosted elsewhere",
    )


class CaseSummary(models.Model):
    """
    Represents a case summary.
    """

    CASE_TYPE_CHOICES = [
        ("CR", "Criminal"),
        ("CV", "Civil"),
        ("JV", "Juvenile"),
        ("PR", "Probate"),
    ]

    appellate_court = models.ForeignKey(
        Court,
        on_delete=models.PROTECT,
        related_name="cases",
    )
    trial_court_case = models.ForeignKey(
        TrialCourt,
        on_delete=models.SET_NULL,
        null=True,
    )
    # TODO: Add validation for appellate court case numbers.
    # https://appellatecases.courtinfo.ca.gov/help.cfm?dist=1&subj=legend
    appellate_court_case_number = models.CharField(
        max_length=7,
        unique=True,
        help_text="Described as Court of Appeal Case in the Case Summary section.",
    )
    court_of_appeal_opinion = models.ForeignKey(
        Opinion, on_delete=models.SET_NULL, null=True
    )
    division = models.IntegerField()
    case_caption = models.CharField(max_length=500)
    case_type = models.CharField(max_length=2, choices=CASE_TYPE_CHOICES)
    filing_date = models.DateField(null=True)
    completion_date = models.DateField(null=True)
    oral_argument_date_time = models.DateTimeField(null=True)


class Party(models.Model):
    """
    Represents a party in a case.
    Can be associated with either a Person or an Organization.
    """

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        null=True,
        related_name="as_party",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        related_name="as_party",
    )
    party_type = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(person__isnull=False, organization__isnull=True)
                    | models.Q(person__isnull=True, organization__isnull=False)
                ),
                name="party_is_person_or_organization",
            )
        ]

    @property
    def entity(self):
        """Get the entity (Person or Organization)."""
        return self.person or self.organization


class Attorney(models.Model):
    """
    Represents an attorney (can be a person or organization).
    """

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        null=True,
        related_name="as_attorney",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        related_name="as_attorney",
    )

    # Contact person for organizations
    contact_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        related_name="attorney_contact_for",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(person__isnull=False, organization__isnull=True)
                    | models.Q(person__isnull=True, organization__isnull=False)
                ),
                name="attorney_is_person_or_organization",
            )
        ]

    @property
    def entity(self):
        """Get the entity (Person or Organization)."""
        return self.person or self.organization


class PartyAttorney(models.Model):
    """
    Represents the relationship between a case, party, and attorney.
    This allows tracking which attorney represents which party in which case.
    """

    associated_case = models.ForeignKey(CaseSummary, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE, null=True)
    attorney = models.ForeignKey(
        Attorney,
        on_delete=models.CASCADE,
    )
    appointment_date = models.DateField(null=True)


class Action(models.Model):
    """
    Represents an action filed in a Register of Actions (ROA).
    """

    associated_case = models.ForeignKey(CaseSummary, on_delete=models.CASCADE)
    date_action_was_filed = models.DateField()
    description = models.TextField(null=True)
    notes = models.TextField(null=True)

    class Meta:
        ordering = ["associated_case", "date_action_was_filed"]
        constraints = [
            models.UniqueConstraint(
                fields=["associated_case", "date_action_was_filed"],
                name="unique_action_per_case_per_date",
            )
        ]
