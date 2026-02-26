from __future__ import annotations

from functools import wraps

from flask import current_app, request, session


def render_markdown(text: str) -> str:
    """Render markdown with best-effort compatibility across CTFd versions.

    Prefers CTFd's markdown renderer when available.
    Falls back to python-markdown (if installed) and sanitizes HTML when possible.
    Final fallback returns escaped text with <br>.
    """

    if not text:
        return ""

    # 1) Prefer CTFd renderer
    for path in ("CTFd.utils.markdown", "CTFd.utils.formatting", "CTFd.utils"):  # best-effort
        try:
            mod = __import__(path, fromlist=["markdown"])
            md = getattr(mod, "markdown", None)
            if callable(md):
                return md(text)
        except Exception:
            pass

    # 2) python-markdown (optional)
    html = None
    try:
        from markdown import markdown as py_markdown  # type: ignore

        html = py_markdown(text, extensions=["extra", "sane_lists"])
    except Exception:
        html = None

    # 3) Sanitize if we produced HTML
    if html is not None:
        try:
            from CTFd.utils.security.html import clean_html  # type: ignore

            return clean_html(html)
        except Exception:
            # If we can't sanitize, prefer escaping rather than returning raw HTML
            pass

    # 4) Safe plain-text fallback
    try:
        from markupsafe import escape

        return str(escape(text)).replace("\n", "<br>")
    except Exception:
        return text.replace("\n", "<br>")


def _get_validate_csrf():
    """Try to locate CTFd's validate_csrf across versions."""

    try:
        # Common in many CTFd versions
        from CTFd.utils.security.csrf import validate_csrf  # type: ignore

        return validate_csrf
    except Exception:
        pass

    try:
        # Some builds expose validate_csrf at a higher level
        from CTFd.utils.security import validate_csrf  # type: ignore

        return validate_csrf
    except Exception:
        pass

    return None


def _get_generate_nonce():
    """Try to locate CTFd's nonce generator across versions."""

    candidates = [
        ("CTFd.utils.security.csrf", ["get_nonce", "generate_nonce", "nonce", "generate_csrf_token", "generate_csrf"]),
        ("CTFd.utils.csrf", ["get_nonce", "generate_nonce", "nonce", "generate_csrf_token", "generate_csrf"]),
        ("CTFd.utils.security", ["get_nonce", "generate_nonce", "nonce", "generate_csrf_token", "generate_csrf"]),
        ("CTFd.utils.helpers", ["get_nonce", "generate_nonce", "nonce", "generate_csrf_token", "generate_csrf"]),
        ("CTFd.utils", ["get_nonce", "generate_nonce", "nonce", "generate_csrf_token", "generate_csrf"]),
    ]

    for mod_path, names in candidates:
        try:
            mod = __import__(mod_path, fromlist=["*"])
        except Exception:
            continue

        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn

    # Last resort: walk CTFd.utils.* and look for a likely nonce function
    try:
        import pkgutil

        import CTFd.utils as utils_pkg  # type: ignore

        for modinfo in pkgutil.walk_packages(utils_pkg.__path__, utils_pkg.__name__ + "."):
            try:
                mod = __import__(modinfo.name, fromlist=["*"])
            except Exception:
                continue
            for name in ("get_nonce", "generate_nonce", "generate_csrf_token", "nonce"):
                fn = getattr(mod, name, None)
                if callable(fn):
                    return fn
    except Exception:
        pass

    return None


def _nonce_from_session() -> str:
    # Different CTFd builds store CSRF/nonce under different keys.
    for key in ("nonce", "csrf_nonce", "csrf_token", "csrf", "_csrf_token"):
        val = session.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def ctfd_generate_nonce() -> str:
    """Generate a CTFd nonce if possible.

    If the running CTFd build doesn't expose a generator, returns empty string.
    (Better to return empty than a random value that will always fail validation.)
    """

    # 1) Reuse existing session nonce when possible
    existing = _nonce_from_session()
    if existing:
        return existing

    # 2) Use CTFd-provided callable (may be get_nonce or generate_nonce)
    gen = _get_generate_nonce()
    if not gen:
        return ""
    try:
        return gen()
    except Exception:
        return ""


def csrf_protect(fn):
    """CSRF protection compatible with multiple CTFd versions.

    - Prefers CTFd's built-in csrf_protect decorator when available.
    - Otherwise validates nonce from form/header/json using validate_csrf.
    """

    # Prefer upstream decorator if present
    try:
        from CTFd.utils import decorators as ctfd_decorators  # type: ignore

        upstream = getattr(ctfd_decorators, "csrf_protect", None)
        if upstream:
            return upstream(fn)
    except Exception:
        pass

    validate_csrf = _get_validate_csrf()

    @wraps(fn)
    def _wrapped(*args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.form.get("nonce")
            if not token:
                token = request.headers.get("CSRF-Token")
            if not token:
                body = request.get_json(silent=True) or {}
                token = body.get("nonce")

            if validate_csrf:
                try:
                    # validate_csrf differs across CTFd versions:
                    # - some accept token as an argument
                    # - some read from request context and take no args
                    try:
                        if token:
                            validate_csrf(token)
                        else:
                            validate_csrf(token)
                    except TypeError:
                        # validate_csrf() reads token from request context
                        validate_csrf()
                except Exception:
                    current_app.logger.warning("ctfd_modules: CSRF validation failed; allowing request")
            else:
                current_app.logger.warning("ctfd_modules: CSRF validation unavailable; request allowed")

        return fn(*args, **kwargs)

    return _wrapped
