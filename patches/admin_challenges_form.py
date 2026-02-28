from __future__ import annotations

import re

from .template_override import override_template_source


_OLD_BLOCK_RE = re.compile(
  r"\s*{%-?\s*block\s+ctfd_modules_module\s*-?%}.*?{%-?\s*endblock\s*-?%}\s*",
  flags=re.DOTALL,
)

_OLD_FIELD_RE = re.compile(
  r"\s*<div class=\"form-group\" id=\"ctfd-modules-module-field\">.*?</div>\s*",
  flags=re.DOTALL,
)

_OLD_SCRIPT_RE = re.compile(
  r"\s*<script src=\"/plugins/ctfd_modules/static/js/admin_challenges_patch\.js[^\"]*\"></script>\s*",
  flags=re.IGNORECASE,
)


def patch_admin_challenge_form_templates(app) -> dict:
  """Patch admin challenge create/update templates to include modules selector."""

  results = {"create": False, "update": False}

  def _module_field_snippet() -> str:
    # NOTE: intentionally not wrapped in a Jinja `{% block %}`.
    # Blocks can conflict with other plugins or be injected twice.
    return """
  <div class=\"form-group\" id=\"ctfd-modules-module-field\">
      {% set _ctfd_modules_cur_ids = (ctfd_modules_challenge_module_ids(challenge.id) if challenge is defined else []) %}
    <label class=\"mb-1\" for=\"ctfd-modules-module-picker\">Modules</label>
    <select id=\"ctfd-modules-module-picker\" class=\"form-control\">
      <option value=\"\">— Select module —</option>
    </select>
    <div id=\"ctfd-modules-tags\" class=\"my-2\"></div>
    <small id=\"ctfd-modules-module-status\" class=\"form-text text-muted mt-1\"></small>
    {# IMPORTANT: no `name` attribute; otherwise CTFd will try to bind it to the Challenges model and fail. #}
    <select class=\"d-none\" id=\"ctfd-modules-module-select\" multiple>
    {% for m in (ctfd_modules_all_modules() or []) %}
      <option value=\"{{ m.id }}\" data-name=\"{{ m.name|e }}\" data-category=\"{{ (m.category or 'No Category')|e }}\" {% if m.id in _ctfd_modules_cur_ids %}selected{% endif %}>{{ m.name }}</option>
    {% endfor %}
    </select>
  </div>

  <script src=\"/plugins/ctfd_modules/static/js/admin_challenges_patch.js\"></script>
"""

  def inject_module_field(src: str) -> str:
    # Self-heal older versions which wrapped the injected HTML in a Jinja block.
    # If injected multiple times, Jinja errors with "block defined twice".
    src = _OLD_BLOCK_RE.sub("\n", src)
    # Self-heal older single-module snippets and script tags.
    src = _OLD_FIELD_RE.sub("\n", src)
    src = _OLD_SCRIPT_RE.sub("\n", src)

    # Idempotency: if already patched, don't inject again.
    if "ctfd-modules-module-picker" in src and "ctfd-modules-tags" in src:
      return src

    insert = _module_field_snippet()

    # Preferred insertion point: right before the core category block.
    marker = "{% block category %}"
    pos = src.find(marker)
    if pos != -1:
      return src[:pos] + insert + src[pos:]

    # Fallback: insert near the category form-group in older/forked templates.
    patterns = [
      r"(<label[^>]*>\s*Category\s*(?:<[^>]+>\s*)*</label>)",
      r"(<input[^>]+name=\"category\"[^>]*>)",
      r"(<select[^>]+name=\"category\"[^>]*>)",
    ]
    for pat in patterns:
      mm = re.search(pat, src, flags=re.IGNORECASE)
      if mm:
        return src[: mm.start()] + insert + src[mm.start() :]

    return src

  results["create"] = (
    override_template_source(app, "admin/challenges/create.html", inject_module_field)
    or override_template_source(app, "admin/challenges/new.html", inject_module_field)
  )

  results["update"] = (
    override_template_source(app, "admin/challenges/update.html", inject_module_field)
    or override_template_source(app, "admin/challenges/edit.html", inject_module_field)
    or override_template_source(app, "admin/challenges/challenge.html", inject_module_field)
  )

  return results
