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
from .settings import get_progress_mode


def _coerce_points(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _apply_user_solve_scope(query, user):
    try:
        if is_teams_mode and is_teams_mode() and get_current_team:
            team = get_current_team()
            if team:
                return query.filter(Solves.team_id == team.id)
            return query.filter(Solves.user_id == user.id)
        return query.filter(Solves.user_id == user.id)
    except Exception:
        return query.filter(Solves.user_id == user.id)


def _progress_payload(
    solved: int,
    total: int,
    points_solved: int,
    points_total: int,
) -> dict:
    challenge_percent = int((solved / total) * 100) if total else 0
    points_percent = int((points_solved / points_total) * 100) if points_total else challenge_percent
    mode = get_progress_mode()

    if mode == "points":
        display_current = points_solved
        display_total = points_total
        percent = points_percent
        display_suffix = "pts"
    else:
        display_current = solved
        display_total = total
        percent = challenge_percent
        display_suffix = ""

    if percent > 100:
        percent = 100

    return {
        "solved": solved,
        "total": total,
        "challenge_percent": challenge_percent,
        "points_solved": points_solved,
        "points_total": points_total,
        "points_percent": points_percent,
        "mode": mode,
        "display_current": display_current,
        "display_total": display_total,
        "display_suffix": display_suffix,
        "percent": percent,
    }


def module_progress(user, module: Module, challenge_ids: list[int] | set[int] | tuple[int, ...] | None = None) -> dict:
    """Return progress for the current user with both challenge and points aggregates."""
    challenge_rows_q = (
        db.session.query(Challenges.id, Challenges.value)
        .join(ModuleChallenge, ModuleChallenge.challenge_id == Challenges.id)
        .filter(ModuleChallenge.module_id == module.id)
    )

    normalized_ids = None
    if challenge_ids is not None:
        normalized_ids = []
        for challenge_id in challenge_ids:
            try:
                normalized_value = int(challenge_id)
            except Exception:
                continue
            if normalized_value > 0:
                normalized_ids.append(normalized_value)
        normalized_ids = list(dict.fromkeys(normalized_ids))
        if not normalized_ids:
            return _progress_payload(solved=0, total=0, points_solved=0, points_total=0)
        challenge_rows_q = challenge_rows_q.filter(Challenges.id.in_(normalized_ids))

    challenge_rows = challenge_rows_q.all()
    total = len(challenge_rows)
    points_total = sum(_coerce_points(value) for _, value in challenge_rows)

    if not user or total == 0:
        return _progress_payload(solved=0, total=total, points_solved=0, points_total=points_total)

    challenge_ids_in_scope = [challenge_id for challenge_id, _ in challenge_rows]

    solves_q = (
        db.session.query(Solves.challenge_id)
        .filter(Solves.challenge_id.in_(challenge_ids_in_scope))
        .distinct()
    )
    solves_q = _apply_user_solve_scope(solves_q, user)

    solved_ids = {challenge_id for (challenge_id,) in solves_q.all()}
    solved = len(solved_ids)
    values_by_id = {challenge_id: _coerce_points(value) for challenge_id, value in challenge_rows}
    points_solved = sum(values_by_id.get(challenge_id, 0) for challenge_id in solved_ids)

    return _progress_payload(
        solved=solved,
        total=total,
        points_solved=points_solved,
        points_total=points_total,
    )


def module_challenges_query(module: Module, include_hidden: bool) -> list[Challenges]:
    q = (
        Challenges.query.join(ModuleChallenge, ModuleChallenge.challenge_id == Challenges.id)
        .filter(ModuleChallenge.module_id == module.id)
    )
    if not include_hidden:
        q = q.filter(Challenges.state == "visible")
    return q.order_by(Challenges.category.asc(), Challenges.value.asc(), Challenges.name.asc()).all()
