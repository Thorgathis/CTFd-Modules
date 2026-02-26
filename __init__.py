from __future__ import annotations

import os

from flask import send_from_directory

from .admin import modules_admin_bp, register_admin_menu
from .api import modules_api_bp
from .hooks import register_plugin_runtime_hooks
from .models import db_init
from .views import modules_bp


def _register_static_route(app):
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    try:
        has_static_rule = any(
            rule.rule == "/plugins/ctfd_modules/static/<path:filename>"
            for rule in app.url_map.iter_rules()
        )
    except Exception:
        has_static_rule = False

    if has_static_rule:
        return

    @app.route("/plugins/ctfd_modules/static/<path:filename>")
    def ctfd_modules_static(filename: str):
        return send_from_directory(static_dir, filename)


def _register_blueprints(app):
    try:
        from CTFd.plugins import register_plugin_blueprint  # type: ignore

        register_plugin_blueprint(app, modules_bp)
        register_plugin_blueprint(app, modules_api_bp)
        register_plugin_blueprint(app, modules_admin_bp)
        return
    except Exception:
        pass

    app.register_blueprint(modules_bp)
    app.register_blueprint(modules_api_bp)
    app.register_blueprint(modules_admin_bp)


def _register_user_menu():
    try:
        from CTFd.plugins import register_user_page_menu_bar

        register_user_page_menu_bar(title="Modules", route="/modules")
    except Exception:
        pass


def _apply_patches(app):
    try:
        from .patches import apply_patches

        apply_patches(app)
    except Exception:
        pass


def load(app):
    """CTFd plugin entrypoint."""

    _register_static_route(app)
    _register_blueprints(app)

    db_init(app)
    register_admin_menu(app)
    register_plugin_runtime_hooks(app)

    _register_user_menu()
    _apply_patches(app)
