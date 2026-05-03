"""Bearer-token gate for the admin HTTP surface.

Capability: `web-admin-bearer-auth` (see
``openspec/changes/web-admin-bearer-auth-v0/specs/web-admin-bearer-auth/spec.md``).

* :class:`AuthError` — raised by :func:`require_admin` on missing /
  malformed / wrong-token requests. Mapped by
  ``ohmystock.api.routes._envelope``'s exception handler to HTTP 401 +
  the unified ``{"ok": false, "error": {...}}`` envelope.
* :func:`require_admin` — FastAPI dependency. Attached to every
  ``/api/admin/*`` router (REST + SSE). Compares the supplied token
  against ``Settings.ohmystock_admin_token`` with
  :func:`secrets.compare_digest` (constant-time).
* :func:`_validate_admin_token` — startup validator. Called from
  :func:`ohmystock.api.app.create_app` *before* admin routes are
  registered, so a misconfigured deploy fails fast at boot.

Design rationale: see ``openspec/changes/web-admin-bearer-auth-v0/design.md``
decisions D1 (per-route Depends), D2 (custom AuthError, not HTTPException),
D3 (two distinct codes), D4 (constant-time compare), D5 (fail-fast in
``create_app``), D6 (32-character minimum).
"""

from __future__ import annotations

import secrets

from fastapi import Header

from ohmystock.config import Settings


_BEARER_PREFIX = "Bearer "  # case-sensitive per design D3 / spec scenario
_MIN_TOKEN_LENGTH = 32


class AuthError(Exception):
    """Raised when the Authorization header is missing, malformed, or wrong.

    ``code`` is one of ``"auth_missing"`` or ``"auth_invalid"`` (spec
    "Two distinct error codes"). ``message`` is a short human-readable
    string suitable for the envelope; it MUST NOT contain the token,
    stack frames, or filesystem paths.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_admin_token(settings: Settings) -> None:
    """Enforce the presence + length invariant on ``ohmystock_admin_token``.

    Called from ``create_app()`` before admin routes are registered.
    Raises :class:`RuntimeError` with a message that includes both the
    string ``"OHMYSTOCK_ADMIN_TOKEN must be set"`` and ``"32"`` so spec
    scenarios can pattern-match. The message also embeds the documented
    generator command.
    """

    token = settings.ohmystock_admin_token
    if token is None or token == "" or len(token) < _MIN_TOKEN_LENGTH:
        raise RuntimeError(
            "OHMYSTOCK_ADMIN_TOKEN must be set and at least 32 characters; "
            "generate with: python -c \"import secrets; "
            "print(secrets.token_urlsafe(32))\""
        )


def require_admin(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency that gates every ``/api/admin/*`` route.

    Behavior:

    * Missing header, empty header, or header that does not start with
      ``"Bearer "`` (case-sensitive) → ``AuthError("auth_missing", ...)``.
    * Header is ``"Bearer <token>"`` but ``<token>`` does not match
      ``Settings.ohmystock_admin_token`` (compared with
      :func:`secrets.compare_digest`) → ``AuthError("auth_invalid", ...)``.
    * Token matches → return ``None`` (handler proceeds).

    Settings are re-instantiated per call to honor the per-call freshness
    contract documented in ``_deps.py``'s ``get_settings_dep``.
    """

    if authorization is None or not authorization.startswith(_BEARER_PREFIX):
        raise AuthError(
            "auth_missing", "Missing or malformed Authorization header"
        )

    supplied = authorization[len(_BEARER_PREFIX):]
    expected = Settings().ohmystock_admin_token or ""
    if not secrets.compare_digest(supplied, expected):
        raise AuthError("auth_invalid", "Invalid admin token")
