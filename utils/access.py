from __future__ import annotations

from datetime import datetime

from flask import current_app

from CTFd.models import Users, db

from ..models import Module, ModuleAccess, ModuleStatus


def is_admin(user: Users | None) -> bool:
    return bool(user and getattr(user, "type", None) == "admin")


def user_has_module_access(user: Users | None, module: Module) -> bool:
    if not user:
        return False

    if module.status == ModuleStatus.public:
        return True

    if module.status == ModuleStatus.locked:
        return False

    # private
    ma = (
        ModuleAccess.query.filter_by(user_id=user.id, module_id=module.id)
        .order_by(ModuleAccess.granted_at.desc())
        .first()
    )
    if not ma:
        return False
    if ma.expires_at and ma.expires_at <= datetime.utcnow():
        return False
    return True


def can_view_module(user: Users | None, module: Module) -> bool:
    return bool(user)


def grant_access(module: Module, user: Users, granted_by_user: Users | None = None, expires_at=None) -> None:
    row = ModuleAccess.query.filter_by(user_id=user.id, module_id=module.id).first()
    if row:
        row.expires_at = expires_at
        row.granted_by = getattr(granted_by_user, "id", None)
        row.granted_at = datetime.utcnow()
    else:
        row = ModuleAccess(
            user_id=user.id,
            module_id=module.id,
            granted_by=getattr(granted_by_user, "id", None),
            expires_at=expires_at,
        )
        db.session.add(row)

    try:
        actor = getattr(granted_by_user, "id", None)
        current_app.logger.info(
            "ctfd_modules: grant access user_id=%s module_id=%s granted_by=%s",
            user.id,
            module.id,
            actor,
        )
    except Exception:
        pass


def revoke_access(module: Module, user_id: int) -> None:
    ModuleAccess.query.filter_by(module_id=module.id, user_id=user_id).delete()
