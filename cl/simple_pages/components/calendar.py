from django_components import Component, register

@register("calendar")
class calendar(Component):
    template = """
      <div class="calendar">
        Today's date is <span>{{ date }}</span>
      </div>
    """

    def get_context_data(self, date):
        return {"date": date}
