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


class _MethodRequest(Request):
    def __init__(self, url, data=None, headers=None, method=None):
        Request.__init__(self, url, data, headers or {})
        self._method = method

    def get_method(self):
        if self._method:
            return self._method
        return Request.get_method(self)


def _json_request(url, payload, headers, timeout, method=None):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = _MethodRequest(url, body, headers, method=method)
    response = urlopen(request, timeout=timeout)
    return json.loads(response.read())


def ai_gateway_chat(session, config_get, payload):
    """Forward a Collector user prompt to the AI gateway chat endpoint."""
    if not _as_bool(config_get("ai_gateway_enabled", False)):
        raise AiGatewayError(503, "AI gateway is disabled")

    gateway_url = config_get("ai_gateway_url", None)
    endpoint = config_get("ai_gateway_chat_endpoint", "/api/v1/ai/chat")
    timeout = config_get("ai_gateway_chat_timeout", 120)
    session_id = getattr(session, "ai_gateway_session_id", None)

    if not gateway_url:
        raise AiGatewayError(503, "AI gateway url is not configured")
    if not session_id:
        raise AiGatewayError(401, "Missing AI gateway session")

    url = gateway_url.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-OpenSVC-AI-Session": session_id,
    }

    try:
        return _json_request(url, payload, headers, timeout)
    except HTTPError as exc:
        raise AiGatewayError(exc.code, _read_error_body(exc))
    except URLError as exc:
        raise AiGatewayError(502, "AI gateway request failed: %s" % exc)
    except Exception as exc:
        raise AiGatewayError(502, "AI gateway request failed: %s" % exc)


def ai_gateway_login_onaccept(form, request, session, config_get):
    """Create a short-lived gateway session after a successful Collector login."""
    if not _as_bool(config_get("ai_gateway_enabled", False)):
        return

    ai_gateway_delete_session(session, config_get)

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


def ai_gateway_logout_onlogout(user, session, config_get):
    """Delete the gateway session when the Collector user explicitly logs out."""
    ai_gateway_delete_session(session, config_get)


def ai_gateway_delete_session(session, config_get):
    """Best-effort deletion of the current gateway session."""
    if not _as_bool(config_get("ai_gateway_enabled", False)):
        return False

    session_id = getattr(session, "ai_gateway_session_id", None)
    if not session_id:
        return False

    gateway_url = config_get("ai_gateway_url", None)
    internal_token = config_get("ai_gateway_internal_token", None)
    endpoint = config_get("ai_gateway_sessions_endpoint", "/internal/v1/sessions")
    timeout = config_get("ai_gateway_request_timeout", 5)

    try:
        del session.ai_gateway_session_id
    except Exception:
        session.ai_gateway_session_id = None
    try:
        del session.ai_gateway_session_expires_at
    except Exception:
        session.ai_gateway_session_expires_at = None
    try:
        del session.ai_gateway_username
    except Exception:
        session.ai_gateway_username = None

    if not gateway_url or not internal_token:
        LOG.warning(
            "AI gateway session deletion skipped: ai_gateway_url or "
            "ai_gateway_internal_token is missing"
        )
        return False

    url = gateway_url.rstrip("/") + "/" + endpoint.strip("/") + "/" + session_id
    headers = {
        "Accept": "application/json",
        "X-OpenSVC-Gateway-Token": internal_token,
    }

    try:
        _json_request(url, None, headers, timeout, method="DELETE")
        return True
    except HTTPError as exc:
        LOG.warning("AI gateway session deletion failed with HTTP %s", exc.code)
    except URLError as exc:
        LOG.warning("AI gateway session deletion failed: %s", exc)
    except Exception as exc:
        LOG.warning("AI gateway session deletion failed: %s", exc)
    return False


def _handle_error(message, login_required):
    LOG.warning(message)
    if login_required:
        raise RuntimeError(message)


class AiGatewayError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, detail)


def _read_error_body(exc):
    try:
        body = exc.read()
    except Exception:
        return "AI gateway request failed with HTTP %s" % exc.code
    if not body:
        return "AI gateway request failed with HTTP %s" % exc.code
    try:
        return json.loads(body)
    except Exception:
        if isinstance(body, bytes):
            return body.decode("utf-8", "replace")
        return body
