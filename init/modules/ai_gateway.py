# coding: utf8

import json
import logging

try:
    from urllib2 import Request, urlopen, HTTPError, URLError
except ImportError:  # pragma: no cover - python3 compatibility for local tooling
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

try:
    string_types = (basestring,)
except NameError:  # pragma: no cover - python3 compatibility for local tooling
    string_types = (str,)


LOG = logging.getLogger("web2py.app.init.ai_gateway")


def _as_bool(value):
    if isinstance(value, string_types):
        return value.lower() in ("1", "yes", "true", "on")
    return bool(value)


def _json_request(url, payload, headers, timeout):
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, body, headers)
    response = urlopen(request, timeout=timeout)
    return json.loads(response.read())


def ai_gateway_login_onaccept(form, request, session, config_get):
    """Create a short-lived gateway session after a successful Collector login."""
    if not _as_bool(config_get("ai_gateway_enabled", False)):
        return

    gateway_url = config_get("ai_gateway_url", None)
    internal_token = config_get("ai_gateway_internal_token", None)
    endpoint = config_get("ai_gateway_sessions_endpoint", "/internal/v1/sessions")
    timeout = config_get("ai_gateway_request_timeout", 5)
    login_required = _as_bool(config_get("ai_gateway_login_required", False))
    ttl_seconds = config_get("ai_gateway_session_ttl", None)
    if ttl_seconds is None:
        ttl_seconds = config_get("session_expire", 604800)

    username = request.post_vars.get("email") or request.post_vars.get("username")
    password = request.post_vars.get("password")

    if not gateway_url or not internal_token:
        message = "AI gateway is enabled but ai_gateway_url or ai_gateway_internal_token is missing"
        return _handle_error(message, login_required)

    if not username or password is None:
        message = "AI gateway session skipped: login credentials not found in post vars"
        return _handle_error(message, login_required)

    url = gateway_url.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-OpenSVC-Gateway-Token": internal_token,
    }
    payload = {
        "username": username,
        "password": password,
        "ttl_seconds": int(ttl_seconds),
    }

    try:
        data = _json_request(url, payload, headers, timeout)
    except HTTPError as exc:
        message = "AI gateway session creation failed with HTTP %s" % exc.code
        return _handle_error(message, login_required)
    except URLError as exc:
        message = "AI gateway session creation failed: %s" % exc
        return _handle_error(message, login_required)
    except Exception as exc:
        message = "AI gateway session creation failed: %s" % exc
        return _handle_error(message, login_required)

    session_id = data.get("session_id")
    if not session_id:
        message = "AI gateway session creation failed: missing session_id in response"
        return _handle_error(message, login_required)

    session.ai_gateway_session_id = session_id
    session.ai_gateway_session_expires_at = data.get("expires_at")
    session.ai_gateway_username = data.get("username") or username


def _handle_error(message, login_required):
    LOG.warning(message)
    if login_required:
        raise RuntimeError(message)
