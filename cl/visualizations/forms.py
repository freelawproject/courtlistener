from cl.visualizations.models import SCOTUSMap
from django import forms
from django.forms import ModelForm


class VizForm(ModelForm):
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
