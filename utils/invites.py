from __future__ import annotations

import secrets
import string

from CTFd.models import db

from ..models import Module, ModuleStatus
from .settings import get_settings


ALPHABET = string.ascii_uppercase + string.digits


def invite_code_length() -> int:
    s = get_settings(create=True)
    try:
        return int(getattr(s, "invite_code_length", 8) or 8)
    except Exception:
        return 8


def generate_invite_code() -> str:
    length = invite_code_length()
    suffix = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"MOD-{suffix}"


def ensure_private_invite_code(module: Module) -> None:
    if module.status != ModuleStatus.private:
        module.invite_code = None
        return

    if module.invite_code:
        return

    # Ensure uniqueness
    for _ in range(20):
        code = generate_invite_code()
        exists = db.session.query(Module.id).filter(Module.invite_code == code).first()
        if not exists:
            module.invite_code = code
            return

    raise RuntimeError("Unable to generate a unique invite_code")
