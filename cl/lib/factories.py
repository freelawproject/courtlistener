import copy

from factory import RelatedFactoryList


class RelatedFactoryVariableList(RelatedFactoryList):
    """This factory allows you to specify how many related objects do you
    want to create, but also allows you to define the data for each related
    object. For example:

    Define how many objects do you want:

        court_scotus = CourtFactory(id="scotus")
        cluster = OpinionClusterFactoryMultipleOpinions(
            docket=DocketFactory(
                court=court_scotus,
                case_name="Lorem v. Ipsum",
                case_name_full="Lorem v. Ipsum",
            ),
            case_name="Lorem v. Ipsum",
            date_filed=date.today(),
            sub_opinions__size=10
        )

    Define each related object:

        court_scotus = CourtFactory(id="scotus")
        cluster = OpinionClusterFactoryMultipleOpinions(
            docket=DocketFactory(
                court=court_scotus,
                case_name="Foo v. Bar",
                case_name_full="Foo v. Bar",
            ),
            case_name="Foo v. Bar",
            date_filed=date.today(),
            sub_opinions__data=[
                {"type": "010combined"},
                {"type": "025plurality"},
                {"type": "080onthemerits", "author_str": "kevin ramirez"},
                {"type": "070rehearing", "plain_text": "hello world"},
            ],
        )

    """

    def call(self, instance, step, context):
        size = context.extra.pop("size", None)
        data = context.extra.pop("data", [])
        if size and data:
            if size != len(data):
                raise TypeError(
                    "RelatedFactoryVariableList you can only use data or size, not both."
                )

        if not size and not data:
            size = self.size

        if size and not data:
            # Generate size number of objects
            return [
                super(RelatedFactoryList, self).call(instance, step, context)
                for i in range(size)
            ]
        results = []
        for d in data:
            # Create copy of PostGenerationContext object
            copied_context = copy.deepcopy(context)
            if isinstance(d, dict):
                # Update data for each factory instance
                copied_context.extra.update(d)
            results.append(
                super(RelatedFactoryList, self).call(
                    instance, step, copied_context
                )
            )
        return results
