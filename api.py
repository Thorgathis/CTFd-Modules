from __future__ import annotations

from flask import Blueprint, jsonify, request

from CTFd.models import Challenges, Solves, Users, db
from CTFd.utils.decorators import authed_only, ratelimit
from CTFd.utils.user import get_current_user

try:
    from CTFd.utils.config import is_teams_mode
except Exception:
    is_teams_mode = None

try:
    from CTFd.utils.user import get_current_team
except Exception:
    get_current_team = None

from .models import Module, ModuleChallenge, ModuleStatus
from .compat import csrf_protect
from .utils import (
    module_challenges_query,
    module_progress,
    user_has_module_access,
    grant_access,
    modules_enabled,
    ordered_modules_query,
)


modules_api_bp = Blueprint("ctfd_modules_api", __name__, url_prefix="/api/v1/modules")


def _modules_disabled_response():
    return jsonify({"success": False, "error": "MODULES_DISABLED"}), 404


def _ensure_modules_enabled():
    if modules_enabled():
        return None
    return _modules_disabled_response()


def _forbidden_response():
    return jsonify({"success": False, "error": "FORBIDDEN"}), 403


def _module_access_error(module: Module, user: Users | None):
    if module.status == ModuleStatus.locked:
        return jsonify({"success": False, "error": "MODULE_LOCKED"}), 403
    if module.status == ModuleStatus.private and not user_has_module_access(user, module):
        return jsonify({"success": False, "error": "MODULE_ACCESS_REQUIRED"}), 403
    return None


def _solved_ids_for_user(user: Users | None) -> set[int]:
    if not user:
        return set()

    try:
        if is_teams_mode and is_teams_mode() and get_current_team:
            team = get_current_team()
            if team:
                return {
                    cid
                    for (cid,) in db.session.query(Solves.challenge_id)
                    .filter(Solves.team_id == team.id)
                    .all()
                }
    except Exception:
        pass

    return {
        cid
        for (cid,) in db.session.query(Solves.challenge_id)
        .filter(Solves.user_id == user.id)
        .all()
    }


def _module_to_dict(module: Module, user: Users | None):
    has_access = user_has_module_access(user, module) if user else False
    progress = module_progress(user, module) if has_access else {"solved": 0, "total": 0, "percent": 0}
    return {
        "id": module.id,
        "name": module.name,
        "category": module.category,
        "banner_url": module.banner_url,
        "order": module.order,
        "status": module.status.value if hasattr(module.status, "value") else str(module.status),
        "created_at": module.created_at.isoformat() if module.created_at else None,
        "updated_at": module.updated_at.isoformat() if module.updated_at else None,
        "has_access": has_access,
        "progress": progress,
    }


@modules_api_bp.route("", methods=["GET"])
@authed_only
def api_modules_list():
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    modules = ordered_modules_query().all()
    # Locked modules are not visible via list for anyone.
    modules = [m for m in modules if m.status != ModuleStatus.locked]

    # Private modules should not appear in the general list unless the user has access.
    modules = [
        m
        for m in modules
        if m.status == ModuleStatus.public
        or (m.status == ModuleStatus.private and user_has_module_access(user, m))
    ]

    return jsonify({"success": True, "data": [_module_to_dict(m, user) for m in modules]})


@modules_api_bp.route("/<int:module_id>", methods=["GET"])
@authed_only
def api_modules_get(module_id: int):
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    module = Module.query.get_or_404(module_id)
    access_error = _module_access_error(module, user)
    if access_error:
        return access_error

    return jsonify({"success": True, "data": _module_to_dict(module, user)})


@modules_api_bp.route("/<int:module_id>/join", methods=["POST"])
@authed_only
@ratelimit(method="POST", limit=10, interval=60)
@csrf_protect
def api_modules_join(module_id: int):
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    module = Module.query.get_or_404(module_id)

    if module.status != ModuleStatus.private:
        return jsonify({"success": False, "error": "MODULE_NOT_PRIVATE"}), 400

    body = request.get_json(silent=True) or {}
    code = (body.get("invite_code") or "").strip().upper()
    if not code or not module.invite_code or code != module.invite_code:
        return jsonify({"success": False, "error": "INVALID_INVITE_CODE"}), 400

    grant_access(module, user, granted_by_user=None)
    db.session.commit()

    return jsonify({"success": True, "data": _module_to_dict(module, user)})


@modules_api_bp.route("/<int:module_id>/challenges", methods=["GET"])
@authed_only
def api_modules_challenges(module_id: int):
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    module = Module.query.get_or_404(module_id)
    access_error = _module_access_error(module, user)
    if access_error:
        return access_error

    challenges = module_challenges_query(module, include_hidden=False)
    solved_ids = _solved_ids_for_user(user)

    data = []
    for c in challenges:
        data.append(
            {
                "id": c.id,
                "name": c.name,
                "category": c.category,
                "value": c.value,
                "state": c.state,
                "type": c.type,
                "solved": c.id in solved_ids,
            }
        )

    return jsonify({"success": True, "data": data})


@modules_api_bp.route("/assign", methods=["POST"])
@authed_only
@csrf_protect
def api_modules_assign_challenge():
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    if not user or getattr(user, "type", None) != "admin":
        return _forbidden_response()

    body = request.get_json(silent=True) or {}
    challenge_id = body.get("challenge_id")
    module_id = body.get("module_id")
    try:
        challenge_id = int(challenge_id)
        module_id = int(module_id)
    except Exception:
        return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    # Validate existence
    if not Challenges.query.get(challenge_id):
        return jsonify({"success": False, "error": "CHALLENGE_NOT_FOUND"}), 404
    if not Module.query.get(module_id):
        return jsonify({"success": False, "error": "MODULE_NOT_FOUND"}), 404

    # One-to-many mapping: ensure at most one module per challenge.
    from .models import ModuleChallenge

    row = ModuleChallenge.query.filter_by(challenge_id=challenge_id).first()
    if row:
        row.module_id = module_id
    else:
        db.session.add(ModuleChallenge(challenge_id=challenge_id, module_id=module_id))

    db.session.commit()
    return jsonify({"success": True})


@modules_api_bp.route("/unassign", methods=["POST"])
@authed_only
@csrf_protect
def api_modules_unassign_challenge():
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    if not user or getattr(user, "type", None) != "admin":
        return _forbidden_response()

    body = request.get_json(silent=True) or {}
    challenge_id = body.get("challenge_id")
    try:
        challenge_id = int(challenge_id)
    except Exception:
        return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    from .models import ModuleChallenge

    ModuleChallenge.query.filter_by(challenge_id=challenge_id).delete()
    db.session.commit()
    return jsonify({"success": True})


@modules_api_bp.route("/challenge/<int:challenge_id>", methods=["GET"])
@authed_only
def api_modules_challenge_mapping(challenge_id: int):
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    if not user or getattr(user, "type", None) != "admin":
        return _forbidden_response()

    row = ModuleChallenge.query.filter_by(challenge_id=challenge_id).first()
    module = Module.query.get(row.module_id) if row else None

    return jsonify(
        {
            "success": True,
            "data": {
                "challenge_id": challenge_id,
                "module_id": (row.module_id if row else None),
                "module_name": (module.name if module else None),
            },
        }
    )


@modules_api_bp.route("/bulk/assign", methods=["POST"])
@authed_only
@csrf_protect
def api_modules_bulk_assign_challenges():
    """Assign or unassign module for multiple challenges.

    Payload:
      - challenge_ids: list[int]
      - module_id: int | null | ""  (empty/null -> unassign)
    """

    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    if not user or getattr(user, "type", None) != "admin":
        return _forbidden_response()

    body = request.get_json(silent=True) or {}
    raw_ids = body.get("challenge_ids")
    raw_module_id = body.get("module_id")

    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    challenge_ids: list[int] = []
    for x in raw_ids:
        try:
            challenge_ids.append(int(x))
        except Exception:
            continue
    # De-dup while preserving order
    challenge_ids = list(dict.fromkeys([cid for cid in challenge_ids if cid > 0]))
    if not challenge_ids:
        return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    module_id: int | None
    if raw_module_id in (None, ""):
        module_id = None
    else:
        try:
            module_id = int(raw_module_id)
        except Exception:
            return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    # Validate module existence if assigning
    if module_id is not None and not Module.query.get(module_id):
        return jsonify({"success": False, "error": "MODULE_NOT_FOUND"}), 404

    # Only operate on existing challenges
    existing_ids = {
        cid
        for (cid,) in db.session.query(Challenges.id)
        .filter(Challenges.id.in_(challenge_ids))
        .all()
    }
    if not existing_ids:
        return jsonify({"success": False, "error": "NO_CHALLENGES_FOUND"}), 404

    from .models import ModuleChallenge

    if module_id is None:
        ModuleChallenge.query.filter(ModuleChallenge.challenge_id.in_(list(existing_ids))).delete(
            synchronize_session=False
        )
        db.session.commit()
        return jsonify({"success": True, "data": {"updated": len(existing_ids), "module_id": None}})

    # Upsert mapping for one-to-many relation
    rows = ModuleChallenge.query.filter(ModuleChallenge.challenge_id.in_(list(existing_ids))).all()
    seen = set()
    for row in rows:
        row.module_id = module_id
        seen.add(row.challenge_id)

    missing = [cid for cid in existing_ids if cid not in seen]
    for cid in missing:
        db.session.add(ModuleChallenge(challenge_id=cid, module_id=module_id))

    db.session.commit()
    return jsonify({"success": True, "data": {"updated": len(existing_ids), "module_id": module_id}})


@modules_api_bp.route("/<int:module_id>/progress", methods=["GET"])
@authed_only
def api_modules_progress(module_id: int):
    disabled = _ensure_modules_enabled()
    if disabled:
        return disabled

    user = get_current_user()
    module = Module.query.get_or_404(module_id)
    access_error = _module_access_error(module, user)
    if access_error:
        return access_error

    return jsonify({"success": True, "data": module_progress(user, module)})
