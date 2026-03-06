from __future__ import annotations

import json
import re

from flask import abort, g, redirect, request
from werkzeug.exceptions import HTTPException

from CTFd.utils.user import get_current_user

from .compat import ctfd_generate_nonce
from .models import Module, ModuleAccess, ModuleChallenge, ModuleStatus
from .utils import get_settings, get_ui_theme, modules_enabled, user_has_module_access


def _challenge_id(item):
    if not isinstance(item, dict):
        return None
    raw = item.get("id", item.get("challenge_id"))
    try:
        return int(raw)
    except Exception:
        return None


def _extract_data_list(payload):
    if not isinstance(payload, dict):
        return None, None, None

    data_root = payload.get("data")
    if isinstance(data_root, list):
        return payload, "data", data_root

    if isinstance(data_root, dict):
        for key in ("challenges", "results", "items", "data"):
            value = data_root.get(key)
            if isinstance(value, list):
                return data_root, key, value

    return None, None, None


def _set_json_response_data(response, payload):
    raw = json.dumps(payload)
    response.set_data(raw)
    response.headers["Content-Length"] = str(len(raw.encode("utf-8")))
    return response


def _modules_for_challenge(challenge_id):
    from CTFd.models import db  # type: ignore

    return (
        db.session.query(Module)
        .join(ModuleChallenge, ModuleChallenge.module_id == Module.id)
        .filter(ModuleChallenge.challenge_id == challenge_id)
        .all()
    )


def _challenge_module_map():
    from CTFd.models import db  # type: ignore

    rows = (
        db.session.query(ModuleChallenge.challenge_id, Module.id, Module.status)
        .join(Module, Module.id == ModuleChallenge.module_id)
        .all()
    )
    out = {}
    for cid, mid, status in rows:
        out.setdefault(cid, []).append((mid, status))
    return out


def _private_module_access_map(private_module_ids):
    user = None
    try:
        user = get_current_user()
    except Exception:
        user = None

    if user is None or not hasattr(user, "id") or not private_module_ids:
        return set()

    from CTFd.models import db  # type: ignore

    return {
        module_id
        for (module_id,) in (
            db.session.query(ModuleAccess.module_id)
            .filter(ModuleAccess.user_id == user.id)
            .filter(ModuleAccess.module_id.in_(list(private_module_ids)))
            .all()
        )
    }


def _module_challenge_ids(module_id):
    from CTFd.models import db  # type: ignore

    return {
        cid
        for (cid,) in (
            db.session.query(ModuleChallenge.challenge_id)
            .filter(ModuleChallenge.module_id == module_id)
            .all()
        )
    }


def _assigned_challenge_ids():
    from CTFd.models import db  # type: ignore

    return {cid for (cid,) in db.session.query(ModuleChallenge.challenge_id).all()}


def _challenge_accessible_via_modules(challenge_modules, allowed_private_module_ids):
    if not challenge_modules:
        return True

    for module_id, status in challenge_modules:
        status_value = status.value if hasattr(status, "value") else str(status)
        if status_value == ModuleStatus.public.value:
            return True
        if status_value == ModuleStatus.private.value and module_id in allowed_private_module_ids:
            return True

    return False


def _parse_module_ids_payload(raw):
    if raw is None:
        return None

    values = None
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if text == "":
            return []
        try:
            decoded = json.loads(text)
            values = decoded if isinstance(decoded, list) else [decoded]
        except Exception:
            values = [part.strip() for part in text.split(",")]
    else:
        values = [raw]

    out = []
    seen = set()
    for item in values:
        try:
            mid = int(item)
        except Exception:
            continue
        if mid <= 0 or mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def _requested_challenge_module_ids():
    staged = getattr(g, "ctfd_modules_requested_module_ids", None)
    if staged is not None:
        return _parse_module_ids_payload(staged)

    if "ctfd_modules_module_ids" in request.form:
        return _parse_module_ids_payload(request.form.get("ctfd_modules_module_ids"))

    body = request.get_json(silent=True) or {}
    if isinstance(body, dict) and "ctfd_modules_module_ids" in body:
        return _parse_module_ids_payload(body.get("ctfd_modules_module_ids"))

    return None


def _challenge_id_from_write_response(response):
    try:
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "application/json" not in ctype:
            return None
        payload = json.loads(response.get_data(as_text=True) or "{}")
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    cid = _challenge_id(payload)
    if cid:
        return cid

    data = payload.get("data")
    cid = _challenge_id(data)
    if cid:
        return cid

    if isinstance(data, dict):
        for key in ("challenge", "result", "item"):
            cid = _challenge_id(data.get(key))
            if cid:
                return cid

    return None


def _apply_challenge_module_ids(challenge_id: int, module_ids: list[int]):
    from CTFd.models import Challenges, db  # type: ignore

    if not Challenges.query.get(challenge_id):
        return

    normalized = []
    seen = set()
    for mid in module_ids or []:
        try:
            value = int(mid)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    if normalized:
        existing = {
            mid
            for (mid,) in db.session.query(Module.id).filter(Module.id.in_(normalized)).all()
        }
        normalized = [mid for mid in normalized if mid in existing]

    ModuleChallenge.query.filter_by(challenge_id=challenge_id).delete()
    for module_id in normalized:
        db.session.add(ModuleChallenge(challenge_id=challenge_id, module_id=module_id))
    db.session.commit()


def register_plugin_runtime_hooks(app):
    @app.context_processor
    def ctfd_modules_inject_nonce():
        return {
            "ctfd_modules_nonce": ctfd_generate_nonce,
            "ctfd_modules_ui_theme": get_ui_theme(),
        }

    @app.before_request
    def ctfd_modules_stage_challenge_write_payload():
        try:
            if not modules_enabled():
                return None

            user = get_current_user()
            if not user or getattr(user, "type", None) != "admin":
                return None

            method = (request.method or "").upper()
            path = request.path or ""
            create_write = method == "POST" and path == "/api/v1/challenges"
            update_write = bool(re.match(r"^/api/v1/challenges/\d+$", path)) and method in {"POST", "PUT", "PATCH"}
            if not create_write and not update_write:
                return None

            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return None

            if "ctfd_modules_module_ids" not in payload:
                return None

            g.ctfd_modules_requested_module_ids = payload.get("ctfd_modules_module_ids")
            try:
                # Prevent CTFd challenge handlers from seeing unknown plugin field.
                payload.pop("ctfd_modules_module_ids", None)
            except Exception:
                pass
        except Exception:
            return None

        return None

    @app.before_request
    def ctfd_modules_redirect_challenges():
        try:
            if not modules_enabled():
                return None

            settings = get_settings(create=True)
            hide = bool(getattr(settings, "hide_challenges_page", False))
            if hide and getattr(request, "endpoint", None) == "challenges.listing":
                return redirect("/modules")
        except Exception:
            return None

        return None

    @app.before_request
    def ctfd_modules_protect_challenge_api():
        try:
            if not modules_enabled():
                return None

            challenge_id = None
            if request.method == "GET":
                match = re.match(r"^/api/v1/challenges/(\d+)$", request.path or "")
                if not match:
                    match = re.match(r"^/api/v1/challenges/(\d+)/solves$", request.path or "")
                if match:
                    challenge_id = int(match.group(1))
            elif request.method == "POST" and (request.path or "") == "/api/v1/challenges/attempt":
                payload = request.get_json(silent=True) or {}
                raw_id = payload.get("challenge_id")
                try:
                    challenge_id = int(raw_id)
                except Exception:
                    challenge_id = None

            if not challenge_id:
                return None

            modules = _modules_for_challenge(challenge_id)
            if not modules:
                return None

            user = get_current_user()
            allowed_private_ids = set()
            for module in modules:
                status_value = module.status.value if hasattr(module.status, "value") else str(module.status)
                if status_value == ModuleStatus.private.value and user_has_module_access(user, module):
                    allowed_private_ids.add(module.id)

            challenge_modules = [(module.id, module.status) for module in modules]
            if not _challenge_accessible_via_modules(challenge_modules, allowed_private_ids):
                abort(403)
        except HTTPException:
            raise
        except Exception:
            return None

        return None

    @app.after_request
    def ctfd_modules_apply_modules_on_challenge_write(response):
        try:
            if not modules_enabled():
                return response

            user = get_current_user()
            if not user or getattr(user, "type", None) != "admin":
                return response

            method = (request.method or "").upper()
            path = request.path or ""
            create_write = method == "POST" and path == "/api/v1/challenges"
            update_match = re.match(r"^/api/v1/challenges/(\d+)$", path)
            update_write = bool(update_match) and method in {"POST", "PUT", "PATCH"}
            if not create_write and not update_write:
                return response

            if int(getattr(response, "status_code", 500) or 500) >= 400:
                return response

            module_ids = _requested_challenge_module_ids()
            if module_ids is None:
                return response

            challenge_id = None
            if update_match:
                challenge_id = int(update_match.group(1))
            else:
                challenge_id = _challenge_id_from_write_response(response)

            if not challenge_id:
                return response

            _apply_challenge_module_ids(int(challenge_id), module_ids)
        except Exception:
            return response

        return response

    @app.after_request
    def ctfd_modules_filter_challenges_api(response):
        try:
            if not modules_enabled():
                return response
            if request.method != "GET" or request.path != "/api/v1/challenges":
                return response
            if getattr(response, "status_code", 200) != 200:
                return response

            ctype = (response.headers.get("Content-Type") or "").lower()
            if "application/json" not in ctype:
                return response

            payload = json.loads(response.get_data(as_text=True) or "{}")
            data_container, data_key, data = _extract_data_list(payload)
            if data_container is None or data_key is None:
                return response
        except Exception:
            return response

        try:
            challenge_to_modules = _challenge_module_map()
            private_module_ids = {
                module_id
                for challenge_modules in challenge_to_modules.values()
                for (module_id, status) in challenge_modules
                if (status.value if hasattr(status, "value") else str(status)) == ModuleStatus.private.value
            }
            allowed_private_module_ids = _private_module_access_map(private_module_ids)

            secured = []
            for challenge in data:
                challenge_id = _challenge_id(challenge)
                if challenge_id is None:
                    continue

                if challenge_id not in challenge_to_modules:
                    secured.append(challenge)
                    continue

                challenge_modules = challenge_to_modules[challenge_id]
                if not _challenge_accessible_via_modules(challenge_modules, allowed_private_module_ids):
                    continue
                secured.append(challenge)

            data_container[data_key] = secured
        except Exception:
            return response

        if (request.args.get("ctfd_modules") or "").strip() == "1":
            try:
                module_id = None
                raw_module_id = (request.args.get("module_id") or "").strip()
                if raw_module_id:
                    try:
                        module_id = int(raw_module_id)
                    except Exception:
                        module_id = None

                if module_id:
                    allowed_ids = _module_challenge_ids(module_id)
                    data_container[data_key] = [
                        challenge
                        for challenge in (data_container.get(data_key) or [])
                        if _challenge_id(challenge) in allowed_ids
                    ]

                    meta = payload.get("meta")
                    if isinstance(meta, dict):
                        pagination = meta.get("pagination")
                        if isinstance(pagination, dict):
                            pagination["total"] = len(data_container.get(data_key, []) or [])

                return _set_json_response_data(response, payload)
            except Exception:
                return response

        try:
            settings = get_settings(create=True)
            mode = (getattr(settings, "challenges_board_mode", "all") or "all").strip().lower()
            if mode in ("", "all", "none"):
                return _set_json_response_data(response, payload)

            assigned_ids = _assigned_challenge_ids()
            data_list = data_container.get(data_key) or []
            if mode == "only_modules":
                filtered = [challenge for challenge in data_list if _challenge_id(challenge) in assigned_ids]
            elif mode == "only_unassigned":
                filtered = [challenge for challenge in data_list if _challenge_id(challenge) not in assigned_ids]
            else:
                filtered = data_list

            data_container[data_key] = filtered
            return _set_json_response_data(response, payload)
        except Exception:
            return response
