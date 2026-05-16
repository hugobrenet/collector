import gluon.contrib.simplejson as json

from applications.init.modules.ai_gateway import AiGatewayError, ai_gateway_chat

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


@auth.requires_login()
def chat():
    response.headers["Content-Type"] = "application/json"

    try:
        payload = json.loads(request.body.read())
    except Exception:
        raise HTTP(400, json.dumps({"error": "Invalid JSON payload"}))

    if not isinstance(payload, dict):
        raise HTTP(400, json.dumps({"error": "JSON payload must be an object"}))

    message = payload.get("message")
    if not isinstance(message, string_types) or not message.strip():
        raise HTTP(400, json.dumps({"error": "Missing or empty message"}))

    try:
        return json.dumps(ai_gateway_chat(session, config_get, payload))
    except AiGatewayError as exc:
        raise HTTP(exc.status_code, json.dumps({"error": exc.detail}))
