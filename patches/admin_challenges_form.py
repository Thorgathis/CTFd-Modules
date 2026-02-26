from __future__ import annotations

import re

from .template_override import override_template_source


_OLD_BLOCK_RE = re.compile(
  r"\s*{%-?\s*block\s+ctfd_modules_module\s*-?%}.*?{%-?\s*endblock\s*-?%}\s*",
  flags=re.DOTALL,
)


def patch_admin_challenge_form_templates(app) -> dict:
  """Patch admin challenge create/update templates to include module selector."""

  results = {"create": False, "update": False}

  def _module_field_snippet() -> str:
    # NOTE: intentionally not wrapped in a Jinja `{% block %}`.
    # Blocks can conflict with other plugins or be injected twice.
    return """
  <div class=\"form-group\" id=\"ctfd-modules-module-field\">
    <label>Module</label>
    {% set _ctfd_modules_cur = (ctfd_modules_challenge_module_id(challenge.id) if challenge is defined else None) %}
    {# IMPORTANT: no `name` attribute; otherwise CTFd will try to bind it to the Challenges model and fail. #}
    <select class=\"form-control\" id=\"ctfd-modules-module-select\">
    <option value=\"\">—</option>
    {% for m in (ctfd_modules_all_modules() or []) %}
      <option value=\"{{ m.id }}\" {% if _ctfd_modules_cur == m.id %}selected{% endif %}>{{ m.name }}</option>
    {% endfor %}
    </select>
  </div>

  <script src=\"/plugins/ctfd_modules/static/js/admin_challenges_patch.js?v=admin-modules-fix-1\"></script>
"""

  def inject_module_field(src: str) -> str:
    # Self-heal older versions which wrapped the injected HTML in a Jinja block.
    # If injected multiple times, Jinja errors with "block defined twice".
    src = _OLD_BLOCK_RE.sub("\n", src)

    # Idempotency: if already patched, don't inject again.
    if "ctfd-modules-module-select" in src or "ctfd-modules-module-field" in src:
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
