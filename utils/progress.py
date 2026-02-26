from __future__ import annotations

from CTFd.models import Challenges, Solves, db

try:
    from CTFd.utils.config import is_teams_mode
except Exception:
    is_teams_mode = None

try:
    from CTFd.utils.user import get_current_team
except Exception:
    get_current_team = None

from ..models import Module, ModuleChallenge


def module_progress(user, module: Module) -> dict:
    """Return {solved, total, percent} for the current user."""
    total = (
        db.session.query(ModuleChallenge.challenge_id)
        .filter(ModuleChallenge.module_id == module.id)
        .count()
    )
    if not user or total == 0:
        return {"solved": 0, "total": total, "percent": 0}

    solves_q = (
        db.session.query(Solves.id)
        .join(ModuleChallenge, ModuleChallenge.challenge_id == Solves.challenge_id)
        .filter(ModuleChallenge.module_id == module.id)
    )

    try:
        if is_teams_mode and is_teams_mode() and get_current_team:
            team = get_current_team()
            if team:
                solves_q = solves_q.filter(Solves.team_id == team.id)
            else:
                solves_q = solves_q.filter(Solves.user_id == user.id)
        else:
            solves_q = solves_q.filter(Solves.user_id == user.id)
    except Exception:
        solves_q = solves_q.filter(Solves.user_id == user.id)

    solved = solves_q.count()
    percent = int((solved / total) * 100) if total else 0
    if percent > 100:
        percent = 100
    return {"solved": solved, "total": total, "percent": percent}


def module_challenges_query(module: Module, include_hidden: bool) -> list[Challenges]:
    q = (
        Challenges.query.join(ModuleChallenge, ModuleChallenge.challenge_id == Challenges.id)
        .filter(ModuleChallenge.module_id == module.id)
    )
    if not include_hidden:
        q = q.filter(Challenges.state == "visible")
    return q.order_by(Challenges.category.asc(), Challenges.value.asc(), Challenges.name.asc()).all()
