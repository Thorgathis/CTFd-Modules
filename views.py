from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from CTFd.models import Solves, db
from CTFd.utils.decorators import ratelimit
from CTFd.utils.user import get_current_user

from .models import Module, ModuleChallenge, ModuleStatus
from .compat import csrf_protect
from .utils import (
    can_view_module,
    module_challenges_query,
    module_progress,
    modules_enabled,
    user_has_module_access,
    grant_access,
    get_settings,
    ordered_modules_query,
    ordered_category_names,
)

try:
    from CTFd.utils.config import is_teams_mode
except Exception:
    is_teams_mode = None

try:
    from CTFd.utils.user import get_current_team
except Exception:
    get_current_team = None


modules_bp = Blueprint("ctfd_modules", __name__, template_folder="templates", static_folder="static")


def _require_login():
    user = get_current_user()
    if user:
        return user

    next_url = request.full_path if request.query_string else request.path
    return redirect(f"/login?next={next_url}")


def _current_user_or_redirect():
    user = _require_login()
    if hasattr(user, "id"):
        return user, None
    return None, user


def _ensure_modules_enabled():
    if not modules_enabled():
        abort(404)


def _extract_payload(result):
    if isinstance(result, tuple):
        body = result[0]
    else:
        body = result

    if hasattr(body, "get_json"):
        try:
            body = body.get_json(silent=True)
        except Exception:
            body = None

    return body if isinstance(body, dict) else None


def _extract_challenge_rows(payload):
    if not isinstance(payload, dict):
        return []

    data_root = payload.get("data")
    if isinstance(data_root, list):
        return data_root

    if isinstance(data_root, dict):
        for key in ("challenges", "results", "items", "data"):
            rows = data_root.get(key)
            if isinstance(rows, list):
                return rows

    return []


def _visible_challenge_ids_for_current_user(challenge_ids: set[int]) -> set[int] | None:
    if not challenge_ids:
        return set()

    try:
        from CTFd.api.v1.challenges import ChallengeList as ChallengeListResource
    except Exception:
        return None

    visible_ids: set[int] = set()
    checker = ChallengeListResource()

    try:
        payload = _extract_payload(checker.get({}))
    except TypeError:
        payload = _extract_payload(checker.get())
    except HTTPException:
        return None
    except Exception:
        return None

    if not payload or payload.get("success") is not True:
        return None

    for row in _extract_challenge_rows(payload):
        if not isinstance(row, dict):
            continue
        if str(row.get("type", "")).lower() == "hidden":
            continue
        try:
            challenge_id = int(row.get("id"))
        except Exception:
            continue
        if challenge_id in challenge_ids:
            visible_ids.add(challenge_id)

    return visible_ids


def _solve_ids_for_user(user, allowed_challenge_ids: set[int]) -> set[int]:
    if not user or not allowed_challenge_ids:
        return set()

    q = db.session.query(Solves.challenge_id).filter(Solves.challenge_id.in_(list(allowed_challenge_ids)))

    try:
        if is_teams_mode and is_teams_mode() and get_current_team:
            team = get_current_team()
            if team:
                q = q.filter(Solves.team_id == team.id)
            else:
                q = q.filter(Solves.user_id == user.id)
        else:
            q = q.filter(Solves.user_id == user.id)
    except Exception:
        q = q.filter(Solves.user_id == user.id)

    return {challenge_id for (challenge_id,) in q.all()}


@modules_bp.route("/modules")
def modules_index():
    _ensure_modules_enabled()
    user, redirect_response = _current_user_or_redirect()
    if redirect_response:
        return redirect_response

    modules = ordered_modules_query().all()
    visible = [m for m in modules if can_view_module(user, m)]

    # Do not show locked modules in the list.
    visible = [m for m in visible if m.status != ModuleStatus.locked]

    # Requirement: private modules must not be shown in the general list
    # unless the user already has access.
    visible = [
        m
        for m in visible
        if m.status == ModuleStatus.public
        or (m.status == ModuleStatus.private and user_has_module_access(user, m))
    ]

    module_ids = [m.id for m in visible]
    challenge_ids_by_module: dict[int, list[int]] = {}
    if module_ids:
        rows = (
            db.session.query(ModuleChallenge.module_id, ModuleChallenge.challenge_id)
            .filter(ModuleChallenge.module_id.in_(module_ids))
            .all()
        )
        for module_id, challenge_id in rows:
            if module_id not in challenge_ids_by_module:
                challenge_ids_by_module[module_id] = []
            challenge_ids_by_module[module_id].append(challenge_id)

    all_module_challenge_ids = {
        challenge_id
        for ids in challenge_ids_by_module.values()
        for challenge_id in ids
    }

    visible_challenge_ids = _visible_challenge_ids_for_current_user(all_module_challenge_ids)
    if visible_challenge_ids is None:
        visible_challenge_ids = set()

    solved_ids = _solve_ids_for_user(user, visible_challenge_ids)

    cards = []
    for m in visible:
        has_access = user_has_module_access(user, m)
        module_challenge_ids = challenge_ids_by_module.get(m.id, [])
        available_ids = [challenge_id for challenge_id in module_challenge_ids if challenge_id in visible_challenge_ids]
        if not available_ids:
            continue

        if has_access:
            solved = sum(1 for challenge_id in available_ids if challenge_id in solved_ids)
            total = len(available_ids)
            percent = int((solved / total) * 100) if total else 0
            prog = {"solved": solved, "total": total, "percent": percent}
        else:
            prog = {"solved": 0, "total": len(available_ids), "percent": 0}

        cards.append(
            {
                "module": m,
                "has_access": has_access,
                "progress": prog,
            }
        )

    # Group by categories (with ordering from ModuleCategory).
    # Modules without a category are intentionally hidden from the public /modules list.
    category_names = ordered_category_names()
    grouped = {name: [] for name in category_names}
    extra_category_names = []

    for card in cards:
        cat = (card["module"].category or "").strip()
        if not cat:
            continue
        if cat not in grouped:
            grouped[cat] = []
            extra_category_names.append(cat)
        grouped[cat].append(card)

    ordered_all = category_names + sorted(set(extra_category_names))
    grouped_list = [(name, grouped.get(name, [])) for name in ordered_all if grouped.get(name)]
    return render_template("modules/index.html", grouped=grouped_list)


@modules_bp.route("/modules/join", methods=["GET", "POST"])
@ratelimit(method="POST", limit=10, interval=60)
@csrf_protect
def modules_join():
    _ensure_modules_enabled()
    user, redirect_response = _current_user_or_redirect()
    if redirect_response:
        return redirect_response
    prefill = request.args.get("code")

    if request.method == "POST":
        code = (request.form.get("invite_code") or "").strip().upper()
        module = Module.query.filter(Module.invite_code == code).first()
        if not module:
            flash("Invalid invite code", "danger")
            return render_template("modules/join.html", prefill=prefill)

        if module.status != ModuleStatus.private:
            flash("This module does not require an invite", "info")
            return redirect(url_for("ctfd_modules.module_view", module_id=module.id))

        grant_access(module, user, granted_by_user=None)
        db.session.commit()

        flash("Access granted", "success")
        return redirect(url_for("ctfd_modules.module_view", module_id=module.id))

    return render_template("modules/join.html", prefill=prefill)


@modules_bp.route("/modules/<int:module_id>")
def module_view(module_id: int):
    _ensure_modules_enabled()
    user, redirect_response = _current_user_or_redirect()
    if redirect_response:
        return redirect_response
    module = Module.query.get_or_404(module_id)

    has_access = user_has_module_access(user, module)

    # locked modules are not accessible (no tasks) regardless of role/access
    if module.status == ModuleStatus.locked:
        s = get_settings(create=True)
        lock_message = getattr(s, "lock_message", None)
        return render_template(
            "modules/locked.html",
            module=module,
            lock_message=lock_message,
        )

    if module.status == ModuleStatus.private and not has_access:
        abort(403)

    challenges = module_challenges_query(module, include_hidden=False)
    progress = module_progress(user, module)

    challenge_ids = [c.id for c in challenges]

    return render_template(
        "modules/challenge_listing.html",
        module=module,
        progress=progress,
        challenge_ids=challenge_ids,
    )


@modules_bp.route("/modules/<int:module_id>/join", methods=["POST"])
@ratelimit(method="POST", limit=10, interval=60)
@csrf_protect
def module_join_post(module_id: int):
    _ensure_modules_enabled()
    user, redirect_response = _current_user_or_redirect()
    if redirect_response:
        return redirect_response
    module = Module.query.get_or_404(module_id)

    if module.status != ModuleStatus.private:
        flash("This module does not require an invite", "info")
        return redirect(url_for("ctfd_modules.module_view", module_id=module.id))

    code = (request.form.get("invite_code") or "").strip().upper()
    if not code:
        flash("Please enter a valid invite code", "danger")
        return redirect(url_for("ctfd_modules.module_view", module_id=module.id))
    if not module.invite_code or code != module.invite_code:
        flash("Invalid invite code", "danger")
        return redirect(url_for("ctfd_modules.module_view", module_id=module.id))

    grant_access(module, user, granted_by_user=None)
    db.session.commit()

    flash("Access granted", "success")
    return redirect(url_for("ctfd_modules.module_view", module_id=module.id))
