from django import forms
from django.forms import ModelForm
from cl.favorites.models import Favorite


class FavoriteForm(ModelForm):
    class Meta:
        model = Favorite
        exclude = ('user',)
        fields = (
            'id',
            'audio_id',
            'cluster_id',
            'name',
            'notes'
        )
        widgets = {
            'id': forms.HiddenInput(),
            'cluster_id': forms.HiddenInput(),
            'audio_id': forms.HiddenInput(),
            'name': forms.TextInput(
                attrs={
                    'id': 'save-favorite-name-field',
                    'tabindex': '1',
                    'maxlength': '100'}),
            'notes': forms.Textarea(
                attrs={
                    'class': 'bottom',
                    'id': 'save-favorite-notes-field',
                    'tabindex': '2',
                    'maxlength': '600'})
        }
