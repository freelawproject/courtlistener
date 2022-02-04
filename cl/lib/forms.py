from django import forms


class BootstrapModelForm(forms.ModelForm):
    # Add form-control to all fields
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            attrs = visible.field.widget.attrs
            try:
                attrs["class"] += " form-control"
            except KeyError:
                attrs["class"] = "form-control"
