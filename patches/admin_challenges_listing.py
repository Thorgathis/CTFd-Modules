from __future__ import annotations

import re

from .template_override import override_template_source

_OLD_BULK_TEMPLATE_RE = re.compile(
    r"\s*<template id=\"ctfd-modules-bulk-module-options\">.*?</template>\s*",
    flags=re.DOTALL,
)

_OLD_PATCH_SCRIPT_RE = re.compile(
    r"\s*<script src=\"/plugins/ctfd_modules/static/js/admin_challenges_patch\.js[^\"]*\"></script>\s*",
    flags=re.IGNORECASE,
)


def patch_admin_challenge_listing_templates(app) -> dict:
    """Patch admin challenge listing template to show Module + bulk assignment."""

    results = {"listing": False}

    def inject_listing_column(src: str) -> str:
        src2 = src

        # Cleanup from older buggy patch versions that accidentally inserted literal "\\1".
        src2 = src2.replace("\\1\n<script>", "\n<script>").replace("\\1<script>", "<script>")
        if "\\1" in src2:
            src2 = src2.replace("\\1\n", "\n").replace("\\1", "")
        # Self-heal old template/script injections.
        src2 = _OLD_BULK_TEMPLATE_RE.sub("\n", src2)
        src2 = _OLD_PATCH_SCRIPT_RE.sub("\n", src2)

        # Header insert before Category
        src2 = re.sub(
            r"<th class=\"sort-col\">\s*<b>Category</b>\s*</th>",
            '<th class="sort-col"><b>Modules</b></th>\\n\\g<0>',
            src2,
            count=1,
        )

        # Row insert before category cell
        src2 = re.sub(
            r"<td>\s*{{\s*challenge\.category\s*}}\s*</td>",
            '<td>{{ ctfd_modules_challenge_module_name(challenge.id) }}</td>\\n\\g<0>',
            src2,
            count=1,
        )

        # Bulk module assignment inside the existing CTFd bulk-edit modal.
        # We inject only a <template> with module options and the JS loader.
        if "ctfd-modules-bulk-module-options" not in src2:
            inject = """
<template id=\"ctfd-modules-bulk-module-options\">
  {% for m in (ctfd_modules_all_modules() or []) %}<option value=\"{{ m.id }}\">{{ m.name|e }}</option>{% endfor %}
</template>
<script src=\"/plugins/ctfd_modules/static/js/admin_challenges_patch.js\"></script>
"""

            def _after_table(m):
                return m.group(1) + "\n" + inject

            if re.search(r"</table>", src2, flags=re.IGNORECASE):
                src2 = re.sub(r"(</table>)", _after_table, src2, count=1, flags=re.IGNORECASE)
            else:
                src2 = src2 + "\n" + inject

        return src2

    results["listing"] = (
        override_template_source(app, "admin/challenges/challenges.html", inject_listing_column)
        or override_template_source(app, "admin/challenges/index.html", inject_listing_column)
        or override_template_source(app, "admin/challenges/list.html", inject_listing_column)
    )

    return results
