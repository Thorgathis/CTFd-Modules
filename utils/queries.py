from __future__ import annotations

from CTFd.models import db

from ..models import Module, ModuleCategory


def module_ordering():
    return (
        db.case([(Module.category.is_(None), 1)], else_=0),
        Module.category.asc(),
        Module.order.asc(),
        Module.name.asc(),
    )


def ordered_modules_query():
    return Module.query.order_by(*module_ordering())


def ordered_categories_query():
    return ModuleCategory.query.order_by(ModuleCategory.order.asc(), ModuleCategory.name.asc())


def ordered_category_names():
    return [category.name for category in ordered_categories_query().all()]
