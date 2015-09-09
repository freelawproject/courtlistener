from cl.visualizations.models import SCOTUSMap, JSONVersion
from django import forms


class VizForm(forms.ModelForm):
    """NB: The VizEditForm subclasses this!"""
    def __init__(self, *args, **kwargs):
        super(VizForm, self).__init__(*args, **kwargs)
        self.fields['title'].required = False

    class Meta:
        model = SCOTUSMap
        fields = [
            'cluster_start',
            'cluster_end',
            'title',
            'subtitle',
            'notes',
        ]
        widgets = {
            'cluster_start': forms.TextInput(attrs={'class': 'form-control'}),
            'cluster_end': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'subtitle': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control'}),
        }


class VizEditForm(VizForm):
    class Meta(VizForm.Meta):
        fields = [
            'title',
            'subtitle',
            'notes',
            'published',
        ]

class JSONEditForm(forms.ModelForm):
    class Meta:
        model = JSONVersion
        fields = [
            'json_data',
        ]
        widgets = {
            'json_data': forms.Textarea(attrs={'class': 'form-control'})
        }
