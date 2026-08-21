from cl.lib.widgets import NEW_STACK_WIDGET_CLASSES, Select, TextInput
from cl.tests.cases import SimpleTestCase


class TextInputTest(SimpleTestCase):
    """Test the shared text input used by new-stack Django forms."""

    def test_defaults_and_caller_attrs(self) -> None:
        """Apply defaults without mutating or reordering caller attributes."""
        attrs = {"placeholder": "mm/dd/yyyy"}

        widget = TextInput(attrs=attrs)

        self.assertEqual(attrs, {"placeholder": "mm/dd/yyyy"})
        self.assertEqual(
            widget.attrs,
            {
                "placeholder": "mm/dd/yyyy",
                "class": NEW_STACK_WIDGET_CLASSES,
                "autocomplete": "off",
            },
        )
        self.assertEqual(
            widget.render("date", None),
            '<input type="text" name="date" placeholder="mm/dd/yyyy" '
            f'class="{NEW_STACK_WIDGET_CLASSES}" autocomplete="off">',
        )

    def test_caller_attrs_override_defaults(self) -> None:
        """Retain explicit class and autocomplete values from the caller."""
        widget = TextInput(
            attrs={"class": "custom-class", "autocomplete": "name"}
        )

        self.assertEqual(
            widget.attrs,
            {"class": "custom-class", "autocomplete": "name"},
        )


class SelectTest(SimpleTestCase):
    """Test the shared select used by new-stack Django forms."""

    def test_defaults_and_caller_attrs(self) -> None:
        """Apply select defaults without mutating caller attributes."""
        attrs = {"data-example": "value"}

        widget = Select(attrs=attrs)

        self.assertEqual(attrs, {"data-example": "value"})
        self.assertEqual(
            widget.attrs,
            {
                "data-example": "value",
                "class": NEW_STACK_WIDGET_CLASSES,
            },
        )
        self.assertNotIn("autocomplete", widget.attrs)

    def test_input_text_class(self) -> None:
        """Append input-text once after the common classes when requested."""
        expected_classes = f"{NEW_STACK_WIDGET_CLASSES} input-text"

        widget = Select(input_text=True)
        existing_widget = Select(
            attrs={"class": expected_classes}, input_text=True
        )

        self.assertEqual(widget.attrs["class"], expected_classes)
        self.assertEqual(existing_widget.attrs["class"], expected_classes)
        self.assertEqual(
            widget.render("state", None).partition(">")[0] + ">",
            f'<select name="state" class="{expected_classes}">',
        )

    def test_caller_class_overrides_default(self) -> None:
        """Retain an explicit caller class when input-text is not requested."""
        widget = Select(attrs={"class": "custom-class"})

        self.assertEqual(widget.attrs["class"], "custom-class")

    def test_choices(self) -> None:
        """Pass choices through to Django's Select implementation."""
        widget = Select(choices=(("ny", "New York"),))

        rendered = widget.render("state", "ny")

        self.assertInHTML(
            '<option value="ny" selected>New York</option>', rendered
        )
