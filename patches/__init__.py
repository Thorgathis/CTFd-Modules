from __future__ import annotations

from .admin_challenges import patch_admin_challenge_templates
from .admin_challenges_form import patch_admin_challenge_form_templates
from .admin_challenges_listing import patch_admin_challenge_listing_templates


def apply_patches(app) -> dict:
    results: dict[str, object] = {}

    results["admin_challenges_form"] = patch_admin_challenge_form_templates(app)
    results["admin_challenges_listing"] = patch_admin_challenge_listing_templates(app)


    return results
