from __future__ import annotations

from collections.abc import Callable


def get_template_source(app, template_name: str) -> str | None:
    try:
        source, _, _ = app.jinja_loader.get_source(app.jinja_env, template_name)
        return source
    except Exception:
        return None


def override_template_source(app, template_name: str, transform: Callable[[str], str]) -> bool:
    """Best-effort override of a Jinja template source.

    Returns True if template was overridden and the content changed.
    """

    try:
        from CTFd.plugins import override_template

        original = None
        try:
            # If already overridden, prefer that source.
            original = app.overridden_templates.get(template_name)
        except Exception:
            original = None

        if not original:
            original = get_template_source(app, template_name)

        if not original:
            return False

        patched = transform(original)
        if not patched or patched == original:
            return False

        override_template(template_name, patched)
        return True
    except Exception:
        return False
