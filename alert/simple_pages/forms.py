from django import forms


class ContactForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField(required=False)
    subject = forms.CharField(max_length=150)
    message = forms.CharField(widget=forms.Textarea, min_length=20)
