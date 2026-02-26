from __future__ import annotations

from .admin_challenges_form import patch_admin_challenge_form_templates
from .admin_challenges_listing import patch_admin_challenge_listing_templates


def patch_admin_challenge_templates(app) -> dict:
    """Patch core admin challenge templates to include module selector.

    We avoid touching CTFd internals: the selector is saved via a small JS call to
    our plugin API endpoint which updates module_challenges mapping.
    """

    results = {"create": False, "update": False, "listing": False}

    try:
        results.update(patch_admin_challenge_form_templates(app))
    except Exception:
        pass

    try:
        results.update(patch_admin_challenge_listing_templates(app))
    except Exception:
        pass

    return results
