from __future__ import annotations

from .access import can_view_module, grant_access, is_admin, revoke_access, user_has_module_access
from .invites import ensure_private_invite_code, generate_invite_code, invite_code_length
from .progress import module_challenges_query, module_progress
from .queries import module_ordering, ordered_modules_query, ordered_categories_query, ordered_category_names
from .settings import get_settings, update_settings_from_form, get_ui_theme


def modules_enabled() -> bool:
    s = get_settings(create=True)
    return bool(getattr(s, "modules_enabled", True))
