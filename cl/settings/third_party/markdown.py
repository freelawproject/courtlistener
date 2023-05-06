import re

MARKDOWN_DEUX_STYLES = {
    "default": {
        "extras": {
            "code-friendly": None,
            "cuddled-lists": None,
            "footnotes": None,
            "header-ids": None,
            "link-patterns": None,
            "nofollow": None,
            "smarty-pants": None,
            "tables": None,
        },
        "safe_mode": "escape",
        "link_patterns": [
            (
                re.compile(r"network\s+#?(\d+)\b", re.I),
                r"/visualizations/scotus-mapper/\1/md/",
            ),
            (re.compile(r"opinion\s+#?(\d+)\b", re.I), r"/opinion/\1/md/"),
        ],
    },
}
