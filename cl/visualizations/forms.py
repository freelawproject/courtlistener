from django import forms

from cl.visualizations.models import SCOTUSMap


class VizForm(forms.ModelForm):
    """NB: The VizEditForm subclasses this!"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False

    class Meta:
        model = SCOTUSMap
        fields = [
            "cluster_start",
            "cluster_end",
            "title",
            "notes",
        ]
        widgets = {
            "cluster_start": forms.HiddenInput(),
            "cluster_end": forms.HiddenInput(),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control"}),
        }


class VizEditForm(VizForm):
    class Meta(VizForm.Meta):
        fields = [
            "title",
            "notes",
            "published",
        ]
