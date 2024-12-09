from django_components.component import Component, register


@register("date")
class Date(Component):
    template = "<div class='date-component rounded-lg border border-gray-200 flex items-center px-4 py-2'>Today's date is {{ date }}</div>"

    def get_context_data(self, date):
        return {"date": date}
