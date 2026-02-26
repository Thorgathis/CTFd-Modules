from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from CTFd.models import db

from ..models import ModuleSettings


@dataclass(frozen=True)
class SettingsDefaults:
    modules_enabled: bool = True
    hide_challenges_page: bool = False
    challenges_board_mode: str = "all"
    invite_code_length: int = 8
    lock_message: str = "This module is under construction. Access will be available soon."


UI_THEME_DEFAULT = "auto"
UI_THEME_ALLOWED = ("auto", "pixo", "core-beta")
UI_THEME_CONFIG_KEY = "CTFD_MODULES_UI_THEME"


DEFAULTS = SettingsDefaults()


def _read_ctfd_config(key: str):
    try:
        from CTFd.utils import get_config  # type: ignore

        return get_config(key)
    except Exception:
        pass

    try:
        from CTFd.utils.config import get_config as get_config2  # type: ignore

        return get_config2(key)
    except Exception:
        pass

    return None


def _write_ctfd_config(key: str, value: str) -> None:
    try:
        from CTFd.utils import set_config  # type: ignore

        set_config(key, value)
        return
    except Exception:
        pass

    try:
        from CTFd.utils.config import set_config as set_config2  # type: ignore

        set_config2(key, value)
        return
    except Exception:
        pass


def get_ui_theme() -> str:
    raw = _read_ctfd_config(UI_THEME_CONFIG_KEY)
    val = (str(raw or UI_THEME_DEFAULT)).strip().lower()
    if val not in UI_THEME_ALLOWED:
        val = UI_THEME_DEFAULT
    return val


def set_ui_theme(value: str) -> None:
    val = (str(value or UI_THEME_DEFAULT)).strip().lower()
    if val not in UI_THEME_ALLOWED:
        val = UI_THEME_DEFAULT
    _write_ctfd_config(UI_THEME_CONFIG_KEY, val)


def _read_legacy_ctfd_config(key: str):
    """Best-effort read from CTFd Configs store used by older versions of this plugin."""
    cfg_key = f"CTFD_MODULES_{key.upper()}"

    try:
        from CTFd.utils import get_config  # type: ignore

        val = get_config(cfg_key)
        if val is not None:
            return val
    except Exception:
        pass

    try:
        from CTFd.utils.config import get_config as get_config2  # type: ignore

        val = get_config2(cfg_key)
        if val is not None:
            return val
    except Exception:
        pass

    return None


def _coerce_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _coerce_int(val, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default


def get_settings(create: bool = True) -> ModuleSettings:
    """Return the singleton settings row, creating it if missing.

    Uses a dedicated DB table (`ctfd_modules_settings`).
    On first creation, migrates any legacy values stored in CTFd Configs.
    """

    row = ModuleSettings.query.first()
    if row or not create:
        return row

    # Seed from legacy config values (if present)
    legacy_modules_enabled = _read_legacy_ctfd_config("modules_enabled")
    legacy_hide_challenges_page = _read_legacy_ctfd_config("hide_challenges_page")
    legacy_challenges_board_mode = _read_legacy_ctfd_config("challenges_board_mode")
    legacy_invite_code_length = _read_legacy_ctfd_config("invite_code_length")
    legacy_lock_message = _read_legacy_ctfd_config("lock_message")

    mode = (str(legacy_challenges_board_mode or DEFAULTS.challenges_board_mode)).strip().lower()
    if mode not in ("all", "only_modules", "only_unassigned"):
        mode = DEFAULTS.challenges_board_mode

    row = ModuleSettings(
        modules_enabled=_coerce_bool(legacy_modules_enabled, DEFAULTS.modules_enabled),
        hide_challenges_page=_coerce_bool(legacy_hide_challenges_page, DEFAULTS.hide_challenges_page),
        challenges_board_mode=mode,
        invite_code_length=_coerce_int(legacy_invite_code_length, DEFAULTS.invite_code_length),
        lock_message=str(legacy_lock_message or DEFAULTS.lock_message),
    )

    db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        # In case commit isn't safe at this point, keep it in-session.
        try:
            current_app.logger.warning("ctfd_modules: failed to commit settings row; using in-session instance")
        except Exception:
            pass

    return row


def update_settings_from_form(form) -> None:
    s = get_settings(create=True)

    # checkboxes
    s.modules_enabled = bool(form.get("modules_enabled") == "on")
    s.hide_challenges_page = bool(form.get("hide_challenges_page") == "on")

    # select
    mode = (form.get("challenges_board_mode") or DEFAULTS.challenges_board_mode).strip().lower()
    if mode not in ("all", "only_modules", "only_unassigned"):
        mode = DEFAULTS.challenges_board_mode
    s.challenges_board_mode = mode

    # ints
    s.invite_code_length = _coerce_int(form.get("invite_code_length"), DEFAULTS.invite_code_length)
    if s.invite_code_length < 4:
        s.invite_code_length = 4
    if s.invite_code_length > 32:
        s.invite_code_length = 32

    # text
    s.lock_message = (form.get("lock_message") or DEFAULTS.lock_message).strip() or DEFAULTS.lock_message

    # theme (stored in CTFd Configs to avoid DB migrations)
    set_ui_theme(form.get("ui_theme") or UI_THEME_DEFAULT)

    db.session.commit()
