from eyecite.models import (
    FullCitation,
    IdCitation,
    ShortformCitation,
    SupraCitation,
)


def full_citation_as_html(self):
    # Uses reporter_found so that we don't update the text. This guards us
    # against accidentally updating things like docket number 22 Cr. 1 as
    # 22 Cranch 1, which is totally wrong.
    template = (
        '<span class="volume">%(volume)d</span>\\g<1>'
        '<span class="reporter">%(reporter)s</span>\\g<2>'
        '<span class="page">%(page)s</span>\\g<3>'
    )
    inner_html = template % self.__dict__
    span_class = "citation"
    if self.match_url:
        inner_html = '<a href="%s">%s</a>' % (self.match_url, inner_html)
        data_attr = ' data-id="%s"' % self.match_id
    else:
        span_class += " no-link"
        data_attr = ""
    return '<span class="%s"%s>%s</span>' % (
        span_class,
        data_attr,
        inner_html,
    )


def shortform_citation_as_html(self):
    # Don't include the antecedent guess in the HTML link, since the guess
    # might be horribly wrong.
    inner_html = (
        '<span class="volume">%(volume)d</span>\\g<2>'
        + '<span class="reporter">%(reporter)s</span>\\g<3>\\g<4>at\\g<5>'
        + '<span class="page">%(page)s</span>\\g<6>'
    )
    inner_html = inner_html % self.__dict__
    span_class = "citation"
    if self.match_url:
        inner_html = '<a href="%s">%s</a>' % (self.match_url, inner_html)
        data_attr = ' data-id="%s"' % self.match_id
    else:
        span_class += " no-link"
        data_attr = ""
    return (
        '<span class="%s"%s><span class="antecedent_guess">%s</span>\\g<1>%s</span>'
        % (span_class, data_attr, self.antecedent_guess, inner_html)
    )


def supra_citation_as_html(self):
    inner_html = (
        '<span class="antecedent_guess">%s</span>' % self.antecedent_guess
    )
    if self.volume:
        inner_html += (
            '\\g<1><span class="volume">%d</span>\\g<2>supra' % self.volume
        )
        if self.page:
            inner_html += (
                ',\\g<3>at\\g<4><span class="page">%s</span>\\g<5>' % self.page
            )
        else:
            inner_html += "\\g<3>"
    else:
        inner_html += "\\g<1>supra"
        if self.page:
            inner_html += (
                ',\\g<2>at\\g<3><span class="page">%s</span>\\g<4>' % self.page
            )
        else:
            inner_html += "\\g<2>"

    span_class = "citation"
    if self.match_url:
        inner_html = '<a href="%s">%s</a>' % (self.match_url, inner_html)
        data_attr = ' data-id="%s"' % self.match_id
    else:
        span_class += " no-link"
        data_attr = ""
    return '<span class="%s"%s>%s</span>' % (
        span_class,
        data_attr,
        inner_html,
    )


def id_citation_as_html(self):
    def generate_after_token_html():
        # First, insert the regex backreferences between each "after token"
        # The group numbers of each backreference (g<NUMBER>) must be
        #   dynamically generated because total number of "after tokens" varies
        # Produces something like this:
        # "\\g<2>after_token_1\\g<3>after_token_2\\g<4>after_token_3" ...
        template = "\\g<%s>%s"
        after_token_html = "".join(
            [
                template % (str(i + 2), t)
                for i, t in enumerate(self.after_tokens)
            ]
        )

        # Then, append one final backreference to the end of the string
        after_token_html += "\\g<" + str(len(self.after_tokens) + 2) + ">"

        # Return the full string
        return after_token_html

    span_class = "citation"
    after_token_html = generate_after_token_html()
    if self.match_url:
        if self.has_page:
            id_string_template = (
                '<a href="%s"><span class="id_token">%s</span>%s</a>'
            )
        else:
            id_string_template = (
                '<a href="%s"><span class="id_token">%s</span></a>%s'
            )
        id_string = id_string_template % (
            self.match_url,
            self.id_token,
            after_token_html,
        )
        data_attr = ' data-id="%s"' % self.match_id
    else:
        id_string = '<span class="id_token">%s</span>%s' % (
            self.id_token,
            after_token_html,
        )
        span_class += " no-link"
        data_attr = ""
    return '<span class="%s"%s>\\g<1>%s</span>' % (
        span_class,
        data_attr,
        id_string,
    )


FullCitation.as_html = full_citation_as_html
ShortformCitation.as_html = shortform_citation_as_html
SupraCitation.as_html = supra_citation_as_html
IdCitation.as_html = id_citation_as_html
