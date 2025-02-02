from django_components import Component, register

@register("h1")
class h1(Component):
    template = """
      <h1 class="">{{ inner }}</h1>
    """

    def get_context_data(self, inner):
        return {"inner": inner}
