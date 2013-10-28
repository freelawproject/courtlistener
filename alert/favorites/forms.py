from django import forms
from django.forms import ModelForm
from alert.favorites.models import Favorite


class FavoriteForm(ModelForm):
    class Meta:
        model = Favorite
        fields = (
            'id',
            'doc_id',
            'name',
            'notes'
        )
        widgets = {
            'id': forms.HiddenInput(),
            'doc_id': forms.HiddenInput(),
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
