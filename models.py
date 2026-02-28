from __future__ import annotations

import enum
from datetime import datetime

from CTFd.models import db


class ModuleStatus(str, enum.Enum):
    public = "public"
    private = "private"
    locked = "locked"


class ModuleCategory(db.Model):
    __tablename__ = "module_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    order = db.Column(db.Integer, default=0, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    category = db.Column(db.String(80), nullable=True, index=True)
    banner_url = db.Column(db.String(255), nullable=True)
    order = db.Column(db.Integer, default=0, index=True)

    status = db.Column(db.Enum(ModuleStatus), default=ModuleStatus.public, nullable=False, index=True)
    invite_code = db.Column(db.String(32), unique=True, nullable=True, index=True)

    prerequisites = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ModuleAccess(db.Model):
    __tablename__ = "module_access"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True)

    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)


class ModuleChallenge(db.Model):
    """Link table: many-to-many module <-> challenge."""

    __tablename__ = "module_challenge_links"

    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True, index=True)


class ModuleSettings(db.Model):
    __tablename__ = "ctfd_modules_settings"

    id = db.Column(db.Integer, primary_key=True)

    modules_enabled = db.Column(db.Boolean, default=True, nullable=False)
    hide_challenges_page = db.Column(db.Boolean, default=False, nullable=False)
    challenges_board_mode = db.Column(db.String(32), default="all", nullable=False)

    invite_code_length = db.Column(db.Integer, default=8, nullable=False)
    lock_message = db.Column(
        db.Text,
        default="This module is under construction. Access will be available soon.",
        nullable=False,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def db_init(app):
    with app.app_context():
        db.create_all()
        _migrate_legacy_module_challenges()


def _migrate_legacy_module_challenges():
    """Copy data from legacy one-to-many table if it exists."""
    try:
        inspector = db.inspect(db.engine)
        tables = set(inspector.get_table_names())
        if "module_challenges" not in tables or "module_challenge_links" not in tables:
            return

        rows = db.session.execute(db.text("SELECT challenge_id, module_id FROM module_challenges")).fetchall()
        if not rows:
            return

        inserted = False
        for challenge_id, module_id in rows:
            try:
                cid = int(challenge_id)
                mid = int(module_id)
            except Exception:
                continue

            exists = ModuleChallenge.query.filter_by(challenge_id=cid, module_id=mid).first()
            if exists:
                continue

            db.session.add(ModuleChallenge(challenge_id=cid, module_id=mid))
            inserted = True

        if inserted:
            db.session.commit()
    except Exception:
        db.session.rollback()
