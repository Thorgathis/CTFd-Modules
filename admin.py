from __future__ import annotations

import csv
import io

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, jsonify

from CTFd.models import Challenges, Users, db
from CTFd.utils.decorators import admins_only, ratelimit
from CTFd.utils.user import get_current_user

from .models import Module, ModuleAccess, ModuleCategory, ModuleChallenge, ModuleStatus
from .compat import csrf_protect
from .utils import (
    ensure_private_invite_code,
    generate_invite_code,
    grant_access,
    revoke_access,
    ordered_modules_query,
    ordered_categories_query,
)


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


modules_admin_bp = Blueprint(
    "ctfd_modules_admin",
    __name__,
    url_prefix="/plugins/ctfd_modules/admin",
    template_folder="templates",
    static_folder="static",
)


def _ensure_module_category(name: str) -> ModuleCategory:
    name = (name or "").strip()
    if not name:
        raise ValueError("empty category")

    existing = ModuleCategory.query.filter(ModuleCategory.name == name).first()
    if existing:
        return existing

    max_order = db.session.query(db.func.max(ModuleCategory.order)).scalar() or 0
    cat = ModuleCategory(name=name, order=int(max_order) + 1)
    db.session.add(cat)
    return cat


def register_admin_menu(app):
    # In CTFd 3.x the admin menu is rendered via templates.
    # We inject helpers via a context_processor (minimally invasive).
    @app.context_processor
    def inject_admin_modules_menu():
        def ctfd_modules_all_modules():
            try:
                return Module.query.order_by(Module.name.asc()).all()
            except Exception:
                return []

        def ctfd_modules_challenge_module_id(challenge_id):
            try:
                row = ModuleChallenge.query.filter_by(challenge_id=challenge_id).first()
                return row.module_id if row else None
            except Exception:
                return None

        def ctfd_modules_challenge_module_name(challenge_id):
            try:
                row = ModuleChallenge.query.filter_by(challenge_id=challenge_id).first()
                if not row:
                    return ""
                m = Module.query.get(row.module_id)
                return m.name if m else ""
            except Exception:
                return ""

        return {
            "ctfd_modules_all_modules": ctfd_modules_all_modules,
            "ctfd_modules_challenge_module_id": ctfd_modules_challenge_module_id,
            "ctfd_modules_challenge_module_name": ctfd_modules_challenge_module_name,
        }


@modules_admin_bp.route("/modules", methods=["GET"])
@admins_only
def admin_modules_list():
    status = request.args.get("status")
    category = request.args.get("category")

    q = ordered_modules_query()
    if status:
        q = q.filter(Module.status == status)
    if category:
        q = q.filter(Module.category == category)

    modules = q.all()
    categories = [category_row.name for category_row in ordered_categories_query().all()]
    return render_template("admin/modules/list.html", modules=modules, categories=categories)


@modules_admin_bp.route("/modules/new", methods=["GET", "POST"])
@admins_only
def admin_modules_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name is required", "danger")
            categories = ordered_categories_query().all()
            return render_template("admin/modules/edit.html", module=None, categories=categories)

        category_name = (request.form.get("category") or "").strip() or None
        if category_name and not ModuleCategory.query.filter_by(name=category_name).first():
            flash("Please select a category from the list", "danger")
            categories = ordered_categories_query().all()
            return render_template("admin/modules/edit.html", module=None, categories=categories)

        m = Module(
            name=name,
            category=category_name,
            banner_url=(request.form.get("banner_url") or "").strip() or None,
            order=_to_int(request.form.get("order"), 0),
            status=(request.form.get("status") or "public").strip(),
        )
        ensure_private_invite_code(m)
        db.session.add(m)
        db.session.commit()

        flash("Module created", "success")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=m.id))

    categories = ordered_categories_query().all()
    return render_template("admin/modules/edit.html", module=None, categories=categories)


@modules_admin_bp.route("/modules/<int:module_id>/edit", methods=["GET", "POST"])
@admins_only
def admin_modules_edit(module_id: int):
    module = Module.query.get_or_404(module_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name is required", "danger")
            return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

        category_name = (request.form.get("category") or "").strip() or None
        if category_name and not ModuleCategory.query.filter_by(name=category_name).first():
            flash("Please select a category from the list", "danger")
            return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

        module.name = name
        module.category = category_name
        module.banner_url = (request.form.get("banner_url") or "").strip() or None
        module.order = _to_int(request.form.get("order"), 0)
        module.status = (request.form.get("status") or "public").strip()

        ensure_private_invite_code(module)
        db.session.commit()

        flash("Module updated", "success")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    categories = ordered_categories_query().all()

    access_q = (request.args.get("access_q") or "").strip()
    access_results = []
    access_users = []
    access_user_ids = set()
    try:
        access_users = (
            db.session.query(Users)
            .join(ModuleAccess, ModuleAccess.user_id == Users.id)
            .filter(ModuleAccess.module_id == module.id)
            .order_by(Users.name.asc())
            .all()
        )
        access_user_ids = {u.id for u in access_users}
    except Exception:
        access_users = []
        access_user_ids = set()

    if access_q:
        try:
            filters = []
            if hasattr(Users, "name"):
                filters.append(Users.name.ilike(f"%{access_q}%"))
            if hasattr(Users, "email"):
                filters.append(Users.email.ilike(f"%{access_q}%"))
            if hasattr(Users, "username"):
                filters.append(Users.username.ilike(f"%{access_q}%"))

            q = Users.query
            if filters:
                cond = filters[0]
                for f in filters[1:]:
                    cond = cond | f
                q = q.filter(cond)

            order_col = Users.name if hasattr(Users, "name") else Users.id
            access_results = q.order_by(order_col.asc()).limit(25).all()
        except Exception:
            access_results = []

    return render_template(
        "admin/modules/edit.html",
        module=module,
        categories=categories,
        access_q=access_q,
        access_results=access_results,
        access_users=access_users,
        access_user_ids=access_user_ids,
    )


@modules_admin_bp.route("/settings", methods=["GET", "POST"])
@admins_only
def admin_modules_settings():
    if request.method == "POST":
        from .utils import update_settings_from_form

        update_settings_from_form(request.form)

        flash("Settings updated", "success")
        return redirect(url_for("ctfd_modules_admin.admin_modules_settings"))

    from .utils import get_settings, get_ui_theme

    s = get_settings(create=True)
    current_mode = (getattr(s, "challenges_board_mode", "all") or "all").strip().lower()
    hide_challenges_page = bool(getattr(s, "hide_challenges_page", False))
    modules_enabled = bool(getattr(s, "modules_enabled", True))
    invite_code_length = int(getattr(s, "invite_code_length", 8) or 8)
    lock_message = str(getattr(s, "lock_message", "") or "")
    ui_theme = get_ui_theme()

    return render_template(
        "admin/modules/settings.html",
        challenges_board_mode=current_mode,
        hide_challenges_page=hide_challenges_page,
        modules_enabled=modules_enabled,
        invite_code_length=invite_code_length,
        lock_message=lock_message,
        ui_theme=ui_theme,
    )


@modules_admin_bp.route("/categories", methods=["GET"])
@admins_only
def admin_module_categories_list():
    categories = ordered_categories_query().all()
    return render_template("admin/modules/categories/list.html", categories=categories)


@modules_admin_bp.route("/categories/new", methods=["GET", "POST"])
@admins_only
def admin_module_categories_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name is required", "danger")
            return render_template("admin/modules/categories/edit.html", category=None)

        order = _to_int(request.form.get("order"), 0)
        if ModuleCategory.query.filter_by(name=name).first():
            flash("A category with this name already exists", "warning")
            return render_template("admin/modules/categories/edit.html", category=None)

        cat = ModuleCategory(name=name, order=order)
        db.session.add(cat)
        db.session.commit()
        flash("Category created", "success")
        return redirect(url_for("ctfd_modules_admin.admin_module_categories_list"))

    return render_template("admin/modules/categories/edit.html", category=None)


@modules_admin_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admins_only
def admin_module_categories_edit(category_id: int):
    category = ModuleCategory.query.get_or_404(category_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name is required", "danger")
            return redirect(url_for("ctfd_modules_admin.admin_module_categories_edit", category_id=category.id))

        # Rename: keep modules.category in sync
        old_name = category.name
        category.name = name
        category.order = _to_int(request.form.get("order"), 0)

        if old_name != name:
            Module.query.filter(Module.category == old_name).update({"category": name})

        db.session.commit()
        flash("Category updated", "success")
        return redirect(url_for("ctfd_modules_admin.admin_module_categories_list"))

    return render_template("admin/modules/categories/edit.html", category=category)


@modules_admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admins_only
def admin_module_categories_delete(category_id: int):
    category = ModuleCategory.query.get_or_404(category_id)

    # Detach modules from this category
    Module.query.filter(Module.category == category.name).update({"category": None})
    db.session.delete(category)
    db.session.commit()
    flash("Category deleted", "success")
    return redirect(url_for("ctfd_modules_admin.admin_module_categories_list"))


@modules_admin_bp.route("/modules/<int:module_id>/challenges", methods=["GET"])
@admins_only
def admin_modules_manage_challenges(module_id: int):
    module = Module.query.get_or_404(module_id)
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()

    assigned = (
        db.session.query(Challenges)
        .join(ModuleChallenge, ModuleChallenge.challenge_id == Challenges.id)
        .filter(ModuleChallenge.module_id == module.id)
        .order_by(Challenges.category.asc(), Challenges.value.asc(), Challenges.name.asc())
        .all()
    )

    limit = 100
    unassigned_q = (
        db.session.query(Challenges)
        .outerjoin(ModuleChallenge, ModuleChallenge.challenge_id == Challenges.id)
        .filter(ModuleChallenge.challenge_id.is_(None))
    )
    if q:
        unassigned_q = unassigned_q.filter(Challenges.name.ilike(f"%{q}%"))
    if category:
        unassigned_q = unassigned_q.filter(Challenges.category == category)

    unassigned = (
        unassigned_q.order_by(Challenges.category.asc(), Challenges.value.asc(), Challenges.name.asc())
        .limit(limit)
        .all()
    )

    return render_template(
        "admin/modules/challenges.html",
        module=module,
        assigned=assigned,
        unassigned=unassigned,
        q=q,
        category=category,
        limit=limit,
    )


@modules_admin_bp.route("/modules/<int:module_id>/delete", methods=["POST"])
@admins_only
def admin_modules_delete(module_id: int):
    module = Module.query.get_or_404(module_id)
    ModuleAccess.query.filter_by(module_id=module.id).delete()
    ModuleChallenge.query.filter_by(module_id=module.id).delete()
    db.session.delete(module)
    db.session.commit()
    flash("Module deleted", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_list"))


@modules_admin_bp.route("/modules/reorder", methods=["POST"])
@admins_only
def admin_modules_reorder():
    body = request.get_json(silent=True) or {}
    ordered_ids = body.get("ordered_ids") or []
    if not isinstance(ordered_ids, list):
        return jsonify({"success": False, "error": "INVALID_PAYLOAD"}), 400

    for idx, mid in enumerate(ordered_ids):
        Module.query.filter_by(id=mid).update({"order": idx})

    db.session.commit()
    return jsonify({"success": True})


@modules_admin_bp.route("/modules/<int:module_id>/regen", methods=["POST"])
@admins_only
def admin_modules_regen_invite(module_id: int):
    module = Module.query.get_or_404(module_id)
    if module.status != ModuleStatus.private:
        flash("Invite codes are only available for private modules", "warning")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    for _ in range(20):
        code = generate_invite_code()
        if not Module.query.filter(Module.invite_code == code).first():
            module.invite_code = code
            db.session.commit()
            flash("Invite code updated", "success")
            return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    flash("Failed to generate a new code", "danger")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/modules/<int:module_id>/access/add", methods=["POST"])
@admins_only
@ratelimit(method="POST", limit=60, interval=60)
def admin_modules_access_add(module_id: int):
    module = Module.query.get_or_404(module_id)
    user_id = request.form.get("user_id")
    try:
        user_id_int = int(user_id)
    except Exception:
        flash("Invalid user_id", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    user = Users.query.get(user_id_int)
    if not user:
        flash("User not found", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    grant_access(module, user, granted_by_user=get_current_user())
    db.session.commit()
    flash("Access granted", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/modules/<int:module_id>/access/revoke", methods=["POST"])
@admins_only
def admin_modules_access_revoke(module_id: int):
    module = Module.query.get_or_404(module_id)
    user_id = request.form.get("user_id")
    try:
        user_id_int = int(user_id)
    except Exception:
        flash("Invalid user_id", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    revoke_access(module, user_id_int)
    db.session.commit()
    flash("Access revoked", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/users/search", methods=["GET"])
@admins_only
def admin_users_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": True, "data": []})

    try:
        filters = []
        if hasattr(Users, "name"):
            filters.append(Users.name.ilike(f"%{q}%"))
        if hasattr(Users, "email"):
            filters.append(Users.email.ilike(f"%{q}%"))
        if hasattr(Users, "username"):
            filters.append(Users.username.ilike(f"%{q}%"))

        query = Users.query
        if filters:
            cond = filters[0]
            for f in filters[1:]:
                cond = cond | f
            query = query.filter(cond)

        order_col = Users.name if hasattr(Users, "name") else Users.id
        users = query.order_by(order_col.asc()).limit(20).all()
    except Exception:
        users = []

    data = []
    for u in users:
        data.append(
            {
                "id": getattr(u, "id", None),
                "name": getattr(u, "name", None) or getattr(u, "username", None) or "",
                "email": getattr(u, "email", None) or "",
            }
        )

    return jsonify({"success": True, "data": data})


@modules_admin_bp.route("/modules/<int:module_id>/challenges/assign", methods=["POST"])
@admins_only
def admin_modules_challenges_assign(module_id: int):
    module = Module.query.get_or_404(module_id)
    challenge_id = request.form.get("challenge_id")
    try:
        cid = int(challenge_id)
    except Exception:
        flash("Invalid challenge_id", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    if not Challenges.query.get(cid):
        flash("Challenge not found", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    # One-to-many: remove any previous module mapping for this challenge
    ModuleChallenge.query.filter_by(challenge_id=cid).delete()
    db.session.add(ModuleChallenge(challenge_id=cid, module_id=module.id))
    db.session.commit()

    flash("Challenge assigned", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/modules/<int:module_id>/challenges/unassign", methods=["POST"])
@admins_only
def admin_modules_challenges_unassign(module_id: int):
    module = Module.query.get_or_404(module_id)
    challenge_id = request.form.get("challenge_id")
    try:
        cid = int(challenge_id)
    except Exception:
        flash("Invalid challenge_id", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    ModuleChallenge.query.filter_by(challenge_id=cid, module_id=module.id).delete()
    db.session.commit()

    flash("Challenge unassigned", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/modules/<int:module_id>/bulk/by-category", methods=["POST"])
@admins_only
def admin_modules_bulk_by_category(module_id: int):
    module = Module.query.get_or_404(module_id)
    category = (request.form.get("category") or "").strip()
    if not category:
        flash("Please provide a category", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    challenges = Challenges.query.filter_by(category=category).all()
    for c in challenges:
        ModuleChallenge.query.filter_by(challenge_id=c.id).delete()
        db.session.add(ModuleChallenge(challenge_id=c.id, module_id=module.id))

    db.session.commit()
    flash(f"Challenges assigned: {len(challenges)}", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))


@modules_admin_bp.route("/modules/<int:module_id>/bulk/csv", methods=["POST"])
@admins_only
def admin_modules_bulk_csv(module_id: int):
    module = Module.query.get_or_404(module_id)

    f = request.files.get("csv")
    if not f:
        flash("Please upload a CSV file", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    try:
        raw = f.read().decode("utf-8")
    except Exception:
        flash("Unable to read CSV", "danger")
        return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))

    reader = csv.DictReader(io.StringIO(raw))
    updated = 0
    for row in reader:
        try:
            cid = int(row.get("challenge_id"))
            mid = int(row.get("module_id"))
        except Exception:
            continue

        if not Challenges.query.get(cid) or not Module.query.get(mid):
            continue

        ModuleChallenge.query.filter_by(challenge_id=cid).delete()
        db.session.add(ModuleChallenge(challenge_id=cid, module_id=mid))
        updated += 1

    db.session.commit()
    flash(f"Updated mappings: {updated}", "success")
    return redirect(url_for("ctfd_modules_admin.admin_modules_edit", module_id=module.id))
